"""FastAPI router for document browser operations.

Provides REST API endpoints for hierarchical document browsing, CRUD operations,
search, and category-based query routing.
"""

import asyncio
import json as _json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field, validator

from auth_middleware import get_current_user
from db import get_pool
from document_exceptions import (
    DirectoryNotEmptyError,
    DocumentConflictError,
    DocumentError,
    DocumentNotFoundError,
    DocumentValidationError,
)
from document_rate_limiter import (
    check_document_rate_limit,
    get_retry_after,
    record_document_request,
)
from document_validation import (
    normalize_line_endings,
    validate_dirname,
    validate_filename,
    validate_markdown_content,
    validate_path,
)
from hierarchical_chunking import chunk_document_hierarchical
from markdown_parser import markdown_round_trip
from query_router import build_category_tree as _build_category_tree
from query_router import build_category_tree_sync_filtered as _build_category_tree_filtered
from query_router import route_query_to_categories as _route_query
import db_documents
from sync_manager import (
    ConflictResolution,
    DocumentSyncInfo,
    SyncManager,
    SyncStatus,
    get_sync_manager,
)
from vertex_embeddings import VertexEmbeddingClient
from websocket_manager import WebSocketManager, get_websocket_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])

# Base directory for documents
RAG_DOCUMENTS_DIR = os.getenv("RAG_DOCUMENTS_DIR", "/rag-documents")


# ==============================================================================
# Pydantic Models
# ==============================================================================

class DocumentMetadata(BaseModel):
    """Metadata for a document file."""
    size: int = Field(ge=0, description="File size in bytes")
    modified: datetime
    word_count: int = Field(ge=0, description="Total word count")


class TreeNode(BaseModel):
    """Node in the document tree (directory or document)."""
    type: str = Field(description="'directory' or 'document'")
    name: str
    path: str
    children: Optional[List["TreeNode"]] = None
    metadata: Optional[DocumentMetadata] = None


TreeNode.update_forward_refs()


class DocumentStats(BaseModel):
    """Aggregate statistics about the document collection."""
    total_directories: int = Field(ge=0)
    total_documents: int = Field(ge=0)
    total_subdirectories: int = Field(ge=0)
    total_words: int = Field(ge=0)


class Document(BaseModel):
    """Full document with content and metadata."""
    path: str
    content: str
    metadata: DocumentMetadata


class CreateDocumentRequest(BaseModel):
    """Request to create a new document."""
    path: str
    content: str = ""
    
    @validator("path")
    def validate_path_format(cls, v):
        if not v.endswith(".md"):
            raise ValueError("Document path must end with .md")
        return v


class UpdateDocumentRequest(BaseModel):
    """Request to update document content."""
    content: str
    expected_mtime: Optional[str] = None  # ISO 8601 timestamp for conflict detection


class SearchRequest(BaseModel):
    """Request to search documents."""
    query: str = Field(min_length=1)
    search_content: bool = True


class SearchMatch(BaseModel):
    """A single search match."""
    type: str = Field(description="'filename' or 'content'")
    snippet: str
    position: int


class SearchResult(BaseModel):
    """Search result with matches."""
    path: str
    name: str
    matches: List[SearchMatch]
    metadata: DocumentMetadata


class CreateDirectoryRequest(BaseModel):
    """Request to create a new directory."""
    path: str


class DeleteResponse(BaseModel):
    """Response for delete operations."""
    message: str
    path: str


class DirectoryResponse(BaseModel):
    """Response for directory operations."""
    message: str
    path: str


class BulkDeleteRequest(BaseModel):
    """Request to delete multiple documents."""
    paths: List[str] = Field(min_items=1)


class BulkMoveRequest(BaseModel):
    """Request to move multiple documents."""
    paths: List[str] = Field(min_items=1)
    target_directory: str


class BulkOperationResult(BaseModel):
    """Result of bulk operation."""
    successful: List[str]
    failed: List[Dict[str, str]]


class CategoryNode(BaseModel):
    """Node in the category tree."""
    name: str
    path: str
    document_count: int
    total_chunks: int
    subcategories: List["CategoryNode"]


CategoryNode.update_forward_refs()


class QueryRoutingRequest(BaseModel):
    """Request to route a query to categories."""
    query: str = Field(min_length=1)
    max_categories: int = Field(default=3, ge=1, le=10)


class QueryRoutingResponse(BaseModel):
    """Response with selected categories."""
    query: str
    selected_categories: List[str]
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


class CategoryStats(BaseModel):
    """Statistics for a category."""
    category_path: str
    document_count: int
    total_chunks: int
    chunk_level_distribution: Dict[str, int]
    avg_chunk_size: float
    total_words: int
    last_updated: datetime


# ==============================================================================
# Helper Functions
# ==============================================================================

def get_file_metadata(file_path: Path) -> DocumentMetadata:
    """Get metadata for a file."""
    stat = file_path.stat()
    
    # Count words in file
    try:
        content = file_path.read_text(encoding="utf-8")
        word_count = len(content.split())
    except Exception:
        word_count = 0
    
    return DocumentMetadata(
        size=stat.st_size,
        modified=datetime.fromtimestamp(stat.st_mtime),
        word_count=word_count
    )


def build_tree(directory: Path, base_path: Path) -> List[TreeNode]:
    """Recursively build document tree."""
    nodes = []
    
    try:
        items = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name))
    except PermissionError:
        return nodes
    
    for item in items:
        # Skip hidden files and directories
        if item.name.startswith("."):
            continue
        
        relative_path = str(item.relative_to(base_path))
        
        if item.is_dir():
            children = build_tree(item, base_path)
            node = TreeNode(
                type="directory",
                name=item.name,
                path=relative_path,
                children=children
            )
            nodes.append(node)
        elif item.suffix == ".md":
            metadata = get_file_metadata(item)
            node = TreeNode(
                type="document",
                name=item.name,
                path=relative_path,
                metadata=metadata
            )
            nodes.append(node)
    
    return nodes


def calculate_stats(directory: Path) -> DocumentStats:
    """Calculate aggregate statistics."""
    total_directories = 0
    total_documents = 0
    total_subdirectories = 0
    total_words = 0
    
    def walk_dir(path: Path, is_root: bool = True):
        nonlocal total_directories, total_documents, total_subdirectories, total_words
        
        try:
            items = list(path.iterdir())
        except PermissionError:
            return
        
        has_subdirs = False
        for item in items:
            if item.name.startswith("."):
                continue
            
            if item.is_dir():
                if is_root:
                    total_directories += 1
                else:
                    total_subdirectories += 1
                    has_subdirs = True
                walk_dir(item, is_root=False)
            elif item.suffix == ".md":
                total_documents += 1
                try:
                    content = item.read_text(encoding="utf-8")
                    total_words += len(content.split())
                except Exception:
                    pass
    
    walk_dir(directory)
    
    return DocumentStats(
        total_directories=total_directories,
        total_documents=total_documents,
        total_subdirectories=total_subdirectories,
        total_words=total_words
    )


_embedding_client: Optional[VertexEmbeddingClient] = None


async def _get_embedding(text: str):
    """Lazy-init embedding client and generate a single embedding."""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = VertexEmbeddingClient()
    return await _embedding_client.create_query_embedding(text)


def _convert_category_node(node) -> dict:
    """Convert query_router.CategoryNode dataclass to Pydantic-compatible dict."""
    return {
        "name": node.name,
        "path": node.path,
        "document_count": node.document_count,
        "total_chunks": 0,
        "subcategories": [_convert_category_node(sub) for sub in node.subcategories],
    }


def _check_rate_limit(current_user: dict):
    """Check rate limit and raise 429 if exceeded."""
    user_id = current_user.get("user_id", current_user.get("sub", "unknown"))
    if check_document_rate_limit(user_id):
        retry_after = get_retry_after(user_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
    record_document_request(user_id)


def _audit_log(operation: str, path: str, user_id: str, status: str = "success", error: str = None, details: dict = None):
    """Structured audit log for document operations."""
    entry = {
        "event": f"document.{operation}",
        "user_id": user_id,
        "path": path,
        "status": status,
    }
    if error:
        entry["error"] = error
    if details:
        entry.update(details)
    logger.info(_json.dumps(entry))


async def insert_chunks_with_embeddings(
    pool: asyncpg.Pool,
    chunks: List[Dict],
    embedding_fn
) -> None:
    """Insert hierarchical chunks with embeddings into database.
    
    Handles parent-child relationships by inserting in order:
    1. Document level
    2. Section level (with parent_chunk_id from document)
    3. Leaf level (with parent_chunk_id from sections)
    """
    # Separate chunks by level
    doc_chunks = [c for c in chunks if c["chunk_level"] == "document"]
    section_chunks = [c for c in chunks if c["chunk_level"] == "section"]
    leaf_chunks = [c for c in chunks if c["chunk_level"] == "leaf"]
    
    # Insert document chunk first
    doc_chunk_id = None
    if doc_chunks:
        doc_chunk = doc_chunks[0]
        embedding = await embedding_fn(doc_chunk["content"])
        
        doc_chunk_id = await pool.fetchval(
            """
            INSERT INTO documents (
                content, metadata, embedding, chunk_level,
                parent_chunk_id, category_path, sibling_count, sibling_position
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            doc_chunk["content"],
            _json.dumps(doc_chunk["metadata"]),
            str(embedding),
            doc_chunk["chunk_level"],
            doc_chunk["parent_chunk_id"],
            doc_chunk["category_path"],
            doc_chunk["sibling_count"],
            doc_chunk["sibling_position"]
        )

    # Insert section chunks with parent reference
    section_chunk_ids = []
    for section_chunk in section_chunks:
        embedding = await embedding_fn(section_chunk["content"])

        section_id = await pool.fetchval(
            """
            INSERT INTO documents (
                content, metadata, embedding, chunk_level,
                parent_chunk_id, category_path, sibling_count, sibling_position
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            section_chunk["content"],
            _json.dumps(section_chunk["metadata"]),
            str(embedding),
            section_chunk["chunk_level"],
            doc_chunk_id,  # Parent is document chunk
            section_chunk["category_path"],
            section_chunk["sibling_count"],
            section_chunk["sibling_position"]
        )
        section_chunk_ids.append(section_id)

    # Insert leaf chunks with parent reference to sections
    for leaf_chunk in leaf_chunks:
        embedding = await embedding_fn(leaf_chunk["content"])

        # Get parent section ID from temp field
        parent_section_idx = leaf_chunk.get("parent_section_idx", 0)
        parent_section_id = (
            section_chunk_ids[parent_section_idx]
            if parent_section_idx < len(section_chunk_ids)
            else doc_chunk_id
        )

        await pool.execute(
            """
            INSERT INTO documents (
                content, metadata, embedding, chunk_level,
                parent_chunk_id, category_path, sibling_count, sibling_position
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            leaf_chunk["content"],
            _json.dumps(leaf_chunk["metadata"]),
            str(embedding),
            leaf_chunk["chunk_level"],
            parent_section_id,
            leaf_chunk["category_path"],
            leaf_chunk["sibling_count"],
            leaf_chunk["sibling_position"]
        )


# ==============================================================================
# API Endpoints
# ==============================================================================

@router.get("/tree", response_model=List[TreeNode])
async def get_document_tree(
    current_user: dict = Depends(get_current_user)
):
    """Get the complete document tree structure."""
    try:
        base_path = Path(RAG_DOCUMENTS_DIR)
        if not base_path.exists():
            base_path.mkdir(parents=True, exist_ok=True)
        
        tree = build_tree(base_path, base_path)
        return tree
    
    except Exception as e:
        logger.error(f"Error building document tree: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build document tree: {str(e)}"
        )


@router.get("/stats", response_model=DocumentStats)
async def get_document_stats(
    current_user: dict = Depends(get_current_user)
):
    """Get aggregate statistics about the document collection."""
    try:
        base_path = Path(RAG_DOCUMENTS_DIR)
        if not base_path.exists():
            return DocumentStats(
                total_directories=0,
                total_documents=0,
                total_subdirectories=0,
                total_words=0
            )
        
        stats = calculate_stats(base_path)
        return stats
    
    except Exception as e:
        logger.error(f"Error calculating document stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate stats: {str(e)}"
        )


@router.get("/categories", response_model=List[CategoryNode])
async def get_categories(
    sync_filter: bool = Query(False, description="Only count in-sync documents"),
    pool: asyncpg.Pool = Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    """Get category tree from document directory structure."""
    try:
        if sync_filter and pool:
            tree = await _build_category_tree_filtered(RAG_DOCUMENTS_DIR, pool)
        else:
            tree = _build_category_tree(RAG_DOCUMENTS_DIR)
        result = [_convert_category_node(node) for node in tree]
        _audit_log("categories_listed", "all", current_user.get("user_id"))
        return result
    except Exception as e:
        logger.error(f"Error getting categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get categories: {str(e)}",
        )


@router.get("/category-stats", response_model=List[CategoryStats])
async def get_category_stats(
    pool: asyncpg.Pool = Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    """Get statistics for each document category."""
    try:
        rows = await pool.fetch("""
            SELECT
                category_path,
                COUNT(DISTINCT metadata->>'file_id') as document_count,
                COUNT(*) as total_chunks,
                COUNT(*) FILTER (WHERE chunk_level = 'document') as doc_chunks,
                COUNT(*) FILTER (WHERE chunk_level = 'section') as section_chunks,
                COUNT(*) FILTER (WHERE chunk_level = 'leaf') as leaf_chunks,
                COALESCE(AVG(array_length(string_to_array(content, ' '), 1)), 0) as avg_chunk_size,
                COALESCE(SUM(array_length(string_to_array(content, ' '), 1)), 0) as total_words,
                MAX(COALESCE((metadata->>'last_modified')::timestamptz, NOW())) as last_updated
            FROM documents
            WHERE category_path IS NOT NULL
            GROUP BY category_path
            ORDER BY category_path
        """)
        _audit_log("category_stats_viewed", "all", current_user.get("user_id"))
        return [
            CategoryStats(
                category_path=row["category_path"],
                document_count=row["document_count"],
                total_chunks=row["total_chunks"],
                chunk_level_distribution={
                    "document": row["doc_chunks"],
                    "section": row["section_chunks"],
                    "leaf": row["leaf_chunks"],
                },
                avg_chunk_size=round(float(row["avg_chunk_size"]), 1),
                total_words=row["total_words"],
                last_updated=row["last_updated"],
            )
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Error getting category stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get category stats: {str(e)}",
        )


@router.post("/search", response_model=List[SearchResult])
async def search_documents(
    request: SearchRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    current_user: dict = Depends(get_current_user)
):
    """Search documents by name or content."""
    try:
        results = []
        base_path = Path(RAG_DOCUMENTS_DIR)

        if request.search_content and pool:
            # Search in database
            db_results = await db_documents.search_documents_by_content(
                pool,
                request.query,
                limit=50
            )

            for row in db_results:
                file_path = base_path / row["file_path"]
                if file_path.exists():
                    metadata = get_file_metadata(file_path)

                    match = SearchMatch(
                        type="content",
                        snippet=row["content_snippet"],
                        position=row["match_position"]
                    )

                    result = SearchResult(
                        path=row["file_path"],
                        name=file_path.name,
                        matches=[match],
                        metadata=metadata
                    )
                    results.append(result)

        else:
            # Search filenames only
            query_lower = request.query.lower()

            for file_path in base_path.rglob("*.md"):
                if query_lower in file_path.name.lower():
                    relative_path = str(file_path.relative_to(base_path))
                    metadata = get_file_metadata(file_path)

                    match = SearchMatch(
                        type="filename",
                        snippet=file_path.name,
                        position=file_path.name.lower().find(query_lower)
                    )

                    result = SearchResult(
                        path=relative_path,
                        name=file_path.name,
                        matches=[match],
                        metadata=metadata
                    )
                    results.append(result)

        _audit_log("searched", request.query, current_user.get("user_id"), details={"results": len(results)})
        return results

    except Exception as e:
        logger.error(f"Error searching documents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.post("/directories", response_model=DirectoryResponse, status_code=status.HTTP_201_CREATED)
async def create_directory(
    request: CreateDirectoryRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new directory."""
    try:
        _check_rate_limit(current_user)

        # Validate path
        full_path = validate_path(request.path, RAG_DOCUMENTS_DIR)
        dir_path = Path(full_path)

        # Check if already exists
        if dir_path.exists():
            raise DocumentConflictError(request.path)

        # Validate directory name
        validate_dirname(dir_path.name)

        # Create directory
        dir_path.mkdir(parents=True, exist_ok=True)

        _audit_log("directory_created", request.path, current_user.get("user_id"))

        return DirectoryResponse(
            message="Directory created successfully",
            path=request.path
        )

    except DocumentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating directory {request.path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create directory: {str(e)}"
        )


@router.delete("/directories/{path:path}", response_model=DirectoryResponse)
async def delete_directory(
    path: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete an empty directory."""
    try:
        _check_rate_limit(current_user)

        # Validate path
        full_path = validate_path(path, RAG_DOCUMENTS_DIR)
        dir_path = Path(full_path)

        if not dir_path.exists():
            raise DocumentNotFoundError(path)

        if not dir_path.is_dir():
            raise DocumentValidationError(f"Path is not a directory: {path}")

        # Check if empty
        if any(dir_path.iterdir()):
            raise DirectoryNotEmptyError(path)

        # Delete directory
        dir_path.rmdir()

        _audit_log("directory_deleted", path, current_user.get("user_id"))

        return DirectoryResponse(
            message="Directory deleted successfully",
            path=path
        )

    except DocumentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting directory {path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete directory: {str(e)}"
        )


@router.post("/bulk-delete", response_model=BulkOperationResult)
async def bulk_delete_documents(
    request: BulkDeleteRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    current_user: dict = Depends(get_current_user)
):
    """Delete multiple documents."""
    _check_rate_limit(current_user)

    successful = []
    failed = []

    for path in request.paths:
        try:
            full_path = validate_path(path, RAG_DOCUMENTS_DIR)
            file_path = Path(full_path)

            if not file_path.exists():
                failed.append({"path": path, "error": "File not found"})
                continue

            # Delete from database
            if pool:
                await db_documents.delete_document_by_path(pool, path)

            # Delete file
            file_path.unlink()
            successful.append(path)

        except Exception as e:
            failed.append({"path": path, "error": str(e)})

    _audit_log("bulk_deleted", "bulk", current_user.get("user_id"), details={"successful": len(successful), "failed": len(failed)})

    return BulkOperationResult(successful=successful, failed=failed)


@router.post("/bulk-move", response_model=BulkOperationResult)
async def bulk_move_documents(
    request: BulkMoveRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    current_user: dict = Depends(get_current_user)
):
    """Move multiple documents to a different directory."""
    _check_rate_limit(current_user)

    successful = []
    failed = []

    # Validate target directory
    try:
        target_full_path = validate_path(request.target_directory, RAG_DOCUMENTS_DIR)
        target_dir = Path(target_full_path)
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid target directory: {str(e)}"
        )

    for path in request.paths:
        try:
            full_path = validate_path(path, RAG_DOCUMENTS_DIR)
            file_path = Path(full_path)

            if not file_path.exists():
                failed.append({"path": path, "error": "File not found"})
                continue

            # Calculate new path
            new_path = target_dir / file_path.name
            new_relative_path = str(new_path.relative_to(Path(RAG_DOCUMENTS_DIR)))

            if new_path.exists():
                failed.append({"path": path, "error": "File already exists in target"})
                continue

            # Move file
            file_path.rename(new_path)

            # Update database (delete old, create new)
            if pool:
                await db_documents.delete_document_by_path(pool, path)

                content = new_path.read_text(encoding="utf-8")
                file_id = str(uuid.uuid4())
                file_title = new_path.stem.replace("-", " ").replace("_", " ").title()

                chunks = chunk_document_hierarchical(
                    content=content,
                    file_path=new_relative_path,
                    file_id=file_id,
                    file_title=file_title
                )

                await insert_chunks_with_embeddings(pool, chunks, _get_embedding)

            successful.append(path)

        except Exception as e:
            failed.append({"path": path, "error": str(e)})

    _audit_log("bulk_moved", "bulk", current_user.get("user_id"), details={"successful": len(successful), "failed": len(failed)})

    return BulkOperationResult(successful=successful, failed=failed)


@router.post("/route-query", response_model=QueryRoutingResponse)
async def route_query(
    request: QueryRoutingRequest,
    current_user: dict = Depends(get_current_user),
):
    """Route a query to relevant document categories using LLM."""
    try:
        _check_rate_limit(current_user)

        category_tree = _build_category_tree(RAG_DOCUMENTS_DIR)
        result = await asyncio.to_thread(
            _route_query, request.query, category_tree, request.max_categories
        )
        _audit_log("query_routed", request.query, current_user.get("user_id"), details={"categories": result.selected_categories})
        return QueryRoutingResponse(
            query=result.query,
            selected_categories=result.selected_categories,
            reasoning=result.reasoning,
            confidence=result.confidence,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error routing query: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to route query: {str(e)}",
        )


# ==============================================================================
# Sync Status & Re-indexing Endpoints
# ==============================================================================


@router.get("/sync-status", response_model=List[DocumentSyncInfo])
async def get_all_sync_statuses(
    sync_manager: SyncManager = Depends(get_sync_manager),
    current_user: dict = Depends(get_current_user),
):
    """Get sync status for all tracked documents."""
    try:
        return await sync_manager.get_all_sync_statuses()
    except Exception as e:
        logger.error("Error getting sync statuses: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get sync statuses: {e}")


@router.get("/sync-status/{path:path}", response_model=DocumentSyncInfo)
async def get_sync_status(
    path: str,
    sync_manager: SyncManager = Depends(get_sync_manager),
    current_user: dict = Depends(get_current_user),
):
    """Get sync status for a single document."""
    try:
        return await sync_manager.get_sync_status(path)
    except Exception as e:
        logger.error("Error getting sync status for %s: %s", path, e)
        raise HTTPException(status_code=500, detail=f"Failed to get sync status: {e}")


@router.post("/reindex/{path:path}", response_model=DocumentSyncInfo)
async def reindex_document(
    path: str,
    sync_manager: SyncManager = Depends(get_sync_manager),
    current_user: dict = Depends(get_current_user),
):
    """Manually trigger re-indexing for a single document."""
    try:
        _check_rate_limit(current_user)
        user_id = current_user.get("user_id", "unknown")
        result = await sync_manager.reindex_document(path, user_id)
        # Broadcast update
        try:
            ws_mgr = get_websocket_manager()
            await ws_mgr.send_sync_status_update(path, result.sync_status.value)
        except Exception:
            pass
        return result
    except DocumentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error reindexing %s: %s", path, e)
        raise HTTPException(status_code=500, detail=f"Re-indexing failed: {e}")


@router.post("/reindex-directory/{path:path}", response_model=List[DocumentSyncInfo])
async def reindex_directory(
    path: str,
    sync_manager: SyncManager = Depends(get_sync_manager),
    current_user: dict = Depends(get_current_user),
):
    """Manually trigger re-indexing for all documents in a directory."""
    try:
        _check_rate_limit(current_user)
        user_id = current_user.get("user_id", "unknown")
        return await sync_manager.reindex_directory(path, user_id)
    except DocumentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error reindexing directory %s: %s", path, e)
        raise HTTPException(status_code=500, detail=f"Directory re-indexing failed: {e}")


@router.post("/reindex-all", response_model=List[DocumentSyncInfo])
async def reindex_all(
    sync_manager: SyncManager = Depends(get_sync_manager),
    current_user: dict = Depends(get_current_user),
):
    """Manually trigger re-indexing for all documents."""
    try:
        _check_rate_limit(current_user)
        user_id = current_user.get("user_id", "unknown")
        return await sync_manager.reindex_all(user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error reindexing all: %s", e)
        raise HTTPException(status_code=500, detail=f"Full re-indexing failed: {e}")


@router.post("/resolve-conflict/{path:path}", response_model=Document)
async def resolve_conflict(
    path: str,
    resolution: ConflictResolution,
    sync_manager: SyncManager = Depends(get_sync_manager),
    current_user: dict = Depends(get_current_user),
):
    """Resolve a document conflict between filesystem and database."""
    try:
        _check_rate_limit(current_user)
        user_id = current_user.get("user_id", "unknown")
        await sync_manager.resolve_conflict(path, resolution, user_id)

        # Return the resolved document
        full_path = validate_path(path, RAG_DOCUMENTS_DIR)
        file_path = Path(full_path)
        content = file_path.read_text(encoding="utf-8")
        metadata = get_file_metadata(file_path)
        return Document(path=path, content=content, metadata=metadata)
    except DocumentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resolving conflict for %s: %s", path, e)
        raise HTTPException(status_code=500, detail=f"Conflict resolution failed: {e}")


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(default=""),
):
    """WebSocket endpoint for real-time document update notifications."""
    from token_manager import decode_access_token

    # Authenticate
    payload = decode_access_token(token) if token else None
    if not payload:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    user_id = payload.get("sub", "unknown")

    try:
        ws_mgr = get_websocket_manager()
    except RuntimeError:
        await websocket.close(code=4002, reason="Service unavailable")
        return

    accepted = await ws_mgr.connect(websocket, user_id)
    if not accepted:
        await websocket.close(code=4003, reason="Too many connections")
        return

    # Send any missed messages
    await ws_mgr.send_missed_messages(user_id)

    try:
        while True:
            # Keep connection alive; ignore client messages (ping/pong handled by ASGI)
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await ws_mgr.disconnect(websocket, user_id)


# ==============================================================================
# Metadata-only update (no re-indexing)
# ==============================================================================


class UpdateMetadataRequest(BaseModel):
    """Request to update document metadata without re-indexing."""
    title: Optional[str] = None
    author: Optional[str] = None
    tags: Optional[List[str]] = None


@router.patch("/{path:path}/metadata")
async def update_document_metadata(
    path: str,
    request: UpdateMetadataRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    current_user: dict = Depends(get_current_user),
):
    """Update document metadata without triggering re-indexing."""
    try:
        _check_rate_limit(current_user)

        full_path = validate_path(path, RAG_DOCUMENTS_DIR)
        file_path = Path(full_path)
        if not file_path.is_file():
            raise DocumentNotFoundError(path)

        # Build metadata patch from non-None fields
        patch: Dict[str, Any] = {}
        if request.title is not None:
            patch["file_title"] = request.title
        if request.author is not None:
            patch["author"] = request.author
        if request.tags is not None:
            patch["tags"] = request.tags

        if not patch:
            raise DocumentValidationError("No metadata fields provided")

        # Merge into existing metadata JSONB for all chunks of this document
        import json as _meta_json
        await pool.execute(
            "UPDATE documents SET metadata = metadata || $2::jsonb WHERE metadata->>'file_path' = $1",
            path,
            _meta_json.dumps(patch),
        )

        _audit_log("metadata_updated", path, current_user.get("user_id"),
                    details={"fields": list(patch.keys())})

        # Broadcast WebSocket event (no re-indexing needed)
        try:
            ws = get_websocket_manager()
            await ws.send_document_event("metadata_updated", path)
        except Exception:
            pass

        return {"message": "Metadata updated", "path": path, "updated_fields": list(patch.keys())}

    except DocumentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update metadata: {str(e)}")


# --- Catch-all path routes MUST be registered last ---


@router.post("/", response_model=Document, status_code=status.HTTP_201_CREATED)
async def create_document(
    request: CreateDocumentRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    current_user: dict = Depends(get_current_user)
):
    """Create a new document via SyncManager atomic operation."""
    try:
        _check_rate_limit(current_user)

        # Validate path and filename
        full_path = validate_path(request.path, RAG_DOCUMENTS_DIR)
        file_path = Path(full_path)
        validate_filename(file_path.name)

        # Validate and normalize content
        content = validate_markdown_content(request.content)
        content = normalize_line_endings(content)
        content = markdown_round_trip(content)  # Format consistently

        # Delegate to SyncManager for atomic create (filesystem + DB + sync status)
        user_id = current_user.get("user_id", "unknown")
        sm = get_sync_manager()
        await sm.create_document_atomic(request.path, content, user_id)

        # Read back metadata from the newly created file
        metadata = get_file_metadata(file_path)

        # Broadcast WebSocket event
        try:
            ws = get_websocket_manager()
            await ws.send_document_event("document_created", request.path)
        except Exception:
            pass  # Non-critical

        return Document(
            path=request.path,
            content=content,
            metadata=metadata
        )

    except DocumentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        _audit_log("create_failed", request.path, current_user.get("user_id", "unknown"), status="failure", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create document: {str(e)}"
        )


@router.get("/{path:path}", response_model=Document)
async def get_document(
    path: str,
    current_user: dict = Depends(get_current_user)
):
    """Get document content and metadata."""
    try:
        # Validate and resolve path
        full_path = validate_path(path, RAG_DOCUMENTS_DIR)
        file_path = Path(full_path)

        if not file_path.exists():
            raise DocumentNotFoundError(path)

        if not file_path.is_file():
            raise DocumentValidationError(f"Path is not a file: {path}")

        # Read content
        content = file_path.read_text(encoding="utf-8")
        metadata = get_file_metadata(file_path)

        return Document(
            path=path,
            content=content,
            metadata=metadata
        )

    except DocumentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error reading document {path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read document: {str(e)}"
        )


@router.put("/{path:path}", response_model=Document)
async def update_document(
    path: str,
    request: UpdateDocumentRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    current_user: dict = Depends(get_current_user)
):
    """Update document content via SyncManager atomic operation."""
    try:
        _check_rate_limit(current_user)

        # Validate path
        full_path = validate_path(path, RAG_DOCUMENTS_DIR)
        file_path = Path(full_path)

        if not file_path.exists():
            raise DocumentNotFoundError(path)

        # Validate and normalize content
        content = validate_markdown_content(request.content)
        content = normalize_line_endings(content)
        content = markdown_round_trip(content)

        # Parse expected_mtime for conflict detection
        expected_mtime = None
        if request.expected_mtime:
            try:
                expected_mtime = datetime.fromisoformat(request.expected_mtime)
            except (ValueError, TypeError):
                raise DocumentValidationError("Invalid expected_mtime format (use ISO 8601)")

        # Delegate to SyncManager for atomic update (backup, write, re-chunk, rollback)
        user_id = current_user.get("user_id", "unknown")
        sm = get_sync_manager()
        await sm.update_document_atomic(path, content, user_id, expected_mtime=expected_mtime)

        # Read back metadata from the updated file
        metadata = get_file_metadata(file_path)

        # Broadcast WebSocket event
        try:
            ws = get_websocket_manager()
            await ws.send_document_event("document_updated", path)
        except Exception:
            pass  # Non-critical

        return Document(
            path=path,
            content=content,
            metadata=metadata
        )

    except DocumentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        _audit_log("update_failed", path, current_user.get("user_id", "unknown"), status="failure", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update document: {str(e)}"
        )


@router.delete("/{path:path}", response_model=DeleteResponse)
async def delete_document(
    path: str,
    pool: asyncpg.Pool = Depends(get_pool),
    current_user: dict = Depends(get_current_user)
):
    """Delete a document via SyncManager atomic operation."""
    try:
        _check_rate_limit(current_user)

        # Validate path
        full_path = validate_path(path, RAG_DOCUMENTS_DIR)
        file_path = Path(full_path)

        if not file_path.is_file():
            if not file_path.exists():
                raise DocumentNotFoundError(path)
            raise DocumentValidationError(f"Path is not a file: {path}")

        # Delegate to SyncManager for atomic delete (backup, DB delete, FS delete, rollback)
        user_id = current_user.get("user_id", "unknown")
        sm = get_sync_manager()
        await sm.delete_document_atomic(path, user_id)

        # Broadcast WebSocket event
        try:
            ws = get_websocket_manager()
            await ws.send_document_event("document_deleted", path)
        except Exception:
            pass  # Non-critical

        return DeleteResponse(
            message="Document deleted successfully",
            path=path
        )

    except DocumentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        _audit_log("delete_failed", path, current_user.get("user_id", "unknown"), status="failure", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )
