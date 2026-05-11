"""Vertex AI embedding client using google-genai SDK.

Generates text embeddings via gemini-embedding-001 for both
document indexing (RETRIEVAL_DOCUMENT) and query-time search
(RETRIEVAL_QUERY).
"""

import os
from typing import List

from google import genai

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL_CHOICE", "gemini-embedding-001")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))


class VertexEmbeddingClient:
    """Generates text embeddings via Vertex AI."""

    def __init__(self) -> None:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        self._client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )

    def create_embeddings(
        self, texts: List[str], task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> List[List[float]]:
        """Generate embeddings for a batch of texts.

        Args:
            texts: List of text strings to embed.
            task_type: One of RETRIEVAL_DOCUMENT, RETRIEVAL_QUERY,
                       SEMANTIC_SIMILARITY, CLASSIFICATION, CLUSTERING.

        Returns:
            List of embedding vectors, one per input text.
        """
        if not texts:
            return []

        result = self._client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=texts,
            config={
                "output_dimensionality": EMBEDDING_DIMENSIONS,
                "task_type": task_type,
            },
        )
        return [e.values for e in result.embeddings]

    async def create_query_embedding(self, text: str) -> List[float]:
        """Generate a single query embedding using RETRIEVAL_QUERY task type.

        Uses the async API for non-blocking operation in the agent service.
        """
        result = await self._client.aio.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[text],
            config={
                "output_dimensionality": EMBEDDING_DIMENSIONS,
                "task_type": "RETRIEVAL_QUERY",
            },
        )
        if result.embeddings:
            return result.embeddings[0].values
        return [0.0] * EMBEDDING_DIMENSIONS
