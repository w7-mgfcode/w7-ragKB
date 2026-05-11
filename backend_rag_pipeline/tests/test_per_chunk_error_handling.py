"""Tests for RAG pipeline per-chunk error handling and sequential processing.

Validates:
- Requirement 2.4: Embedding API errors are logged and failing chunks skipped
  without halting the pipeline.
- Requirement 9.3: Files are processed sequentially to avoid memory spikes.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os
import sys

# Add parent directory so ``common.*`` imports resolve
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.db_handler import (
    insert_document_chunks,
    process_file_for_rag,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool():
    """Return a mock asyncpg.Pool whose acquire() yields a mock connection."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value="INSERT 1")

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    ctx.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = ctx

    return mock_pool, mock_conn


# ---------------------------------------------------------------------------
# Per-chunk insert error handling in insert_document_chunks
# ---------------------------------------------------------------------------

class TestInsertDocumentChunksErrorHandling:
    """Validates Requirement 2.4: skip failing chunk, continue pipeline."""

    @pytest.mark.asyncio
    async def test_failing_chunk_does_not_stop_remaining_inserts(self):
        """When one chunk insert fails, the rest should still be inserted."""
        pool, conn = _make_pool()

        # Chunk at index 1 fails, others succeed
        conn.execute = AsyncMock(
            side_effect=[
                "INSERT 1",       # chunk 0 succeeds
                Exception("DB write error on chunk 1"),
                "INSERT 1",       # chunk 2 succeeds
            ]
        )

        chunks = ["Chunk A", "Chunk B", "Chunk C"]
        embeddings = [[0.1], [0.2], [0.3]]

        await insert_document_chunks(
            pool, chunks, embeddings,
            "file-err", "https://example.com/file-err", "Error Test", "text/plain",
        )

        # All 3 inserts attempted despite middle failure
        assert conn.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_first_chunk_failure_still_inserts_rest(self):
        """When the first chunk fails, subsequent chunks are still inserted."""
        pool, conn = _make_pool()

        conn.execute = AsyncMock(
            side_effect=[
                Exception("First chunk failed"),
                "INSERT 1",
                "INSERT 1",
            ]
        )

        chunks = ["A", "B", "C"]
        embeddings = [[0.1], [0.2], [0.3]]

        await insert_document_chunks(
            pool, chunks, embeddings,
            "file-first", "url", "Title", "text/plain",
        )

        assert conn.execute.call_count == 3

        # Verify chunks at index 1 and 2 were attempted with correct data
        second_call = conn.execute.call_args_list[1]
        assert second_call.args[1] == "B"
        third_call = conn.execute.call_args_list[2]
        assert third_call.args[1] == "C"

    @pytest.mark.asyncio
    async def test_all_chunks_fail_gracefully(self):
        """When every chunk insert fails, the function completes without raising."""
        pool, conn = _make_pool()

        conn.execute = AsyncMock(side_effect=Exception("All fail"))

        chunks = ["X", "Y"]
        embeddings = [[0.1], [0.2]]

        # Should not raise
        await insert_document_chunks(
            pool, chunks, embeddings,
            "file-all-fail", "url", "Title", "text/plain",
        )

        assert conn.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_error_is_logged_with_chunk_index(self, caplog):
        """Verify the error log includes the chunk index and file ID."""
        pool, conn = _make_pool()

        conn.execute = AsyncMock(
            side_effect=[
                "INSERT 1",
                Exception("Chunk 1 DB error"),
            ]
        )

        import logging
        with caplog.at_level(logging.ERROR, logger="common.db_handler"):
            await insert_document_chunks(
                pool, ["ok", "bad"], [[0.1], [0.2]],
                "file-log", "url", "Title", "text/plain",
            )

        # Check that the error log mentions chunk index and file ID
        assert any("chunk 1" in r.message.lower() or "1" in r.message for r in caplog.records)
        assert any("file-log" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Sequential processing in insert_document_chunks
# ---------------------------------------------------------------------------

class TestSequentialProcessing:
    """Validates Requirement 9.3: sequential (one-at-a-time) chunk insertion."""

    @pytest.mark.asyncio
    async def test_chunks_inserted_one_at_a_time(self):
        """conn.execute is called N times for N chunks (not batched)."""
        pool, conn = _make_pool()

        chunks = ["C1", "C2", "C3", "C4", "C5"]
        embeddings = [[0.1], [0.2], [0.3], [0.4], [0.5]]

        await insert_document_chunks(
            pool, chunks, embeddings,
            "file-seq", "url", "Title", "text/plain",
        )

        # Exactly one call per chunk
        assert conn.execute.call_count == len(chunks)

    @pytest.mark.asyncio
    async def test_chunks_inserted_in_order(self):
        """Chunks are inserted in the order they appear (index 0, 1, 2, ...)."""
        pool, conn = _make_pool()

        chunks = ["First", "Second", "Third"]
        embeddings = [[0.1], [0.2], [0.3]]

        await insert_document_chunks(
            pool, chunks, embeddings,
            "file-order", "url", "Title", "text/plain",
        )

        for i, call_obj in enumerate(conn.execute.call_args_list):
            # args[1] is the chunk content
            assert call_obj.args[1] == chunks[i]
            # Verify chunk_index in metadata
            metadata = json.loads(call_obj.args[2])
            assert metadata["chunk_index"] == i

    @pytest.mark.asyncio
    async def test_single_connection_used_for_all_chunks(self):
        """All chunks use the same connection (single acquire call)."""
        pool, conn = _make_pool()

        chunks = ["A", "B", "C"]
        embeddings = [[0.1], [0.2], [0.3]]

        await insert_document_chunks(
            pool, chunks, embeddings,
            "file-conn", "url", "Title", "text/plain",
        )

        # acquire() called exactly once — all inserts share one connection
        pool.acquire.assert_called_once()


# ---------------------------------------------------------------------------
# process_file_for_rag returns False on embedding error
# ---------------------------------------------------------------------------

class TestProcessFileForRagEmbeddingError:
    """Validates Requirement 2.4: embedding errors don't crash the pipeline."""

    @pytest.fixture
    def setup_mocks(self):
        """Patch text_processor helpers used by process_file_for_rag."""
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
    async def test_returns_false_when_create_embeddings_raises(self, setup_mocks):
        """When create_embeddings raises, process_file_for_rag returns False."""
        mocks = setup_mocks
        pool = AsyncMock()

        mocks["is_tabular"].return_value = False
        mocks["chunk_text"].return_value = ["Chunk 1", "Chunk 2"]
        mocks["create_embeddings"].side_effect = Exception("Vertex AI embedding API error")

        result = await process_file_for_rag(
            pool, b"content", "Some text", "file-emb-err",
            "https://example.com/file", "Test File", "text/plain",
            config={"text_processing": {"default_chunk_size": 400, "default_chunk_overlap": 0}},
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_embedding_error_does_not_prevent_metadata_insert(self, setup_mocks):
        """Metadata is inserted before embeddings, so it persists even on error."""
        mocks = setup_mocks
        pool = AsyncMock()

        mocks["is_tabular"].return_value = False
        mocks["chunk_text"].return_value = ["Chunk 1"]
        mocks["create_embeddings"].side_effect = Exception("Embedding failure")

        await process_file_for_rag(
            pool, b"content", "text", "file-meta",
            "url", "Title", "text/plain",
        )

        # Metadata was inserted before the embedding step failed
        mocks["insert_metadata"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_embedding_error_prevents_chunk_insertion(self, setup_mocks):
        """When embeddings fail, insert_document_chunks is never called."""
        mocks = setup_mocks
        pool = AsyncMock()

        mocks["is_tabular"].return_value = False
        mocks["chunk_text"].return_value = ["Chunk 1"]
        mocks["create_embeddings"].side_effect = Exception("API down")

        await process_file_for_rag(
            pool, b"content", "text", "file-no-chunks",
            "url", "Title", "text/plain",
        )

        mocks["insert_chunks"].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_embedding_error_is_logged(self, setup_mocks, caplog):
        """The embedding error is logged with file context."""
        mocks = setup_mocks
        pool = AsyncMock()

        mocks["is_tabular"].return_value = False
        mocks["chunk_text"].return_value = ["Chunk 1"]
        mocks["create_embeddings"].side_effect = Exception("Vertex AI 503")

        import logging
        with caplog.at_level(logging.ERROR, logger="common.db_handler"):
            await process_file_for_rag(
                pool, b"content", "text", "file-log-emb",
                "url", "Log Test", "text/plain",
            )

        assert any("file-log-emb" in r.message or "Log Test" in r.message for r in caplog.records)
