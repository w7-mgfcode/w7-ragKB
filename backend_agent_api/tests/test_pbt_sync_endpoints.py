"""Integration-style property tests for sync API endpoints (Task 8.3).

Tests sync status retrieval, re-indexing, conflict resolution,
and update_sync_status upsert at the SyncManager level.
"""

import asyncio
import shutil
import tempfile
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis.strategies import sampled_from, integers

from sync_manager import SyncManager, SyncStatus, DocumentSyncInfo, ConflictResolution
from document_exceptions import DocumentNotFoundError


sync_statuses = sampled_from(list(SyncStatus))
file_paths_strat = sampled_from([
    "docs/readme.md", "infra/setup.md", "guides/intro.md", "notes/daily.md"
])


def _make_row(fp, status="in_sync", chunk_count=3, error_msg=None):
    now = datetime.now(timezone.utc)
    return {
        "file_path": fp, "sync_status": status,
        "filesystem_mtime": now, "database_mtime": now,
        "chunk_count": chunk_count, "error_message": error_msg,
        "source": "browser", "last_checked": now,
    }


# ==========================================================================
# Sync status retrieval
# ==========================================================================


@given(status=sync_statuses)
@settings(max_examples=30)
def test_get_sync_status_returns_all_valid_statuses(status):
    """get_sync_status must return DocumentSyncInfo for any valid status."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=_make_row("test.md", status=status.value))
    sm = SyncManager(pool, "/tmp/test")

    result = asyncio.run(sm.get_sync_status("test.md"))
    assert result.sync_status == status


@given(count=integers(min_value=0, max_value=10))
@settings(max_examples=20)
def test_get_all_sync_statuses_returns_correct_count(count):
    """get_all_sync_statuses returns one entry per DB row."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[_make_row(f"doc{i}.md") for i in range(count)])
    sm = SyncManager(pool, "/tmp/test")

    results = asyncio.run(sm.get_all_sync_statuses())
    assert len(results) == count


# ==========================================================================
# Re-indexing endpoints
# ==========================================================================


@given(fp=file_paths_strat)
@settings(max_examples=20)
def test_reindex_nonexistent_file_raises(fp):
    """Reindexing a nonexistent file must raise DocumentNotFoundError."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        sm = SyncManager(pool, str(tmp))
        with pytest.raises(DocumentNotFoundError):
            asyncio.run(sm.reindex_document(fp, "user1"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@given(fp=file_paths_strat)
@settings(max_examples=20)
def test_reindex_existing_file_returns_in_sync(fp):
    """Reindexing an existing file results in in_sync status."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        pool.fetchrow = AsyncMock(return_value=_make_row(fp))
        sm = SyncManager(pool, str(tmp))

        doc = tmp / fp
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("# Content")

        with patch.object(sm, "_chunk_and_insert", new_callable=AsyncMock, return_value=2), \
             patch("db_documents.delete_document_by_path", new_callable=AsyncMock):
            result = asyncio.run(sm.reindex_document(fp, "user1"))

        assert result.sync_status == SyncStatus.IN_SYNC
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# Conflict resolution
# ==========================================================================


@given(strategy=sampled_from(["keep_filesystem", "keep_database"]))
@settings(max_examples=20)
def test_resolve_conflict_delegates_to_update(strategy):
    """Conflict resolution must delegate to update_document_atomic."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "docs" / "cfl.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("# FS")

        with patch.object(sm, "update_document_atomic", new_callable=AsyncMock) as mock_up, \
             patch("db_documents.get_document_content", new_callable=AsyncMock, return_value="# DB"):
            mock_up.return_value = DocumentSyncInfo(
                file_path="docs/cfl.md", sync_status=SyncStatus.IN_SYNC,
            )
            asyncio.run(sm.resolve_conflict("docs/cfl.md", ConflictResolution(strategy=strategy), "u1"))

        mock_up.assert_called_once()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# Update sync status upsert
# ==========================================================================


@given(status=sync_statuses)
@settings(max_examples=30)
def test_update_sync_status_calls_upsert(status):
    """update_sync_status must execute the upsert SQL for any status."""
    pool = AsyncMock()
    pool.execute = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=None)
    sm = SyncManager(pool, "/tmp/test")

    asyncio.run(sm.update_sync_status("test.md", status))
    pool.execute.assert_called_once()
