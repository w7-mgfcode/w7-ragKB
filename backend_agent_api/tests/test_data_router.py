"""Unit tests for data_router module.

Uses FastAPI TestClient with mocked DB pool and auth dependency.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth_middleware import get_current_user
from data_router import router


USER_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _build_app(user_claims: dict) -> FastAPI:
    """Create a FastAPI app with the data router and overridden auth."""
    app = FastAPI()
    app.include_router(router)

    async def _override_auth():
        return user_claims

    app.dependency_overrides[get_current_user] = _override_auth
    return app


def _make_conv_row(session_id: str, title: str | None, web_user_id: str, minutes_ago: int):
    """Build a mock asyncpg Record-like object for a conversation row."""
    ts = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "session_id": session_id,
        "title": title,
        "created_at": ts,
        "last_message_at": ts,
        "web_user_id": web_user_id,
    }[key]
    return row


def _make_msg_row(msg_id: int, session_id: str, content: str):
    """Build a mock asyncpg Record-like object for a message row."""
    ts = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": msg_id,
        "session_id": session_id,
        "message": {"type": "human", "content": content},
        "created_at": ts,
    }[key]
    return row


class TestListConversations:
    """Tests for GET /conversations."""

    @pytest.mark.asyncio
    async def test_returns_user_conversations(self):
        app = _build_app({"sub": USER_A_ID, "email": "a@test.com"})
        client = TestClient(app)

        mock_pool = AsyncMock()
        mock_pool.fetch = AsyncMock(return_value=[
            _make_conv_row("sess-1", "Chat 1", USER_A_ID, 10),
            _make_conv_row("sess-2", "Chat 2", USER_A_ID, 5),
        ])

        with patch("data_router.get_pool", return_value=mock_pool):
            resp = client.get("/conversations")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["session_id"] == "sess-1"
        assert data[1]["session_id"] == "sess-2"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_conversations(self):
        app = _build_app({"sub": USER_A_ID, "email": "a@test.com"})
        client = TestClient(app)

        mock_pool = AsyncMock()
        mock_pool.fetch = AsyncMock(return_value=[])

        with patch("data_router.get_pool", return_value=mock_pool):
            resp = client.get("/conversations")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_conversation_response_shape(self):
        app = _build_app({"sub": USER_A_ID, "email": "a@test.com"})
        client = TestClient(app)

        mock_pool = AsyncMock()
        mock_pool.fetch = AsyncMock(return_value=[
            _make_conv_row("sess-1", "My Chat", USER_A_ID, 0),
        ])

        with patch("data_router.get_pool", return_value=mock_pool):
            resp = client.get("/conversations")

        data = resp.json()
        conv = data[0]
        assert "session_id" in conv
        assert "title" in conv
        assert "created_at" in conv
        assert "last_message_at" in conv


class TestListMessages:
    """Tests for GET /conversations/{session_id}/messages."""

    @pytest.mark.asyncio
    async def test_returns_messages_for_owned_session(self):
        app = _build_app({"sub": USER_A_ID, "email": "a@test.com"})
        client = TestClient(app)

        mock_conv_row = MagicMock()
        mock_conv_row.__getitem__ = lambda self, key: {"web_user_id": USER_A_ID}[key]

        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value=mock_conv_row)
        mock_pool.fetch = AsyncMock(return_value=[
            _make_msg_row(1, "sess-1", "Hello"),
            _make_msg_row(2, "sess-1", "World"),
        ])

        with patch("data_router.get_pool", return_value=mock_pool):
            resp = client.get("/conversations/sess-1/messages")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[0]["message"]["content"] == "Hello"
        assert data[1]["id"] == 2

    @pytest.mark.asyncio
    async def test_returns_403_for_other_users_session(self):
        app = _build_app({"sub": USER_A_ID, "email": "a@test.com"})
        client = TestClient(app)

        mock_conv_row = MagicMock()
        mock_conv_row.__getitem__ = lambda self, key: {"web_user_id": USER_B_ID}[key]

        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value=mock_conv_row)

        with patch("data_router.get_pool", return_value=mock_pool):
            resp = client.get("/conversations/sess-1/messages")

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_returns_403_for_nonexistent_session(self):
        app = _build_app({"sub": USER_A_ID, "email": "a@test.com"})
        client = TestClient(app)

        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value=None)

        with patch("data_router.get_pool", return_value=mock_pool):
            resp = client.get("/conversations/nonexistent/messages")

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_message_response_shape(self):
        app = _build_app({"sub": USER_A_ID, "email": "a@test.com"})
        client = TestClient(app)

        mock_conv_row = MagicMock()
        mock_conv_row.__getitem__ = lambda self, key: {"web_user_id": USER_A_ID}[key]

        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value=mock_conv_row)
        mock_pool.fetch = AsyncMock(return_value=[
            _make_msg_row(1, "sess-1", "Test"),
        ])

        with patch("data_router.get_pool", return_value=mock_pool):
            resp = client.get("/conversations/sess-1/messages")

        msg = resp.json()[0]
        assert "id" in msg
        assert "session_id" in msg
        assert "message" in msg
        assert "created_at" in msg

    @pytest.mark.asyncio
    async def test_handles_json_string_message(self):
        """Messages stored as JSON strings should be parsed into dicts."""
        app = _build_app({"sub": USER_A_ID, "email": "a@test.com"})
        client = TestClient(app)

        mock_conv_row = MagicMock()
        mock_conv_row.__getitem__ = lambda self, key: {"web_user_id": USER_A_ID}[key]

        ts = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        string_msg_row = MagicMock()
        string_msg_row.__getitem__ = lambda self, key: {
            "id": 1,
            "session_id": "sess-1",
            "message": '{"type": "ai", "content": "Hi there"}',
            "created_at": ts,
        }[key]

        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value=mock_conv_row)
        mock_pool.fetch = AsyncMock(return_value=[string_msg_row])

        with patch("data_router.get_pool", return_value=mock_pool):
            resp = client.get("/conversations/sess-1/messages")

        msg = resp.json()[0]
        assert msg["message"]["type"] == "ai"
        assert msg["message"]["content"] == "Hi there"
