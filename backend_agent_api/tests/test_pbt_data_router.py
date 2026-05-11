"""Property-based tests for data_router conversation and message endpoints.

# Feature: frontend-supabase-removal, Property 9: Conversation listing ownership and ordering
# Feature: frontend-supabase-removal, Property 10: Message listing ordering
# Feature: frontend-supabase-removal, Property 11: Cross-user session access forbidden

Uses hypothesis to generate arbitrary conversations/messages and verifies
correctness properties hold across all generated cases. DB interactions
are mocked via patching get_pool.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings, assume
from hypothesis import strategies as st

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pbt-data-router-32bytes!")

from auth_middleware import get_current_user
from data_router import router

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JWT_SECRET = "test-secret-key-for-pbt-data-router-32bytes!"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    """Ensure token_manager uses our test secret."""
    monkeypatch.setenv("JWT_SECRET_KEY", JWT_SECRET)
    import token_manager
    monkeypatch.setattr(token_manager, "JWT_SECRET", JWT_SECRET)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate realistic timestamps spread across a time range
_base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

timestamps = st.integers(min_value=0, max_value=365 * 24 * 60).map(
    lambda mins: _base_time + timedelta(minutes=mins)
)

session_ids = st.uuids().map(lambda u: str(u)[:16])

conversation_titles = st.one_of(
    st.none(),
    st.text(min_size=1, max_size=50, alphabet=st.characters(min_codepoint=32, max_codepoint=126)),
)

user_ids = st.uuids().map(str)

message_types = st.sampled_from(["human", "ai"])

message_contents = st.text(
    min_size=1, max_size=100,
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_app_with_user(user_id: str, email: str = "test@example.com") -> TestClient:
    """Create a FastAPI app with data router and overridden auth for the given user."""
    app = FastAPI()
    app.include_router(router)

    async def _override_auth():
        return {"sub": user_id, "email": email}

    app.dependency_overrides[get_current_user] = _override_auth
    return TestClient(app)


def _make_conv_record(session_id: str, title, web_user_id: str, last_message_at: datetime):
    """Build a mock asyncpg Record for a conversation row."""
    created_at = last_message_at - timedelta(hours=1)
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "session_id": session_id,
        "title": title,
        "created_at": created_at,
        "last_message_at": last_message_at,
        "web_user_id": web_user_id,
    }[key]
    return row


def _make_msg_record(msg_id: int, session_id: str, msg_type: str, content: str, created_at: datetime):
    """Build a mock asyncpg Record for a message row."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": msg_id,
        "session_id": session_id,
        "message": {"type": msg_type, "content": content},
        "created_at": created_at,
    }[key]
    return row


# ---------------------------------------------------------------------------
# Property 9: Conversation listing ownership and ordering
# ---------------------------------------------------------------------------


class TestConversationListingOwnershipAndOrdering:
    """Property 9: Conversation listing ownership and ordering.

    **Validates: Requirements 5.1**

    For any authenticated user, the conversations endpoint should return
    only conversations where web_user_id matches the requesting user's ID,
    and the results should be ordered by last_message_at descending.
    """

    @given(
        owner_convs=st.lists(
            st.tuples(session_ids, conversation_titles, timestamps),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(max_examples=25, deadline=None)
    def test_returns_only_owned_conversations_in_desc_order(
        self, owner_convs
    ):
        # Feature: frontend-supabase-removal, Property 9: Conversation listing ownership and ordering
        owner_id = str(uuid.uuid4())
        client = _build_app_with_user(owner_id)

        # The data_router queries the DB directly with a WHERE clause.
        # The mock simulates the DB returning only the owner's rows,
        # already sorted by last_message_at DESC (as the SQL ORDER BY does).
        owner_rows = [
            _make_conv_record(sid, title, owner_id, ts)
            for sid, title, ts in owner_convs
        ]
        # Sort descending by last_message_at to simulate SQL ORDER BY
        owner_rows.sort(key=lambda r: r["last_message_at"], reverse=True)

        mock_pool = AsyncMock()
        mock_pool.fetch = AsyncMock(return_value=owner_rows)

        with patch("data_router.get_pool", return_value=mock_pool):
            resp = client.get("/conversations")

        assert resp.status_code == 200
        data = resp.json()

        # Only owner's conversations returned
        assert len(data) == len(owner_convs)

        # Verify ordering: last_message_at should be descending
        if len(data) >= 2:
            for i in range(len(data) - 1):
                assert data[i]["last_message_at"] >= data[i + 1]["last_message_at"], (
                    f"Conversations not in descending order at index {i}: "
                    f"{data[i]['last_message_at']} < {data[i + 1]['last_message_at']}"
                )

        # Verify the SQL query was called with the owner's user_id
        mock_pool.fetch.assert_called_once()
        call_args = mock_pool.fetch.call_args
        sql_query = call_args[0][0]
        bound_user_id = call_args[0][1]
        assert "web_user_id = $1" in sql_query
        assert "ORDER BY last_message_at DESC" in sql_query
        assert bound_user_id == owner_id


# ---------------------------------------------------------------------------
# Property 10: Message listing ordering
# ---------------------------------------------------------------------------


class TestMessageListingOrdering:
    """Property 10: Message listing ordering.

    **Validates: Requirements 5.2**

    For any session belonging to the authenticated user, the messages
    endpoint should return messages ordered by created_at ascending.
    """

    @given(
        messages=st.lists(
            st.tuples(message_types, message_contents, timestamps),
            min_size=0,
            max_size=15,
        ),
    )
    @settings(max_examples=25, deadline=None)
    def test_returns_messages_in_ascending_order(self, messages):
        # Feature: frontend-supabase-removal, Property 10: Message listing ordering
        owner_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())[:16]
        client = _build_app_with_user(owner_id)

        # Mock the ownership check — session belongs to this user
        conv_row = MagicMock()
        conv_row.__getitem__ = lambda self, key: {"web_user_id": owner_id}[key]

        # Build message rows sorted by created_at ASC (simulating SQL ORDER BY)
        msg_rows = [
            _make_msg_record(i + 1, session_id, msg_type, content, ts)
            for i, (msg_type, content, ts) in enumerate(messages)
        ]
        msg_rows.sort(key=lambda r: r["created_at"])

        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value=conv_row)
        mock_pool.fetch = AsyncMock(return_value=msg_rows)

        with patch("data_router.get_pool", return_value=mock_pool):
            resp = client.get(f"/conversations/{session_id}/messages")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(messages)

        # Verify ordering: created_at should be ascending
        if len(data) >= 2:
            for i in range(len(data) - 1):
                assert data[i]["created_at"] <= data[i + 1]["created_at"], (
                    f"Messages not in ascending order at index {i}: "
                    f"{data[i]['created_at']} > {data[i + 1]['created_at']}"
                )

        # Verify the SQL query uses ORDER BY created_at ASC
        fetch_call = mock_pool.fetch.call_args
        sql_query = fetch_call[0][0]
        assert "ORDER BY created_at ASC" in sql_query


# ---------------------------------------------------------------------------
# Property 11: Cross-user session access forbidden
# ---------------------------------------------------------------------------


class TestCrossUserSessionAccessForbidden:
    """Property 11: Cross-user session access forbidden.

    **Validates: Requirements 5.4**

    For any two distinct users A and B, if user A owns a conversation
    session, then user B requesting messages for that session should
    receive a 403 Forbidden response.
    """

    @given(
        user_a_id=user_ids,
        user_b_id=user_ids,
        session_id=session_ids,
    )
    @settings(max_examples=25, deadline=None)
    def test_user_b_cannot_access_user_a_session(
        self, user_a_id, user_b_id, session_id
    ):
        # Feature: frontend-supabase-removal, Property 11: Cross-user session access forbidden
        assume(user_a_id != user_b_id)

        # User B is the requester
        client = _build_app_with_user(user_b_id)

        # The conversation belongs to user A
        conv_row = MagicMock()
        conv_row.__getitem__ = lambda self, key: {"web_user_id": user_a_id}[key]

        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value=conv_row)

        with patch("data_router.get_pool", return_value=mock_pool):
            resp = client.get(f"/conversations/{session_id}/messages")

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Forbidden"

        # Messages should never be fetched for a forbidden session
        mock_pool.fetch.assert_not_called()
