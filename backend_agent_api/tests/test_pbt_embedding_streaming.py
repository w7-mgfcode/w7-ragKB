"""Property-based tests for embedding batching and large file streaming (Tasks 24.4, 24.6).

Properties tested:
- P27: Embedding batch generation — batch size respected, all texts embedded
- P28: Large file streaming — files > threshold use streaming mode
"""

import asyncio
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis.strategies import integers

from sync_manager import SyncManager


# ==========================================================================
# P27: Batch embedding — all texts get embeddings
# ==========================================================================


@given(
    text_count=integers(min_value=1, max_value=25),
    batch_size=integers(min_value=1, max_value=10),
)
@settings(max_examples=30)
def test_batch_embedding_processes_all_texts(text_count, batch_size):
    """_get_embeddings_batch must return exactly one embedding per input."""
    pool = AsyncMock()
    sm = SyncManager(pool, "/tmp/test")
    sm._embedding_batch_size = batch_size
    sm._embedding_max_retries = 1

    mock_client = AsyncMock()
    mock_client.create_embeddings = lambda texts, task: [[0.1] * 768] * len(texts)
    sm._embedding_client = mock_client

    texts = [f"text_{i}" for i in range(text_count)]
    result = asyncio.run(sm._get_embeddings_batch(texts))

    assert len(result) == text_count
    for emb in result:
        assert len(emb) == 768


# ==========================================================================
# P27: Batch size respected
# ==========================================================================


@given(batch_size=integers(min_value=1, max_value=5))
@settings(max_examples=15)
def test_batch_embedding_respects_batch_size(batch_size):
    """Embedding API calls must not exceed batch_size."""
    pool = AsyncMock()
    sm = SyncManager(pool, "/tmp/test")
    sm._embedding_batch_size = batch_size
    sm._embedding_max_retries = 1

    call_sizes = []

    def track(texts, task):
        call_sizes.append(len(texts))
        return [[0.1] * 768] * len(texts)

    mock_client = AsyncMock()
    mock_client.create_embeddings = track
    sm._embedding_client = mock_client

    total = batch_size * 3 + 1
    asyncio.run(sm._get_embeddings_batch([f"t{i}" for i in range(total)]))

    for size in call_sizes:
        assert size <= batch_size


# ==========================================================================
# P27: Batch retry
# ==========================================================================


@given(fail_batch=integers(min_value=0, max_value=2))
@settings(max_examples=10, deadline=None)
def test_batch_embedding_retries_on_failure(fail_batch):
    """Transient failures in a batch must be retried."""
    pool = AsyncMock()
    sm = SyncManager(pool, "/tmp/test")
    sm._embedding_batch_size = 3
    sm._embedding_max_retries = 3

    calls = []

    def flaky(texts, task):
        calls.append(1)
        if len(calls) <= fail_batch:
            raise ConnectionError("transient")
        return [[0.1] * 768] * len(texts)

    mock_client = AsyncMock()
    mock_client.create_embeddings = flaky
    sm._embedding_client = mock_client

    result = asyncio.run(sm._get_embeddings_batch(["a", "b", "c"]))
    assert len(result) == 3


# ==========================================================================
# P28: Large file → streaming mode
# ==========================================================================


@given(size_mb=integers(min_value=11, max_value=30))
@settings(max_examples=10)
def test_large_file_uses_streaming_mode(size_mb):
    """Files above LARGE_FILE_THRESHOLD must use _process_large_file."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        pool.fetchval = AsyncMock(return_value=1)
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "large.md"
        doc.write_text("x" * (size_mb * 1024 * 1024))

        called = False

        async def mock_large(fp, ap):
            nonlocal called
            called = True
            return 10

        with patch.object(sm, "_process_large_file", side_effect=mock_large):
            result = asyncio.run(sm._chunk_and_insert("large.md", "x", doc))

        assert called
        assert result == 10
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P28: Small file → hierarchical mode
# ==========================================================================


@given(size_kb=integers(min_value=1, max_value=100))
@settings(max_examples=15)
def test_small_file_uses_hierarchical_mode(size_kb):
    """Files below threshold must use hierarchical chunking."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "small.md"
        content = "# Title\n" + ("word " * size_kb * 50)
        doc.write_text(content)

        with patch.object(sm, "_process_large_file") as mock_large, \
             patch("hierarchical_chunking.chunk_document_hierarchical", return_value=[]), \
             patch.object(sm, "_insert_chunks_with_embeddings", new_callable=AsyncMock):
            asyncio.run(sm._chunk_and_insert("small.md", content, doc))

        mock_large.assert_not_called()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==========================================================================
# P28: Streaming chunk coverage
# ==========================================================================


@given(content_size=integers(min_value=2001, max_value=10000))
@settings(max_examples=15)
def test_large_file_streaming_covers_all_content(content_size):
    """Streaming mode must produce chunks covering the entire content."""
    tmp = Path(tempfile.mkdtemp())
    try:
        pool = AsyncMock()
        pool.execute = AsyncMock()
        pool.fetchval = AsyncMock(return_value=1)
        sm = SyncManager(pool, str(tmp))

        doc = tmp / "stream.md"
        doc.write_text("a" * content_size)

        mock_client = AsyncMock()
        mock_client.create_embeddings = lambda texts, task: [[0.1] * 768] * len(texts)
        sm._embedding_client = mock_client

        chunk_count = asyncio.run(sm._process_large_file("stream.md", doc))

        assert chunk_count >= 1
        assert chunk_count >= content_size // 2000
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
