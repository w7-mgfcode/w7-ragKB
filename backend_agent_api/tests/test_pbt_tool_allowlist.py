"""Property-based tests for tool allowlist system.

Feature: openclaw-integration (Tasks 17.1)
Properties tested: 50, 51, 52, 53, 54, 55

Tests tool allowlist initialization, access control, wildcard pattern matching,
denylist precedence, dynamic updates, and tool blocking audit logging.
"""

import string
import sys
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tool_allowlist import (
    DEFAULT_ALLOWLISTS,
    DEFAULT_DENYLISTS,
    ToolAllowlist,
)
from session import Session


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

safe_id = st.text(
    alphabet=string.ascii_letters + string.digits + "-_.",
    min_size=1,
    max_size=30,
)
session_types = st.sampled_from(["main", "group", "webhook"])
channel_types = st.sampled_from(["slack", "telegram", "discord", "whatsapp"])
tool_names = st.text(
    alphabet=string.ascii_letters + string.digits + "_",
    min_size=1,
    max_size=30,
)
wildcard_patterns = st.sampled_from([
    "*", "web_*", "read_*", "browser_*", "execute_*",
    "retrieve_*", "sessions_*", "list_*", "get_*",
])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_pool():
    """Create a mock asyncpg pool."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock()
    # Mock the acquire() context manager for ToolAllowlist.log_blocked_tool
    conn_mock = MagicMock()
    conn_mock.execute = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn_mock)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=cm)
    return pool


def make_allowlist(pool=None):
    """Create a ToolAllowlist instance with mock pool."""
    if pool is None:
        pool = make_mock_pool()
    return ToolAllowlist(pool)


def make_session(
    pool=None,
    session_id="test:user:chat",
    channel_id="test",
    user_id="user",
    chat_id="chat",
    session_type="main",
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
        tool_allowlist=tool_allowlist,
        tool_denylist=tool_denylist,
        **kwargs,
    )


# ===========================================================================
# Property 50: Allowlist initialization
# ===========================================================================


class TestAllowlistInitialization:
    """Property 50: Sessions initialized with Tool_Allowlist based on
    channel, user, and session type."""

    @given(
        session_type=session_types,
        channel_type=channel_types,
        user_id=safe_id,
    )
    @settings(max_examples=100, deadline=None)
    def test_initialization_returns_correct_defaults(
        self, session_type, channel_type, user_id
    ):
        """
        Feature: openclaw-integration, Property 50: Allowlist initialization

        Allowlist defaults match session_type, denylist defaults match channel_type.
        """
        ta = make_allowlist()
        channel_id = f"{channel_type}-main"

        allowlist, denylist = ta.initialize_allowlist(channel_id, user_id, session_type)

        expected_allowlist = DEFAULT_ALLOWLISTS[session_type]
        expected_denylist = DEFAULT_DENYLISTS[channel_type]

        assert allowlist == expected_allowlist
        assert denylist == expected_denylist

    @given(session_type=session_types)
    @settings(max_examples=50, deadline=None)
    def test_main_sessions_allow_all(self, session_type):
        """
        Feature: openclaw-integration, Property 50: Allowlist initialization

        Main sessions should get wildcard allowlist, others should be restricted.
        """
        ta = make_allowlist()
        allowlist, _ = ta.initialize_allowlist("slack-main", "user1", session_type)

        if session_type == "main":
            assert "*" in allowlist
        else:
            assert "*" not in allowlist

    def test_unknown_channel_type_gets_empty_denylist(self):
        """
        Feature: openclaw-integration, Property 50: Allowlist initialization

        Unknown channel type should get empty denylist.
        """
        ta = make_allowlist()
        _, denylist = ta.initialize_allowlist("custom-adapter", "user1", "main")
        assert denylist == []

    def test_unknown_session_type_gets_wildcard_allowlist(self):
        """
        Feature: openclaw-integration, Property 50: Allowlist initialization

        Unknown session type should default to wildcard allowlist.
        """
        ta = make_allowlist()
        allowlist, _ = ta.initialize_allowlist("slack-main", "user1", "unknown_type")
        assert "*" in allowlist

    def test_initialization_returns_copies(self):
        """
        Feature: openclaw-integration, Property 50: Allowlist initialization

        Returned lists should be copies, not references to defaults.
        """
        ta = make_allowlist()
        al1, dl1 = ta.initialize_allowlist("slack-main", "user1", "group")
        al2, dl2 = ta.initialize_allowlist("slack-main", "user1", "group")

        al1.append("extra_tool")
        assert "extra_tool" not in al2


# ===========================================================================
# Property 51: Tool access control
# ===========================================================================


class TestToolAccessControl:
    """Property 51: Tool execution blocked if not in allowlist."""

    @given(tool_name=tool_names)
    @settings(max_examples=100, deadline=None)
    def test_wildcard_allows_all_tools(self, tool_name):
        """
        Feature: openclaw-integration, Property 51: Tool access control

        Wildcard allowlist should allow any tool.
        """
        ta = make_allowlist()
        assert ta.is_tool_allowed(tool_name, ["*"], []) is True

    @given(tool_name=tool_names)
    @settings(max_examples=100, deadline=None)
    def test_empty_allowlist_blocks_all(self, tool_name):
        """
        Feature: openclaw-integration, Property 51: Tool access control

        Empty allowlist should block all tools.
        """
        ta = make_allowlist()
        assert ta.is_tool_allowed(tool_name, [], []) is False

    @given(tool_name=tool_names)
    @settings(max_examples=100, deadline=None)
    def test_exact_match_allows(self, tool_name):
        """
        Feature: openclaw-integration, Property 51: Tool access control

        Exact tool name in allowlist should be allowed.
        """
        ta = make_allowlist()
        assert ta.is_tool_allowed(tool_name, [tool_name], []) is True

    @given(tool_name=tool_names)
    @settings(max_examples=100, deadline=None)
    def test_unlisted_tool_blocked(self, tool_name):
        """
        Feature: openclaw-integration, Property 51: Tool access control

        Tool not matching any pattern should be blocked.
        """
        ta = make_allowlist()
        # Use a pattern that won't match any tool_name from the strategy
        assert ta.is_tool_allowed(tool_name, ["ZZZUNMATCHED"], []) is False

    @given(tool_name=tool_names)
    @settings(max_examples=100, deadline=None)
    def test_session_is_tool_allowed_matches_allowlist(self, tool_name):
        """
        Feature: openclaw-integration, Property 51: Tool access control

        Session.is_tool_allowed() should behave like ToolAllowlist.is_tool_allowed().
        """
        session = make_session(tool_allowlist=["*"], tool_denylist=[])
        ta = make_allowlist()

        session_result = session.is_tool_allowed(tool_name)
        ta_result = ta.is_tool_allowed(tool_name, ["*"], [])
        assert session_result == ta_result


# ===========================================================================
# Property 52: Wildcard pattern matching
# ===========================================================================


class TestWildcardPatternMatching:
    """Property 52: Wildcard pattern matching with fnmatch."""

    def test_prefix_wildcard_matches(self):
        """
        Feature: openclaw-integration, Property 52: Wildcard pattern matching

        Pattern 'web_*' should match 'web_search' but not 'read_docs'.
        """
        ta = make_allowlist()
        assert ta.is_tool_allowed("web_search", ["web_*"], []) is True
        assert ta.is_tool_allowed("web_scrape", ["web_*"], []) is True
        assert ta.is_tool_allowed("read_docs", ["web_*"], []) is False

    def test_question_mark_wildcard(self):
        """
        Feature: openclaw-integration, Property 52: Wildcard pattern matching

        Pattern 'read_?' should match single-char suffix only.
        """
        ta = make_allowlist()
        assert ta.is_tool_allowed("read_a", ["read_?"], []) is True
        assert ta.is_tool_allowed("read_ab", ["read_?"], []) is False

    @given(tool_name=tool_names)
    @settings(max_examples=100, deadline=None)
    def test_star_matches_everything(self, tool_name):
        """
        Feature: openclaw-integration, Property 52: Wildcard pattern matching

        The '*' pattern should match every tool name.
        """
        ta = make_allowlist()
        assert ta.is_tool_allowed(tool_name, ["*"], []) is True

    def test_multiple_patterns_any_match(self):
        """
        Feature: openclaw-integration, Property 52: Wildcard pattern matching

        Tool matching any pattern in the list should be allowed.
        """
        ta = make_allowlist()
        allowlist = ["web_*", "read_*", "browser_*"]
        assert ta.is_tool_allowed("web_search", allowlist, []) is True
        assert ta.is_tool_allowed("read_docs", allowlist, []) is True
        assert ta.is_tool_allowed("browser_navigate", allowlist, []) is True
        assert ta.is_tool_allowed("execute_code", allowlist, []) is False

    @given(
        prefix=st.text(
            alphabet=string.ascii_lowercase, min_size=1, max_size=10
        ),
        suffix=st.text(
            alphabet=string.ascii_lowercase + string.digits, min_size=1, max_size=10
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_prefix_pattern_matches_prefix(self, prefix, suffix):
        """
        Feature: openclaw-integration, Property 52: Wildcard pattern matching

        Pattern 'prefix_*' should match 'prefix_<anything>'.
        """
        ta = make_allowlist()
        pattern = f"{prefix}_*"
        tool = f"{prefix}_{suffix}"
        assert ta.is_tool_allowed(tool, [pattern], []) is True

    @given(
        prefix=st.text(
            alphabet=string.ascii_lowercase, min_size=1, max_size=10
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_prefix_pattern_rejects_different_prefix(self, prefix):
        """
        Feature: openclaw-integration, Property 52: Wildcard pattern matching

        Pattern 'prefix_*' should not match 'other_tool'.
        """
        ta = make_allowlist()
        pattern = f"{prefix}_*"
        other_tool = "zzz_completely_different"
        if not other_tool.startswith(prefix + "_"):
            assert ta.is_tool_allowed(other_tool, [pattern], []) is False


# ===========================================================================
# Property 53: Denylist precedence
# ===========================================================================


class TestDenylistPrecedence:
    """Property 53: Denylist overrides allowlist for specific dangerous tools."""

    @given(tool_name=tool_names)
    @settings(max_examples=100, deadline=None)
    def test_denied_tool_blocked_even_with_wildcard(self, tool_name):
        """
        Feature: openclaw-integration, Property 53: Denylist precedence

        Tool in denylist should be blocked even with wildcard allowlist.
        """
        ta = make_allowlist()
        assert ta.is_tool_allowed(tool_name, ["*"], [tool_name]) is False

    @given(tool_name=tool_names)
    @settings(max_examples=100, deadline=None)
    def test_denied_tool_blocked_even_with_exact_allow(self, tool_name):
        """
        Feature: openclaw-integration, Property 53: Denylist precedence

        Tool in both allowlist and denylist should be blocked.
        """
        ta = make_allowlist()
        assert ta.is_tool_allowed(tool_name, [tool_name], [tool_name]) is False

    def test_denylist_pattern_blocks_matching_tools(self):
        """
        Feature: openclaw-integration, Property 53: Denylist precedence

        Denylist patterns should block matching tools.
        """
        ta = make_allowlist()
        assert ta.is_tool_allowed("execute_code", ["*"], ["execute_*"]) is False
        assert ta.is_tool_allowed("execute_sql", ["*"], ["execute_*"]) is False
        assert ta.is_tool_allowed("web_search", ["*"], ["execute_*"]) is True

    @given(tool_name=tool_names)
    @settings(max_examples=100, deadline=None)
    def test_session_denylist_precedence(self, tool_name):
        """
        Feature: openclaw-integration, Property 53: Denylist precedence

        Session.is_tool_allowed() respects denylist precedence.
        """
        session = make_session(
            tool_allowlist=["*"],
            tool_denylist=[tool_name],
        )
        assert session.is_tool_allowed(tool_name) is False

    def test_empty_denylist_no_blocking(self):
        """
        Feature: openclaw-integration, Property 53: Denylist precedence

        Empty denylist should not block any tools.
        """
        ta = make_allowlist()
        assert ta.is_tool_allowed("web_search", ["*"], []) is True
        assert ta.is_tool_allowed("execute_code", ["*"], []) is True


# ===========================================================================
# Property 54: Dynamic allowlist updates
# ===========================================================================


class TestDynamicAllowlistUpdates:
    """Property 54: Dynamic updates to allowlist applied immediately."""

    @pytest.mark.asyncio
    async def test_update_allowlist_changes_permissions(self):
        """
        Feature: openclaw-integration, Property 54: Dynamic allowlist updates

        Updating allowlist should change is_tool_allowed() results immediately.
        """
        pool = make_mock_pool()
        session = make_session(pool=pool, tool_allowlist=["*"])

        # Initially all tools are allowed
        assert session.is_tool_allowed("web_search") is True
        assert session.is_tool_allowed("execute_code") is True

        # Update to restricted allowlist
        await session.update_tool_allowlist(["web_search"])

        # Now only web_search is allowed
        assert session.is_tool_allowed("web_search") is True
        assert session.is_tool_allowed("execute_code") is False

    @pytest.mark.asyncio
    async def test_update_denylist_changes_permissions(self):
        """
        Feature: openclaw-integration, Property 54: Dynamic allowlist updates

        Updating denylist should block previously allowed tools.
        """
        pool = make_mock_pool()
        session = make_session(pool=pool, tool_allowlist=["*"], tool_denylist=[])

        assert session.is_tool_allowed("execute_code") is True

        # Add execute_code to denylist
        await session.update_tool_allowlist(["*"], tool_denylist=["execute_code"])

        assert session.is_tool_allowed("execute_code") is False
        assert session.is_tool_allowed("web_search") is True

    @pytest.mark.asyncio
    async def test_update_calls_database(self):
        """
        Feature: openclaw-integration, Property 54: Dynamic allowlist updates

        update_tool_allowlist should persist changes via database.
        """
        pool = make_mock_pool()
        session = make_session(pool=pool, tool_allowlist=["*"])

        await session.update_tool_allowlist(["web_search", "read_*"])

        # Should have called db_sessions.update_session_tool_allowlist
        pool.execute.assert_called()

    @given(
        tool_name=tool_names,
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_update_immediately_reflected(self, tool_name):
        """
        Feature: openclaw-integration, Property 54: Dynamic allowlist updates

        After update, is_tool_allowed() immediately reflects new permissions.
        """
        pool = make_mock_pool()
        session = make_session(pool=pool, tool_allowlist=["ZZZNO_MATCH"])

        # Tool should be blocked (only ZZZNO_MATCH is allowed)
        assert session.is_tool_allowed(tool_name) is False

        # Update to allow the tool
        await session.update_tool_allowlist([tool_name])

        # Now it should be allowed
        assert session.is_tool_allowed(tool_name) is True


# ===========================================================================
# Property 55: Tool blocking audit log
# ===========================================================================


class TestToolBlockingAuditLog:
    """Property 55: All blocked attempts logged with session_id, tool_name, timestamp."""

    @pytest.mark.asyncio
    async def test_blocked_tool_logged_to_database(self):
        """
        Feature: openclaw-integration, Property 55: Tool blocking audit log

        log_blocked_tool() should insert into tool_access_log table.
        """
        pool = make_mock_pool()
        session = make_session(
            pool=pool,
            session_id="test:user:chat",
            channel_id="slack-main",
            user_id="user1",
        )

        await session.log_blocked_tool("execute_code")

        # Should have called pool.execute with INSERT
        pool.execute.assert_called_once()
        call_args = pool.execute.call_args
        sql = call_args[0][0]
        assert "INSERT INTO tool_access_log" in sql
        assert call_args[0][1] == "test:user:chat"   # session_id
        assert call_args[0][2] == "execute_code"      # tool_name
        assert call_args[0][3] == "user1"             # user_id
        assert call_args[0][4] == "slack-main"        # channel_id
        assert call_args[0][5] is False               # access_granted

    @pytest.mark.asyncio
    async def test_blocked_tool_logged_with_toolallowlist(self):
        """
        Feature: openclaw-integration, Property 55: Tool blocking audit log

        ToolAllowlist.log_blocked_tool() should insert audit record.
        """
        pool = make_mock_pool()
        ta = make_allowlist(pool)

        await ta.log_blocked_tool("sess1", "execute_code", "user1", "slack-main")

        # Should have used pool.acquire context manager
        pool.acquire.assert_called_once()

    @pytest.mark.asyncio
    async def test_logging_failure_does_not_raise(self):
        """
        Feature: openclaw-integration, Property 55: Tool blocking audit log

        Database errors during logging should be silenced (non-fatal).
        """
        pool = make_mock_pool()
        pool.execute = AsyncMock(side_effect=Exception("DB error"))
        session = make_session(pool=pool)

        # Should not raise
        await session.log_blocked_tool("execute_code")

    @pytest.mark.asyncio
    async def test_toolallowlist_logging_failure_does_not_raise(self):
        """
        Feature: openclaw-integration, Property 55: Tool blocking audit log

        ToolAllowlist.log_blocked_tool() should not raise on DB error.
        """
        pool = make_mock_pool()
        conn_mock = MagicMock()
        conn_mock.execute = AsyncMock(side_effect=Exception("DB error"))
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=conn_mock)
        cm.__aexit__ = AsyncMock(return_value=False)
        pool.acquire = MagicMock(return_value=cm)

        ta = make_allowlist(pool)

        # Should not raise
        await ta.log_blocked_tool("sess1", "execute_code")

    @given(tool_name=tool_names)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_every_blocked_tool_gets_logged(self, tool_name):
        """
        Feature: openclaw-integration, Property 55: Tool blocking audit log

        Every blocked tool attempt should produce a log entry.
        """
        pool = make_mock_pool()
        session = make_session(pool=pool, tool_allowlist=["ZZZNO_MATCH"], tool_denylist=[])

        # Tool is blocked (only ZZZNO_MATCH is allowed)
        assert session.is_tool_allowed(tool_name) is False

        # Log the blocked attempt
        await session.log_blocked_tool(tool_name)

        # Verify DB insert was called with the tool name
        call_args = pool.execute.call_args
        assert call_args[0][2] == tool_name
