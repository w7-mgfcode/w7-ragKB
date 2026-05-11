"""Unit tests for refactored agent tools.

Tests cover:
- retrieve_relevant_documents_tool with mocked embedding client and asyncpg
- image_analysis_tool uses Gemini vision model
- Error handling for Vertex AI failures
- Validates: Requirements 10.1, 10.2, 10.3, 1.3
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os

# Add parent directory to path so we can import the modules under test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# get_embedding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_embedding_returns_vector_on_success():
    """get_embedding delegates to the embedding client and returns the vector."""
    from tools import get_embedding

    expected = [0.1] * 768
    mock_client = AsyncMock()
    mock_client.create_query_embedding.return_value = expected

    result = await get_embedding("hello world", mock_client)

    mock_client.create_query_embedding.assert_awaited_once_with("hello world")
    assert result == expected


@pytest.mark.asyncio
async def test_get_embedding_returns_zero_vector_on_error():
    """When the embedding client raises, get_embedding returns a zero vector
    of EMBEDDING_DIMENSIONS length (Requirement 1.3 — graceful fallback)."""
    from tools import get_embedding

    mock_client = AsyncMock()
    mock_client.create_query_embedding.side_effect = RuntimeError("Vertex AI unavailable")

    # get_embedding does a lazy `from vertex_embeddings import EMBEDDING_DIMENSIONS`
    # inside the except block, so we patch the module-level constant there.
    with patch("vertex_embeddings.EMBEDDING_DIMENSIONS", 768):
        result = await get_embedding("test query", mock_client)

    assert len(result) == 768
    assert all(v == 0.0 for v in result)


# ---------------------------------------------------------------------------
# retrieve_relevant_documents_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_documents_formats_results():
    """retrieve_relevant_documents_tool calls get_embedding, then match_documents,
    and formats the returned chunks correctly (Requirements 10.2, 10.4)."""
    from tools import retrieve_relevant_documents_tool

    fake_embedding = [0.5] * 768
    mock_client = AsyncMock()

    mock_pool = AsyncMock()

    fake_docs = [
        {
            "content": "chunk one text",
            "metadata": {
                "file_id": "doc-1",
                "file_title": "My Doc",
                "file_url": "https://example.com/doc1",
            },
            "similarity": 0.95,
        },
        {
            "content": "chunk two text",
            "metadata": json.dumps({
                "file_id": "doc-2",
                "file_title": "Other Doc",
                "file_url": "https://example.com/doc2",
            }),
            "similarity": 0.88,
        },
    ]

    with patch("tools.get_embedding", new_callable=AsyncMock, return_value=fake_embedding) as mock_embed, \
         patch("tools.db_documents") as mock_db_docs:
        mock_db_docs.match_documents = AsyncMock(return_value=fake_docs)

        result = await retrieve_relevant_documents_tool(mock_pool, mock_client, "search query")

    mock_embed.assert_awaited_once_with("search query", mock_client)
    mock_db_docs.match_documents.assert_awaited_once_with(mock_pool, fake_embedding, match_count=4)

    # Verify formatting
    assert "# Document ID: doc-1" in result
    assert "# Document Title: My Doc" in result
    assert "chunk one text" in result
    assert "---" in result  # separator between chunks
    # Second doc had JSON-string metadata — should still parse
    assert "# Document ID: doc-2" in result
    assert "chunk two text" in result


@pytest.mark.asyncio
async def test_retrieve_documents_empty_results():
    """When no documents match, returns 'No relevant documents found.'"""
    from tools import retrieve_relevant_documents_tool

    mock_client = AsyncMock()
    mock_pool = AsyncMock()

    with patch("tools.get_embedding", new_callable=AsyncMock, return_value=[0.0] * 768), \
         patch("tools.db_documents") as mock_db_docs:
        mock_db_docs.match_documents = AsyncMock(return_value=[])

        result = await retrieve_relevant_documents_tool(mock_pool, mock_client, "nothing here")

    assert result == "No relevant documents found."


@pytest.mark.asyncio
async def test_retrieve_documents_db_error():
    """When the database raises an exception, returns a user-friendly error
    string instead of propagating (Requirement 1.3)."""
    from tools import retrieve_relevant_documents_tool

    mock_client = AsyncMock()
    mock_pool = AsyncMock()

    with patch("tools.get_embedding", new_callable=AsyncMock, return_value=[0.0] * 768), \
         patch("tools.db_documents") as mock_db_docs:
        mock_db_docs.match_documents = AsyncMock(
            side_effect=Exception("connection lost")
        )

        result = await retrieve_relevant_documents_tool(mock_pool, mock_client, "query")

    assert "Error retrieving documents" in result
    assert "connection lost" in result


# ---------------------------------------------------------------------------
# image_analysis_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_analysis_missing_document():
    """When the document doesn't exist in the DB, returns an appropriate message."""
    from tools import image_analysis_tool

    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value=None)

    result = await image_analysis_tool(mock_pool, "nonexistent-id", "describe this")

    assert "No content found for document: nonexistent-id" in result


@pytest.mark.asyncio
async def test_image_analysis_missing_file_contents():
    """When metadata exists but file_contents is missing, returns an error."""
    from tools import image_analysis_tool

    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value={
        "metadata": {"file_id": "img-1", "mime_type": "image/png"},
    })

    result = await image_analysis_tool(mock_pool, "img-1", "describe this")

    assert "No file contents found for document: img-1" in result


@pytest.mark.asyncio
async def test_image_analysis_uses_gemini_vision_model():
    """image_analysis_tool uses get_model() (Vertex AI Gemini) to create a
    vision sub-agent (Requirement 10.3)."""
    from tools import image_analysis_tool
    import base64

    image_bytes = b"fake-image-data"
    encoded = base64.b64encode(image_bytes).decode("utf-8")

    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value={
        "metadata": {
            "file_id": "img-1",
            "file_contents": encoded,
            "mime_type": "image/png",
        },
    })

    mock_model = MagicMock()
    mock_agent_result = MagicMock()
    mock_agent_result.data = "This image shows a cat."

    with patch("tools.get_model", return_value=mock_model) as mock_get_model, \
         patch("tools.Agent") as MockAgent:
        mock_agent_instance = AsyncMock()
        mock_agent_instance.run = AsyncMock(return_value=mock_agent_result)
        MockAgent.return_value = mock_agent_instance

        result = await image_analysis_tool(mock_pool, "img-1", "what is in this image?")

    # Verify get_model() was called (Vertex AI Gemini)
    mock_get_model.assert_called_once()

    # Verify Agent was created with the Gemini model
    MockAgent.assert_called_once()
    call_args = MockAgent.call_args
    assert call_args[0][0] is mock_model  # first positional arg is the model
    assert "image analyzer" in call_args[1]["system_prompt"].lower()

    # Verify the agent was run with the query and binary content
    mock_agent_instance.run.assert_awaited_once()

    assert result == "This image shows a cat."


@pytest.mark.asyncio
async def test_image_analysis_error_handling():
    """When image analysis raises an exception, returns a user-friendly error
    (Requirement 1.3)."""
    from tools import image_analysis_tool

    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(side_effect=Exception("DB timeout"))

    result = await image_analysis_tool(mock_pool, "img-1", "describe")

    assert "Error analyzing image" in result
    assert "DB timeout" in result
