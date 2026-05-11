"""Agent tool implementations.

Database tools use asyncpg pools and Vertex AI embeddings.
Web search and code execution tools are unchanged.
"""

from RestrictedPython import compile_restricted
from RestrictedPython.Guards import safe_globals, safe_builtins, guarded_unpack_sequence
from pydantic_ai import Agent, BinaryContent
from typing import Dict, Any, List, Optional
from httpx import AsyncClient
import asyncpg
import base64
import json
import logging
import sys
import os
import re

from vertex_embeddings import VertexEmbeddingClient
from vertex_provider import get_model
import db_documents

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Web search tools (unchanged)
# ---------------------------------------------------------------------------

async def brave_web_search(query: str, http_client: AsyncClient, brave_api_key: str) -> str:
    """
    Helper function for web_search_tool - searches the web with the Brave API
    and returns a summary of all the top search results.

    Args are the same as the parent function except without the SearXNG base url.
    """
    headers = {
        'X-Subscription-Token': brave_api_key,
        'Accept': 'application/json',
    }

    response = await http_client.get(
        'https://api.search.brave.com/res/v1/web/search',
        params={
            'q': query,
            'count': 5,
            'text_decorations': True,
            'search_lang': 'en'
        },
        headers=headers
    )
    response.raise_for_status()
    data = response.json()

    results = []

    # Add web results in a nice formatted way
    web_results = data.get('web', {}).get('results', [])
    for item in web_results[:3]:
        title = item.get('title', '')
        description = item.get('description', '')
        url = item.get('url', '')
        if title and description:
            results.append(f"Title: {title}\nSummary: {description}\nSource: {url}\n")

    return "\n".join(results) if results else "No results found for the query."

async def searxng_web_search(query: str, http_client: AsyncClient, searxng_base_url: str) -> str:
    """
    Helper function for web_search_tool - searches the web with SearXNG
    and returns a list of the top search results with the most relevant snippet from each page.

    Args are the same as the parent function except without the Brave API key.
    """
    # Prepare the parameters for the request
    params = {'q': query, 'format': 'json'}

    # Make the request to SearXNG
    response = await http_client.get(f"{searxng_base_url}/search", params=params)
    response.raise_for_status()  # Raise an exception for HTTP errors

    # Parse the results
    data = response.json()

    results = ""
    for i, page in enumerate(data.get('results', []), 1):
        if i > 10:  # Limiting to the top 10 results
            break

        results += f"{i}. {page.get('title', 'No title')}"
        results += f"   URL: {page.get('url', 'No URL')}"
        results += f"   Content: {page.get('content', 'No content')[:300]}...\n\n"

    return results if results else "No results found for the query."

async def web_search_tool(query: str, http_client: AsyncClient, brave_api_key: str, searxng_base_url: str) -> str:
    """
    Search the web with a specific query and get a summary of the top search results.

    Args:
        query: The query for the web search
        http_client: The client for making HTTP requests to Brave or SearXNG
        brave_api_key: The optional key for Brave (will use SearXNG if this isn't defined)
        searxng_base_url: The optional base URL for SearXNG (will use Brave if this isn't defined)

    Returns:
        A summary of the web search.
        For Brave, this is a single paragraph.
        For SearXNG, this is a list of the top search results including the most relevant snippet from the page.
    """
    try:
        if brave_api_key:
            return await brave_web_search(query, http_client, brave_api_key)
        else:
            return await searxng_web_search(query, http_client, searxng_base_url)
    except Exception as e:
        logger.error("Exception during websearch: %s", e)
        return str(e)


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------

async def get_embedding(text: str, embedding_client: VertexEmbeddingClient) -> List[float]:
    """Get embedding vector using Vertex AI.

    Args:
        text: The text to embed.
        embedding_client: VertexEmbeddingClient instance.

    Returns:
        Embedding vector as a list of floats.
    """
    try:
        return await embedding_client.create_query_embedding(text)
    except Exception as e:
        logger.error("Error getting embedding: %s", e)
        from vertex_embeddings import EMBEDDING_DIMENSIONS
        return [0.0] * EMBEDDING_DIMENSIONS


# ---------------------------------------------------------------------------
# RAG / document tools (refactored to asyncpg + Vertex AI)
# ---------------------------------------------------------------------------

async def retrieve_relevant_documents_tool(
    pool: asyncpg.Pool,
    embedding_client: VertexEmbeddingClient,
    user_query: str,
) -> str:
    """
    Retrieve relevant document chunks with RAG using Vertex AI embeddings
    and asyncpg vector search.

    Returns:
        Formatted string of the top relevant document chunks.
    """
    try:
        query_embedding = await get_embedding(user_query, embedding_client)

        results = await db_documents.match_documents(
            pool, query_embedding, match_count=4
        )

        if not results:
            return "No relevant documents found."

        formatted_chunks = []
        for doc in results:
            metadata = doc.get("metadata", {})
            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            chunk_text = (
                f"# Document ID: {metadata.get('file_id', 'unknown')}\n"
                f"# Document Title: {metadata.get('file_title', 'unknown')}\n"
                f"# Document URL: {metadata.get('file_url', 'unknown')}\n\n"
                f"{doc.get('content', '')}"
            )
            formatted_chunks.append(chunk_text)

        return "\n\n---\n\n".join(formatted_chunks)

    except Exception as e:
        logger.error("Error retrieving documents: %s", e)
        return f"Error retrieving documents: {str(e)}"


def _query_needs_expanded_context(user_query: str) -> bool:
    q = user_query.lower()
    hints = (
        "how to",
        "setup",
        "setting up",
        "configure",
        "configuration",
        "jenkins",
        "pipeline",
        "example",
        "sample",
        "code",
    )
    return any(h in q for h in hints)


def _extract_relevant_excerpt(full_text: str, user_query: str, max_chars: int = 5000) -> str:
    """Extract a focused excerpt around a matching heading or keyword."""
    if not full_text:
        return ""

    lines = full_text.splitlines()
    q_terms = [t for t in re.findall(r"[a-zA-Z0-9_-]+", user_query.lower()) if len(t) > 3]

    # Prefer heading match first.
    for i, line in enumerate(lines):
        lower = line.lower()
        if line.strip().startswith("#") and any(term in lower for term in q_terms):
            start = i
            end = min(len(lines), i + 140)
            excerpt = "\n".join(lines[start:end]).strip()
            return excerpt[:max_chars]

    # Fallback: first keyword hit window.
    for i, line in enumerate(lines):
        lower = line.lower()
        if any(term in lower for term in q_terms):
            start = max(0, i - 20)
            end = min(len(lines), i + 120)
            excerpt = "\n".join(lines[start:end]).strip()
            return excerpt[:max_chars]

    # Last resort: head of doc.
    return full_text[:max_chars]


async def retrieve_grounded_context_tool(
    pool: asyncpg.Pool,
    embedding_client: VertexEmbeddingClient,
    user_query: str,
) -> str:
    """Retrieve RAG context with optional expanded document excerpts for code/setup questions."""
    try:
        query_embedding = await get_embedding(user_query, embedding_client)
        results = await db_documents.match_documents(pool, query_embedding, match_count=4)
        if not results:
            return "No relevant documents found."

        formatted_chunks: List[str] = []
        unique_doc_ids: List[str] = []

        for doc in results:
            metadata = doc.get("metadata", {})
            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            file_id = metadata.get("file_id", "unknown")
            if file_id not in unique_doc_ids:
                unique_doc_ids.append(file_id)

            chunk_text = (
                f"# Document ID: {file_id}\n"
                f"# Document Title: {metadata.get('file_title', 'unknown')}\n"
                f"# Document URL: {metadata.get('file_url', 'unknown')}\n\n"
                f"{doc.get('content', '')}"
            )
            formatted_chunks.append(chunk_text)

        base_context = "\n\n---\n\n".join(formatted_chunks)
        if not _query_needs_expanded_context(user_query):
            return base_context

        expanded_sections: List[str] = []
        for doc_id in unique_doc_ids[:2]:
            full_doc = await db_documents.get_document_content(pool, doc_id)
            if not full_doc or full_doc.startswith("No content found for document:"):
                continue
            excerpt = _extract_relevant_excerpt(full_doc, user_query, max_chars=5000)
            if excerpt:
                expanded_sections.append(
                    f"# Expanded Context From: {doc_id}\n\n{excerpt}"
                )

        if expanded_sections:
            return f"{base_context}\n\n===\n\n" + "\n\n===\n\n".join(expanded_sections)
        return base_context
    except Exception as e:
        logger.error("Error retrieving grounded context: %s", e)
        return f"Error retrieving documents: {str(e)}"


async def list_documents_tool(pool: asyncpg.Pool) -> str:
    """
    Retrieve a list of all available documents using asyncpg.

    Returns:
        String representation of document metadata list.
    """
    try:
        results = await db_documents.list_documents(pool)
        return str(results)
    except Exception as e:
        logger.error("Error retrieving documents: %s", e)
        return str([])


async def get_document_content_tool(pool: asyncpg.Pool, document_id: str) -> str:
    """
    Retrieve the full content of a specific document by combining all its chunks.

    Returns:
        The complete content of the document with all chunks combined in order.
    """
    try:
        return await db_documents.get_document_content(pool, document_id)
    except Exception as e:
        logger.error("Error retrieving document content: %s", e)
        return f"Error retrieving document content: {str(e)}"


async def execute_sql_query_tool(pool: asyncpg.Pool, sql_query: str) -> str:
    """
    Run a read-only SQL query against the database using asyncpg.

    Args:
        pool: asyncpg connection pool.
        sql_query: The SQL query to execute (must be read-only).

    Returns:
        The results of the SQL query in JSON format.
    """
    try:
        return await db_documents.execute_custom_sql(pool, sql_query)
    except Exception as e:
        logger.error("Error executing SQL query: %s", e)
        return f"Error executing SQL query: {str(e)}"


# ---------------------------------------------------------------------------
# Image analysis (refactored to Vertex AI Gemini vision)
# ---------------------------------------------------------------------------

async def image_analysis_tool(pool: asyncpg.Pool, document_id: str, query: str) -> str:
    """
    Analyze an image using Vertex AI Gemini vision model.

    Fetches the image binary from the database via asyncpg, then sends it
    to a Pydantic AI sub-agent backed by the Gemini model for analysis.

    Args:
        pool: asyncpg connection pool.
        document_id: The file_id of the image document.
        query: What to extract from the image.

    Returns:
        Analysis result string.
    """
    try:
        # Fetch image metadata from the database
        row = await pool.fetchrow(
            """
            SELECT metadata
            FROM documents
            WHERE metadata->>'file_id' = $1
            LIMIT 1
            """,
            document_id,
        )

        if not row:
            return f"No content found for document: {document_id}"

        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        binary_str = metadata.get("file_contents")
        mime_type = metadata.get("mime_type")

        if not binary_str:
            return f"No file contents found for document: {document_id}"

        # Use the Vertex AI Gemini model for vision analysis
        vision_model = get_model()
        vision_agent = Agent(
            vision_model,
            system_prompt=(
                "You are an image analyzer who looks at images provided "
                "and answers the accompanying query in detail."
            ),
        )

        binary = base64.b64decode(binary_str.encode("utf-8"))
        result = await vision_agent.run(
            [query, BinaryContent(data=binary, media_type=mime_type)]
        )

        return result.data

    except Exception as e:
        logger.error("Error analyzing image: %s", e)
        return f"Error analyzing image: {str(e)}"


# ---------------------------------------------------------------------------
# Code execution (unchanged)
# ---------------------------------------------------------------------------

def execute_safe_code_tool(code: str) -> str:
    # Set up allowed modules
    allowed_modules = {
        # Core utilities
        'datetime': __import__('datetime'),
        'math': __import__('math'),
        'random': __import__('random'),
        'time': __import__('time'),
        'collections': __import__('collections'),
        'itertools': __import__('itertools'),
        'functools': __import__('functools'),
        'copy': __import__('copy'),
        're': __import__('re'),
        'json': __import__('json'),
        'csv': __import__('csv'),
        'uuid': __import__('uuid'),
        'string': __import__('string'),
        'statistics': __import__('statistics'),

        # Data structures and algorithms
        'heapq': __import__('heapq'),
        'bisect': __import__('bisect'),
        'array': __import__('array'),
        'enum': __import__('enum'),
        'dataclasses': __import__('dataclasses'),

        # File/IO (with careful restrictions)
        'io': __import__('io'),
        'base64': __import__('base64'),
        'hashlib': __import__('hashlib'),
        'tempfile': __import__('tempfile')
    }

    # Try to import optional modules that might not be installed
    try:
        allowed_modules['numpy'] = __import__('numpy')
    except ImportError:
        pass

    try:
        allowed_modules['pandas'] = __import__('pandas')
    except ImportError:
        pass

    try:
        allowed_modules['scipy'] = __import__('scipy')
    except ImportError:
        pass

    # Custom import function that only allows whitelisted modules
    def safe_import(name, *args, **kwargs):
        if name in allowed_modules:
            return allowed_modules[name]
        raise ImportError(f"Module {name} is not allowed")

    # Create a safe environment with minimal built-ins
    safe_builtins = {
        # Basic operations
        'abs': abs, 'all': all, 'any': any, 'bin': bin, 'bool': bool,
        'chr': chr, 'complex': complex, 'divmod': divmod, 'float': float,
        'format': format, 'hex': hex, 'int': int, 'len': len, 'max': max,
        'min': min, 'oct': oct, 'ord': ord, 'pow': pow, 'round': round,
        'sorted': sorted, 'sum': sum,

        # Types and conversions
        'bytes': bytes, 'dict': dict, 'frozenset': frozenset, 'list': list,
        'repr': repr, 'set': set, 'slice': slice, 'str': str, 'tuple': tuple,
        'type': type, 'zip': zip,

        # Iteration and generation
        'enumerate': enumerate, 'filter': filter, 'iter': iter, 'map': map,
        'next': next, 'range': range, 'reversed': reversed,

        # Other safe operations
        'getattr': getattr, 'hasattr': hasattr, 'hash': hash,
        'isinstance': isinstance, 'issubclass': issubclass,

        # Import handler
        '__import__': safe_import
    }

    # Set up output capture
    output = []
    def safe_print(*args, **kwargs):
        end = kwargs.get('end', '\n')
        sep = kwargs.get('sep', ' ')
        output.append(sep.join(str(arg) for arg in args) + end)

    # Create restricted globals
    restricted_globals = {
        '__builtins__': safe_builtins,
        'print': safe_print
    }

    try:
        # Execute the code with timeout
        exec(code, restricted_globals)
        return ''.join(output)
    except Exception as e:
        return f"Error executing code: {str(e)}"
