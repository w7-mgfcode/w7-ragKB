"""Text processing utilities for the RAG pipeline.

Handles text chunking, PDF extraction, CSV parsing, and embedding
generation via Vertex AI (gemini-embedding-001).
"""

import os
import io
import csv
import logging
import tempfile
from typing import List, Dict, Any

import pypdf
from google import genai

logger = logging.getLogger(__name__)

# Vertex AI embedding configuration
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL_CHOICE", "gemini-embedding-001")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))

# Lazy-initialized Vertex AI embedding client
_embedding_client = None


def _get_embedding_client() -> genai.Client:
    """Return a lazily-initialized Vertex AI genai client."""
    global _embedding_client
    if _embedding_client is None:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        _embedding_client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )
    return _embedding_client


def chunk_text(text: str, chunk_size: int = 400, overlap: int = 0) -> List[str]:
    """Split text into chunks of specified size with optional overlap."""
    if not text:
        return []

    text = text.replace('\r', '')

    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i:i + chunk_size]
        if chunk:
            chunks.append(chunk)

    return chunks


def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from a PDF file."""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
        temp_file.write(file_content)
        temp_file_path = temp_file.name

    try:
        with open(temp_file_path, 'rb') as file:
            pdf_reader = pypdf.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
        return text
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def extract_text_from_file(
    file_content: bytes, mime_type: str, file_name: str, config: Dict[str, Any] = None
) -> str:
    """Extract text from a file based on its MIME type."""
    supported_mime_types = []
    if config and 'supported_mime_types' in config:
        supported_mime_types = config['supported_mime_types']

    if 'application/pdf' in mime_type:
        return extract_text_from_pdf(file_content)
    elif mime_type.startswith('image'):
        return file_name
    elif config and any(mime_type.startswith(t) for t in supported_mime_types):
        return file_content.decode('utf-8', errors='replace')
    else:
        return file_content.decode('utf-8', errors='replace')


def create_embeddings(texts: List[str]) -> List[List[float]]:
    """Create embeddings for a list of text chunks using Vertex AI.

    Uses task_type="RETRIEVAL_DOCUMENT" for document chunk embeddings.

    Args:
        texts: List of text chunks to embed.

    Returns:
        List of embedding vectors.
    """
    if not texts:
        return []

    client = _get_embedding_client()
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config={
            "output_dimensionality": EMBEDDING_DIMENSIONS,
            "task_type": "RETRIEVAL_DOCUMENT",
        },
    )
    return [e.values for e in result.embeddings]


def is_tabular_file(mime_type: str, config: Dict[str, Any] = None) -> bool:
    """Check if a file is tabular based on its MIME type."""
    tabular_mime_types = [
        'csv',
        'xlsx',
        'text/csv',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.google-apps.spreadsheet'
    ]

    if config and 'tabular_mime_types' in config:
        tabular_mime_types = config['tabular_mime_types']

    return any(mime_type.startswith(t) for t in tabular_mime_types)


def extract_schema_from_csv(file_content: bytes) -> List[str]:
    """Extract column names from a CSV file."""
    try:
        text_content = file_content.decode('utf-8', errors='replace')
        csv_reader = csv.reader(io.StringIO(text_content))
        header = next(csv_reader)
        return header
    except Exception as e:
        print(f"Error extracting schema from CSV: {e}")
        return []


def extract_rows_from_csv(file_content: bytes) -> List[Dict[str, Any]]:
    """Extract rows from a CSV file as a list of dictionaries."""
    try:
        text_content = file_content.decode('utf-8', errors='replace')
        csv_reader = csv.DictReader(io.StringIO(text_content))
        return list(csv_reader)
    except Exception as e:
        print(f"Error extracting rows from CSV: {e}")
        return []
