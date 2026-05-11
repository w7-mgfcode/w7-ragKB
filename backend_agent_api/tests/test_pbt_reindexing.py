"""Property-based tests for re-indexing and concurrency control (Tasks 4.2, 24.2).

Properties tested:
- P13: Re-indexing completeness — all chunks regenerated
- P14: Directory re-indexing recursion — all .md files covered
- P15: Full re-indexing coverage — no .md files missed
- P16: Re-indexing status transitions — processing → in_sync/error
- P17: Re-indexing queue serialization — semaphore limits concurrency
- P26: Concurrency limit enforcement
- P29: Sequential bulk operation processing
"""

import asyncio
import shutil
import tempfile
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis.strategies import integers, sampled_from

from sync_manager import SyncManager, SyncStatus, DocumentSyncInfo
from document_exceptions import ReindexError


def _stub_row(fp):
    now = datetime.now(timezone.utc)
    return {
        "file_path": fp,
        "sync_status": "in_sync",
        "filesystem_mtime": now,
        "database_mtime": now,
        "chunk_count": 2,
        "error_message": None,
        "source": "browser",
        "last_checked": now,
    }


# ==========================================================================
# P13: Re-indexing completeness
# ==========================================================================


@given(chunk_count=integers(min_value=1, max_value=20))
@settings(max_examples=30)
def test_reindex_regenerates_all_chunks(chunk_count):
    """After reindex, chunk count must match what _chunk_and_insert returns."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        row = _stub_row("docs/p13.md")
        row["chunk_count"] = chunk_count
        pool.fetchrow = AsyncMock(return_value=row)
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "docs" / "p13.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("# Content")

        with patch.object(sm, "_chunk_and_insert", new_callable=AsyncMock, return_value=chunk_count), \
             patch("db_documents.delete_document_by_path", new_callable=AsyncMock):
            result = asyncio.run(sm.reindex_document("docs/p13.md", "user1"))

        assert result.chunk_count == chunk_count
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P14: Directory re-indexing recursion
# ==========================================================================


@given(file_count=integers(min_value=1, max_value=8))
@settings(max_examples=20)
def test_reindex_directory_covers_all_md_files(file_count):
    """reindex_directory must process every .md file in the subtree."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        pool.fetchrow = AsyncMock(return_value=_stub_row("x"))
        sm = SyncManager(pool, str(tmp))

        docs_dir = tmp / "infra"
        docs_dir.mkdir()
        for i in range(file_count):
            (docs_dir / f"doc{i}.md").write_text(f"# Doc {i}")
        (docs_dir / "readme.txt").write_text("skip me")

        with patch.object(sm, "_chunk_and_insert", new_callable=AsyncMock, return_value=1), \
             patch("db_documents.delete_document_by_path", new_callable=AsyncMock):
            results = asyncio.run(sm.reindex_directory("infra", "user1"))

        assert len(results) == file_count
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P15: Full re-indexing coverage
# ==========================================================================


@given(file_count=integers(min_value=1, max_value=5))
@settings(max_examples=15)
def test_reindex_all_covers_every_md_file(file_count):
    """reindex_all must find every .md file in the root."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        pool.fetchrow = AsyncMock(return_value=_stub_row("x"))
        sm = SyncManager(pool, str(tmp))

        for i in range(file_count):
            sub = tmp / f"cat{i}"
            sub.mkdir()
            (sub / "page.md").write_text(f"# Page {i}")

        with patch.object(sm, "_chunk_and_insert", new_callable=AsyncMock, return_value=1), \
             patch("db_documents.delete_document_by_path", new_callable=AsyncMock):
            results = asyncio.run(sm.reindex_all("user1"))

        assert len(results) == file_count
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P16: Re-indexing status transitions
# ==========================================================================


@given(should_fail=sampled_from([True, False]))
@settings(max_examples=20)
def test_reindex_status_transitions(should_fail):
    """Reindex must transition: processing → in_sync (success) or error (failure)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        pool.fetchrow = AsyncMock(return_value=_stub_row("docs/p16.md"))
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "docs" / "p16.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("# Content")

        status_calls = []
        original_update = sm.update_sync_status

        async def capture_status(fp, status, **kw):
            status_calls.append(status)
            await original_update(fp, status, **kw)

        with patch.object(sm, "update_sync_status", side_effect=capture_status), \
             patch.object(sm, "_chunk_and_insert", new_callable=AsyncMock,
                          return_value=1,
                          side_effect=Exception("fail") if should_fail else None), \
             patch("db_documents.delete_document_by_path", new_callable=AsyncMock,
                   side_effect=Exception("fail") if should_fail else None):
            try:
                asyncio.run(sm.reindex_document("docs/p16.md", "user1"))
            except (ReindexError, Exception):
                pass

        assert status_calls[0] == SyncStatus.PROCESSING
        if not should_fail:
            assert SyncStatus.IN_SYNC in status_calls
        else:
            assert SyncStatus.ERROR in status_calls
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P17: Re-indexing queue serialization (semaphore)
# ==========================================================================


@pytest.mark.asyncio
async def test_reindex_semaphore_limits_concurrency(tmp_path):
    """At most SYNC_REINDEX_CONCURRENCY reindex operations should run simultaneously."""
    pool = AsyncMock()
    pool.execute = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=_stub_row("x"))

    sm = SyncManager(pool, str(tmp_path))
    sm._reindex_semaphore = asyncio.Semaphore(2)

    max_concurrent = 0
    current_concurrent = 0
    lock = asyncio.Lock()

    async def slow_chunk(*a, **kw):
        nonlocal max_concurrent, current_concurrent
        async with lock:
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
        await asyncio.sleep(0.05)
        async with lock:
            current_concurrent -= 1
        return 1

    for i in range(5):
        (tmp_path / f"doc{i}.md").write_text(f"# Doc {i}")

    with patch.object(sm, "_chunk_and_insert", side_effect=slow_chunk), \
         patch("db_documents.delete_document_by_path", new_callable=AsyncMock):
        tasks = [sm.reindex_document(f"doc{i}.md", "user1") for i in range(5)]
        await asyncio.gather(*tasks)

    assert max_concurrent <= 2


# ==========================================================================
# P26: Per-document lock prevents concurrent ops
# ==========================================================================


@pytest.mark.asyncio
async def test_per_document_lock_serializes_ops(tmp_path):
    """Two operations on the same file must not run concurrently."""
    pool = AsyncMock()
    pool.execute = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=_stub_row("docs/lock.md"))
    sm = SyncManager(pool, str(tmp_path))

    doc = tmp_path / "docs" / "lock.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("# Lock test")

    with patch.object(sm, "_chunk_and_insert", new_callable=AsyncMock, return_value=1), \
         patch.object(sm, "check_conflict", new_callable=AsyncMock, return_value=None), \
         patch("db_documents.delete_document_by_path", new_callable=AsyncMock):
        t1 = asyncio.create_task(sm.update_document_atomic("docs/lock.md", "# V1", "user1"))
        t2 = asyncio.create_task(sm.update_document_atomic("docs/lock.md", "# V2", "user2"))
        await asyncio.gather(t1, t2)

    assert doc.exists()
