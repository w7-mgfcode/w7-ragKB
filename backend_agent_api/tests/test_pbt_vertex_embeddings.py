"""Property-based test: Embedding dimension invariant.

**Validates: Requirements 2.3**

Property 2: For any list of non-empty text strings passed to
``VertexEmbeddingClient.create_embeddings()``, every returned embedding
vector SHALL have a length exactly equal to the configured
``EMBEDDING_DIMENSIONS`` value (768 by default).

The Vertex AI API is mocked so that ``embed_content`` returns one vector
of length ``EMBEDDING_DIMENSIONS`` per input text — mirroring the real
API contract.  The property then asserts that the client faithfully
surfaces those vectors with the correct dimension.
"""

import os
from types import SimpleNamespace
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from vertex_embeddings import EMBEDDING_DIMENSIONS, VertexEmbeddingClient

# ---------------------------------------------------------------------------
# Strategy: lists of non-empty strings (1–10 items, 1–50 chars each)
# ---------------------------------------------------------------------------

non_empty_texts = st.lists(
    st.text(min_size=1, max_size=50),
    min_size=1,
    max_size=10,
)


# ---------------------------------------------------------------------------
# Helpers (same pattern as the existing unit-test helpers)
# ---------------------------------------------------------------------------

def _make_embedding(values: list[float]) -> SimpleNamespace:
    return SimpleNamespace(values=values)


def _make_embed_response(embeddings: list[list[float]]) -> SimpleNamespace:
    return SimpleNamespace(
        embeddings=[_make_embedding(v) for v in embeddings],
    )


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

class TestEmbeddingDimensionProperty:
    """Property 2: Embedding dimension invariant.

    **Validates: Requirements 2.3**
    """

    @given(texts=non_empty_texts)
    @settings(max_examples=100, deadline=None)
    def test_all_vectors_have_correct_dimension(self, texts: list[str]):
        """For any list of non-empty strings, every returned embedding
        vector has length == EMBEDDING_DIMENSIONS."""

        # Build a mock response: one vector of the configured dimension
        # per input text, filled with 0.0 — simulating the real API.
        fake_vectors = [[0.0] * EMBEDDING_DIMENSIONS for _ in texts]

        with patch("vertex_embeddings.genai.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.models.embed_content.return_value = (
                _make_embed_response(fake_vectors)
            )

            with patch.dict(os.environ, {
                "GOOGLE_CLOUD_PROJECT": "test-project",
                "GOOGLE_CLOUD_REGION": "us-central1",
            }):
                client = VertexEmbeddingClient()
                result = client.create_embeddings(texts)

        # One embedding per input text
        assert len(result) == len(texts)

        # Every vector must have exactly EMBEDDING_DIMENSIONS elements
        for vec in result:
            assert len(vec) == EMBEDDING_DIMENSIONS
