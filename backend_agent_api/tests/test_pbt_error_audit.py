"""Property-based tests for error handling and audit logging (Tasks 21.2, 22.2).

Properties tested:
- P40: Filesystem failure rollback
- P41: Database failure rollback
- P42: Embedding failure recovery
- P43: File watcher error isolation
- P44: Re-indexing timeout handling
- P49: Audit log completeness
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import types
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis.strategies import integers, sampled_from, text

# Mock pypdf before any file_watcher import chain triggers
if "pypdf" not in sys.modules:
    sys.modules["pypdf"] = types.ModuleType("pypdf")

# Add rag pipeline paths for file_watcher tests
_rag_root = os.path.join(os.path.dirname(__file__), "..", "..", "backend_rag_pipeline")
sys.path.insert(0, os.path.join(_rag_root, "Local_Files"))
sys.path.insert(0, _rag_root)

from sync_manager import SyncManager, SyncStatus
from document_exceptions import AtomicOperationError, ReindexError


md_content = text(
    alphabet="abcdefghijklmnopqrstuvwxyz #*\n-_0123456789",
    min_size=1, max_size=200,
)
user_ids = sampled_from(["user1", "user2", "admin"])
operations = sampled_from(["create", "update", "delete", "reindex", "resolve_conflict"])


# ==========================================================================
# P40: Create rollback
# ==========================================================================


@given(content=md_content)
@settings(max_examples=20)
def test_create_rollback_removes_file_on_chunk_failure(content):
    """If chunking fails during create, the file must be removed."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        sm = SyncManager(pool, str(tmp))

        with patch.object(sm, "_chunk_and_insert", new_callable=AsyncMock,
                          side_effect=Exception("chunk fail")):
            with pytest.raises(AtomicOperationError):
                asyncio.run(sm.create_document_atomic("docs/r.md", content, "u1"))

        assert not (tmp / "docs" / "r.md").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P41: Update rollback
# ==========================================================================


@given(content=md_content)
@settings(max_examples=20)
def test_update_rollback_restores_on_db_failure(content):
    """If DB fails during update, the original file must be restored."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "docs" / "dbf.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        original = "# Original"
        doc.write_text(original)

        with patch.object(sm, "check_conflict", new_callable=AsyncMock, return_value=None), \
             patch("db_documents.delete_document_by_path", new_callable=AsyncMock,
                   side_effect=Exception("DB error")):
            with pytest.raises(AtomicOperationError):
                asyncio.run(sm.update_document_atomic("docs/dbf.md", content, "u1"))

        assert doc.read_text() == original
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@given(content=md_content)
@settings(max_examples=20)
def test_delete_rollback_restores_on_db_failure(content):
    """If DB fails during delete, the file must be restored."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "docs" / "df.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text(content)

        with patch("db_documents.delete_document_by_path", new_callable=AsyncMock,
                    side_effect=Exception("DB error")):
            with pytest.raises(AtomicOperationError):
                asyncio.run(sm.delete_document_atomic("docs/df.md", "u1"))

        assert doc.exists()
        assert doc.read_text() == content
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P42: Embedding failure recovery
# ==========================================================================


@given(fail_count=integers(min_value=1, max_value=2))
@settings(max_examples=10, deadline=None)
def test_embedding_retry_recovers(fail_count):
    """_get_embedding_with_retry must succeed after transient failures."""
    pool = AsyncMock()
    sm = SyncManager(pool, "/tmp/test")
    sm._embedding_max_retries = 3

    call_count = 0

    async def flaky(text):
        nonlocal call_count
        call_count += 1
        if call_count <= fail_count:
            raise ConnectionError("transient")
        return [0.1] * 768

    with patch.object(sm, "_get_embedding", side_effect=flaky):
        result = asyncio.run(sm._get_embedding_with_retry("test"))

    assert len(result) == 768
    assert call_count == fail_count + 1


def test_embedding_retry_exhaustion_raises():
    """After max retries, must raise."""
    pool = AsyncMock()
    sm = SyncManager(pool, "/tmp/test")
    sm._embedding_max_retries = 2

    with patch.object(sm, "_get_embedding", new_callable=AsyncMock,
                      side_effect=ConnectionError("permanent")):
        with pytest.raises(ConnectionError):
            asyncio.run(sm._get_embedding_with_retry("test"))


# ==========================================================================
# P43: File watcher error isolation
# ==========================================================================


def test_watcher_error_does_not_break_other_files(tmp_path):
    """A failure processing one file must not prevent others."""
    pool = AsyncMock()
    pool.execute = AsyncMock()

    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({
        "supported_mime_types": ["text/plain"],
        "tabular_mime_types": [],
        "text_processing": {"default_chunk_size": 400, "default_chunk_overlap": 0},
        "last_check_time": "1970-01-01T00:00:00.000Z",
    }))

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "good.txt").write_text("good")
    (data_dir / "bad.txt").write_text("bad")

    with patch.dict(os.environ, {"RAG_WATCH_DIRECTORY": str(data_dir)}):
        from file_watcher import LocalFileWatcher
        w = LocalFileWatcher(pool=pool, watch_directory=str(data_dir), config_path=str(cfg))

    w.initialized = True
    process_count = 0

    async def mock_process(fi):
        nonlocal process_count
        if "bad" in fi["name"]:
            raise Exception("Bad!")
        process_count += 1

    with patch.object(w, "process_file", side_effect=mock_process), \
         patch.object(w, "_check_deleted", return_value=[]):
        stats = asyncio.run(w.check_for_changes())

    assert stats["errors"] >= 1
    assert process_count >= 1


# ==========================================================================
# P44: Re-indexing timeout
# ==========================================================================


@pytest.mark.asyncio
async def test_reindex_timeout_sets_error_status(tmp_path):
    """When reindex times out, status transitions to error."""
    pool = AsyncMock()
    pool.execute = AsyncMock()
    sm = SyncManager(pool, str(tmp_path))
    sm._reindex_timeout = 0.01

    doc = tmp_path / "docs" / "slow.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("# Slow")

    async def very_slow(*a, **kw):
        await asyncio.sleep(10)

    with patch.object(sm, "_do_reindex", side_effect=very_slow):
        with pytest.raises(ReindexError, match="Timed out"):
            await sm.reindex_document("docs/slow.md", "u1")


# ==========================================================================
# P49: Audit log completeness
# ==========================================================================


@given(operation=operations, user=user_ids)
@settings(max_examples=30)
def test_audit_produces_structured_json(operation, user):
    """_audit must produce valid JSON with required fields."""
    pool = AsyncMock()
    sm = SyncManager(pool, "/tmp/test")

    records = []
    with patch("sync_manager.logger") as mock_log:
        mock_log.info = lambda msg, *a: records.append(msg)
        sm._audit(operation, "test.md", user)

    entry = json.loads(records[0])
    assert entry["event"] == f"sync.{operation}"
    assert entry["user_id"] == user
    assert entry["path"] == "test.md"
    assert entry["status"] == "success"


@given(operation=operations, user=user_ids)
@settings(max_examples=20)
def test_audit_failure_includes_error(operation, user):
    """Failed operations must include error in audit log."""
    pool = AsyncMock()
    sm = SyncManager(pool, "/tmp/test")

    records = []
    with patch("sync_manager.logger") as mock_log:
        mock_log.info = lambda msg, *a: records.append(msg)
        sm._audit(operation, "test.md", user, error="broke")

    entry = json.loads(records[0])
    assert entry["status"] == "failure"
    assert entry["error"] == "broke"


def test_audit_status_change_logs_transition():
    """_audit_status_change must log old and new status."""
    pool = AsyncMock()
    sm = SyncManager(pool, "/tmp/test")

    records = []
    with patch("sync_manager.logger") as mock_log:
        mock_log.info = lambda msg, *a: records.append(msg)
        sm._audit_status_change("test.md", "processing", "in_sync")

    entry = json.loads(records[0])
    assert entry["event"] == "sync.status_change"
    assert entry["old_status"] == "processing"
    assert entry["new_status"] == "in_sync"
