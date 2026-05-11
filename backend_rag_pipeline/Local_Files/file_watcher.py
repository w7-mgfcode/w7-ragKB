"""Local file watcher for the RAG pipeline.

Watches a directory for new/modified/deleted files and processes them
through the RAG pipeline using asyncpg for database operations and
Vertex AI for embeddings.
"""

import asyncio
import json
import mimetypes
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.text_processor import extract_text_from_file
from common.db_handler import process_file_for_rag, delete_document_by_file_id
from common.state_manager import (
    StateManager,
    create_state_manager,
    load_state_from_config,
    save_state_to_config,
)

import logging

logger = logging.getLogger(__name__)


class LocalFileWatcher:
    """Watches a local directory and processes files for RAG ingestion."""

    # Valid sync statuses matching 005_document_sync_status.sql CHECK constraint
    SYNC_IN_SYNC = "in_sync"
    SYNC_PROCESSING = "processing"
    SYNC_ERROR = "error"
    SYNC_PENDING = "pending_indexing"

    def __init__(
        self,
        pool: asyncpg.Pool,
        watch_directory: str = None,
        config_path: str = None,
    ):
        self.pool = pool
        self.state_manager: Optional[StateManager] = None
        self.known_files: Dict[str, str] = {}
        self.initialized = False
        self.config: Dict[str, Any] = {}
        self._concurrency_semaphore = asyncio.Semaphore(
            int(os.getenv("WATCHER_MAX_CONCURRENT_FILES", "3"))
        )

        self.config_path = config_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config.json"
        )

        self._load_config_file()

        if watch_directory:
            self.watch_directory = watch_directory
        else:
            self.watch_directory = self.config.get("watch_directory", "data")

        self.watch_directory = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), self.watch_directory
        )

        mimetypes.init()
        logger.info("LocalFileWatcher initialized. Watching: %s", self.watch_directory)

    @staticmethod
    def _default_last_check_time() -> datetime:
        """Epoch fallback as a timezone-aware UTC datetime."""
        return datetime.strptime("1970-01-01T00:00:00.000Z", "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )

    @staticmethod
    def _to_utc_aware(dt: datetime) -> datetime:
        """Normalize datetimes to timezone-aware UTC for safe comparisons."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _load_config_file(self) -> None:
        """Load configuration from the JSON config file."""
        try:
            with open(self.config_path, "r") as f:
                self.config = json.load(f)
            logger.info("Loaded config from %s", self.config_path)
        except Exception:
            logger.exception("Error loading config, using defaults")
            self.config = {
                "supported_mime_types": [
                    "application/pdf",
                    "text/plain",
                    "text/csv",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ],
                "tabular_mime_types": [
                    "text/csv",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ],
                "text_processing": {
                    "default_chunk_size": 400,
                    "default_chunk_overlap": 0,
                },
                "last_check_time": "1970-01-01T00:00:00.000Z",
            }

        env_directory = os.getenv("RAG_WATCH_DIRECTORY")
        if env_directory:
            self.watch_directory = env_directory
            os.makedirs(self.watch_directory, exist_ok=True)

    async def initialize_state(self) -> None:
        """Load state from DB (via StateManager) or fall back to config file."""
        self.state_manager = await create_state_manager(self.pool, "local_files")

        if self.state_manager:
            state = await self.state_manager.load_state()
            raw_last_check = state.get("last_check_time") or self._default_last_check_time()
            self.last_check_time = self._to_utc_aware(raw_last_check)
            self.known_files = state.get("known_files", {})
            logger.info(
                "State from DB — last check: %s, known files: %d",
                self.last_check_time,
                len(self.known_files),
            )
        else:
            state = load_state_from_config(self.config_path)
            raw_last_check = state.get("last_check_time") or self._default_last_check_time()
            self.last_check_time = self._to_utc_aware(raw_last_check)
            self.known_files = {}
            logger.info("State from config — last check: %s", self.last_check_time)

    async def save_last_check_time(self) -> None:
        """Persist the last check time."""
        if self.state_manager:
            await self.state_manager.update_last_check_time(self.last_check_time)
        else:
            save_state_to_config(self.config_path, self.last_check_time, self.config)

    async def save_state(self) -> None:
        """Persist full state (last_check_time + known_files)."""
        if self.state_manager:
            await self.state_manager.save_state(
                last_check_time=self.last_check_time,
                known_files=self.known_files,
            )
        else:
            await self.save_last_check_time()

    # ------------------------------------------------------------------
    # File scanning helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_mime_type(file_path: str) -> str:
        """Return the MIME type for a file path."""
        ext_map = {
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".csv": "text/csv",
            ".pdf": "application/pdf",
            ".txt": "text/plain",
        }
        _, ext = os.path.splitext(file_path.lower())
        if ext in ext_map:
            return ext_map[ext]
        mime, _ = mimetypes.guess_type(file_path)
        return mime or "text/plain"

    @staticmethod
    def get_file_content(file_path: str) -> Optional[bytes]:
        """Read file bytes, returning None on failure."""
        try:
            with open(file_path, "rb") as f:
                return f.read()
        except Exception:
            logger.exception("Error reading file %s", file_path)
            return None

    def _scan_directory(self) -> List[Dict[str, Any]]:
        """Walk the watch directory and return file info dicts for changed files."""
        changed: List[Dict[str, Any]] = []
        for root, _, files in os.walk(self.watch_directory):
            for name in files:
                path = os.path.join(root, name)
                stat = os.stat(path)
                mod_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                create_time = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)

                if (
                    path not in self.known_files
                    or mod_time > self.last_check_time
                    or create_time > self.last_check_time
                ):
                    changed.append(
                        {
                            "id": path,
                            "name": name,
                            "mimeType": self.get_mime_type(path),
                            "webViewLink": f"file://{path}",
                            "modifiedTime": mod_time.isoformat(),
                            "createdTime": create_time.isoformat(),
                            "trashed": False,
                        }
                    )
        return changed

    def _check_deleted(self) -> List[str]:
        """Return file paths in known_files that no longer exist on disk."""
        return [p for p in self.known_files if not os.path.exists(p)]

    # ------------------------------------------------------------------
    # Sync status helpers (writes directly to shared PostgreSQL)
    # ------------------------------------------------------------------

    def _get_relative_path(self, abs_path: str) -> str:
        """Convert absolute file path to relative path for sync status."""
        try:
            return os.path.relpath(abs_path, self.watch_directory)
        except ValueError:
            return abs_path

    async def _update_sync_status(
        self,
        rel_path: str,
        sync_status: str,
        *,
        error_message: Optional[str] = None,
        chunk_count: Optional[int] = None,
        filesystem_mtime: Optional[datetime] = None,
    ) -> None:
        """Write sync status directly to document_sync_status table."""
        now = datetime.now(timezone.utc)
        try:
            await self.pool.execute(
                """
                INSERT INTO document_sync_status
                    (file_path, sync_status, error_message, chunk_count, source,
                     filesystem_mtime, last_checked)
                VALUES ($1, $2, $3, COALESCE($4, 0), 'filesystem', $5, $6)
                ON CONFLICT (file_path) DO UPDATE SET
                    sync_status      = EXCLUDED.sync_status,
                    error_message    = EXCLUDED.error_message,
                    chunk_count      = COALESCE(EXCLUDED.chunk_count, document_sync_status.chunk_count),
                    filesystem_mtime = COALESCE(EXCLUDED.filesystem_mtime, document_sync_status.filesystem_mtime),
                    last_checked     = EXCLUDED.last_checked
                """,
                rel_path,
                sync_status,
                error_message,
                chunk_count,
                filesystem_mtime,
                now,
            )
        except Exception:
            logger.exception("Failed to update sync status for %s", rel_path)

    def _audit_watcher(self, action: str, path: str, **extra: Any) -> None:
        """Structured audit log for file watcher actions."""
        entry = {"event": f"watcher.{action}", "path": path, **extra}
        logger.info(json.dumps(entry))

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    async def process_file(self, file: Dict[str, Any]) -> None:
        """Process a single file through the RAG pipeline with sync tracking."""
        file_path = file["id"]
        file_name = file["name"]
        mime_type = file["mimeType"]
        web_view_link = file["webViewLink"]
        rel_path = self._get_relative_path(file_path)

        supported = self.config.get("supported_mime_types", [])
        if not any(mime_type.startswith(t) for t in supported):
            logger.info("Skipping unsupported MIME type: %s", mime_type)
            return

        # Set sync status to processing
        fs_mtime = None
        try:
            fs_mtime = datetime.fromtimestamp(os.stat(file_path).st_mtime, tz=timezone.utc)
        except OSError:
            pass
        await self._update_sync_status(rel_path, self.SYNC_PROCESSING, filesystem_mtime=fs_mtime)

        file_content = self.get_file_content(file_path)
        if not file_content:
            logger.warning("Failed to read file '%s'", file_name)
            await self._update_sync_status(rel_path, self.SYNC_ERROR, error_message="Failed to read file")
            return

        text = extract_text_from_file(file_content, mime_type, file_name, self.config)
        if not text:
            logger.warning("No text extracted from '%s'", file_name)
            await self._update_sync_status(rel_path, self.SYNC_ERROR, error_message="No text extracted")
            return

        async with self._concurrency_semaphore:
            success = await process_file_for_rag(
                self.pool,
                file_content,
                text,
                file_path,
                web_view_link,
                file_name,
                mime_type,
                self.config,
            )

        self.known_files[file_path] = file.get("modifiedTime")

        if success:
            logger.info("Processed file '%s'", file_name)
            await self._update_sync_status(
                rel_path, self.SYNC_IN_SYNC,
                filesystem_mtime=fs_mtime,
            )
            self._audit_watcher("process", rel_path, status="success")
        else:
            logger.error("Failed to process file '%s'", file_name)
            await self._update_sync_status(
                rel_path, self.SYNC_ERROR,
                error_message="RAG processing failed",
            )
            self._audit_watcher("process", rel_path, status="failure")

    async def check_for_changes(self) -> Dict[str, Any]:
        """Run one check cycle: scan for new/modified/deleted files.

        Returns a stats dict with files_processed, files_deleted, errors,
        duration, and initialized.
        """
        start = time.time()
        stats = {
            "files_processed": 0,
            "files_deleted": 0,
            "errors": 0,
            "duration": 0.0,
            "initialized": False,
        }

        try:
            if not self.initialized:
                await self._initial_scan(stats)
                self.initialized = True
                stats["initialized"] = True

            # Incremental scan
            changed = self._scan_directory()
            deleted_ids = self._check_deleted()

            for f in changed:
                try:
                    await self.process_file(f)
                    stats["files_processed"] += 1
                except Exception:
                    logger.exception("Error processing %s", f.get("name"))
                    stats["errors"] += 1

            for fid in deleted_ids:
                try:
                    await delete_document_by_file_id(self.pool, fid)
                    rel = self._get_relative_path(fid)
                    # Remove sync status row for deleted file
                    try:
                        await self.pool.execute(
                            "DELETE FROM document_sync_status WHERE file_path = $1",
                            rel,
                        )
                    except Exception:
                        pass
                    self.known_files.pop(fid, None)
                    stats["files_deleted"] += 1
                    self._audit_watcher("delete", rel, status="success")
                except Exception:
                    logger.exception("Error deleting %s", fid)
                    stats["errors"] += 1

            self.last_check_time = datetime.now(timezone.utc)
            await self.save_state()

            stats["duration"] = time.time() - start
            return stats

        except Exception:
            stats["duration"] = time.time() - start
            stats["errors"] += 1
            logger.exception("Error in check_for_changes")
            raise

    async def _initial_scan(self, stats: Dict[str, Any]) -> None:
        """Handle the first-run scan: detect deletions and process changes."""
        logger.info("Performing initial scan...")

        # Detect files deleted since last run
        for fid in self._check_deleted():
            try:
                await delete_document_by_file_id(self.pool, fid)
                self.known_files.pop(fid, None)
                stats["files_deleted"] += 1
            except Exception:
                logger.exception("Error deleting %s during init", fid)
                stats["errors"] += 1

        # Scan for new/modified files
        changed = self._scan_directory()
        current_files: Dict[str, str] = {}
        for root, _, files in os.walk(self.watch_directory):
            for name in files:
                path = os.path.join(root, name)
                mod_time = datetime.fromtimestamp(os.stat(path).st_mtime, tz=timezone.utc)
                current_files[path] = mod_time.isoformat()

        self.known_files = current_files

        for f in changed:
            try:
                await self.process_file(f)
                stats["files_processed"] += 1
            except Exception:
                logger.exception("Error processing %s during init", f.get("name"))
                stats["errors"] += 1

        self.last_check_time = datetime.now(timezone.utc)
        logger.info(
            "Initial scan: %d processed, %d deleted",
            stats["files_processed"],
            stats["files_deleted"],
        )

    async def watch_for_changes(self, interval_seconds: int = 60) -> None:
        """Continuously watch for changes at the given interval."""
        logger.info(
            "Starting watcher on %s (interval=%ds)",
            self.watch_directory,
            interval_seconds,
        )
        try:
            while True:
                stats = await self.check_for_changes()
                logger.info(
                    "Check: %d processed, %d deleted, %d errors, %.2fs",
                    stats["files_processed"],
                    stats["files_deleted"],
                    stats["errors"],
                    stats["duration"],
                )
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("Watcher cancelled")
        except Exception:
            logger.exception("Watcher error")
