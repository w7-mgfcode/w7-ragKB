"""Unit tests for websocket_manager.py — WebSocketManager."""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from websocket_manager import WebSocketManager, WebSocketMessage


@pytest.fixture
def ws_manager():
    """WebSocketManager with test-friendly limits."""
    return WebSocketManager(max_connections_per_user=3, message_queue_size=5)


def make_mock_websocket():
    """Create a mock WebSocket that tracks sent messages."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


# ==========================================================================
# Connection lifecycle
# ==========================================================================


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_registers_websocket(self, ws_manager):
        """Should accept the websocket and track the connection."""
        ws = make_mock_websocket()

        result = await ws_manager.connect(ws, "user1")

        assert result is True
        ws.accept.assert_called_once()
        assert ws in ws_manager._connections["user1"]

    @pytest.mark.asyncio
    async def test_connect_multiple_users(self, ws_manager):
        """Should track connections per user independently."""
        ws1 = make_mock_websocket()
        ws2 = make_mock_websocket()

        await ws_manager.connect(ws1, "user1")
        await ws_manager.connect(ws2, "user2")

        assert len(ws_manager._connections["user1"]) == 1
        assert len(ws_manager._connections["user2"]) == 1

    @pytest.mark.asyncio
    async def test_max_connections_per_user_enforced(self, ws_manager):
        """Should reject connections beyond the per-user limit."""
        sockets = [make_mock_websocket() for _ in range(4)]

        for ws in sockets[:3]:
            result = await ws_manager.connect(ws, "user1")
            assert result is True

        # Fourth should be rejected
        result = await ws_manager.connect(sockets[3], "user1")
        assert result is False
        assert len(ws_manager._connections["user1"]) == 3


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_removes_websocket(self, ws_manager):
        """Should remove the websocket from tracking."""
        ws = make_mock_websocket()
        await ws_manager.connect(ws, "user1")

        await ws_manager.disconnect(ws, "user1")

        assert "user1" not in ws_manager._connections

    @pytest.mark.asyncio
    async def test_disconnect_leaves_other_connections(self, ws_manager):
        """Should not affect other connections for the same user."""
        ws1 = make_mock_websocket()
        ws2 = make_mock_websocket()
        await ws_manager.connect(ws1, "user1")
        await ws_manager.connect(ws2, "user1")

        await ws_manager.disconnect(ws1, "user1")

        assert len(ws_manager._connections["user1"]) == 1
        assert ws2 in ws_manager._connections["user1"]


# ==========================================================================
# Broadcasting
# ==========================================================================


class TestBroadcastToAll:
    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_clients(self, ws_manager):
        """Should send message to every connected client."""
        ws1 = make_mock_websocket()
        ws2 = make_mock_websocket()
        await ws_manager.connect(ws1, "user1")
        await ws_manager.connect(ws2, "user2")

        msg = WebSocketMessage(
            type="test_event",
            data={"key": "value"},
            timestamp=datetime.now(timezone.utc),
        )

        await ws_manager.broadcast_to_all(msg)

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_handles_send_failure(self, ws_manager):
        """Should not raise if sending to one client fails."""
        ws1 = make_mock_websocket()
        ws2 = make_mock_websocket()
        ws1.send_json.side_effect = Exception("Connection closed")
        await ws_manager.connect(ws1, "user1")
        await ws_manager.connect(ws2, "user2")

        msg = WebSocketMessage(
            type="test_event",
            data={},
            timestamp=datetime.now(timezone.utc),
        )

        # Should not raise
        await ws_manager.broadcast_to_all(msg)

        ws2.send_json.assert_called_once()


class TestBroadcastToUser:
    @pytest.mark.asyncio
    async def test_broadcast_targets_correct_user(self, ws_manager):
        """Should only send to the specified user's connections."""
        ws1 = make_mock_websocket()
        ws2 = make_mock_websocket()
        await ws_manager.connect(ws1, "user1")
        await ws_manager.connect(ws2, "user2")

        msg = WebSocketMessage(
            type="test_event",
            data={"file_path": "test.md"},
            timestamp=datetime.now(timezone.utc),
        )

        await ws_manager.broadcast_to_user("user1", msg)

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_missed_messages_queued(self, ws_manager):
        """Should queue messages for disconnected users."""
        msg = WebSocketMessage(
            type="test_event",
            data={"file_path": "test.md"},
            timestamp=datetime.now(timezone.utc),
        )

        # No connections for user1 — message should be queued
        await ws_manager.broadcast_to_user("user1", msg)

        assert len(ws_manager._missed_messages["user1"]) == 1

    @pytest.mark.asyncio
    async def test_missed_messages_delivered_on_reconnect(self, ws_manager):
        """Should flush queued messages when user reconnects."""
        msg = WebSocketMessage(
            type="queued_event",
            data={"info": "missed"},
            timestamp=datetime.now(timezone.utc),
        )

        # Queue a message while disconnected
        await ws_manager.broadcast_to_user("user1", msg)

        # Reconnect
        ws = make_mock_websocket()
        await ws_manager.connect(ws, "user1")

        # Deliver missed messages
        await ws_manager.send_missed_messages("user1")

        ws.send_json.assert_called_once()
        assert "user1" not in ws_manager._missed_messages


# ==========================================================================
# Convenience helpers
# ==========================================================================


class TestConvenienceHelpers:
    @pytest.mark.asyncio
    async def test_send_sync_status_update(self, ws_manager):
        """Should broadcast a sync_status_update message."""
        ws = make_mock_websocket()
        await ws_manager.connect(ws, "user1")

        await ws_manager.send_sync_status_update(
            "docs/test.md", "in_sync", chunk_count=5
        )

        ws.send_json.assert_called_once()
        payload = ws.send_json.call_args[0][0]
        assert payload["type"] == "sync_status_update"
        assert payload["data"]["file_path"] == "docs/test.md"
        assert payload["data"]["sync_status"] == "in_sync"
        assert payload["data"]["chunk_count"] == 5

    @pytest.mark.asyncio
    async def test_send_document_event(self, ws_manager):
        """Should broadcast a document lifecycle event."""
        ws = make_mock_websocket()
        await ws_manager.connect(ws, "user1")

        await ws_manager.send_document_event(
            "document_created", "docs/new.md"
        )

        ws.send_json.assert_called_once()
        payload = ws.send_json.call_args[0][0]
        assert payload["type"] == "document_created"
        assert payload["data"]["file_path"] == "docs/new.md"


# ==========================================================================
# Module-level singleton
# ==========================================================================


class TestModuleSingleton:
    def test_get_websocket_manager_raises_if_not_initialized(self):
        from websocket_manager import get_websocket_manager
        import websocket_manager as mod

        original = mod._instance
        mod._instance = None
        try:
            with pytest.raises(RuntimeError, match="not initialized"):
                get_websocket_manager()
        finally:
            mod._instance = original
