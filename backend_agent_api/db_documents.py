"""Document-related database queries using asyncpg.

All queries use parameterized inputs ($1, $2, …) to prevent SQL injection.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)


async def match_documents(
    pool: asyncpg.Pool,
    query_embedding: List[float],
    match_count: int = 4,
    filter_metadata: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    """Vector similarity search using the match_documents SQL function.

    Args:
        pool: asyncpg connection pool.
        query_embedding: Query embedding vector (768 dimensions).
        match_count: Maximum number of results to return.
        filter_metadata: Optional JSONB filter for metadata containment (@>).

    Returns:
        List of dicts with id, content, metadata, and similarity.
    """
    filter_json = json.dumps(filter_metadata or {})

    rows = await pool.fetch(
        "SELECT * FROM match_documents($1::vector, $2, $3::jsonb)",
        str(query_embedding),
        match_count,
        filter_json,
    )

    return [dict(row) for row in rows]


async def list_documents(pool: asyncpg.Pool) -> List[Dict[str, Any]]:
    """Query the document_metadata table and return all documents.

    Returns:
        List of dicts with id, title, url, schema, and created_at.
    """
    rows = await pool.fetch(
        "SELECT id, title, url, schema, created_at FROM document_metadata"
    )
    return [dict(row) for row in rows]


async def get_document_content(
    pool: asyncpg.Pool,
    document_id: str,
) -> str:
    """Get all chunks for a document and combine into full content.

    Chunks are ordered by id (insertion order) to reconstruct the
    original document sequence.

    Args:
        pool: asyncpg connection pool.
        document_id: The file_id stored in the documents metadata JSONB.

    Returns:
        Combined document content string, or an error message if not found.
    """
    rows = await pool.fetch(
        """
        SELECT id, content, metadata
        FROM documents
        WHERE metadata->>'file_id' = $1
        ORDER BY id
        """,
        document_id,
    )

    if not rows:
        return f"No content found for document: {document_id}"

    metadata = rows[0]["metadata"]
    # metadata may be a dict (asyncpg JSONB) or a string
    if isinstance(metadata, str):
        metadata = json.loads(metadata)

    title = metadata.get("file_title", "Unknown Document")
    # Strip any chunk suffix like " - Chunk 1"
    title = title.split(" - ")[0]

    parts = [f"# {title}\n"]
    for row in rows:
        if row["content"]:
            parts.append(row["content"])

    # Cap at 20 000 characters to avoid overwhelming the LLM context
    return "\n\n".join(parts)[:20000]


async def execute_custom_sql(
    pool: asyncpg.Pool,
    sql_query: str,
) -> str:
    """Execute a read-only SQL query and return results as JSON.

    Only SELECT statements are allowed. Any write operation
    (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, GRANT, REVOKE)
    is rejected before the query reaches the database.

    Args:
        pool: asyncpg connection pool.
        sql_query: The SQL query to execute.

    Returns:
        JSON string of the query results, or an error message.
    """
    sql_query = sql_query.strip()
    upper_query = sql_query.upper()

    write_operations = [
        "INSERT", "UPDATE", "DELETE", "DROP", "CREATE",
        "ALTER", "TRUNCATE", "GRANT", "REVOKE",
    ]
    for op in write_operations:
        if re.search(r"\b" + op + r"\b", upper_query):
            return f"Error: Write operation '{op}' detected. Only read-only queries are allowed."

    try:
        rows = await pool.fetch(sql_query)
        results = [dict(row) for row in rows]
        return json.dumps(results, indent=2, default=str)
    except Exception as e:
        logger.error("SQL query error: %s", e)
        return f"Error executing SQL query: {str(e)}"


# Hierarchical RAG Database Functions (Task 4.1)


async def get_all_document_metadata(pool: asyncpg.Pool) -> List[Dict[str, Any]]:
    """Get metadata for all documents from the database for tree building.
    
    Returns distinct documents with their file_id, file_path, file_title,
    and total chunk count. Used by the document browser tree view.
    
    Args:
        pool: asyncpg connection pool
        
    Returns:
        List of dicts with file_id, file_path, file_title, chunk_count
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (metadata->>'file_id')
            metadata->>'file_id' as file_id,
            metadata->>'file_path' as file_path,
            metadata->>'file_title' as file_title,
            COUNT(*) OVER (PARTITION BY metadata->>'file_id') as chunk_count
        FROM documents
        WHERE metadata->>'file_id' IS NOT NULL
        ORDER BY metadata->>'file_id', id
        """
    )
    return [dict(row) for row in rows]


async def delete_document_by_path(pool: asyncpg.Pool, file_path: str) -> int:
    """Delete all chunks for a document by file path.
    
    Removes all document chunks (document, section, and leaf levels)
    associated with the given file path.
    
    Args:
        pool: asyncpg connection pool
        file_path: Document file path relative to rag-documents root
        
    Returns:
        Number of chunks deleted
    """
    result = await pool.execute(
        "DELETE FROM documents WHERE metadata->>'file_path' = $1",
        file_path
    )
    # Extract count from result string like "DELETE 15"
    deleted_count = int(result.split()[-1]) if result else 0
    logger.info(f"Deleted {deleted_count} chunks for document: {file_path}")
    return deleted_count


async def search_documents_by_content(
    pool: asyncpg.Pool,
    search_query: str,
    limit: int = 50,
    include_all_statuses: bool = False,
) -> List[Dict[str, Any]]:
    """Search documents by content with snippet extraction and sync status.

    Performs full-text search across document content and extracts
    matching snippets with context (50 chars before/after match).
    Includes sync status and source from document_sync_status table.

    Args:
        pool: asyncpg connection pool
        search_query: Search query string
        limit: Maximum number of results (default 50)
        include_all_statuses: If False, exclude orphaned_chunks and error docs

    Returns:
        List of dicts with file_id, file_path, file_title, content_snippet,
        chunk_level, match_position, sync_status, source
    """
    status_filter = ""
    if not include_all_statuses:
        status_filter = (
            "AND (dss.sync_status IS NULL "
            "OR dss.sync_status NOT IN ('orphaned_chunks', 'error'))"
        )

    query = f"""
        SELECT
            d.metadata->>'file_id' as file_id,
            d.metadata->>'file_path' as file_path,
            d.metadata->>'file_title' as file_title,
            d.chunk_level,
            SUBSTRING(
                d.content FROM
                GREATEST(1, POSITION(LOWER($1) IN LOWER(d.content)) - 50)
                FOR 150
            ) as content_snippet,
            POSITION(LOWER($1) IN LOWER(d.content)) as match_position,
            dss.sync_status,
            dss.source
        FROM documents d
        LEFT JOIN document_sync_status dss
            ON d.metadata->>'file_path' = dss.file_path
        WHERE d.content ILIKE '%' || $1 || '%'
        {status_filter}
        ORDER BY
            CASE d.chunk_level
                WHEN 'document' THEN 1
                WHEN 'section' THEN 2
                WHEN 'leaf' THEN 3
            END,
            match_position
        LIMIT $2
    """
    rows = await pool.fetch(query, search_query, limit)
    return [dict(row) for row in rows]


async def get_chunks_by_level(
    pool: asyncpg.Pool,
    chunk_level: str,
    file_id: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get chunks filtered by hierarchical level.
    
    Retrieves chunks at a specific level (document, section, or leaf).
    Optionally filters by file_id.
    
    Args:
        pool: asyncpg connection pool
        chunk_level: Level to filter ('document', 'section', or 'leaf')
        file_id: Optional file_id to filter by specific document
        limit: Maximum number of results (default 100)
        
    Returns:
        List of chunk dicts with id, content, metadata, chunk_level,
        parent_chunk_id, sibling_count, sibling_position
    """
    if file_id:
        rows = await pool.fetch(
            """
            SELECT 
                id, content, metadata, chunk_level,
                parent_chunk_id, sibling_count, sibling_position,
                category_path
            FROM documents
            WHERE chunk_level = $1 AND metadata->>'file_id' = $2
            ORDER BY id
            LIMIT $3
            """,
            chunk_level,
            file_id,
            limit
        )
    else:
        rows = await pool.fetch(
            """
            SELECT 
                id, content, metadata, chunk_level,
                parent_chunk_id, sibling_count, sibling_position,
                category_path
            FROM documents
            WHERE chunk_level = $1
            ORDER BY id
            LIMIT $2
            """,
            chunk_level,
            limit
        )
    return [dict(row) for row in rows]


async def get_parent_chunk(
    pool: asyncpg.Pool,
    chunk_id: int
) -> Optional[Dict[str, Any]]:
    """Get the parent chunk for a given chunk ID.
    
    Retrieves the parent chunk by following the parent_chunk_id relationship.
    Used for parent context retrieval in hierarchical RAG.
    
    Args:
        pool: asyncpg connection pool
        chunk_id: ID of the child chunk
        
    Returns:
        Parent chunk dict or None if no parent exists
    """
    row = await pool.fetchrow(
        """
        SELECT 
            parent.id, parent.content, parent.metadata, parent.chunk_level,
            parent.parent_chunk_id, parent.sibling_count, parent.sibling_position,
            parent.category_path
        FROM documents AS child
        JOIN documents AS parent ON child.parent_chunk_id = parent.id
        WHERE child.id = $1
        """,
        chunk_id
    )
    return dict(row) if row else None


async def get_sibling_chunks(
    pool: asyncpg.Pool,
    chunk_id: int
) -> List[Dict[str, Any]]:
    """Get all sibling chunks for a given chunk ID.
    
    Retrieves all chunks that share the same parent_chunk_id.
    Used by the auto-merge algorithm to detect when multiple siblings match.
    
    Args:
        pool: asyncpg connection pool
        chunk_id: ID of the reference chunk
        
    Returns:
        List of sibling chunk dicts (including the reference chunk itself)
    """
    rows = await pool.fetch(
        """
        SELECT 
            sibling.id, sibling.content, sibling.metadata, sibling.chunk_level,
            sibling.parent_chunk_id, sibling.sibling_count, sibling.sibling_position,
            sibling.category_path
        FROM documents AS reference
        JOIN documents AS sibling ON reference.parent_chunk_id = sibling.parent_chunk_id
        WHERE reference.id = $1
        ORDER BY sibling.sibling_position
        """,
        chunk_id
    )
    return [dict(row) for row in rows]


# Atomic Document Operations (Task 4.2)


async def create_document_atomic(
    pool: asyncpg.Pool,
    file_path: str,
    content: str,
    user_id: str
) -> Dict[str, Any]:
    """Create a document with atomic filesystem and database operations.
    
    Creates both the filesystem file and database chunks atomically.
    If either operation fails, both are rolled back to maintain consistency.
    
    Args:
        pool: asyncpg connection pool
        file_path: Document file path relative to rag-documents root
        content: Markdown content to write
        user_id: User ID performing the operation (for logging)
        
    Returns:
        Dict with file_id, file_path, chunk_count
        
    Raises:
        DocumentError: If creation fails (filesystem or database)
    """
    from pathlib import Path
    from document_validation import RAG_DOCUMENTS_DIR
    from document_exceptions import DocumentError, DocumentConflictError
    from hierarchical_chunker import chunk_document_hierarchical
    from vertex_embeddings import VertexEmbeddingClient
    import json
    
    full_path = RAG_DOCUMENTS_DIR / file_path
    file_created = False
    
    try:
        # Check if file already exists
        if full_path.exists():
            raise DocumentConflictError(file_path)
        
        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file to disk
        full_path.write_text(content, encoding='utf-8')
        file_created = True
        logger.info(f"Created file: {file_path}")
        
        # Generate file_id from relative path
        file_id = file_path
        
        # Chunk document hierarchically
        chunks = chunk_document_hierarchical(content, file_path, file_id)
        
        if not chunks:
            raise DocumentError("Failed to chunk document: no chunks generated")
        
        # Generate embeddings
        embedding_client = VertexEmbeddingClient()
        chunk_texts = [chunk['content'] for chunk in chunks]
        embeddings = embedding_client.create_embeddings(
            chunk_texts,
            task_type="RETRIEVAL_DOCUMENT"
        )
        
        if len(embeddings) != len(chunks):
            raise DocumentError(
                f"Embedding count mismatch: {len(embeddings)} != {len(chunks)}"
            )
        
        # Insert chunks into database within transaction
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Map temporary chunk IDs to actual database IDs
                chunk_id_map = {}
                
                for chunk, embedding in zip(chunks, embeddings):
                    # Resolve parent_chunk_id if it exists
                    parent_id = chunk.get('parent_chunk_id')
                    if parent_id is not None and parent_id in chunk_id_map:
                        parent_id = chunk_id_map[parent_id]
                    
                    # Insert chunk
                    row = await conn.fetchrow(
                        """
                        INSERT INTO documents (
                            content, metadata, embedding,
                            chunk_level, parent_chunk_id, category_path,
                            sibling_count, sibling_position
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        RETURNING id
                        """,
                        chunk['content'],
                        json.dumps(chunk['metadata']),
                        str(embedding),
                        chunk['chunk_level'],
                        parent_id,
                        chunk['category_path'],
                        chunk['sibling_count'],
                        chunk['sibling_position']
                    )
                    
                    # Store mapping for child chunks
                    temp_id = chunk.get('id')
                    if temp_id is not None:
                        chunk_id_map[temp_id] = row['id']
        
        logger.info(
            f"Document created atomically by user {user_id}: {file_path} "
            f"({len(chunks)} chunks)"
        )
        
        return {
            'file_id': file_id,
            'file_path': file_path,
            'chunk_count': len(chunks)
        }
        
    except Exception as e:
        # Rollback filesystem changes if file was created
        if file_created and full_path.exists():
            try:
                full_path.unlink()
                logger.info(f"Rolled back file creation: {file_path}")
            except Exception as cleanup_error:
                logger.error(
                    f"Failed to rollback file {file_path}: {cleanup_error}"
                )
        
        logger.error(
            f"Failed to create document {file_path}: {e}",
            exc_info=True
        )
        raise DocumentError(f"Failed to create document: {str(e)}")


async def update_document_atomic(
    pool: asyncpg.Pool,
    file_path: str,
    content: str,
    user_id: str
) -> Dict[str, Any]:
    """Update a document with atomic filesystem and database operations.
    
    Updates both the filesystem file and database chunks atomically with
    backup/rollback support. If either operation fails, both are rolled back.
    
    Args:
        pool: asyncpg connection pool
        file_path: Document file path relative to rag-documents root
        content: New markdown content
        user_id: User ID performing the operation (for logging)
        
    Returns:
        Dict with file_id, file_path, chunk_count
        
    Raises:
        DocumentError: If update fails (filesystem or database)
        DocumentNotFoundError: If document doesn't exist
    """
    from pathlib import Path
    from document_validation import RAG_DOCUMENTS_DIR
    from document_exceptions import DocumentError, DocumentNotFoundError
    from hierarchical_chunker import chunk_document_hierarchical
    from vertex_embeddings import VertexEmbeddingClient
    import json
    import shutil
    
    full_path = RAG_DOCUMENTS_DIR / file_path
    backup_path = full_path.with_suffix('.md.backup')
    backup_created = False
    
    try:
        # Check if file exists
        if not full_path.exists():
            raise DocumentNotFoundError(file_path)
        
        # Create backup of existing file
        shutil.copy2(full_path, backup_path)
        backup_created = True
        logger.info(f"Created backup: {backup_path}")
        
        # Write new content to file
        full_path.write_text(content, encoding='utf-8')
        logger.info(f"Updated file: {file_path}")
        
        # Generate file_id from relative path
        file_id = file_path
        
        # Chunk document hierarchically
        chunks = chunk_document_hierarchical(content, file_path, file_id)
        
        if not chunks:
            raise DocumentError("Failed to chunk document: no chunks generated")
        
        # Generate embeddings
        embedding_client = VertexEmbeddingClient()
        chunk_texts = [chunk['content'] for chunk in chunks]
        embeddings = embedding_client.create_embeddings(
            chunk_texts,
            task_type="RETRIEVAL_DOCUMENT"
        )
        
        if len(embeddings) != len(chunks):
            raise DocumentError(
                f"Embedding count mismatch: {len(embeddings)} != {len(chunks)}"
            )
        
        # Update database within transaction
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Delete old chunks
                await conn.execute(
                    "DELETE FROM documents WHERE metadata->>'file_path' = $1",
                    file_path
                )
                
                # Map temporary chunk IDs to actual database IDs
                chunk_id_map = {}
                
                # Insert new chunks
                for chunk, embedding in zip(chunks, embeddings):
                    # Resolve parent_chunk_id if it exists
                    parent_id = chunk.get('parent_chunk_id')
                    if parent_id is not None and parent_id in chunk_id_map:
                        parent_id = chunk_id_map[parent_id]
                    
                    # Insert chunk
                    row = await conn.fetchrow(
                        """
                        INSERT INTO documents (
                            content, metadata, embedding,
                            chunk_level, parent_chunk_id, category_path,
                            sibling_count, sibling_position
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        RETURNING id
                        """,
                        chunk['content'],
                        json.dumps(chunk['metadata']),
                        str(embedding),
                        chunk['chunk_level'],
                        parent_id,
                        chunk['category_path'],
                        chunk['sibling_count'],
                        chunk['sibling_position']
                    )
                    
                    # Store mapping for child chunks
                    temp_id = chunk.get('id')
                    if temp_id is not None:
                        chunk_id_map[temp_id] = row['id']
        
        # Success - remove backup
        if backup_path.exists():
            backup_path.unlink()
            logger.info(f"Removed backup: {backup_path}")
        
        logger.info(
            f"Document updated atomically by user {user_id}: {file_path} "
            f"({len(chunks)} chunks)"
        )
        
        return {
            'file_id': file_id,
            'file_path': file_path,
            'chunk_count': len(chunks)
        }
        
    except Exception as e:
        # Rollback filesystem changes if backup exists
        if backup_created and backup_path.exists():
            try:
                shutil.move(str(backup_path), str(full_path))
                logger.info(f"Rolled back file update: {file_path}")
            except Exception as cleanup_error:
                logger.error(
                    f"Failed to rollback file {file_path}: {cleanup_error}"
                )
        
        logger.error(
            f"Failed to update document {file_path}: {e}",
            exc_info=True
        )
        raise DocumentError(f"Failed to update document: {str(e)}")


async def delete_document_atomic(
    pool: asyncpg.Pool,
    file_path: str,
    user_id: str
) -> Dict[str, Any]:
    """Delete a document with atomic filesystem and database operations.
    
    Deletes both the filesystem file and database chunks atomically within
    a transaction. If either operation fails, both are rolled back.
    
    Args:
        pool: asyncpg connection pool
        file_path: Document file path relative to rag-documents root
        user_id: User ID performing the operation (for logging)
        
    Returns:
        Dict with file_path, chunks_deleted
        
    Raises:
        DocumentError: If deletion fails (filesystem or database)
        DocumentNotFoundError: If document doesn't exist
    """
    from pathlib import Path
    from document_validation import RAG_DOCUMENTS_DIR
    from document_exceptions import DocumentError, DocumentNotFoundError
    import shutil
    
    full_path = RAG_DOCUMENTS_DIR / file_path
    backup_path = full_path.with_suffix('.md.deleted')
    backup_created = False
    
    try:
        # Check if file exists
        if not full_path.exists():
            raise DocumentNotFoundError(file_path)
        
        # Create backup before deletion (for rollback)
        shutil.copy2(full_path, backup_path)
        backup_created = True
        logger.info(f"Created deletion backup: {backup_path}")
        
        # Delete from database within transaction
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Delete all chunks for this document
                result = await conn.execute(
                    "DELETE FROM documents WHERE metadata->>'file_path' = $1",
                    file_path
                )
                
                # Extract count from result string like "DELETE 15"
                chunks_deleted = int(result.split()[-1]) if result else 0
                
                if chunks_deleted == 0:
                    logger.warning(
                        f"No database chunks found for {file_path}, "
                        f"but file exists on disk"
                    )
                
                # Delete file from disk (still within transaction scope)
                full_path.unlink()
                logger.info(f"Deleted file: {file_path}")
        
        # Success - remove backup
        if backup_path.exists():
            backup_path.unlink()
            logger.info(f"Removed deletion backup: {backup_path}")
        
        logger.info(
            f"Document deleted atomically by user {user_id}: {file_path} "
            f"({chunks_deleted} chunks)"
        )
        
        return {
            'file_path': file_path,
            'chunks_deleted': chunks_deleted
        }
        
    except Exception as e:
        # Rollback filesystem changes if backup exists
        if backup_created and backup_path.exists():
            try:
                shutil.move(str(backup_path), str(full_path))
                logger.info(f"Rolled back file deletion: {file_path}")
            except Exception as cleanup_error:
                logger.error(
                    f"Failed to rollback deletion of {file_path}: {cleanup_error}"
                )
        
        logger.error(
            f"Failed to delete document {file_path}: {e}",
            exc_info=True
        )
        raise DocumentError(f"Failed to delete document: {str(e)}")
