"""Tests for the asyncpg-based RAG pipeline db_handler.

All database functions are async and accept an asyncpg.Pool as their
first argument.  We use ``AsyncMock`` to simulate the pool/connection
without requiring a live PostgreSQL instance.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import os
import sys
import base64

# Add parent directory so ``common.*`` imports resolve
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.db_handler import (
    delete_document_by_file_id,
    insert_document_chunks,
    insert_or_update_document_metadata,
    insert_document_rows,
    process_file_for_rag,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool() -> AsyncMock:
    """Return a mock asyncpg.Pool whose acquire() yields a mock connection.

    ``pool.acquire()`` must behave as a synchronous call that returns an
    async context manager (matching real asyncpg behaviour).
    """
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value="DELETE 1")

    # Build an object that supports ``async with … as conn``
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    ctx.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = ctx

    return mock_pool, mock_conn


# ---------------------------------------------------------------------------
# delete_document_by_file_id
# ---------------------------------------------------------------------------

class TestDeleteDocumentByFileId:
    @pytest.mark.asyncio
    async def test_deletes_from_all_three_tables(self):
        pool, conn = _make_pool()

        await delete_document_by_file_id(pool, "file123")

        # Three DELETE calls: documents, document_rows, document_metadata
        assert conn.execute.call_count == 3

        calls = conn.execute.call_args_list
        assert "documents" in calls[0].args[0]
        assert calls[0].args[1] == "file123"

        assert "document_rows" in calls[1].args[0]
        assert calls[1].args[1] == "file123"

        assert "document_metadata" in calls[2].args[0]
        assert calls[2].args[1] == "file123"

    @pytest.mark.asyncio
    async def test_continues_on_partial_failure(self):
        """If deleting from one table fails, the others still run."""
        pool, conn = _make_pool()
        conn.execute = AsyncMock(
            side_effect=[Exception("boom"), "DELETE 0", "DELETE 0"]
        )

        # Should not raise
        await delete_document_by_file_id(pool, "file123")

        # All three calls attempted despite first failure
        assert conn.execute.call_count == 3


# ---------------------------------------------------------------------------
# insert_document_chunks
# ---------------------------------------------------------------------------

class TestInsertDocumentChunks:
    @pytest.mark.asyncio
    async def test_inserts_each_chunk_sequentially(self):
        pool, conn = _make_pool()

        chunks = ["Chunk 1", "Chunk 2"]
        embeddings = [[0.1, 0.2], [0.3, 0.4]]

        await insert_document_chunks(
            pool, chunks, embeddings, "file123",
            "https://example.com/file123", "Test File", "text/plain",
        )

        # One INSERT per chunk
        assert conn.execute.call_count == 2

        first_call = conn.execute.call_args_list[0]
        assert first_call.args[1] == "Chunk 1"
        meta = json.loads(first_call.args[2])
        assert meta["file_id"] == "file123"
        assert meta["chunk_index"] == 0
        assert meta["file_title"] == "Test File"

        second_call = conn.execute.call_args_list[1]
        assert second_call.args[1] == "Chunk 2"
        meta2 = json.loads(second_call.args[2])
        assert meta2["chunk_index"] == 1

    @pytest.mark.asyncio
    async def test_raises_on_chunk_embedding_mismatch(self):
        pool, _ = _make_pool()

        with pytest.raises(ValueError, match="must match"):
            await insert_document_chunks(
                pool, ["a", "b"], [[0.1]], "f", "u", "t", "text/plain",
            )

    @pytest.mark.asyncio
    async def test_includes_file_contents_for_images(self):
        pool, conn = _make_pool()

        raw = b"imagebytes"
        await insert_document_chunks(
            pool, ["img desc"], [[0.5]], "img1",
            "https://example.com/img1", "photo.png", "image/png",
            file_contents=raw,
        )

        meta = json.loads(conn.execute.call_args_list[0].args[2])
        assert meta["file_contents"] == base64.b64encode(raw).decode("utf-8")


# ---------------------------------------------------------------------------
# insert_or_update_document_metadata
# ---------------------------------------------------------------------------

class TestInsertOrUpdateDocumentMetadata:
    @pytest.mark.asyncio
    async def test_upserts_metadata(self):
        pool, conn = _make_pool()

        await insert_or_update_document_metadata(
            pool, "file123", "Test File", "https://example.com",
        )

        conn.execute.assert_awaited_once()
        sql = conn.execute.call_args.args[0]
        assert "ON CONFLICT" in sql
        assert conn.execute.call_args.args[1] == "file123"
        assert conn.execute.call_args.args[2] == "Test File"
        assert conn.execute.call_args.args[3] == "https://example.com"
        # schema is None
        assert conn.execute.call_args.args[4] is None

    @pytest.mark.asyncio
    async def test_upserts_with_schema(self):
        pool, conn = _make_pool()

        await insert_or_update_document_metadata(
            pool, "file123", "data.csv", "https://example.com",
            schema=["col1", "col2"],
        )

        assert conn.execute.call_args.args[4] == json.dumps(["col1", "col2"])

    @pytest.mark.asyncio
    async def test_handles_db_error(self):
        pool, conn = _make_pool()
        conn.execute = AsyncMock(side_effect=Exception("DB error"))

        # Should not raise — error is logged
        await insert_or_update_document_metadata(
            pool, "file123", "Test", "https://example.com",
        )


# ---------------------------------------------------------------------------
# insert_document_rows
# ---------------------------------------------------------------------------

class TestInsertDocumentRows:
    @pytest.mark.asyncio
    async def test_deletes_then_inserts(self):
        pool, conn = _make_pool()

        rows = [{"name": "John", "age": 30}, {"name": "Jane", "age": 25}]
        await insert_document_rows(pool, "file123", rows)

        # 1 DELETE + 2 INSERTs = 3 calls
        assert conn.execute.call_count == 3

        # First call is the DELETE
        assert "DELETE" in conn.execute.call_args_list[0].args[0]
        assert conn.execute.call_args_list[0].args[1] == "file123"

        # Second call inserts first row
        assert "INSERT" in conn.execute.call_args_list[1].args[0]
        assert conn.execute.call_args_list[1].args[1] == "file123"
        assert json.loads(conn.execute.call_args_list[1].args[2]) == rows[0]

    @pytest.mark.asyncio
    async def test_handles_db_error(self):
        pool, conn = _make_pool()
        conn.execute = AsyncMock(side_effect=Exception("DB error"))

        # Should not raise
        await insert_document_rows(pool, "file123", [{"x": 1}])


# ---------------------------------------------------------------------------
# process_file_for_rag
# ---------------------------------------------------------------------------

class TestProcessFileForRag:
    @pytest.fixture
    def setup_mocks(self):
        """Patch the text_processor helpers used by process_file_for_rag."""
        with (
            patch("common.db_handler.delete_document_by_file_id", new_callable=AsyncMock) as mock_delete,
            patch("common.db_handler.insert_or_update_document_metadata", new_callable=AsyncMock) as mock_meta,
            patch("common.db_handler.insert_document_rows", new_callable=AsyncMock) as mock_rows,
            patch("common.db_handler.insert_document_chunks", new_callable=AsyncMock) as mock_chunks,
            patch("common.db_handler.is_tabular_file") as mock_is_tabular,
            patch("common.db_handler.extract_schema_from_csv") as mock_schema,
            patch("common.db_handler.extract_rows_from_csv") as mock_extract_rows,
            patch("common.db_handler.chunk_text") as mock_chunk_text,
            patch("common.db_handler.create_embeddings") as mock_embeddings,
        ):
            yield {
                "delete_document": mock_delete,
                "insert_metadata": mock_meta,
                "insert_rows": mock_rows,
                "insert_chunks": mock_chunks,
                "is_tabular": mock_is_tabular,
                "extract_schema": mock_schema,
                "extract_rows": mock_extract_rows,
                "chunk_text": mock_chunk_text,
                "create_embeddings": mock_embeddings,
            }

    @pytest.mark.asyncio
    async def test_non_tabular_file(self, setup_mocks):
        mocks = setup_mocks
        pool = AsyncMock()

        mocks["is_tabular"].return_value = False
        mocks["chunk_text"].return_value = ["Chunk 1", "Chunk 2"]
        mocks["create_embeddings"].return_value = [[0.1, 0.2], [0.3, 0.4]]

        result = await process_file_for_rag(
            pool, b"content", "Text content", "file123",
            "https://example.com/file123", "Test File", "text/plain",
            config={"text_processing": {"default_chunk_size": 400, "default_chunk_overlap": 0}},
        )

        assert result is True
        mocks["delete_document"].assert_awaited_once_with(pool, "file123")
        mocks["insert_metadata"].assert_awaited_once_with(
            pool, "file123", "Test File", "https://example.com/file123", None,
        )
        mocks["extract_rows"].assert_not_called()
        mocks["insert_rows"].assert_not_awaited()
        mocks["chunk_text"].assert_called_once_with("Text content", chunk_size=400, overlap=0)
        mocks["create_embeddings"].assert_called_once_with(["Chunk 1", "Chunk 2"])
        mocks["insert_chunks"].assert_awaited_once_with(
            pool, ["Chunk 1", "Chunk 2"], [[0.1, 0.2], [0.3, 0.4]],
            "file123", "https://example.com/file123", "Test File", "text/plain",
        )

    @pytest.mark.asyncio
    async def test_tabular_file(self, setup_mocks):
        mocks = setup_mocks
        pool = AsyncMock()

        mocks["is_tabular"].return_value = True
        mocks["extract_schema"].return_value = ["col1", "col2"]
        mocks["extract_rows"].return_value = [{"col1": "v1", "col2": "v2"}]
        mocks["chunk_text"].return_value = ["Chunk 1"]
        mocks["create_embeddings"].return_value = [[0.1]]

        result = await process_file_for_rag(
            pool, b"col1,col2\nv1,v2", "col1,col2\nv1,v2", "file123",
            "https://example.com/file123", "data.csv", "text/csv",
            config={"text_processing": {"default_chunk_size": 400, "default_chunk_overlap": 0}},
        )

        assert result is True
        mocks["extract_schema"].assert_called_once()
        mocks["insert_metadata"].assert_awaited_once_with(
            pool, "file123", "data.csv", "https://example.com/file123", ["col1", "col2"],
        )
        mocks["insert_rows"].assert_awaited_once_with(
            pool, "file123", [{"col1": "v1", "col2": "v2"}],
        )

    @pytest.mark.asyncio
    async def test_image_file_passes_contents(self, setup_mocks):
        mocks = setup_mocks
        pool = AsyncMock()

        mocks["is_tabular"].return_value = False
        mocks["chunk_text"].return_value = ["photo.png"]
        mocks["create_embeddings"].return_value = [[0.5]]

        result = await process_file_for_rag(
            pool, b"imgdata", "photo.png", "img1",
            "https://example.com/img1", "photo.png", "image/png",
            config={},
        )

        assert result is True
        mocks["insert_chunks"].assert_awaited_once_with(
            pool, ["photo.png"], [[0.5]], "img1",
            "https://example.com/img1", "photo.png", "image/png", b"imgdata",
        )

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self, setup_mocks):
        mocks = setup_mocks
        pool = AsyncMock()
        mocks["delete_document"].side_effect = Exception("boom")

        result = await process_file_for_rag(
            pool, b"x", "text", "f1", "u", "t", "text/plain",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_empty_chunks_returns_true(self, setup_mocks):
        mocks = setup_mocks
        pool = AsyncMock()

        mocks["is_tabular"].return_value = False
        mocks["chunk_text"].return_value = []

        result = await process_file_for_rag(
            pool, b"x", "", "f1", "u", "t", "text/plain",
        )

        assert result is True
        mocks["create_embeddings"].assert_not_called()
        mocks["insert_chunks"].assert_not_awaited()
