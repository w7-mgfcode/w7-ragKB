"""Property-based tests for conflict detection and resolution (Task 5.2).

Properties tested:
- P18: Conflict detection on edit — mtime mismatch → ConflictInfo returned
- P19: Duplicate file_id prevention — existing file → ConflictError
- P20: Atomic conflict resolution — successful resolve returns in_sync
"""

import asyncio
import shutil
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis.strategies import integers, sampled_from, text

from sync_manager import SyncManager, SyncStatus, ConflictResolution, DocumentSyncInfo
from document_exceptions import DocumentConflictError, DocumentValidationError


md_content = text(
    alphabet="abcdefghijklmnopqrstuvwxyz #*\n-_0123456789",
    min_size=1,
    max_size=200,
)


def _stub_row(fp):
    now = datetime.now(timezone.utc)
    return {
        "file_path": fp, "sync_status": "in_sync",
        "filesystem_mtime": now, "database_mtime": now,
        "chunk_count": 2, "error_message": None,
        "source": "browser", "last_checked": now,
    }


# ==========================================================================
# P18: Conflict detection — mtime mismatch
# ==========================================================================


@given(offset_seconds=integers(min_value=2, max_value=86400))
@settings(max_examples=30)
def test_mtime_mismatch_detects_conflict(offset_seconds):
    """When expected_mtime differs from filesystem mtime by > 1s, conflict is detected."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "docs" / "conflict.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("# Content")

        fs_mtime = datetime.fromtimestamp(doc.stat().st_mtime, tz=timezone.utc)
        expected = fs_mtime - timedelta(seconds=offset_seconds)

        with patch("db_documents.get_document_content", new_callable=AsyncMock, return_value="# DB"):
            result = asyncio.run(sm.check_conflict("docs/conflict.md", expected_mtime=expected))

        assert result is not None
        assert result.conflict_type == "content_mismatch"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P18 (inverse): Matching mtime → no conflict
# ==========================================================================


def test_matching_mtime_no_conflict(tmp_path):
    """When expected_mtime matches filesystem mtime, no conflict returned."""
    pool = AsyncMock()
    sm = SyncManager(pool, str(tmp_path))

    doc = tmp_path / "docs" / "ok.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("# Content")
    fs_mtime = datetime.fromtimestamp(doc.stat().st_mtime, tz=timezone.utc)

    result = asyncio.run(sm.check_conflict("docs/ok.md", expected_mtime=fs_mtime))
    assert result is None


# ==========================================================================
# P19: Duplicate file prevention
# ==========================================================================


@given(content=md_content)
@settings(max_examples=20)
def test_create_existing_file_raises_conflict(content):
    """Creating a document that already exists must raise DocumentConflictError."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "docs" / "exists.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("# Already here")

        with pytest.raises(DocumentConflictError):
            asyncio.run(sm.create_document_atomic("docs/exists.md", content, "user1"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P20: Atomic conflict resolution returns in_sync
# ==========================================================================


@given(strategy=sampled_from(["keep_filesystem", "keep_database"]))
@settings(max_examples=20)
def test_resolve_conflict_returns_in_sync(strategy):
    """After resolving a conflict, the document should be in_sync."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        pool.fetchrow = AsyncMock(return_value=_stub_row("docs/resolve.md"))
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "docs" / "resolve.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text("# FS version")

        with patch.object(sm, "update_document_atomic", new_callable=AsyncMock) as mock_up, \
             patch("db_documents.get_document_content", new_callable=AsyncMock, return_value="# DB"):
            mock_up.return_value = DocumentSyncInfo(
                file_path="docs/resolve.md", sync_status=SyncStatus.IN_SYNC,
            )
            resolution = ConflictResolution(strategy=strategy)
            result = asyncio.run(sm.resolve_conflict("docs/resolve.md", resolution, "user1"))

        assert result.sync_status == SyncStatus.IN_SYNC
        mock_up.assert_called_once()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P20: Manual merge requires content
# ==========================================================================


def test_manual_merge_requires_content(tmp_path):
    """manual_merge with empty merged_content must raise validation error."""
    pool = AsyncMock()
    sm = SyncManager(pool, str(tmp_path))

    doc = tmp_path / "docs" / "merge.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("# Content")

    resolution = ConflictResolution(strategy="manual_merge", merged_content="")
    with pytest.raises(DocumentValidationError):
        asyncio.run(sm.resolve_conflict("docs/merge.md", resolution, "user1"))
