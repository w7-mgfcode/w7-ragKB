"""Database handler for the RAG pipeline.

All operations use asyncpg parameterized queries against self-hosted
PostgreSQL 16 with pgvector.  Functions accept an ``asyncpg.Pool`` as
their first argument so callers control connection lifecycle.

Sequential (one-row-at-a-time) inserts are used throughout to keep
memory usage low on the 4 GB GCP VM.
"""

import json
import logging
import base64
from typing import Any, Dict, List, Optional

import asyncpg

from common.text_processor import (
    chunk_text,
    create_embeddings,
    extract_rows_from_csv,
    extract_schema_from_csv,
    is_tabular_file,
)

logger = logging.getLogger(__name__)


async def delete_document_by_file_id(pool: asyncpg.Pool, file_id: str) -> None:
    """Delete all records related to a file ID.

    Removes rows from ``documents``, ``document_rows``, and
    ``document_metadata`` in the correct order to respect FK constraints.
    """
    async with pool.acquire() as conn:
        try:
            deleted_docs = await conn.execute(
                "DELETE FROM documents WHERE metadata->>'file_id' = $1",
                file_id,
            )
            logger.info("Deleted document chunks for file ID %s: %s", file_id, deleted_docs)
        except Exception:
            logger.exception("Error deleting document chunks for file ID %s", file_id)

        try:
            deleted_rows = await conn.execute(
                "DELETE FROM document_rows WHERE dataset_id = $1",
                file_id,
            )
            logger.info("Deleted document rows for file ID %s: %s", file_id, deleted_rows)
        except Exception:
            logger.exception("Error deleting document rows for file ID %s", file_id)

        try:
            deleted_meta = await conn.execute(
                "DELETE FROM document_metadata WHERE id = $1",
                file_id,
            )
            logger.info("Deleted metadata for file ID %s: %s", file_id, deleted_meta)
        except Exception:
            logger.exception("Error deleting document metadata for file ID %s", file_id)


async def insert_document_chunks(
    pool: asyncpg.Pool,
    chunks: List[str],
    embeddings: List[List[float]],
    file_id: str,
    file_url: str,
    file_title: str,
    mime_type: str,
    file_contents: Optional[bytes] = None,
) -> None:
    """Insert document chunks with embeddings into the ``documents`` table.

    Inserts one row at a time (sequential) to keep memory usage low on
    the 4 GB VM.
    """
    if len(chunks) != len(embeddings):
        raise ValueError("Number of chunks and embeddings must match")

    file_bytes_str = (
        base64.b64encode(file_contents).decode("utf-8") if file_contents else None
    )

    async with pool.acquire() as conn:
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            metadata = {
                "file_id": file_id,
                "file_url": file_url,
                "file_title": file_title,
                "mime_type": mime_type,
                "chunk_index": i,
            }
            if file_bytes_str:
                metadata["file_contents"] = file_bytes_str

            try:
                await conn.execute(
                    """
                    INSERT INTO documents (content, metadata, embedding)
                    VALUES ($1, $2::jsonb, $3::vector)
                    """,
                    chunk,
                    json.dumps(metadata),
                    str(embedding),
                )
            except Exception:
                logger.exception(
                    "Error inserting chunk %d for file %s", i, file_id
                )

    logger.info(
        "Inserted %d chunks for file '%s' (ID: %s)",
        len(chunks),
        file_title,
        file_id,
    )


async def insert_or_update_document_metadata(
    pool: asyncpg.Pool,
    file_id: str,
    file_title: str,
    file_url: str,
    schema: Optional[List[str]] = None,
) -> None:
    """Upsert a record in the ``document_metadata`` table."""
    schema_json = json.dumps(schema) if schema else None

    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO document_metadata (id, title, url, schema)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (id) DO UPDATE
                    SET title  = EXCLUDED.title,
                        url    = EXCLUDED.url,
                        schema = EXCLUDED.schema
                """,
                file_id,
                file_title,
                file_url,
                schema_json,
            )
            logger.info(
                "Upserted metadata for file '%s' (ID: %s)", file_title, file_id
            )
        except Exception:
            logger.exception(
                "Error upserting document metadata for file '%s' (ID: %s)",
                file_title,
                file_id,
            )


async def insert_document_rows(
    pool: asyncpg.Pool,
    file_id: str,
    rows: List[Dict[str, Any]],
) -> None:
    """Insert rows from a tabular file into ``document_rows``.

    Existing rows for the file are deleted first, then new rows are
    inserted one at a time for memory efficiency.
    """
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "DELETE FROM document_rows WHERE dataset_id = $1", file_id
            )
            logger.info("Deleted existing rows for file ID: %s", file_id)

            for row in rows:
                await conn.execute(
                    """
                    INSERT INTO document_rows (dataset_id, row_data)
                    VALUES ($1, $2::jsonb)
                    """,
                    file_id,
                    json.dumps(row),
                )

            logger.info("Inserted %d rows for file ID: %s", len(rows), file_id)
        except Exception:
            logger.exception("Error inserting document rows for file ID %s", file_id)


async def process_file_for_rag(
    pool: asyncpg.Pool,
    file_content: bytes,
    text: str,
    file_id: str,
    file_url: str,
    file_title: str,
    mime_type: str = None,
    config: Optional[Dict[str, Any]] = None,
) -> bool:
    """Orchestrate RAG processing for a single file.

    Steps are executed sequentially to avoid memory spikes on the
    constrained VM.

    Returns ``True`` on success, ``False`` on failure.
    """
    if config is None:
        config = {}

    try:
        # 1. Remove any previous records for this file
        await delete_document_by_file_id(pool, file_id)

        # 2. Determine if the file is tabular
        is_tabular = False
        schema = None
        if mime_type:
            is_tabular = is_tabular_file(mime_type, config)
        if is_tabular:
            schema = extract_schema_from_csv(file_content)

        # 3. Upsert metadata (needed before document_rows FK)
        await insert_or_update_document_metadata(
            pool, file_id, file_title, file_url, schema
        )

        # 4. Insert tabular rows if applicable
        if is_tabular:
            rows = extract_rows_from_csv(file_content)
            if rows:
                await insert_document_rows(pool, file_id, rows)

        # 5. Chunk the text
        text_processing = config.get("text_processing", {})
        chunk_size = text_processing.get("default_chunk_size", 400)
        chunk_overlap = text_processing.get("default_chunk_overlap", 0)

        chunks = chunk_text(text, chunk_size=chunk_size, overlap=chunk_overlap)
        if not chunks:
            logger.warning(
                "No chunks created for file '%s' (ID: %s)", file_title, file_id
            )
            return True

        # 6. Generate embeddings
        embeddings = create_embeddings(chunks)

        # 7. Insert chunks — pass file_contents for images
        if mime_type and mime_type.startswith("image"):
            await insert_document_chunks(
                pool, chunks, embeddings, file_id, file_url,
                file_title, mime_type, file_content,
            )
        else:
            await insert_document_chunks(
                pool, chunks, embeddings, file_id, file_url,
                file_title, mime_type,
            )

        return True

    except Exception:
        logger.exception("Error processing file for RAG: %s (ID: %s)", file_title, file_id)
        return False
