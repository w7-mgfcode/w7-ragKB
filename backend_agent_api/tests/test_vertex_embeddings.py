"""Tests for vertex_embeddings module."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vertex_embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, VertexEmbeddingClient


def _make_embedding(values: list[float]) -> SimpleNamespace:
    """Create a fake ContentEmbedding-like object."""
    return SimpleNamespace(values=values)


def _make_embed_response(embeddings: list[list[float]]) -> SimpleNamespace:
    """Create a fake EmbedContentResponse-like object."""
    return SimpleNamespace(
        embeddings=[_make_embedding(v) for v in embeddings]
    )


class TestModuleConstants:
    """Tests for module-level configuration constants."""

    def test_default_embedding_model(self):
        assert EMBEDDING_MODEL == os.getenv(
            "EMBEDDING_MODEL_CHOICE", "gemini-embedding-001"
        )

    def test_default_embedding_dimensions(self):
        assert EMBEDDING_DIMENSIONS == int(
            os.getenv("EMBEDDING_DIMENSIONS", "768")
        )


class TestCreateEmbeddings:
    """Tests for VertexEmbeddingClient.create_embeddings()."""

    @patch("vertex_embeddings.genai.Client")
    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_REGION": "us-central1",
    })
    def test_returns_empty_list_for_empty_input(self, mock_client_cls):
        client = VertexEmbeddingClient()
        result = client.create_embeddings([])
        assert result == []
        # Should not call the API at all
        mock_client_cls.return_value.models.embed_content.assert_not_called()

    @patch("vertex_embeddings.genai.Client")
    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_REGION": "us-central1",
    })
    def test_returns_embedding_vectors(self, mock_client_cls):
        fake_vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_client = mock_client_cls.return_value
        mock_client.models.embed_content.return_value = _make_embed_response(
            fake_vectors
        )

        client = VertexEmbeddingClient()
        result = client.create_embeddings(["hello", "world"])

        assert result == fake_vectors

    @patch("vertex_embeddings.genai.Client")
    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_REGION": "us-central1",
    })
    def test_passes_correct_config(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.models.embed_content.return_value = _make_embed_response(
            [[0.1]]
        )

        client = VertexEmbeddingClient()
        client.create_embeddings(["test"], task_type="RETRIEVAL_QUERY")

        mock_client.models.embed_content.assert_called_once_with(
            model=EMBEDDING_MODEL,
            contents=["test"],
            config={
                "output_dimensionality": EMBEDDING_DIMENSIONS,
                "task_type": "RETRIEVAL_QUERY",
            },
        )

    @patch("vertex_embeddings.genai.Client")
    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_REGION": "us-central1",
    })
    def test_default_task_type_is_retrieval_document(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.models.embed_content.return_value = _make_embed_response(
            [[0.1]]
        )

        client = VertexEmbeddingClient()
        client.create_embeddings(["test"])

        call_kwargs = mock_client.models.embed_content.call_args
        assert call_kwargs.kwargs["config"]["task_type"] == "RETRIEVAL_DOCUMENT"


class TestCreateQueryEmbedding:
    """Tests for VertexEmbeddingClient.create_query_embedding()."""

    @patch("vertex_embeddings.genai.Client")
    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_REGION": "us-central1",
    })
    @pytest.mark.asyncio
    async def test_returns_single_embedding_vector(self, mock_client_cls):
        fake_vector = [0.1, 0.2, 0.3]
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.embed_content = AsyncMock(
            return_value=_make_embed_response([fake_vector])
        )

        client = VertexEmbeddingClient()
        result = await client.create_query_embedding("search query")

        assert result == fake_vector

    @patch("vertex_embeddings.genai.Client")
    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_REGION": "us-central1",
    })
    @pytest.mark.asyncio
    async def test_uses_retrieval_query_task_type(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.embed_content = AsyncMock(
            return_value=_make_embed_response([[0.1]])
        )

        client = VertexEmbeddingClient()
        await client.create_query_embedding("test")

        call_kwargs = mock_client.aio.models.embed_content.call_args
        assert call_kwargs.kwargs["config"]["task_type"] == "RETRIEVAL_QUERY"

    @patch("vertex_embeddings.genai.Client")
    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_REGION": "us-central1",
    })
    @pytest.mark.asyncio
    async def test_returns_zero_vector_when_no_embeddings(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.embed_content = AsyncMock(
            return_value=SimpleNamespace(embeddings=[])
        )

        client = VertexEmbeddingClient()
        result = await client.create_query_embedding("test")

        assert result == [0.0] * EMBEDDING_DIMENSIONS
        assert len(result) == EMBEDDING_DIMENSIONS


class TestClientInitialization:
    """Tests for VertexEmbeddingClient constructor."""

    @patch("vertex_embeddings.genai.Client")
    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "my-project-id",
        "GOOGLE_CLOUD_REGION": "europe-west1",
    })
    def test_passes_project_and_region_to_client(self, mock_client_cls):
        VertexEmbeddingClient()

        mock_client_cls.assert_called_once_with(
            vertexai=True,
            project="my-project-id",
            location="europe-west1",
        )

    @patch("vertex_embeddings.genai.Client")
    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "my-project-id",
    }, clear=False)
    def test_defaults_region_to_us_central1(self, mock_client_cls):
        env = os.environ.copy()
        env.pop("GOOGLE_CLOUD_REGION", None)
        env["GOOGLE_CLOUD_PROJECT"] = "my-project-id"
        with patch.dict(os.environ, env, clear=True):
            VertexEmbeddingClient()

            mock_client_cls.assert_called_once_with(
                vertexai=True,
                project="my-project-id",
                location="us-central1",
            )
