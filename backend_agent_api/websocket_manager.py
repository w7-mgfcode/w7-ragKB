"""WebSocket connection manager for real-time document update notifications.

Tracks connected clients per user, broadcasts messages on document operations,
and queues missed messages for clients that reconnect.
"""

import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ==============================================================================
# Models
# ==============================================================================


class WebSocketMessage(BaseModel):
    """Message sent over WebSocket to clients."""

    type: str  # sync_status_update, document_created, document_updated, document_deleted, reindex_complete
    data: Dict[str, Any]
    timestamp: datetime


# ==============================================================================
# WebSocketManager
# ==============================================================================


class WebSocketManager:
    """Manages WebSocket connections and broadcasts real-time updates."""

    def __init__(
        self,
        max_connections_per_user: int = 5,
        message_queue_size: int = 100,
    ):
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self._missed_messages: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=message_queue_size)
        )
        self._lock = asyncio.Lock()
        self._max_connections_per_user = max_connections_per_user
        self._message_queue_size = message_queue_size

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, websocket: WebSocket, user_id: str) -> bool:
        """Accept and register a WebSocket connection.

        Returns False if the per-user connection limit is reached.
        """
        async with self._lock:
            if len(self._connections[user_id]) >= self._max_connections_per_user:
                logger.warning(
                    "User %s exceeded max WebSocket connections (%d)",
                    user_id,
                    self._max_connections_per_user,
                )
                return False
            await websocket.accept()
            self._connections[user_id].add(websocket)
            logger.info("WebSocket connected: user=%s, total=%d", user_id, len(self._connections[user_id]))
        return True

    async def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        """Unregister a WebSocket connection."""
        async with self._lock:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]
            logger.info("WebSocket disconnected: user=%s", user_id)

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def broadcast_to_user(
        self, user_id: str, message: WebSocketMessage
    ) -> None:
        """Send a message to all connections for a specific user."""
        payload = message.model_dump(mode="json")
        async with self._lock:
            sockets = list(self._connections.get(user_id, set()))

        if not sockets:
            # Queue for later delivery
            self._missed_messages[user_id].append(payload)
            return

        for ws in sockets:
            try:
                await asyncio.wait_for(ws.send_json(payload), timeout=5.0)
            except Exception:
                logger.debug("Failed to send to user %s WebSocket", user_id)

    async def broadcast_to_all(self, message: WebSocketMessage) -> None:
        """Send a message to every connected client."""
        payload = message.model_dump(mode="json")
        async with self._lock:
            all_sockets = [
                (uid, list(sockets))
                for uid, sockets in self._connections.items()
            ]

        for uid, sockets in all_sockets:
            for ws in sockets:
                try:
                    await asyncio.wait_for(ws.send_json(payload), timeout=5.0)
                except Exception:
                    logger.debug("Failed to broadcast to user %s", uid)

    async def send_missed_messages(self, user_id: str) -> None:
        """Flush queued messages to a reconnected user."""
        missed = list(self._missed_messages.pop(user_id, deque()))
        if not missed:
            return

        async with self._lock:
            sockets = list(self._connections.get(user_id, set()))

        for payload in missed:
            for ws in sockets:
                try:
                    await asyncio.wait_for(ws.send_json(payload), timeout=5.0)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    async def send_sync_status_update(
        self, file_path: str, sync_status: str, **extra: Any
    ) -> None:
        """Broadcast a sync status change to all clients."""
        msg = WebSocketMessage(
            type="sync_status_update",
            data={"file_path": file_path, "sync_status": sync_status, **extra},
            timestamp=datetime.now(timezone.utc),
        )
        await self.broadcast_to_all(msg)

    async def send_document_event(
        self, event_type: str, file_path: str, **extra: Any
    ) -> None:
        """Broadcast a document lifecycle event (created, updated, deleted)."""
        msg = WebSocketMessage(
            type=event_type,
            data={"file_path": file_path, **extra},
            timestamp=datetime.now(timezone.utc),
        )
        await self.broadcast_to_all(msg)


# ==============================================================================
# Module-level singleton
# ==============================================================================

_instance: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """FastAPI dependency — return the global WebSocketManager instance."""
    if _instance is None:
        raise RuntimeError(
            "WebSocketManager not initialized — call init during startup"
        )
    return _instance
