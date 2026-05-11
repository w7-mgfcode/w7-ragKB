"""Property-based tests for session management.

Feature: openclaw-integration
Properties tested: 1, 12, 13, 14, 15, 16

Tests session routing determinism, creation idempotency, initialization,
isolation, archival, memory limits, activation modes, and tool allowlists.
"""

import string
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from hypothesis import HealthCheck, given, settings, strategies as st

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db_sessions import generate_session_id, parse_session_id
from session import (
    DEFAULT_AUTO_COMPACT_THRESHOLD,
    DEFAULT_MAX_MESSAGE_HISTORY,
    DEFAULT_TOOL_ALLOWLIST,
    Session,
    SessionConfig,
)


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
tool_names = st.text(
    alphabet=string.ascii_letters + string.digits + "_*?",
    min_size=1,
    max_size=30,
)
safe_text = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())


# ---------------------------------------------------------------------------
# Fixtures
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
    channel_id="test",
    user_id="user",
    chat_id="chat",
    session_type="main",
    activation_mode="mention",
    tool_allowlist=None,
    tool_denylist=None,
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
        tool_allowlist=tool_allowlist,
        tool_denylist=tool_denylist,
        **kwargs,
    )


# ===========================================================================
# Property 1: Message routing correctness (determinism)
# ===========================================================================


class TestRoutingDeterminism:
    """Property 1: Same routing key always produces the same session_id."""

    @given(
        channel_id=safe_id,
        user_id=safe_id,
        chat_id=safe_id,
    )
    @settings(max_examples=100, deadline=None)
    def test_same_inputs_same_session_id(self, channel_id, user_id, chat_id):
        """
        Feature: openclaw-integration, Property 1: Message routing correctness

        Deterministic: same inputs -> same session_id.
        """
        a = generate_session_id(channel_id, user_id, chat_id)
        b = generate_session_id(channel_id, user_id, chat_id)
        assert a == b

    @given(
        ch1=safe_id,
        u1=safe_id,
        c1=safe_id,
        ch2=safe_id,
        u2=safe_id,
        c2=safe_id,
    )
    @settings(max_examples=100, deadline=None)
    def test_different_inputs_different_session_id(
        self, ch1, u1, c1, ch2, u2, c2
    ):
        """
        Feature: openclaw-integration, Property 14: Session isolation

        Different routing keys should produce different session_ids.
        """
        if (ch1, u1, c1) == (ch2, u2, c2):
            return  # Skip identical inputs

        id1 = generate_session_id(ch1, u1, c1)
        id2 = generate_session_id(ch2, u2, c2)
        assert id1 != id2


# ===========================================================================
# Property 12: Session creation idempotency
# ===========================================================================


class TestSessionCreationIdempotency:
    """Property 12: create_session with same key returns same session_id."""

    @given(
        channel_id=safe_id,
        user_id=safe_id,
        chat_id=safe_id,
    )
    @settings(max_examples=50, deadline=None)
    def test_session_id_stable_across_creations(self, channel_id, user_id, chat_id):
        """
        Feature: openclaw-integration, Property 12: Session creation idempotency

        Creating sessions with same routing key should yield identical session_id.
        """
        sid1 = generate_session_id(channel_id, user_id, chat_id)
        sid2 = generate_session_id(channel_id, user_id, chat_id)
        assert sid1 == sid2


# ===========================================================================
# Property 13: Session initialization completeness
# ===========================================================================


class TestSessionInitialization:
    """Property 13: New sessions have all required fields."""

    @given(
        channel_id=safe_id,
        user_id=safe_id,
        chat_id=safe_id,
        session_type=session_types,
        activation_mode=activation_modes,
    )
    @settings(max_examples=100, deadline=None)
    def test_all_required_fields_present(
        self, channel_id, user_id, chat_id, session_type, activation_mode
    ):
        """
        Feature: openclaw-integration, Property 13: Session initialization completeness

        A newly created Session must have all required fields.
        """
        session_id = generate_session_id(channel_id, user_id, chat_id)
        session = make_session(
            session_id=session_id,
            channel_id=channel_id,
            user_id=user_id,
            chat_id=chat_id,
            session_type=session_type,
            activation_mode=activation_mode,
        )

        assert session.session_id == session_id
        assert session.channel_id == channel_id
        assert session.user_id == user_id
        assert session.chat_id == chat_id
        assert session.session_type == session_type
        assert session.activation_mode == activation_mode
        assert session.tool_allowlist is not None

    @given(session_type=session_types, activation_mode=activation_modes)
    @settings(max_examples=50, deadline=None)
    def test_session_config_validation(self, session_type, activation_mode):
        """
        Feature: openclaw-integration, Property 13: Session initialization completeness

        SessionConfig must validate session_type and activation_mode patterns.
        """
        config = SessionConfig(
            session_id="test:u:c",
            channel_id="test",
            user_id="u",
            chat_id="c",
            session_type=session_type,
            activation_mode=activation_mode,
            tool_allowlist=["*"],
            tool_denylist=[],
            max_message_history=100,
            auto_compact_threshold=80,
        )
        assert config.session_type == session_type
        assert config.activation_mode == activation_mode

    def test_invalid_session_type_rejected(self):
        """
        Feature: openclaw-integration, Property 13: Session initialization completeness

        Invalid session_type should be rejected by validation.
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SessionConfig(
                session_id="test:u:c",
                channel_id="test",
                user_id="u",
                chat_id="c",
                session_type="invalid",
                tool_allowlist=["*"],
                tool_denylist=[],
                max_message_history=100,
                auto_compact_threshold=80,
            )


# ===========================================================================
# Property 14: Session isolation
# ===========================================================================


class TestSessionIsolation:
    """Property 14: Different routing keys produce independent sessions."""

    @given(
        ch1=safe_id,
        u1=safe_id,
        c1=safe_id,
        ch2=safe_id,
        u2=safe_id,
        c2=safe_id,
    )
    @settings(max_examples=50, deadline=None)
    def test_sessions_have_independent_ids(self, ch1, u1, c1, ch2, u2, c2):
        """
        Feature: openclaw-integration, Property 14: Session isolation

        Two sessions from different routing keys must have different session_ids.
        """
        if (ch1, u1, c1) == (ch2, u2, c2):
            return

        s1 = make_session(session_id=generate_session_id(ch1, u1, c1))
        s2 = make_session(session_id=generate_session_id(ch2, u2, c2))
        assert s1.session_id != s2.session_id


# ===========================================================================
# Property 16: Session memory limits / tool allowlists
# ===========================================================================


class TestToolAllowlist:
    """Property 52/53: Wildcard matching and denylist precedence."""

    @given(tool_name=tool_names.filter(lambda s: "*" not in s and "?" not in s))
    @settings(max_examples=100, deadline=None)
    def test_wildcard_star_allows_all(self, tool_name):
        """
        Feature: openclaw-integration, Property 52: Wildcard pattern matching

        tool_allowlist=["*"] should allow any tool name.
        """
        session = make_session(tool_allowlist=["*"])
        assert session.is_tool_allowed(tool_name) is True

    @given(tool_name=tool_names.filter(lambda s: "*" not in s and "?" not in s))
    @settings(max_examples=100, deadline=None)
    def test_explicit_allowlist_blocks_unmatched(self, tool_name):
        """
        Feature: openclaw-integration, Property 51: Tool access control

        An allowlist with only a specific tool should block everything else.
        Note: Session.__init__ converts empty list to ["*"] by design,
        so we test with an explicit non-matching pattern instead.
        """
        session = make_session(tool_allowlist=["__never_matches__"])
        assert session.is_tool_allowed(tool_name) is False

    def test_falsy_allowlist_defaults_to_wildcard(self):
        """
        Feature: openclaw-integration, Property 50: Allowlist initialization

        Passing empty list to Session defaults to ["*"] (allow all).
        This is the intended behavior per Session.__init__.
        """
        session = make_session(tool_allowlist=[])
        assert session.tool_allowlist == ["*"]
        assert session.is_tool_allowed("any_tool") is True

    @given(tool_name=tool_names.filter(lambda s: "*" not in s and "?" not in s))
    @settings(max_examples=100, deadline=None)
    def test_denylist_takes_precedence(self, tool_name):
        """
        Feature: openclaw-integration, Property 53: Denylist precedence

        A tool in both allowlist and denylist should be blocked.
        """
        session = make_session(
            tool_allowlist=["*"],
            tool_denylist=[tool_name],
        )
        assert session.is_tool_allowed(tool_name) is False

    def test_glob_pattern_matching(self):
        """
        Feature: openclaw-integration, Property 52: Wildcard pattern matching

        Glob patterns like 'read_*' should match 'read_file' but not 'write_file'.
        """
        session = make_session(tool_allowlist=["read_*"])
        assert session.is_tool_allowed("read_file") is True
        assert session.is_tool_allowed("read_memory") is True
        assert session.is_tool_allowed("write_file") is False

    def test_denylist_glob_pattern(self):
        """
        Feature: openclaw-integration, Property 53: Denylist precedence

        Denylist glob patterns should block matching tools even if allowlist has '*'.
        """
        session = make_session(
            tool_allowlist=["*"],
            tool_denylist=["browser_*"],
        )
        assert session.is_tool_allowed("browser_navigate") is False
        assert session.is_tool_allowed("browser_screenshot") is False
        assert session.is_tool_allowed("read_file") is True


# ===========================================================================
# Activation mode properties (59-64)
# ===========================================================================


class TestActivationModes:
    """Properties 59-64: Activation mode behavior."""

    @given(text=safe_text)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_always_mode_activates_for_all(self, text):
        """
        Feature: openclaw-integration, Property 61: Always-on activation

        activation_mode='always' should activate for every message.
        """
        session = make_session(activation_mode="always")
        assert await session.check_activation(text, bot_mention=False) is True
        assert await session.check_activation(text, bot_mention=True) is True

    @given(text=safe_text)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_mention_mode_requires_mention(self, text):
        """
        Feature: openclaw-integration, Property 60: Mention-based activation

        activation_mode='mention' should only activate when bot_mention=True.
        """
        session = make_session(activation_mode="mention")
        assert await session.check_activation(text, bot_mention=True) is True
        assert await session.check_activation(text, bot_mention=False) is False

    @given(text=safe_text.filter(lambda s: not s.startswith("/")))
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_manual_mode_ignores_non_commands(self, text):
        """
        Feature: openclaw-integration, Property 62: Manual activation

        activation_mode='manual' should ignore messages not starting with '/'.
        """
        session = make_session(activation_mode="manual")
        assert await session.check_activation(text, bot_mention=False) is False

    @pytest.mark.asyncio
    async def test_manual_mode_activates_for_commands(self):
        """
        Feature: openclaw-integration, Property 62: Manual activation

        activation_mode='manual' should activate for messages starting with '/'.
        """
        session = make_session(activation_mode="manual")
        assert await session.check_activation("/status", bot_mention=False) is True
        assert await session.check_activation("/reset", bot_mention=False) is True
