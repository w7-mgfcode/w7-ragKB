"""Database State Manager for RAG Pipeline.

Handles persistence of pipeline state (last_check_time, known_files)
in PostgreSQL via asyncpg.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import asyncpg

logger = logging.getLogger(__name__)


class StateManager:
    """Manages pipeline state persistence in PostgreSQL via asyncpg.

    Stores runtime state (last_check_time, known_files) in the
    ``rag_pipeline_state`` table.
    """

    def __init__(self, pool: asyncpg.Pool, pipeline_id: str, pipeline_type: str):
        self.pool = pool
        self.pipeline_id = pipeline_id
        self.pipeline_type = pipeline_type

    async def load_state(self) -> Dict[str, Any]:
        """Load pipeline state from the database."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM rag_pipeline_state WHERE pipeline_id = $1",
                    self.pipeline_id,
                )

            if row:
                last_check_time = row.get("last_check_time")
                known_files = row.get("known_files") or {}
                # asyncpg returns jsonb as dict already
                if isinstance(known_files, str):
                    known_files = json.loads(known_files)
                return {
                    "last_check_time": last_check_time,
                    "known_files": known_files,
                    "exists": True,
                }

            return {"last_check_time": None, "known_files": {}, "exists": False}

        except Exception:
            logger.exception("Error loading state for pipeline %s", self.pipeline_id)
            return {"last_check_time": None, "known_files": {}, "exists": False}

    async def save_state(
        self,
        last_check_time: Optional[datetime] = None,
        known_files: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Upsert pipeline state into the database."""
        try:
            # Ensure timezone-aware
            if last_check_time and last_check_time.tzinfo is None:
                last_check_time = last_check_time.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            known_files_json = json.dumps(known_files) if known_files is not None else None

            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO rag_pipeline_state
                        (pipeline_id, pipeline_type, last_check_time, known_files, last_run, updated_at)
                    VALUES ($1, $2, $3, $4::jsonb, $5, $5)
                    ON CONFLICT (pipeline_id) DO UPDATE SET
                        last_check_time = COALESCE($3, rag_pipeline_state.last_check_time),
                        known_files     = COALESCE($4::jsonb, rag_pipeline_state.known_files),
                        last_run        = $5,
                        updated_at      = $5
                    """,
                    self.pipeline_id,
                    self.pipeline_type,
                    last_check_time,
                    known_files_json,
                    now,
                )
            logger.debug("Saved state for pipeline %s", self.pipeline_id)
            return True

        except Exception:
            logger.exception("Error saving state for pipeline %s", self.pipeline_id)
            return False

    async def update_last_check_time(self, last_check_time: datetime) -> bool:
        """Update only the last_check_time field."""
        return await self.save_state(last_check_time=last_check_time)

    async def update_known_files(self, known_files: Dict[str, str]) -> bool:
        """Update only the known_files field."""
        return await self.save_state(known_files=known_files)


async def create_state_manager(
    pool: asyncpg.Pool, pipeline_type: str
) -> Optional[StateManager]:
    """Factory: create a StateManager if RAG_PIPELINE_ID is set."""
    pipeline_id = os.getenv("RAG_PIPELINE_ID")
    if not pipeline_id:
        return None
    try:
        return StateManager(pool, pipeline_id, pipeline_type)
    except Exception:
        logger.exception("Failed to create StateManager")
        return None


# ---------------------------------------------------------------------------
# Backward-compatible file-based helpers (used when no DB is available)
# ---------------------------------------------------------------------------

def load_state_from_config(config_path: str) -> Dict[str, Any]:
    """Load state from a config.json file (fallback)."""
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        last_check_str = config.get("last_check_time", "1970-01-01T00:00:00.000Z")
        try:
            last_check_time = datetime.strptime(last_check_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            last_check_time = datetime.strptime("1970-01-01T00:00:00.000Z", "%Y-%m-%dT%H:%M:%S.%fZ")
        return {"last_check_time": last_check_time, "known_files": {}, "exists": True}
    except Exception:
        return {
            "last_check_time": datetime.strptime("1970-01-01T00:00:00.000Z", "%Y-%m-%dT%H:%M:%S.%fZ"),
            "known_files": {},
            "exists": False,
        }


def save_state_to_config(
    config_path: str, last_check_time: datetime, config: Dict[str, Any]
) -> bool:
    """Save state to a config.json file (fallback)."""
    try:
        config["last_check_time"] = last_check_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception:
        logger.exception("Error saving state to config")
        return False
