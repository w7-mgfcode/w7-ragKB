"""Property-based tests for atomic document operations (Tasks 2.4, 9.4).

Properties tested:
- P8:  Edit synchronization to filesystem — file content matches after update
- P9:  Re-chunking trigger — update triggers chunk re-insertion
- P10: Atomic chunk replacement — old chunks deleted, new ones inserted
- P11: Atomic operations guarantee — on failure, state is unchanged
"""

import asyncio
import shutil
import tempfile
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis.strategies import text, sampled_from

from sync_manager import SyncManager, SyncStatus, DocumentSyncInfo
from document_exceptions import AtomicOperationError, DocumentConflictError


# --------------------------------------------------------------------------
# Strategies
# --------------------------------------------------------------------------

md_content = text(
    alphabet="abcdefghijklmnopqrstuvwxyz #*\n-_0123456789",
    min_size=1,
    max_size=500,
)
user_ids = sampled_from(["user1", "user2", "admin", "bot"])


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
# P8: Edit synchronization to filesystem
# ==========================================================================


@given(content=md_content, user=user_ids)
@settings(max_examples=30)
def test_update_writes_content_to_filesystem(content, user):
    """After update_document_atomic, filesystem content must match the input."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        pool.fetchrow = AsyncMock(return_value=_stub_row("docs/p8.md"))
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "docs" / "p8.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("# original", encoding="utf-8")

        with patch.object(sm, "_chunk_and_insert", new_callable=AsyncMock, return_value=2), \
             patch.object(sm, "check_conflict", new_callable=AsyncMock, return_value=None), \
             patch("db_documents.delete_document_by_path", new_callable=AsyncMock):
            asyncio.run(sm.update_document_atomic("docs/p8.md", content, user))

        assert doc.read_text(encoding="utf-8") == content
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P9: Re-chunking trigger
# ==========================================================================


@given(content=md_content, user=user_ids)
@settings(max_examples=30)
def test_update_triggers_rechunking(content, user):
    """Every update must call _chunk_and_insert to regenerate embeddings."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        pool.fetchrow = AsyncMock(return_value=_stub_row("docs/p9.md"))
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "docs" / "p9.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("# old", encoding="utf-8")

        with patch.object(sm, "_chunk_and_insert", new_callable=AsyncMock, return_value=1) as mock_chunk, \
             patch.object(sm, "check_conflict", new_callable=AsyncMock, return_value=None), \
             patch("db_documents.delete_document_by_path", new_callable=AsyncMock):
            asyncio.run(sm.update_document_atomic("docs/p9.md", content, user))

        mock_chunk.assert_called_once()
        assert mock_chunk.call_args[0][1] == content
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P10: Atomic chunk replacement — delete before insert
# ==========================================================================


@given(content=md_content, user=user_ids)
@settings(max_examples=30)
def test_update_deletes_old_chunks_before_insert(content, user):
    """Update must delete old chunks before inserting new ones."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        pool.fetchrow = AsyncMock(return_value=_stub_row("docs/p10.md"))
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "docs" / "p10.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("# old", encoding="utf-8")

        call_order = []

        async def track_delete(*a, **kw):
            call_order.append("delete")

        async def track_chunk(*a, **kw):
            call_order.append("chunk")
            return 3

        with patch.object(sm, "_chunk_and_insert", side_effect=track_chunk), \
             patch.object(sm, "check_conflict", new_callable=AsyncMock, return_value=None), \
             patch("db_documents.delete_document_by_path", side_effect=track_delete):
            asyncio.run(sm.update_document_atomic("docs/p10.md", content, user))

        assert call_order == ["delete", "chunk"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P11: Atomic operations guarantee — create rollback
# ==========================================================================


@given(content=md_content, user=user_ids)
@settings(max_examples=30)
def test_create_rollback_on_failure_removes_file(content, user):
    """If DB insert fails during create, filesystem file must be removed."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        sm = SyncManager(pool, str(tmp))

        with patch.object(sm, "_chunk_and_insert", new_callable=AsyncMock, side_effect=Exception("DB fail")):
            with pytest.raises(AtomicOperationError):
                asyncio.run(sm.create_document_atomic("docs/p11.md", content, user))

        assert not (tmp / "docs" / "p11.md").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P11: Update rollback
# ==========================================================================


@given(content=md_content, user=user_ids)
@settings(max_examples=30)
def test_update_rollback_on_failure_restores_original(content, user):
    """If re-chunking fails during update, original file must be restored."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "docs" / "p11u.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        original = "# Original content"
        doc.write_text(original, encoding="utf-8")

        with patch.object(sm, "check_conflict", new_callable=AsyncMock, return_value=None), \
             patch("db_documents.delete_document_by_path", new_callable=AsyncMock, side_effect=Exception("DB fail")):
            with pytest.raises(AtomicOperationError):
                asyncio.run(sm.update_document_atomic("docs/p11u.md", content, user))

        assert doc.exists()
        assert doc.read_text(encoding="utf-8") == original
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P11: Duplicate file prevention
# ==========================================================================


@given(content=md_content, user=user_ids)
@settings(max_examples=20)
def test_create_duplicate_file_raises_conflict(content, user):
    """Creating a document that already exists must raise DocumentConflictError."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "docs" / "dup.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("existing", encoding="utf-8")

        with pytest.raises(DocumentConflictError):
            asyncio.run(sm.create_document_atomic("docs/dup.md", content, user))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
