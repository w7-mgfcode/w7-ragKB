"""Google Drive watcher for the RAG pipeline.

Watches a Google Drive folder for new/modified/deleted files and
processes them through the RAG pipeline using asyncpg for database
operations and Vertex AI for embeddings.
"""

import asyncio
import io
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.db_handler import delete_document_by_file_id, process_file_for_rag
from common.state_manager import (
    StateManager,
    create_state_manager,
    load_state_from_config,
    save_state_to_config,
)
from common.text_processor import extract_text_from_file

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


class GoogleDriveWatcher:
    """Watches a Google Drive folder and processes files for RAG ingestion."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        credentials_path: str = "credentials.json",
        token_path: str = "token.json",
        folder_id: str = None,
        config_path: str = None,
    ):
        self.pool = pool
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.folder_id = folder_id
        self.service = None
        self.known_files: Dict[str, str] = {}
        self.initialized = False
        self.state_manager: Optional[StateManager] = None
        self.config: Dict[str, Any] = {}

        self.config_path = config_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config.json"
        )
        self._load_config_file()

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
                    "text/html",
                    "text/csv",
                    "application/vnd.google-apps.document",
                    "application/vnd.google-apps.spreadsheet",
                    "application/vnd.google-apps.presentation",
                ],
                "export_mime_types": {
                    "application/vnd.google-apps.document": "text/plain",
                    "application/vnd.google-apps.spreadsheet": "text/csv",
                    "application/vnd.google-apps.presentation": "text/plain",
                },
                "text_processing": {
                    "default_chunk_size": 400,
                    "default_chunk_overlap": 0,
                },
                "last_check_time": "1970-01-01T00:00:00.000Z",
            }

        env_folder_id = os.getenv("RAG_WATCH_FOLDER_ID")
        if env_folder_id:
            self.folder_id = env_folder_id
        elif not self.folder_id:
            self.folder_id = self.config.get("watch_folder_id")

    async def initialize_state(self) -> None:
        """Load state from DB (via StateManager) or fall back to config file."""
        self.state_manager = await create_state_manager(self.pool, "google_drive")

        if self.state_manager:
            state = await self.state_manager.load_state()
            self.last_check_time = state.get("last_check_time") or datetime.strptime(
                "1970-01-01T00:00:00.000Z", "%Y-%m-%dT%H:%M:%S.%fZ"
            )
            self.known_files = state.get("known_files", {})
            logger.info(
                "State from DB — last check: %s, known files: %d",
                self.last_check_time,
                len(self.known_files),
            )
        else:
            state = load_state_from_config(self.config_path)
            self.last_check_time = state.get("last_check_time") or datetime.strptime(
                "1970-01-01T00:00:00.000Z", "%Y-%m-%dT%H:%M:%S.%fZ"
            )
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
    # Google Drive authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> None:
        """Authenticate with Google Drive API (service account or OAuth2)."""
        creds = None

        # Priority 1: service account from env var
        sa_json = os.getenv("GOOGLE_DRIVE_CREDENTIALS_JSON")
        if sa_json:
            try:
                info = json.loads(sa_json)
                creds = ServiceAccountCredentials.from_service_account_info(info, scopes=SCOPES)
                logger.info("Using service account auth for Google Drive")
            except (json.JSONDecodeError, ValueError):
                logger.exception("Error parsing service account credentials")

        # Priority 2: existing OAuth2 token
        if not creds and os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_info(
                    json.loads(open(self.token_path).read()), SCOPES
                )
            except Exception:
                logger.exception("Error loading OAuth2 token")

        # Priority 3: OAuth2 interactive flow
        if not creds:
            if (
                creds
                and hasattr(creds, "expired")
                and creds.expired
                and hasattr(creds, "refresh_token")
                and creds.refresh_token
            ):
                try:
                    creds.refresh(Request())
                except RefreshError:
                    creds = self._oauth2_authenticate()
            else:
                creds = self._oauth2_authenticate()

        self.service = build("drive", "v3", credentials=creds)
        logger.info("Google Drive API service initialized")

    def _oauth2_authenticate(self) -> Credentials:
        """Run the OAuth2 installed-app flow."""
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(
                f"Credentials file not found: {self.credentials_path}. "
                "Set GOOGLE_DRIVE_CREDENTIALS_JSON or provide OAuth2 credentials."
            )
        flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
        creds = flow.run_local_server(port=0)
        try:
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())
        except Exception:
            logger.exception("Could not save OAuth2 token")
        return creds

    # ------------------------------------------------------------------
    # Google Drive helpers
    # ------------------------------------------------------------------

    def get_folder_contents(self, folder_id: str, time_str: str) -> List[Dict[str, Any]]:
        """Recursively get files modified after *time_str* in a folder."""
        query = f"(modifiedTime > '{time_str}' or createdTime > '{time_str}') and '{folder_id}' in parents"
        results = self.service.files().list(
            q=query,
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType, webViewLink, modifiedTime, createdTime, trashed)",
        ).execute()
        items = results.get("files", [])

        folder_query = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder'"
        folder_results = self.service.files().list(
            q=folder_query, pageSize=100, fields="files(id)"
        ).execute()
        for sub in folder_results.get("files", []):
            items.extend(self.get_folder_contents(sub["id"], time_str))

        return items

    def get_changes(self) -> List[Dict[str, Any]]:
        """Get files changed since last_check_time."""
        if not self.service:
            self.authenticate()

        time_str = self.last_check_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        if self.folder_id:
            files = self.get_folder_contents(self.folder_id, time_str)
        else:
            query = f"modifiedTime > '{time_str}' or createdTime > '{time_str}'"
            results = self.service.files().list(
                q=query,
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType, webViewLink, modifiedTime, createdTime, trashed)",
            ).execute()
            files = results.get("files", [])

        self.last_check_time = datetime.now(timezone.utc)
        return files

    def download_file(self, file_id: str, mime_type: str) -> Optional[bytes]:
        """Download a file from Google Drive."""
        if not self.service:
            self.authenticate()
        try:
            buf = io.BytesIO()
            export_types = self.config.get("export_mime_types", {})
            if mime_type in export_types:
                request = self.service.files().export_media(
                    fileId=file_id, mimeType=export_types[mime_type]
                )
            else:
                request = self.service.files().get_media(fileId=file_id)

            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            buf.seek(0)
            return buf.read()
        except Exception:
            logger.exception("Error downloading file %s", file_id)
            return None

    def check_for_deleted_files(self) -> List[str]:
        """Return IDs of known files that are trashed or deleted."""
        if not self.service:
            self.authenticate()
        deleted: List[str] = []
        for fid in list(self.known_files.keys()):
            try:
                meta = self.service.files().get(fileId=fid, fields="trashed,name").execute()
                if meta.get("trashed", False):
                    deleted.append(fid)
            except Exception as e:
                if "File not found" in str(e) or "404" in str(e):
                    deleted.append(fid)
                else:
                    logger.exception("Error checking file %s", fid)
        return deleted

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    async def process_file(self, file: Dict[str, Any]) -> None:
        """Process a single Google Drive file through the RAG pipeline."""
        file_id = file["id"]
        file_name = file["name"]
        mime_type = file["mimeType"]
        web_view_link = file.get("webViewLink", "")
        is_trashed = file.get("trashed", False)

        if is_trashed:
            logger.info("File '%s' trashed — removing from DB", file_name)
            await delete_document_by_file_id(self.pool, file_id)
            self.known_files.pop(file_id, None)
            return

        supported = self.config.get("supported_mime_types", [])
        if not any(mime_type.startswith(t) for t in supported):
            logger.info("Skipping unsupported MIME type: %s", mime_type)
            return

        file_content = self.download_file(file_id, mime_type)
        if not file_content:
            logger.warning("Failed to download '%s' (ID: %s)", file_name, file_id)
            return

        text = extract_text_from_file(file_content, mime_type, file_name, self.config)
        if not text:
            logger.warning("No text extracted from '%s' (ID: %s)", file_name, file_id)
            return

        success = await process_file_for_rag(
            self.pool,
            file_content,
            text,
            file_id,
            web_view_link,
            file_name,
            mime_type,
            self.config,
        )

        self.known_files[file_id] = file.get("modifiedTime")

        if success:
            logger.info("Processed '%s' (ID: %s)", file_name, file_id)
        else:
            logger.error("Failed to process '%s' (ID: %s)", file_name, file_id)

    async def check_for_changes(self) -> Dict[str, Any]:
        """Run one check cycle: scan for new/modified/deleted files."""
        start = time.time()
        stats = {
            "files_processed": 0,
            "files_deleted": 0,
            "errors": 0,
            "duration": 0.0,
            "initialized": False,
        }

        try:
            if not self.service:
                self.authenticate()

            if not self.initialized:
                await self._initial_scan(stats)
                self.initialized = True
                stats["initialized"] = True

            changed = self.get_changes()
            deleted_ids = self.check_for_deleted_files()

            for f in changed:
                try:
                    await self.process_file(f)
                    self.known_files[f["id"]] = f.get("modifiedTime")
                    stats["files_processed"] += 1
                except Exception:
                    logger.exception("Error processing %s", f.get("name"))
                    stats["errors"] += 1

            for fid in deleted_ids:
                try:
                    await delete_document_by_file_id(self.pool, fid)
                    self.known_files.pop(fid, None)
                    stats["files_deleted"] += 1
                except Exception:
                    logger.exception("Error deleting %s", fid)
                    stats["errors"] += 1

            stats["duration"] = time.time() - start
            await self.save_state()
            return stats

        except Exception:
            stats["duration"] = time.time() - start
            stats["errors"] += 1
            logger.exception("Error in check_for_changes")
            raise

    async def _initial_scan(self, stats: Dict[str, Any]) -> None:
        """Handle the first-run scan."""
        logger.info("Performing initial scan...")
        time_str = self.last_check_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        if self.folder_id:
            changed = self.get_folder_contents(self.folder_id, time_str)
        else:
            query = f"modifiedTime > '{time_str}' or createdTime > '{time_str}'"
            results = self.service.files().list(
                q=query,
                pageSize=1000,
                fields="nextPageToken, files(id, name, mimeType, webViewLink, modifiedTime, createdTime, trashed)",
            ).execute()
            changed = results.get("files", [])

        for f in changed:
            if f.get("trashed", False):
                continue
            try:
                await self.process_file(f)
                self.known_files[f["id"]] = f.get("modifiedTime")
                stats["files_processed"] += 1
            except Exception:
                logger.exception("Error processing %s during init", f.get("name"))
                stats["errors"] += 1

        self.last_check_time = datetime.now(timezone.utc)
        logger.info("Initial scan: %d processed", stats["files_processed"])

    async def watch_for_changes(self, interval_seconds: int = 60) -> None:
        """Continuously watch for changes at the given interval."""
        folder_msg = f" in folder {self.folder_id}" if self.folder_id else ""
        logger.info("Starting Drive watcher%s (interval=%ds)", folder_msg, interval_seconds)
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
            logger.info("Drive watcher cancelled")
        except Exception:
            logger.exception("Drive watcher error")
