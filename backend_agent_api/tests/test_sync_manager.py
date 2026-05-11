"""Unit tests for sync_manager.py — SyncManager core coordinator."""

import sys
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from sync_manager import SyncManager, SyncStatus, DocumentSyncInfo, ConflictResolution
from document_exceptions import (
    AtomicOperationError,
    DocumentConflictError,
    DocumentNotFoundError,
    DocumentValidationError,
    ReindexError,
)


@pytest.fixture
def mock_db_documents():
    """Mock db_documents module that sync_manager imports lazily."""
    mod = MagicMock()
    mod.delete_document_by_path = AsyncMock()
    mod.get_document_content = AsyncMock(return_value="# DB content")
    original = sys.modules.get("db_documents")
    sys.modules["db_documents"] = mod
    yield mod
    if original is not None:
        sys.modules["db_documents"] = original
    else:
        sys.modules.pop("db_documents", None)


@pytest.fixture
def mock_pool():
    """Mock asyncpg connection pool."""
    pool = AsyncMock()
    return pool


@pytest.fixture
def sync_manager(mock_pool, tmp_path):
    """SyncManager with a temp directory for rag-documents."""
    return SyncManager(mock_pool, str(tmp_path))


# ==========================================================================
# Sync status queries
# ==========================================================================


class TestGetSyncStatus:
    @pytest.mark.asyncio
    async def test_get_sync_status_from_db(self, sync_manager, mock_pool):
        """Should return sync info from document_sync_status table."""
        now = datetime.now(timezone.utc)
        mock_pool.fetchrow.return_value = {
            "file_path": "docs/test.md",
            "sync_status": "in_sync",
            "filesystem_mtime": now,
            "database_mtime": now,
            "chunk_count": 5,
            "error_message": None,
            "source": "browser",
            "last_checked": now,
        }

        result = await sync_manager.get_sync_status("docs/test.md")

        assert result.file_path == "docs/test.md"
        assert result.sync_status == SyncStatus.IN_SYNC
        assert result.chunk_count == 5
        assert result.source == "browser"

    @pytest.mark.asyncio
    async def test_get_sync_status_computes_when_missing(self, sync_manager, mock_pool, tmp_path):
        """Should compute sync info on the fly when no DB row exists."""
        mock_pool.fetchrow.side_effect = [
            None,  # First call: no row in document_sync_status
            {"cnt": 0, "db_mtime": None},  # Second call: _compute_sync_info
        ]

        # Create a file so it exists on filesystem
        test_file = tmp_path / "docs" / "test.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# Hello")

        result = await sync_manager.get_sync_status("docs/test.md")

        assert result.sync_status == SyncStatus.PENDING_INDEXING

    @pytest.mark.asyncio
    async def test_get_sync_status_orphaned_chunks(self, sync_manager, mock_pool):
        """File doesn't exist but DB has chunks → orphaned."""
        now = datetime.now(timezone.utc)
        mock_pool.fetchrow.side_effect = [
            None,  # No tracking row
            {"cnt": 3, "db_mtime": now},  # DB has chunks
        ]

        result = await sync_manager.get_sync_status("docs/gone.md")

        assert result.sync_status == SyncStatus.ORPHANED_CHUNKS

    @pytest.mark.asyncio
    async def test_get_sync_status_in_sync(self, sync_manager, mock_pool, tmp_path):
        """File and DB both exist with matching times → in_sync."""
        test_file = tmp_path / "docs" / "test.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# Hello")

        fs_mtime = datetime.fromtimestamp(test_file.stat().st_mtime, tz=timezone.utc)
        # DB mtime is newer (or equal) — should be in_sync
        db_mtime = fs_mtime + timedelta(seconds=1)

        mock_pool.fetchrow.side_effect = [
            None,  # No tracking row
            {"cnt": 5, "db_mtime": db_mtime},
        ]

        result = await sync_manager.get_sync_status("docs/test.md")

        assert result.sync_status == SyncStatus.IN_SYNC

    @pytest.mark.asyncio
    async def test_get_sync_status_out_of_sync(self, sync_manager, mock_pool, tmp_path):
        """File mtime newer than DB → out_of_sync."""
        test_file = tmp_path / "docs" / "test.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# Updated content")

        # DB mtime is 10 minutes in the past
        db_mtime = datetime.now(timezone.utc) - timedelta(minutes=10)

        mock_pool.fetchrow.side_effect = [
            None,  # No tracking row
            {"cnt": 5, "db_mtime": db_mtime},
        ]

        result = await sync_manager.get_sync_status("docs/test.md")

        assert result.sync_status == SyncStatus.OUT_OF_SYNC


class TestGetAllSyncStatuses:
    @pytest.mark.asyncio
    async def test_returns_all_rows(self, sync_manager, mock_pool):
        now = datetime.now(timezone.utc)
        mock_pool.fetch.return_value = [
            {
                "file_path": "a.md",
                "sync_status": "in_sync",
                "filesystem_mtime": now,
                "database_mtime": now,
                "chunk_count": 3,
                "error_message": None,
                "source": "filesystem",
                "last_checked": now,
            },
            {
                "file_path": "b.md",
                "sync_status": "error",
                "filesystem_mtime": None,
                "database_mtime": None,
                "chunk_count": 0,
                "error_message": "embedding failed",
                "source": "browser",
                "last_checked": now,
            },
        ]

        results = await sync_manager.get_all_sync_statuses()

        assert len(results) == 2
        assert results[0].sync_status == SyncStatus.IN_SYNC
        assert results[1].sync_status == SyncStatus.ERROR
        assert results[1].error_message == "embedding failed"


# ==========================================================================
# Atomic operations
# ==========================================================================


class TestCreateDocumentAtomic:
    @pytest.mark.asyncio
    async def test_create_success(self, sync_manager, mock_pool, tmp_path):
        """Should create file on filesystem and insert chunks."""
        mock_pool.execute = AsyncMock()
        mock_pool.fetchrow.return_value = {
            "file_path": "docs/new.md",
            "sync_status": "in_sync",
            "filesystem_mtime": datetime.now(timezone.utc),
            "database_mtime": datetime.now(timezone.utc),
            "chunk_count": 2,
            "error_message": None,
            "source": "browser",
            "last_checked": datetime.now(timezone.utc),
        }

        with patch.object(sync_manager, "_chunk_and_insert", new_callable=AsyncMock) as mock_chunk:
            mock_chunk.return_value = 2

            result = await sync_manager.create_document_atomic(
                "docs/new.md", "# New Doc", "user1"
            )

        # File should have been written
        created_file = tmp_path / "docs" / "new.md"
        assert created_file.exists()
        assert created_file.read_text() == "# New Doc"
        assert result.sync_status == SyncStatus.IN_SYNC

    @pytest.mark.asyncio
    async def test_create_conflict_if_exists(self, sync_manager, tmp_path):
        """Should raise DocumentConflictError if file already exists."""
        existing = tmp_path / "docs" / "existing.md"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("already here")

        with pytest.raises(DocumentConflictError):
            await sync_manager.create_document_atomic(
                "docs/existing.md", "content", "user1"
            )

    @pytest.mark.asyncio
    async def test_create_rollback_on_db_error(self, sync_manager, mock_pool, tmp_path):
        """Should delete file on DB error (rollback)."""
        mock_pool.execute = AsyncMock()

        with patch.object(sync_manager, "_chunk_and_insert", new_callable=AsyncMock) as mock_chunk:
            mock_chunk.side_effect = Exception("DB insert failed")

            with pytest.raises(AtomicOperationError):
                await sync_manager.create_document_atomic(
                    "docs/fail.md", "# Content", "user1"
                )

        # Rollback: file should be cleaned up
        assert not (tmp_path / "docs" / "fail.md").exists()


class TestUpdateDocumentAtomic:
    @pytest.mark.asyncio
    async def test_update_success(self, sync_manager, mock_pool, tmp_path, mock_db_documents):
        """Should backup, update, re-chunk, cleanup backup."""
        test_file = tmp_path / "docs" / "update.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# Old content")

        mock_pool.execute = AsyncMock()
        mock_pool.fetchrow.return_value = {
            "file_path": "docs/update.md",
            "sync_status": "in_sync",
            "filesystem_mtime": datetime.now(timezone.utc),
            "database_mtime": datetime.now(timezone.utc),
            "chunk_count": 3,
            "error_message": None,
            "source": "browser",
            "last_checked": datetime.now(timezone.utc),
        }

        with patch.object(sync_manager, "_chunk_and_insert", new_callable=AsyncMock) as mock_chunk, \
             patch.object(sync_manager, "check_conflict", new_callable=AsyncMock) as mock_conflict:
            mock_chunk.return_value = 3
            mock_conflict.return_value = None

            result = await sync_manager.update_document_atomic(
                "docs/update.md", "# New content", "user1"
            )

        assert test_file.read_text() == "# New content"
        # Backup should be cleaned up
        assert not (tmp_path / "docs" / "update.md.bak").exists()

    @pytest.mark.asyncio
    async def test_update_not_found(self, sync_manager, tmp_path):
        """Should raise DocumentNotFoundError if file doesn't exist."""
        with pytest.raises(DocumentNotFoundError):
            await sync_manager.update_document_atomic(
                "docs/nonexistent.md", "content", "user1"
            )


class TestDeleteDocumentAtomic:
    @pytest.mark.asyncio
    async def test_delete_success(self, sync_manager, mock_pool, tmp_path, mock_db_documents):
        """Should backup file, delete from DB, cleanup backup."""
        test_file = tmp_path / "docs" / "delete.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# To delete")

        mock_pool.execute = AsyncMock()

        await sync_manager.delete_document_atomic(
            "docs/delete.md", "user1"
        )

        # File and backup should both be gone
        assert not test_file.exists()
        assert not (tmp_path / "docs" / "delete.md.deleted").exists()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, sync_manager, tmp_path):
        """Should raise DocumentNotFoundError if file doesn't exist."""
        with pytest.raises(DocumentNotFoundError):
            await sync_manager.delete_document_atomic(
                "docs/nonexistent.md", "user1"
            )

    @pytest.mark.asyncio
    async def test_delete_rollback_on_db_error(self, sync_manager, mock_pool, tmp_path, mock_db_documents):
        """Should restore backup on DB error."""
        test_file = tmp_path / "docs" / "delete_fail.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# Restore me")

        mock_pool.execute = AsyncMock()
        mock_db_documents.delete_document_by_path = AsyncMock(
            side_effect=Exception("DB delete failed")
        )

        with pytest.raises(AtomicOperationError):
            await sync_manager.delete_document_atomic(
                "docs/delete_fail.md", "user1"
            )

        # Rollback: file should be restored
        assert test_file.exists()
        assert test_file.read_text() == "# Restore me"


# ==========================================================================
# Re-indexing
# ==========================================================================


class TestReindexDocument:
    @pytest.mark.asyncio
    async def test_reindex_success(self, sync_manager, mock_pool, tmp_path, mock_db_documents):
        """Should re-chunk and re-embed a document."""
        test_file = tmp_path / "docs" / "reindex.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# Reindex me")

        mock_pool.execute = AsyncMock()
        mock_pool.fetchrow.return_value = {
            "file_path": "docs/reindex.md",
            "sync_status": "in_sync",
            "filesystem_mtime": datetime.now(timezone.utc),
            "database_mtime": datetime.now(timezone.utc),
            "chunk_count": 2,
            "error_message": None,
            "source": "browser",
            "last_checked": datetime.now(timezone.utc),
        }

        with patch.object(sync_manager, "_chunk_and_insert", new_callable=AsyncMock) as mock_chunk:
            mock_chunk.return_value = 2

            result = await sync_manager.reindex_document("docs/reindex.md", "user1")

        assert result.sync_status == SyncStatus.IN_SYNC

    @pytest.mark.asyncio
    async def test_reindex_not_found(self, sync_manager, tmp_path):
        """Should raise DocumentNotFoundError if file doesn't exist."""
        with pytest.raises(DocumentNotFoundError):
            await sync_manager.reindex_document("docs/nonexistent.md", "user1")

    @pytest.mark.asyncio
    async def test_reindex_error_updates_status(self, sync_manager, mock_pool, tmp_path, mock_db_documents):
        """Should update sync status to error on failure."""
        test_file = tmp_path / "docs" / "fail.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# Will fail")

        mock_pool.execute = AsyncMock()
        mock_db_documents.delete_document_by_path = AsyncMock(
            side_effect=Exception("Chunk failure")
        )

        with pytest.raises(ReindexError):
            await sync_manager.reindex_document("docs/fail.md", "user1")


class TestReindexDirectory:
    @pytest.mark.asyncio
    async def test_reindex_directory_success(self, sync_manager, mock_pool, tmp_path, mock_db_documents):
        """Should re-index all .md files in directory."""
        docs_dir = tmp_path / "infra"
        docs_dir.mkdir()
        (docs_dir / "a.md").write_text("# A")
        (docs_dir / "b.md").write_text("# B")
        (docs_dir / "not_md.txt").write_text("skip me")

        mock_pool.execute = AsyncMock()

        now = datetime.now(timezone.utc)
        mock_pool.fetchrow.return_value = {
            "file_path": "infra/a.md",
            "sync_status": "in_sync",
            "filesystem_mtime": now,
            "database_mtime": now,
            "chunk_count": 1,
            "error_message": None,
            "source": "browser",
            "last_checked": now,
        }

        with patch.object(sync_manager, "_chunk_and_insert", new_callable=AsyncMock) as mock_chunk:
            mock_chunk.return_value = 1

            results = await sync_manager.reindex_directory("infra", "user1")

        assert len(results) == 2  # Only .md files


# ==========================================================================
# Conflict resolution
# ==========================================================================


class TestResolveConflict:
    @pytest.mark.asyncio
    async def test_resolve_keep_filesystem(self, sync_manager, mock_pool, tmp_path):
        """Should read filesystem content and update atomically."""
        test_file = tmp_path / "docs" / "conflict.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# Filesystem version")

        mock_pool.execute = AsyncMock()
        mock_pool.fetchrow.return_value = {
            "file_path": "docs/conflict.md",
            "sync_status": "in_sync",
            "filesystem_mtime": datetime.now(timezone.utc),
            "database_mtime": datetime.now(timezone.utc),
            "chunk_count": 2,
            "error_message": None,
            "source": "browser",
            "last_checked": datetime.now(timezone.utc),
        }

        with patch.object(sync_manager, "update_document_atomic", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = DocumentSyncInfo(
                file_path="docs/conflict.md",
                sync_status=SyncStatus.IN_SYNC,
            )

            resolution = ConflictResolution(strategy="keep_filesystem")
            result = await sync_manager.resolve_conflict("docs/conflict.md", resolution, "user1")

            mock_update.assert_called_once()
            # The content passed should be the filesystem content
            call_args = mock_update.call_args
            assert call_args[0][1] == "# Filesystem version"

    @pytest.mark.asyncio
    async def test_resolve_keep_database(self, sync_manager, mock_pool, tmp_path, mock_db_documents):
        """Should read database content and update atomically."""
        test_file = tmp_path / "docs" / "conflict.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# FS version")

        mock_db_documents.get_document_content = AsyncMock(return_value="# DB version")

        with patch.object(sync_manager, "update_document_atomic", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = DocumentSyncInfo(
                file_path="docs/conflict.md",
                sync_status=SyncStatus.IN_SYNC,
            )

            resolution = ConflictResolution(strategy="keep_database")
            result = await sync_manager.resolve_conflict("docs/conflict.md", resolution, "user1")

            call_args = mock_update.call_args
            assert call_args[0][1] == "# DB version"

    @pytest.mark.asyncio
    async def test_resolve_manual_merge_requires_content(self, sync_manager, tmp_path):
        """Should raise if manual_merge has no merged_content."""
        test_file = tmp_path / "docs" / "conflict.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# FS version")

        resolution = ConflictResolution(strategy="manual_merge", merged_content="")

        with pytest.raises(DocumentValidationError):
            await sync_manager.resolve_conflict("docs/conflict.md", resolution, "user1")


# ==========================================================================
# Module-level singleton
# ==========================================================================


class TestModuleSingleton:
    def test_get_sync_manager_raises_if_not_initialized(self):
        from sync_manager import get_sync_manager, _instance
        import sync_manager as mod

        original = mod._instance
        mod._instance = None
        try:
            with pytest.raises(RuntimeError, match="not initialized"):
                get_sync_manager()
        finally:
            mod._instance = original
