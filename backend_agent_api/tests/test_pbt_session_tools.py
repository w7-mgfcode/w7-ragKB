"""Property-based tests for session tools.

Feature: openclaw-integration
Properties tested: 17, 18, 19, 20, 21

Tests sessions_list, sessions_history, sessions_send,
permission checks, and error handling.
"""

import string
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
import pytest_asyncio
from hypothesis import HealthCheck, given, settings, strategies as st

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.session_tools import (
    PermissionError as SessionPermissionError,
    SessionNotFoundError,
    SessionToolsError,
    can_access_session,
    sessions_history,
    sessions_list,
    sessions_send,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

session_id_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + "-_:",
    min_size=5,
    max_size=50,
)
safe_text = st.text(min_size=1, max_size=500).filter(lambda s: s.strip())
limit_strategy = st.integers(min_value=-100, max_value=200)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_session(
    session_id="s1",
    user_id="user1",
    channel_id="ch1",
    chat_id="c1",
    session_type="main",
    session_tools_enabled=True,
    message_count=0,
    last_activity_at=None,
    created_at=None,
):
    """Create a mock Session object."""
    session = MagicMock()
    session.session_id = session_id
    session.user_id = user_id
    session.channel_id = channel_id
    session.chat_id = chat_id
    session.session_type = session_type
    session.session_tools_enabled = session_tools_enabled
    session.message_count = message_count
    session.last_activity_at = last_activity_at
    session.created_at = created_at
    session.get_history = AsyncMock(return_value=[])
    session.add_message = AsyncMock()
    return session


def make_mock_session_manager(sessions=None):
    """Create a mock SessionManager with pre-configured sessions."""
    sm = MagicMock()
    session_map = {}
    if sessions:
        for s in sessions:
            session_map[s.session_id] = s

    async def get_session(sid):
        return session_map.get(sid)

    async def list_sessions_fn(include_archived=False):
        return list(session_map.values())

    sm.get_session = AsyncMock(side_effect=get_session)
    sm.list_sessions = AsyncMock(side_effect=list_sessions_fn)
    return sm


def make_ctx(session_manager, session_id):
    """Create a mock RunContext with deps."""
    ctx = MagicMock()
    ctx.deps = MagicMock()
    ctx.deps.session_manager = session_manager
    ctx.deps.session_id = session_id
    return ctx


# ===========================================================================
# Property 17: sessions_list completeness + access control
# ===========================================================================


class TestCanAccessSession:
    """Property 17: Access control for session tools."""

    @given(session_id=session_id_strategy)
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_self_access_always_allowed(self, session_id):
        """
        Feature: openclaw-integration, Property 17: sessions_list completeness

        A session can always access itself (reflexive property).
        """
        sm = make_mock_session_manager()
        result = await can_access_session(sm, session_id, session_id)
        assert result is True

    @given(
        sid_a=session_id_strategy,
        sid_b=session_id_strategy,
    )
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_same_user_can_access(self, sid_a, sid_b):
        """
        Feature: openclaw-integration, Property 17: sessions_list completeness

        Sessions from the same user can access each other.
        """
        if sid_a == sid_b:
            return  # Tested by self_access

        session_a = make_mock_session(session_id=sid_a, user_id="shared_user")
        session_b = make_mock_session(session_id=sid_b, user_id="shared_user")
        sm = make_mock_session_manager([session_a, session_b])

        result = await can_access_session(sm, sid_a, sid_b)
        assert result is True

    @given(
        sid_a=session_id_strategy,
        sid_b=session_id_strategy,
    )
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_different_user_denied(self, sid_a, sid_b):
        """
        Feature: openclaw-integration, Property 17: sessions_list completeness

        Sessions from different users cannot access each other.
        """
        if sid_a == sid_b:
            return

        session_a = make_mock_session(session_id=sid_a, user_id="user_alpha")
        session_b = make_mock_session(session_id=sid_b, user_id="user_beta")
        sm = make_mock_session_manager([session_a, session_b])

        result = await can_access_session(sm, sid_a, sid_b)
        assert result is False

    @given(session_id=session_id_strategy)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_nonexistent_session_denied(self, session_id):
        """
        Feature: openclaw-integration, Property 17: sessions_list completeness

        Access to a non-existent session should return False.
        """
        sm = make_mock_session_manager()
        result = await can_access_session(sm, session_id, "nonexistent")
        assert result is False


# ===========================================================================
# Property 18: sessions_history retrieval (limit clamping)
# ===========================================================================


class TestSessionsHistoryLimitClamping:
    """Property 18: sessions_history clamps limit to [1, 100]."""

    @given(limit=limit_strategy)
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_limit_clamped(self, limit):
        """
        Feature: openclaw-integration, Property 18: sessions_history retrieval

        The limit parameter should be clamped: <1 -> 10, >100 -> 100.
        """
        current_session = make_mock_session(
            session_id="current", user_id="u1", session_tools_enabled=True
        )
        target_session = make_mock_session(
            session_id="target", user_id="u1", session_tools_enabled=True
        )
        sm = make_mock_session_manager([current_session, target_session])
        ctx = make_ctx(sm, "current")

        await sessions_history(ctx, "target", limit=limit)

        # Check what limit was passed to get_history
        call_args = target_session.get_history.call_args
        actual_limit = call_args.kwargs.get("limit", call_args.args[0] if call_args.args else 10)

        if limit < 1:
            assert actual_limit == 10
        elif limit > 100:
            assert actual_limit == 100
        else:
            assert actual_limit == limit


# ===========================================================================
# Property 19: sessions_send delivery
# ===========================================================================


class TestSessionsSendDelivery:
    """Property 19: sessions_send delivers messages with source metadata."""

    @given(message=safe_text)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_message_delivered_with_metadata(self, message):
        """
        Feature: openclaw-integration, Property 19: sessions_send delivery

        sessions_send should deliver message with source_session metadata.
        """
        current_session = make_mock_session(
            session_id="sender", user_id="u1", session_tools_enabled=True
        )
        target_session = make_mock_session(
            session_id="receiver", user_id="u1", session_tools_enabled=True
        )
        sm = make_mock_session_manager([current_session, target_session])
        ctx = make_ctx(sm, "sender")

        result = await sessions_send(ctx, "receiver", message)

        assert result["status"] == "delivered"
        assert result["session_id"] == "receiver"
        assert result["message_length"] == len(message)

        # Verify add_message was called with correct args
        target_session.add_message.assert_called_once()
        call_kwargs = target_session.add_message.call_args.kwargs
        assert call_kwargs["role"] == "system"
        assert call_kwargs["content"] == message
        assert call_kwargs["metadata"]["source_session"] == "sender"
        assert call_kwargs["metadata"]["inter_session_message"] is True


# ===========================================================================
# Property 20: Session tool permissions
# ===========================================================================


class TestSessionToolPermissions:
    """Property 20: session_tools_enabled=False raises PermissionError."""

    @pytest.mark.asyncio
    async def test_sessions_list_blocked_when_disabled(self):
        """
        Feature: openclaw-integration, Property 20: Session tool permissions

        sessions_list should raise PermissionError when session_tools_enabled=False.
        """
        current_session = make_mock_session(
            session_id="current", user_id="u1", session_tools_enabled=False
        )
        sm = make_mock_session_manager([current_session])
        ctx = make_ctx(sm, "current")

        with pytest.raises(SessionPermissionError):
            await sessions_list(ctx)

    @pytest.mark.asyncio
    async def test_sessions_history_blocked_when_disabled(self):
        """
        Feature: openclaw-integration, Property 20: Session tool permissions

        sessions_history should raise PermissionError when session_tools_enabled=False.
        """
        current_session = make_mock_session(
            session_id="current", user_id="u1", session_tools_enabled=False
        )
        sm = make_mock_session_manager([current_session])
        ctx = make_ctx(sm, "current")

        with pytest.raises(SessionPermissionError):
            await sessions_history(ctx, "target")

    @pytest.mark.asyncio
    async def test_sessions_send_blocked_when_disabled(self):
        """
        Feature: openclaw-integration, Property 20: Session tool permissions

        sessions_send should raise PermissionError when session_tools_enabled=False.
        """
        current_session = make_mock_session(
            session_id="current", user_id="u1", session_tools_enabled=False
        )
        sm = make_mock_session_manager([current_session])
        ctx = make_ctx(sm, "current")

        with pytest.raises(SessionPermissionError):
            await sessions_send(ctx, "target", "hello")


# ===========================================================================
# Property 21: sessions_send error handling
# ===========================================================================


class TestSessionsSendErrorHandling:
    """Property 21: Non-existent session returns error without side effects."""

    @given(bad_session_id=session_id_strategy)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_send_to_nonexistent_raises_error(self, bad_session_id):
        """
        Feature: openclaw-integration, Property 21: sessions_send error handling

        Sending to a non-existent session should raise SessionNotFoundError.
        """
        current_session = make_mock_session(
            session_id="sender", user_id="u1", session_tools_enabled=True
        )
        sm = make_mock_session_manager([current_session])
        ctx = make_ctx(sm, "sender")

        with pytest.raises((SessionNotFoundError, SessionPermissionError)):
            await sessions_send(ctx, bad_session_id, "hello")

    @pytest.mark.asyncio
    async def test_send_empty_message_raises_value_error(self):
        """
        Feature: openclaw-integration, Property 21: sessions_send error handling

        Sending an empty message should raise ValueError.
        """
        current_session = make_mock_session(
            session_id="sender", user_id="u1", session_tools_enabled=True
        )
        target_session = make_mock_session(
            session_id="target", user_id="u1", session_tools_enabled=True
        )
        sm = make_mock_session_manager([current_session, target_session])
        ctx = make_ctx(sm, "sender")

        with pytest.raises(ValueError, match="empty"):
            await sessions_send(ctx, "target", "")

    @pytest.mark.asyncio
    async def test_send_whitespace_message_raises_value_error(self):
        """
        Feature: openclaw-integration, Property 21: sessions_send error handling

        Sending a whitespace-only message should raise ValueError.
        """
        current_session = make_mock_session(
            session_id="sender", user_id="u1", session_tools_enabled=True
        )
        target_session = make_mock_session(
            session_id="target", user_id="u1", session_tools_enabled=True
        )
        sm = make_mock_session_manager([current_session, target_session])
        ctx = make_ctx(sm, "sender")

        with pytest.raises(ValueError, match="empty"):
            await sessions_send(ctx, "target", "   \t\n  ")
