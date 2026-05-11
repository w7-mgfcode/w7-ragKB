"""Property-based tests for activation modes.

Feature: openclaw-integration (Task 20.1)
Properties tested: 59, 60, 61, 62, 63, 64, 65

Tests activation mode initialization, mention-based activation, always-on,
manual activation, persistence, dynamic updates, and decision logging.
"""

import string
import sys
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from session import Session


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

safe_id = st.text(
    alphabet=string.ascii_letters + string.digits + "-_.",
    min_size=1,
    max_size=30,
)
activation_modes = st.sampled_from(["mention", "always", "manual"])
session_types = st.sampled_from(["main", "group", "webhook"])
safe_text = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_pool():
    """Create a mock asyncpg pool."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock()
    return pool


def make_session(
    pool=None,
    session_id="test:user:chat",
    channel_id="slack-main",
    user_id="user1",
    chat_id="chat1",
    session_type="group",
    activation_mode="mention",
    **kwargs,
):
    """Create a Session instance with mock pool."""
    if pool is None:
        pool = make_mock_pool()
    return Session(
        pool=pool,
        session_id=session_id,
        channel_id=channel_id,
        user_id=user_id,
        chat_id=chat_id,
        session_type=session_type,
        activation_mode=activation_mode,
        **kwargs,
    )


# ===========================================================================
# Property 59: Activation mode initialization
# ===========================================================================


class TestActivationModeInitialization:
    """Property 59: Group sessions created with configured activation_mode."""

    @given(mode=activation_modes)
    @settings(max_examples=50, deadline=None)
    def test_session_stores_activation_mode(self, mode):
        """
        Feature: openclaw-integration, Property 59: Activation mode initialization

        Session should store the configured activation_mode.
        """
        session = make_session(activation_mode=mode)
        assert session.activation_mode == mode

    @given(mode=activation_modes, stype=session_types)
    @settings(max_examples=50, deadline=None)
    def test_config_reflects_activation_mode(self, mode, stype):
        """
        Feature: openclaw-integration, Property 59: Activation mode initialization

        Session.config should reflect the activation_mode.
        """
        session = make_session(activation_mode=mode, session_type=stype)
        assert session.config.activation_mode == mode

    def test_default_activation_mode_is_mention(self):
        """
        Feature: openclaw-integration, Property 59: Activation mode initialization

        Default activation mode should be 'mention'.
        """
        pool = make_mock_pool()
        session = Session(
            pool=pool,
            session_id="t:u:c",
            channel_id="ch",
            user_id="u",
            chat_id="c",
            session_type="main",
        )
        assert session.activation_mode == "mention"


# ===========================================================================
# Property 60: Mention-based activation
# ===========================================================================


class TestMentionBasedActivation:
    """Property 60: check_activation returns True only when bot_mention=True
    in mention mode."""

    @pytest.mark.asyncio
    async def test_mention_mode_responds_to_mention(self):
        """
        Feature: openclaw-integration, Property 60: Mention-based activation

        Mention mode should respond when bot is mentioned.
        """
        session = make_session(activation_mode="mention")
        assert await session.check_activation("hello", bot_mention=True) is True

    @pytest.mark.asyncio
    async def test_mention_mode_ignores_without_mention(self):
        """
        Feature: openclaw-integration, Property 60: Mention-based activation

        Mention mode should ignore messages without mention.
        """
        session = make_session(activation_mode="mention")
        assert await session.check_activation("hello", bot_mention=False) is False

    @given(text=safe_text)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_mention_mode_depends_only_on_mention_flag(self, text):
        """
        Feature: openclaw-integration, Property 60: Mention-based activation

        In mention mode, result depends only on bot_mention, not text content.
        """
        session = make_session(activation_mode="mention")
        assert await session.check_activation(text, bot_mention=True) is True
        assert await session.check_activation(text, bot_mention=False) is False


# ===========================================================================
# Property 61: Always-on activation
# ===========================================================================


class TestAlwaysOnActivation:
    """Property 61: Always mode returns True for any text."""

    @given(text=safe_text, mention=st.booleans())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_always_mode_always_responds(self, text, mention):
        """
        Feature: openclaw-integration, Property 61: Always-on activation

        Always mode should respond regardless of text or mention.
        """
        session = make_session(activation_mode="always")
        assert await session.check_activation(text, bot_mention=mention) is True


# ===========================================================================
# Property 62: Manual activation
# ===========================================================================


class TestManualActivation:
    """Property 62: Manual mode returns True only for command text."""

    @pytest.mark.asyncio
    async def test_manual_mode_responds_to_slash_command(self):
        """
        Feature: openclaw-integration, Property 62: Manual activation

        Manual mode should respond to /command text.
        """
        session = make_session(activation_mode="manual")
        assert await session.check_activation("/status", bot_mention=False) is True

    @pytest.mark.asyncio
    async def test_manual_mode_ignores_regular_text(self):
        """
        Feature: openclaw-integration, Property 62: Manual activation

        Manual mode should ignore regular text.
        """
        session = make_session(activation_mode="manual")
        assert await session.check_activation("hello world", bot_mention=False) is False

    @given(
        text=safe_text.filter(lambda s: not s.strip().startswith("/"))
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_manual_mode_ignores_all_non_slash(self, text):
        """
        Feature: openclaw-integration, Property 62: Manual activation

        Manual mode should ignore all text not starting with /.
        """
        session = make_session(activation_mode="manual")
        assert await session.check_activation(text, bot_mention=True) is False

    @given(
        cmd=st.sampled_from(["/status", "/reset", "/new", "/compact", "/help"])
    )
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_manual_mode_responds_to_commands(self, cmd):
        """
        Feature: openclaw-integration, Property 62: Manual activation

        Manual mode should respond to all slash commands.
        """
        session = make_session(activation_mode="manual")
        assert await session.check_activation(cmd, bot_mention=False) is True


# ===========================================================================
# Property 63: Activation mode persistence
# ===========================================================================


class TestActivationModePersistence:
    """Property 63: Mode stored in DB, survives session reload."""

    @given(mode=activation_modes)
    @settings(max_examples=20, deadline=None)
    def test_to_dict_includes_activation_mode(self, mode):
        """
        Feature: openclaw-integration, Property 63: Activation mode persistence

        Session.to_dict() should include activation_mode for DB storage.
        """
        session = make_session(activation_mode=mode)
        d = session.to_dict()
        assert d["activation_mode"] == mode

    @given(mode=activation_modes)
    @settings(max_examples=20, deadline=None)
    def test_session_config_includes_activation_mode(self, mode):
        """
        Feature: openclaw-integration, Property 63: Activation mode persistence

        SessionConfig should include activation_mode for serialization.
        """
        session = make_session(activation_mode=mode)
        config = session.config
        assert config.activation_mode == mode


# ===========================================================================
# Property 64: Dynamic activation mode updates
# ===========================================================================


class TestDynamicActivationModeUpdates:
    """Property 64: update_activation_mode changes behavior immediately."""

    @pytest.mark.asyncio
    async def test_update_changes_mode(self):
        """
        Feature: openclaw-integration, Property 64: Dynamic activation mode updates

        update_activation_mode should change the mode immediately.
        """
        session = make_session(activation_mode="mention")
        assert session.activation_mode == "mention"

        await session.update_activation_mode("always")
        assert session.activation_mode == "always"

    @pytest.mark.asyncio
    async def test_update_changes_behavior(self):
        """
        Feature: openclaw-integration, Property 64: Dynamic activation mode updates

        After update, check_activation behavior should change.
        """
        session = make_session(activation_mode="mention")

        # Mention mode: no mention = no response
        assert await session.check_activation("hello", bot_mention=False) is False

        # Switch to always
        await session.update_activation_mode("always")

        # Always mode: always responds
        assert await session.check_activation("hello", bot_mention=False) is True

    @pytest.mark.asyncio
    async def test_update_calls_database(self):
        """
        Feature: openclaw-integration, Property 64: Dynamic activation mode updates

        update_activation_mode should persist via database call.
        """
        pool = make_mock_pool()
        session = make_session(pool=pool, activation_mode="mention")

        await session.update_activation_mode("manual")

        pool.execute.assert_called()

    @given(mode=activation_modes)
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_update_to_any_valid_mode(self, mode):
        """
        Feature: openclaw-integration, Property 64: Dynamic activation mode updates

        Should be able to update to any valid mode.
        """
        session = make_session(activation_mode="mention")
        await session.update_activation_mode(mode)
        assert session.activation_mode == mode


# ===========================================================================
# Property 65: Activation decision logging
# ===========================================================================


class TestActivationDecisionLogging:
    """Property 65: Each activation check produces a log entry."""

    @pytest.mark.asyncio
    async def test_check_activation_logs_to_db(self):
        """
        Feature: openclaw-integration, Property 65: Activation decision logging

        check_activation should log the decision to the database.
        """
        pool = make_mock_pool()
        session = make_session(pool=pool, activation_mode="always")

        await session.check_activation("hello", bot_mention=False)

        pool.execute.assert_called_once()
        call_args = pool.execute.call_args
        sql = call_args[0][0]
        assert "INSERT INTO tool_access_log" in sql
        assert call_args[0][2] == "__activation__always"  # tool_name encodes mode

    @pytest.mark.asyncio
    async def test_log_records_responded(self):
        """
        Feature: openclaw-integration, Property 65: Activation decision logging

        Log should record access_granted=True when agent responds.
        """
        pool = make_mock_pool()
        session = make_session(pool=pool, activation_mode="always")

        await session.check_activation("hello", bot_mention=False)

        call_args = pool.execute.call_args
        access_granted = call_args[0][5]
        assert access_granted is True

    @pytest.mark.asyncio
    async def test_log_records_ignored(self):
        """
        Feature: openclaw-integration, Property 65: Activation decision logging

        Log should record access_granted=False when agent ignores.
        """
        pool = make_mock_pool()
        session = make_session(pool=pool, activation_mode="mention")

        await session.check_activation("hello", bot_mention=False)

        call_args = pool.execute.call_args
        access_granted = call_args[0][5]
        assert access_granted is False

    @pytest.mark.asyncio
    async def test_log_failure_does_not_raise(self):
        """
        Feature: openclaw-integration, Property 65: Activation decision logging

        Database errors during logging should be silenced.
        """
        pool = make_mock_pool()
        pool.execute = AsyncMock(side_effect=Exception("DB error"))
        session = make_session(pool=pool, activation_mode="always")

        # Should not raise
        result = await session.check_activation("hello", bot_mention=False)
        assert result is True

    @given(mode=activation_modes, mention=st.booleans())
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_every_check_produces_log(self, mode, mention):
        """
        Feature: openclaw-integration, Property 65: Activation decision logging

        Every call to check_activation should produce exactly one log entry.
        """
        pool = make_mock_pool()
        session = make_session(pool=pool, activation_mode=mode)

        await session.check_activation("hello", bot_mention=mention)

        assert pool.execute.call_count == 1
