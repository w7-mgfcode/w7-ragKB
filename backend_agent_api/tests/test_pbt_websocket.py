"""Property-based tests for WebSocket notifications (Task 7.2).

Properties tested:
- P21: WebSocket broadcast on operations — all connected clients receive
- P22: Sync status broadcast — correct payload
- P23: Missed notification delivery — queued and delivered on reconnect
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from hypothesis import given, settings
from hypothesis.strategies import integers, sampled_from

from websocket_manager import WebSocketManager, WebSocketMessage


event_types = sampled_from([
    "sync_status_update", "document_created", "document_updated",
    "document_deleted", "reindex_complete",
])


def make_ws():
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


# ==========================================================================
# P21: Broadcast reaches all clients
# ==========================================================================


@given(user_count=integers(min_value=1, max_value=5), event_type=event_types)
@settings(max_examples=30)
def test_broadcast_reaches_all_connected_clients(user_count, event_type):
    """Every connected client must receive a broadcast message."""
    mgr = WebSocketManager(max_connections_per_user=10, message_queue_size=50)
    sockets = []

    async def run():
        for i in range(user_count):
            ws = make_ws()
            await mgr.connect(ws, f"user{i}")
            sockets.append(ws)

        msg = WebSocketMessage(
            type=event_type,
            data={"file_path": "test.md"},
            timestamp=datetime.now(timezone.utc),
        )
        await mgr.broadcast_to_all(msg)

    asyncio.run(run())

    for ws in sockets:
        ws.send_json.assert_called_once()
        assert ws.send_json.call_args[0][0]["type"] == event_type


# ==========================================================================
# P21: Targeted broadcast
# ==========================================================================


@given(target=sampled_from(["user0", "user1", "user2"]))
@settings(max_examples=20)
def test_broadcast_to_user_only_reaches_target(target):
    """broadcast_to_user must only send to the targeted user."""
    mgr = WebSocketManager(max_connections_per_user=10, message_queue_size=50)
    user_sockets = {}

    async def run():
        for uid in ["user0", "user1", "user2"]:
            ws = make_ws()
            await mgr.connect(ws, uid)
            user_sockets[uid] = ws
        msg = WebSocketMessage(
            type="test_event", data={"file_path": "doc.md"},
            timestamp=datetime.now(timezone.utc),
        )
        await mgr.broadcast_to_user(target, msg)

    asyncio.run(run())

    user_sockets[target].send_json.assert_called_once()
    for uid, ws in user_sockets.items():
        if uid != target:
            ws.send_json.assert_not_called()


# ==========================================================================
# P22: Sync status broadcast payload
# ==========================================================================


@given(status=sampled_from(["in_sync", "out_of_sync", "processing", "error"]))
@settings(max_examples=30)
def test_sync_status_update_correct_payload(status):
    """send_sync_status_update must broadcast correct type and data."""
    mgr = WebSocketManager(max_connections_per_user=5, message_queue_size=50)
    ws = make_ws()

    async def run():
        await mgr.connect(ws, "user1")
        await mgr.send_sync_status_update("test.md", status, chunk_count=3)

    asyncio.run(run())

    payload = ws.send_json.call_args[0][0]
    assert payload["type"] == "sync_status_update"
    assert payload["data"]["sync_status"] == status
    assert payload["data"]["chunk_count"] == 3


# ==========================================================================
# P23: Missed notification delivery
# ==========================================================================


@given(message_count=integers(min_value=1, max_value=10))
@settings(max_examples=20)
def test_missed_messages_queued_and_delivered(message_count):
    """Messages to offline user are queued and delivered on reconnect."""
    mgr = WebSocketManager(max_connections_per_user=5, message_queue_size=50)

    async def run():
        for i in range(message_count):
            msg = WebSocketMessage(
                type="document_updated", data={"file_path": f"doc{i}.md"},
                timestamp=datetime.now(timezone.utc),
            )
            await mgr.broadcast_to_user("offline_user", msg)

        assert len(mgr._missed_messages["offline_user"]) == message_count

        ws = make_ws()
        await mgr.connect(ws, "offline_user")
        await mgr.send_missed_messages("offline_user")

        assert ws.send_json.call_count == message_count
        assert "offline_user" not in mgr._missed_messages

    asyncio.run(run())


# ==========================================================================
# P23: Queue size limit
# ==========================================================================


@given(overflow=integers(min_value=1, max_value=20))
@settings(max_examples=15)
def test_missed_message_queue_bounded(overflow):
    """Missed message queue must not exceed configured size."""
    queue_size = 5
    mgr = WebSocketManager(max_connections_per_user=5, message_queue_size=queue_size)

    async def run():
        for i in range(queue_size + overflow):
            msg = WebSocketMessage(
                type="event", data={"i": i},
                timestamp=datetime.now(timezone.utc),
            )
            await mgr.broadcast_to_user("user1", msg)

    asyncio.run(run())
    assert len(mgr._missed_messages["user1"]) <= queue_size


# ==========================================================================
# Connection limit enforcement
# ==========================================================================


@given(max_conns=integers(min_value=1, max_value=5))
@settings(max_examples=15)
def test_connection_limit_enforced(max_conns):
    """Connections beyond the per-user limit must be rejected."""
    mgr = WebSocketManager(max_connections_per_user=max_conns, message_queue_size=50)

    async def run():
        accepted = 0
        for _ in range(max_conns + 3):
            ws = make_ws()
            if await mgr.connect(ws, "user1"):
                accepted += 1
        return accepted

    count = asyncio.run(run())
    assert count == max_conns
