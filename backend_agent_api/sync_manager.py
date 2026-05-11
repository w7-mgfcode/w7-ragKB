"""Central coordinator for document synchronization between filesystem and database.

Manages sync status tracking, atomic document operations with rollback,
conflict detection and resolution, and manual re-indexing with concurrency control.
"""

import asyncio
import json as _json
import logging
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg
from pydantic import BaseModel

from document_exceptions import (
    AtomicOperationError,
    DocumentConflictError,
    DocumentNotFoundError,
    DocumentValidationError,
    ReindexError,
)
from document_validation import validate_path

logger = logging.getLogger(__name__)

RAG_DOCUMENTS_DIR = os.getenv("RAG_DOCUMENTS_DIR", "/rag-documents")


# ==============================================================================
# Models
# ==============================================================================


class SyncStatus(str, Enum):
    """Document synchronization status."""

    IN_SYNC = "in_sync"
    OUT_OF_SYNC = "out_of_sync"
    PROCESSING = "processing"
    ERROR = "error"
    ORPHANED_CHUNKS = "orphaned_chunks"
    PENDING_INDEXING = "pending_indexing"


class DocumentSyncInfo(BaseModel):
    """Sync information for a document."""

    file_path: str
    sync_status: SyncStatus
    filesystem_mtime: Optional[datetime] = None
    database_mtime: Optional[datetime] = None
    chunk_count: int = 0
    error_message: Optional[str] = None
    source: str = "filesystem"
    last_checked: Optional[datetime] = None


class ConflictInfo(BaseModel):
    """Information about a document conflict."""

    file_path: str
    filesystem_content: str
    database_content: str
    filesystem_mtime: datetime
    database_mtime: datetime
    conflict_type: str  # "content_mismatch", "missing_file", "missing_chunks"


class ConflictResolution(BaseModel):
    """Resolution strategy for a document conflict."""

    strategy: str  # "keep_filesystem", "keep_database", "manual_merge"
    merged_content: Optional[str] = None


# ==============================================================================
# SyncManager
# ==============================================================================


class SyncManager:
    """Manages document synchronization between filesystem and database."""

    def __init__(self, pool: asyncpg.Pool, rag_documents_dir: str = None):
        self.pool = pool
        self.rag_documents_dir = Path(rag_documents_dir or RAG_DOCUMENTS_DIR)
        self._reindex_semaphore = asyncio.Semaphore(
            int(os.getenv("SYNC_REINDEX_CONCURRENCY", "3"))
        )
        self._reindex_timeout = int(os.getenv("SYNC_REINDEX_TIMEOUT", "300"))
        self._embedding_batch_size = int(os.getenv("SYNC_EMBEDDING_BATCH_SIZE", "10"))
        self._embedding_max_retries = 3
        self._document_locks: Dict[str, asyncio.Lock] = {}
        self._embedding_client = None

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    def _ensure_embedding_client(self):
        """Lazy-init the Vertex AI embedding client."""
        if self._embedding_client is None:
            from vertex_embeddings import VertexEmbeddingClient

            self._embedding_client = VertexEmbeddingClient()

    async def _get_embedding(self, text: str) -> list:
        """Generate a single query embedding."""
        self._ensure_embedding_client()
        return await self._embedding_client.create_query_embedding(text)

    async def _get_embedding_with_retry(self, text: str) -> list:
        """Generate a single embedding with exponential backoff retry."""
        for attempt in range(self._embedding_max_retries):
            try:
                return await self._get_embedding(text)
            except Exception as exc:
                if attempt == self._embedding_max_retries - 1:
                    raise
                delay = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    "Embedding retry %d/%d for text[:50]=%r: %s",
                    attempt + 1, self._embedding_max_retries, text[:50], exc,
                )
                await asyncio.sleep(delay)

    async def _get_embeddings_batch(self, texts: List[str]) -> List[list]:
        """Generate embeddings for multiple texts in batches with retry."""
        self._ensure_embedding_client()
        all_embeddings: List[list] = []
        for i in range(0, len(texts), self._embedding_batch_size):
            batch = texts[i : i + self._embedding_batch_size]
            for attempt in range(self._embedding_max_retries):
                try:
                    embeddings = await asyncio.to_thread(
                        self._embedding_client.create_embeddings,
                        batch,
                        "RETRIEVAL_DOCUMENT",
                    )
                    all_embeddings.extend(embeddings)
                    break
                except Exception as exc:
                    if attempt == self._embedding_max_retries - 1:
                        raise
                    delay = 2 ** attempt
                    logger.warning(
                        "Batch embedding retry %d/%d (batch %d-%d): %s",
                        attempt + 1, self._embedding_max_retries,
                        i, i + len(batch), exc,
                    )
                    await asyncio.sleep(delay)
        return all_embeddings

    # ------------------------------------------------------------------
    # Per-document locking
    # ------------------------------------------------------------------

    def _get_document_lock(self, file_path: str) -> asyncio.Lock:
        if file_path not in self._document_locks:
            self._document_locks[file_path] = asyncio.Lock()
        return self._document_locks[file_path]

    # ------------------------------------------------------------------
    # Sync status queries
    # ------------------------------------------------------------------

    async def get_sync_status(self, file_path: str) -> DocumentSyncInfo:
        """Get current sync status for a single document."""
        row = await self.pool.fetchrow(
            "SELECT * FROM document_sync_status WHERE file_path = $1", file_path
        )
        if row:
            return DocumentSyncInfo(
                file_path=row["file_path"],
                sync_status=SyncStatus(row["sync_status"]),
                filesystem_mtime=row["filesystem_mtime"],
                database_mtime=row["database_mtime"],
                chunk_count=row["chunk_count"],
                error_message=row["error_message"],
                source=row["source"],
                last_checked=row["last_checked"],
            )
        # No tracking row — compute on the fly
        return await self._compute_sync_info(file_path)

    async def get_all_sync_statuses(self) -> List[DocumentSyncInfo]:
        """Get sync status for every tracked document."""
        rows = await self.pool.fetch(
            "SELECT * FROM document_sync_status ORDER BY file_path"
        )
        results = [
            DocumentSyncInfo(
                file_path=r["file_path"],
                sync_status=SyncStatus(r["sync_status"]),
                filesystem_mtime=r["filesystem_mtime"],
                database_mtime=r["database_mtime"],
                chunk_count=r["chunk_count"],
                error_message=r["error_message"],
                source=r["source"],
                last_checked=r["last_checked"],
            )
            for r in rows
        ]
        return results

    async def update_sync_status(
        self,
        file_path: str,
        status: SyncStatus,
        *,
        error_message: Optional[str] = None,
        chunk_count: Optional[int] = None,
        source: Optional[str] = None,
        filesystem_mtime: Optional[datetime] = None,
        database_mtime: Optional[datetime] = None,
    ) -> None:
        """Upsert sync status for a document, logging transitions."""
        # Fetch current status for audit logging
        old_status = None
        try:
            old_row = await self.pool.fetchrow(
                "SELECT sync_status FROM document_sync_status WHERE file_path = $1",
                file_path,
            )
            if old_row:
                old_status = str(old_row["sync_status"]) if old_row["sync_status"] else None
        except Exception:
            pass  # Non-critical — don't block status updates for audit

        now = datetime.now(timezone.utc)
        await self.pool.execute(
            """
            INSERT INTO document_sync_status
                (file_path, sync_status, error_message, chunk_count, source,
                 filesystem_mtime, database_mtime, last_checked)
            VALUES ($1, $2, $3, COALESCE($4, 0), COALESCE($5, 'filesystem'),
                    $6, $7, $8)
            ON CONFLICT (file_path) DO UPDATE SET
                sync_status      = EXCLUDED.sync_status,
                error_message    = EXCLUDED.error_message,
                chunk_count      = COALESCE(EXCLUDED.chunk_count, document_sync_status.chunk_count),
                source           = COALESCE(EXCLUDED.source, document_sync_status.source),
                filesystem_mtime = COALESCE(EXCLUDED.filesystem_mtime, document_sync_status.filesystem_mtime),
                database_mtime   = COALESCE(EXCLUDED.database_mtime, document_sync_status.database_mtime),
                last_checked     = EXCLUDED.last_checked
            """,
            file_path,
            status.value,
            error_message,
            chunk_count,
            source,
            filesystem_mtime,
            database_mtime,
            now,
        )

        # Log status transitions
        if old_status and old_status != status.value:
            self._audit_status_change(file_path, old_status, status.value)

    # ------------------------------------------------------------------
    # Sync status computation
    # ------------------------------------------------------------------

    async def _compute_sync_info(self, file_path: str) -> DocumentSyncInfo:
        """Compute sync status for a document not yet tracked."""
        abs_path = self.rag_documents_dir / file_path
        file_exists = abs_path.is_file()

        db_row = await self.pool.fetchrow(
            """
            SELECT COUNT(*) as cnt,
                   MAX(COALESCE((metadata->>'last_modified')::timestamptz, NOW())) as db_mtime
            FROM documents
            WHERE metadata->>'file_path' = $1
            """,
            file_path,
        )
        chunk_count = int(db_row["cnt"]) if db_row else 0
        db_mtime = db_row["db_mtime"] if db_row else None

        if file_exists and chunk_count > 0:
            fs_mtime = datetime.fromtimestamp(abs_path.stat().st_mtime, tz=timezone.utc)
            if db_mtime and fs_mtime > db_mtime:
                sync_st = SyncStatus.OUT_OF_SYNC
            else:
                sync_st = SyncStatus.IN_SYNC
        elif file_exists and chunk_count == 0:
            fs_mtime = datetime.fromtimestamp(abs_path.stat().st_mtime, tz=timezone.utc)
            sync_st = SyncStatus.PENDING_INDEXING
        elif not file_exists and chunk_count > 0:
            fs_mtime = None
            sync_st = SyncStatus.ORPHANED_CHUNKS
        else:
            fs_mtime = None
            sync_st = SyncStatus.PENDING_INDEXING

        return DocumentSyncInfo(
            file_path=file_path,
            sync_status=sync_st,
            filesystem_mtime=fs_mtime,
            database_mtime=db_mtime,
            chunk_count=chunk_count,
            source="filesystem",
            last_checked=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    async def check_conflict(
        self, file_path: str, expected_mtime: Optional[datetime] = None
    ) -> Optional[ConflictInfo]:
        """Check if filesystem and expected state diverge."""
        abs_path = self.rag_documents_dir / file_path
        if not abs_path.is_file():
            return None

        fs_mtime = datetime.fromtimestamp(abs_path.stat().st_mtime, tz=timezone.utc)

        if expected_mtime is not None:
            # Compare with a small tolerance (1 second)
            diff = abs((fs_mtime - expected_mtime).total_seconds())
            if diff > 1.0:
                import db_documents

                db_content = await db_documents.get_document_content(
                    self.pool, file_path
                )
                fs_content = abs_path.read_text(encoding="utf-8")
                return ConflictInfo(
                    file_path=file_path,
                    filesystem_content=fs_content,
                    database_content=db_content or "",
                    filesystem_mtime=fs_mtime,
                    database_mtime=expected_mtime,
                    conflict_type="content_mismatch",
                )
        return None

    # ------------------------------------------------------------------
    # Atomic operations
    # ------------------------------------------------------------------

    async def create_document_atomic(
        self, file_path: str, content: str, user_id: str
    ) -> DocumentSyncInfo:
        """Create a document atomically on filesystem + database."""
        lock = self._get_document_lock(file_path)
        async with lock:
            abs_path = self.rag_documents_dir / file_path
            if abs_path.exists():
                raise DocumentConflictError(file_path)

            await self.update_sync_status(file_path, SyncStatus.PROCESSING, source="browser")

            try:
                # Write to filesystem
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text(content, encoding="utf-8")

                # Chunk and embed
                chunk_count = await self._chunk_and_insert(file_path, content, abs_path)

                fs_mtime = datetime.fromtimestamp(
                    abs_path.stat().st_mtime, tz=timezone.utc
                )
                now = datetime.now(timezone.utc)
                await self.update_sync_status(
                    file_path,
                    SyncStatus.IN_SYNC,
                    chunk_count=chunk_count,
                    source="browser",
                    filesystem_mtime=fs_mtime,
                    database_mtime=now,
                )
                self._audit("create", file_path, user_id)
                return await self.get_sync_status(file_path)

            except Exception as exc:
                # Rollback: remove filesystem file
                if abs_path.exists():
                    abs_path.unlink()
                await self.update_sync_status(
                    file_path, SyncStatus.ERROR, error_message=str(exc), source="browser"
                )
                self._audit("create", file_path, user_id, error=str(exc))
                raise AtomicOperationError("create", file_path, exc) from exc

    async def update_document_atomic(
        self,
        file_path: str,
        content: str,
        user_id: str,
        expected_mtime: Optional[datetime] = None,
    ) -> DocumentSyncInfo:
        """Update a document atomically with backup and rollback."""
        lock = self._get_document_lock(file_path)
        async with lock:
            abs_path = self.rag_documents_dir / file_path
            if not abs_path.is_file():
                raise DocumentNotFoundError(file_path)

            # Conflict check
            conflict = await self.check_conflict(file_path, expected_mtime)
            if conflict:
                raise DocumentConflictError(file_path)

            await self.update_sync_status(file_path, SyncStatus.PROCESSING)

            backup_path = abs_path.with_suffix(".md.bak")
            try:
                # Backup
                abs_path.rename(backup_path)

                # Write new content
                abs_path.write_text(content, encoding="utf-8")

                # Re-chunk
                import db_documents

                await db_documents.delete_document_by_path(self.pool, file_path)
                chunk_count = await self._chunk_and_insert(file_path, content, abs_path)

                # Cleanup backup
                if backup_path.exists():
                    backup_path.unlink()

                fs_mtime = datetime.fromtimestamp(
                    abs_path.stat().st_mtime, tz=timezone.utc
                )
                now = datetime.now(timezone.utc)
                await self.update_sync_status(
                    file_path,
                    SyncStatus.IN_SYNC,
                    chunk_count=chunk_count,
                    filesystem_mtime=fs_mtime,
                    database_mtime=now,
                )
                self._audit("update", file_path, user_id)
                return await self.get_sync_status(file_path)

            except Exception as exc:
                # Rollback
                if abs_path.exists():
                    abs_path.unlink()
                if backup_path.exists():
                    backup_path.rename(abs_path)
                await self.update_sync_status(
                    file_path, SyncStatus.ERROR, error_message=str(exc)
                )
                self._audit("update", file_path, user_id, error=str(exc))
                raise AtomicOperationError("update", file_path, exc) from exc

    async def delete_document_atomic(
        self, file_path: str, user_id: str
    ) -> None:
        """Delete a document atomically with backup for rollback."""
        lock = self._get_document_lock(file_path)
        async with lock:
            abs_path = self.rag_documents_dir / file_path
            if not abs_path.is_file():
                raise DocumentNotFoundError(file_path)

            await self.update_sync_status(file_path, SyncStatus.PROCESSING)

            backup_path = abs_path.with_suffix(".md.deleted")
            try:
                abs_path.rename(backup_path)

                import db_documents

                await db_documents.delete_document_by_path(self.pool, file_path)

                # Success: remove backup and sync status row
                if backup_path.exists():
                    backup_path.unlink()
                await self.pool.execute(
                    "DELETE FROM document_sync_status WHERE file_path = $1", file_path
                )
                self._audit("delete", file_path, user_id)

            except Exception as exc:
                # Rollback
                if backup_path.exists():
                    backup_path.rename(abs_path)
                await self.update_sync_status(
                    file_path, SyncStatus.ERROR, error_message=str(exc)
                )
                self._audit("delete", file_path, user_id, error=str(exc))
                raise AtomicOperationError("delete", file_path, exc) from exc

    # ------------------------------------------------------------------
    # Conflict resolution
    # ------------------------------------------------------------------

    async def resolve_conflict(
        self, file_path: str, resolution: ConflictResolution, user_id: str
    ) -> DocumentSyncInfo:
        """Apply a conflict resolution strategy."""
        abs_path = self.rag_documents_dir / file_path

        if resolution.strategy == "keep_filesystem":
            content = abs_path.read_text(encoding="utf-8")
        elif resolution.strategy == "keep_database":
            import db_documents

            content = await db_documents.get_document_content(self.pool, file_path)
            if content is None:
                raise DocumentNotFoundError(file_path)
        elif resolution.strategy == "manual_merge":
            if not resolution.merged_content:
                raise DocumentValidationError("merged_content required for manual_merge")
            content = resolution.merged_content
        else:
            raise DocumentValidationError(f"Unknown resolution strategy: {resolution.strategy}")

        self._audit(
            "resolve_conflict", file_path, user_id,
            details={"strategy": resolution.strategy},
        )
        return await self.update_document_atomic(file_path, content, user_id)

    # ------------------------------------------------------------------
    # Re-indexing
    # ------------------------------------------------------------------

    async def reindex_document(self, file_path: str, user_id: str) -> DocumentSyncInfo:
        """Re-chunk and re-embed a single document with timeout."""
        async with self._reindex_semaphore:
            abs_path = self.rag_documents_dir / file_path
            if not abs_path.is_file():
                raise DocumentNotFoundError(file_path)

            await self.update_sync_status(file_path, SyncStatus.PROCESSING)
            try:
                return await asyncio.wait_for(
                    self._do_reindex(file_path, abs_path, user_id),
                    timeout=self._reindex_timeout,
                )
            except asyncio.TimeoutError:
                msg = f"Timed out after {self._reindex_timeout}s"
                await self.update_sync_status(
                    file_path, SyncStatus.ERROR, error_message=msg
                )
                self._audit("reindex", file_path, user_id, error=msg)
                raise ReindexError(file_path, msg)
            except ReindexError:
                raise
            except Exception as exc:
                await self.update_sync_status(
                    file_path, SyncStatus.ERROR, error_message=str(exc)
                )
                self._audit("reindex", file_path, user_id, error=str(exc))
                raise ReindexError(file_path, str(exc)) from exc

    async def _do_reindex(
        self, file_path: str, abs_path: Path, user_id: str
    ) -> DocumentSyncInfo:
        """Inner reindex logic (separted for timeout wrapping)."""
        content = abs_path.read_text(encoding="utf-8")

        import db_documents

        await db_documents.delete_document_by_path(self.pool, file_path)
        chunk_count = await self._chunk_and_insert(file_path, content, abs_path)

        fs_mtime = datetime.fromtimestamp(abs_path.stat().st_mtime, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        await self.update_sync_status(
            file_path,
            SyncStatus.IN_SYNC,
            chunk_count=chunk_count,
            filesystem_mtime=fs_mtime,
            database_mtime=now,
        )
        self._audit("reindex", file_path, user_id)
        return await self.get_sync_status(file_path)

    async def reindex_directory(
        self, directory_path: str, user_id: str
    ) -> List[DocumentSyncInfo]:
        """Re-index all documents in a directory recursively."""
        abs_dir = self.rag_documents_dir / directory_path
        if not abs_dir.is_dir():
            raise DocumentNotFoundError(directory_path)

        results: List[DocumentSyncInfo] = []
        for md_file in sorted(abs_dir.rglob("*.md")):
            rel = str(md_file.relative_to(self.rag_documents_dir))
            try:
                info = await self.reindex_document(rel, user_id)
                results.append(info)
            except Exception as exc:
                logger.error("Failed to reindex %s: %s", rel, exc)
                results.append(
                    DocumentSyncInfo(
                        file_path=rel,
                        sync_status=SyncStatus.ERROR,
                        error_message=str(exc),
                    )
                )
        return results

    async def reindex_all(self, user_id: str) -> List[DocumentSyncInfo]:
        """Re-index every document in the rag-documents directory."""
        return await self.reindex_directory("", user_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _chunk_and_insert(
        self, file_path: str, content: str, abs_path: Optional[Path] = None
    ) -> int:
        """Chunk a document and insert with embeddings.

        For files > 10 MB, uses streaming mode with simplified chunking.
        Otherwise uses hierarchical chunking.

        Returns the number of chunks inserted.
        """
        # Large file streaming mode
        if abs_path and abs_path.stat().st_size > self.LARGE_FILE_THRESHOLD:
            logger.info("Large file detected (%d bytes), using streaming mode: %s",
                        abs_path.stat().st_size, file_path)
            return await self._process_large_file(file_path, abs_path)

        from hierarchical_chunking import chunk_document_hierarchical

        file_id = str(uuid.uuid4())
        file_title = Path(file_path).stem.replace("-", " ").replace("_", " ").title()

        chunks = chunk_document_hierarchical(
            content=content,
            file_path=file_path,
            file_id=file_id,
            file_title=file_title,
        )

        await self._insert_chunks_with_embeddings(chunks)
        return len(chunks)

    async def _insert_chunks_with_embeddings(self, chunks: List[Dict]) -> None:
        """Insert hierarchical chunks with parent-child linking.

        Uses batch embedding generation for efficiency.
        Mirrors the logic in documents_router.insert_chunks_with_embeddings.
        """
        doc_chunks = [c for c in chunks if c["chunk_level"] == "document"]
        section_chunks = [c for c in chunks if c["chunk_level"] == "section"]
        leaf_chunks = [c for c in chunks if c["chunk_level"] == "leaf"]

        # Pre-compute all embeddings in batches for efficiency
        all_texts = (
            [c["content"] for c in doc_chunks]
            + [c["content"] for c in section_chunks]
            + [c["content"] for c in leaf_chunks]
        )
        all_embeddings = await self._get_embeddings_batch(all_texts)

        idx = 0  # cursor into all_embeddings

        doc_chunk_id = None
        if doc_chunks:
            dc = doc_chunks[0]
            embedding = all_embeddings[idx]; idx += 1
            doc_chunk_id = await self.pool.fetchval(
                """
                INSERT INTO documents (
                    content, metadata, embedding, chunk_level,
                    parent_chunk_id, category_path, sibling_count, sibling_position
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                dc["content"],
                _json.dumps(dc["metadata"]),
                str(embedding),
                dc["chunk_level"],
                dc["parent_chunk_id"],
                dc["category_path"],
                dc["sibling_count"],
                dc["sibling_position"],
            )

        section_chunk_ids: List[int] = []
        for sc in section_chunks:
            embedding = all_embeddings[idx]; idx += 1
            sid = await self.pool.fetchval(
                """
                INSERT INTO documents (
                    content, metadata, embedding, chunk_level,
                    parent_chunk_id, category_path, sibling_count, sibling_position
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                sc["content"],
                _json.dumps(sc["metadata"]),
                str(embedding),
                sc["chunk_level"],
                doc_chunk_id,
                sc["category_path"],
                sc["sibling_count"],
                sc["sibling_position"],
            )
            section_chunk_ids.append(sid)

        for lc in leaf_chunks:
            embedding = all_embeddings[idx]; idx += 1
            parent_idx = lc.get("parent_section_idx", 0)
            parent_id = (
                section_chunk_ids[parent_idx]
                if parent_idx < len(section_chunk_ids)
                else doc_chunk_id
            )
            await self.pool.execute(
                """
                INSERT INTO documents (
                    content, metadata, embedding, chunk_level,
                    parent_chunk_id, category_path, sibling_count, sibling_position
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                lc["content"],
                _json.dumps(lc["metadata"]),
                str(embedding),
                lc["chunk_level"],
                parent_id,
                lc["category_path"],
                lc["sibling_count"],
                lc["sibling_position"],
            )

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    def _audit(
        self,
        operation: str,
        file_path: str,
        user_id: str,
        *,
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry: Dict[str, Any] = {
            "event": f"sync.{operation}",
            "user_id": user_id,
            "path": file_path,
            "status": "failure" if error else "success",
        }
        if error:
            entry["error"] = error
        if details:
            entry.update(details)
        logger.info(_json.dumps(entry))

    def _audit_status_change(
        self, file_path: str, old_status: str, new_status: str, reason: str = ""
    ) -> None:
        """Log sync status transitions."""
        logger.info(
            _json.dumps(
                {
                    "event": "sync.status_change",
                    "path": file_path,
                    "old_status": old_status,
                    "new_status": new_status,
                    "reason": reason,
                }
            )
        )

    # ------------------------------------------------------------------
    # Chunk hierarchy validation
    # ------------------------------------------------------------------

    async def validate_chunk_hierarchy(self, file_path: str) -> List[str]:
        """Validate parent-child chunk references for a document.

        Returns a list of integrity issues (empty list = valid).
        """
        rows = await self.pool.fetch(
            """
            SELECT id, chunk_level, parent_chunk_id
            FROM documents
            WHERE metadata->>'file_path' = $1
            ORDER BY id
            """,
            file_path,
        )
        if not rows:
            return []

        ids = {r["id"] for r in rows}
        issues: List[str] = []

        for row in rows:
            level = row["chunk_level"]
            parent = row["parent_chunk_id"]
            cid = row["id"]

            if level == "document" and parent is not None:
                issues.append(f"Chunk {cid}: document-level has parent_chunk_id={parent}")
            if level in ("section", "leaf") and parent is not None and parent not in ids:
                issues.append(f"Chunk {cid}: parent_chunk_id={parent} not found in document chunks")
            if level == "section" and parent is None:
                issues.append(f"Chunk {cid}: section-level missing parent_chunk_id")
            if level == "leaf" and parent is None:
                issues.append(f"Chunk {cid}: leaf-level missing parent_chunk_id")

        if issues:
            self._audit(
                "validate_chunks", file_path, "system",
                details={"issue_count": len(issues), "issues": issues[:5]},
            )
        return issues

    # ------------------------------------------------------------------
    # Large file streaming
    # ------------------------------------------------------------------

    LARGE_FILE_THRESHOLD = 10 * 1024 * 1024  # 10 MB

    async def _process_large_file(self, file_path: str, abs_path: Path) -> int:
        """Process files > 10 MB with simplified streaming chunking.

        Falls back to fixed-size chunks to avoid loading the full file
        into memory for hierarchical analysis.
        """
        chunk_size = 2000  # chars per chunk
        overlap = 200
        file_id = str(uuid.uuid4())
        file_title = Path(file_path).stem.replace("-", " ").replace("_", " ").title()
        category_path = str(Path(file_path).parent) if "/" in file_path else ""
        chunk_count = 0

        texts: List[str] = []
        metadata_list: List[Dict] = []
        buffer = ""

        with open(abs_path, "r", encoding="utf-8") as f:
            while True:
                block = f.read(chunk_size)
                if not block:
                    break
                buffer += block
                while len(buffer) >= chunk_size:
                    chunk_text = buffer[:chunk_size]
                    buffer = buffer[chunk_size - overlap:]
                    texts.append(chunk_text)
                    metadata_list.append({
                        "file_id": file_id,
                        "file_path": file_path,
                        "file_title": file_title,
                        "chunk_index": chunk_count,
                    })
                    chunk_count += 1

        if buffer.strip():
            texts.append(buffer)
            metadata_list.append({
                "file_id": file_id,
                "file_path": file_path,
                "file_title": file_title,
                "chunk_index": chunk_count,
            })
            chunk_count += 1

        # Batch-embed and insert
        embeddings = await self._get_embeddings_batch(texts)

        doc_chunk_id = None
        for i, (text, meta, emb) in enumerate(zip(texts, metadata_list, embeddings)):
            level = "document" if i == 0 else "leaf"
            cid = await self.pool.fetchval(
                """
                INSERT INTO documents (
                    content, metadata, embedding, chunk_level,
                    parent_chunk_id, category_path, sibling_count, sibling_position
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                text,
                _json.dumps(meta),
                str(emb),
                level,
                doc_chunk_id if i > 0 else None,
                category_path,
                chunk_count,
                i,
            )
            if i == 0:
                doc_chunk_id = cid

        return chunk_count


# ==============================================================================
# Module-level singleton
# ==============================================================================

_instance: Optional[SyncManager] = None


def get_sync_manager() -> SyncManager:
    """FastAPI dependency — return the global SyncManager instance."""
    if _instance is None:
        raise RuntimeError("SyncManager not initialized — call init during startup")
    return _instance
