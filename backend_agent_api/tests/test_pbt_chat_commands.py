"""Property-based tests for chat command system.

Feature: openclaw-integration (Task 19.1)
Properties tested: 56, 57, 58

Tests command parsing and execution, error handling,
and channel-specific command prefixes.
"""

import string
import sys
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat_commands import (
    AVAILABLE_COMMANDS,
    CHANNEL_PREFIXES,
    DEFAULT_PREFIX,
    ChatCommandHandler,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

safe_text = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())
channel_types = st.sampled_from(["slack", "telegram", "discord", "whatsapp"])
known_commands = st.sampled_from(AVAILABLE_COMMANDS)
safe_id = st.text(
    alphabet=string.ascii_letters + string.digits + "-_.",
    min_size=1,
    max_size=30,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_session(
    session_id="test:user:chat",
    channel_id="slack-main",
    user_id="user1",
    chat_id="chat1",
    session_type="main",
    activation_mode="mention",
    message_count=10,
    tool_allowlist=None,
    tool_denylist=None,
    browser_enabled=False,
    session_tools_enabled=False,
    token_usage=None,
):
    """Create a mock Session object."""
    session = MagicMock()
    session.session_id = session_id
    session.channel_id = channel_id
    session.user_id = user_id
    session.chat_id = chat_id
    session.session_type = session_type
    session.activation_mode = activation_mode
    session.message_count = message_count
    session.tool_allowlist = tool_allowlist or ["*"]
    session.tool_denylist = tool_denylist or []
    session.browser_enabled = browser_enabled
    session.session_tools_enabled = session_tools_enabled
    session.token_usage = token_usage or {}
    session.clear_history = AsyncMock()
    session.compact = AsyncMock()
    session.update_token_usage = AsyncMock()
    return session


def make_mock_session_manager():
    """Create a mock SessionManager."""
    sm = MagicMock()
    new_session = make_mock_session(session_id="new:session:id")
    sm.create_session = AsyncMock(return_value=new_session)
    return sm


def make_handler(session_manager=None):
    """Create a ChatCommandHandler with mock dependencies."""
    if session_manager is None:
        session_manager = make_mock_session_manager()
    return ChatCommandHandler(session_manager=session_manager)


# ===========================================================================
# Property 56: Command parsing and execution
# ===========================================================================


class TestCommandParsingAndExecution:
    """Property 56: All registered commands parse correctly and return
    non-empty results."""

    @given(command=known_commands, channel_type=channel_types)
    @settings(max_examples=100, deadline=None)
    def test_known_commands_parse_correctly(self, command, channel_type):
        """
        Feature: openclaw-integration, Property 56: Command parsing and execution

        All known commands should parse to (command_name, []) when sent
        with the correct prefix.
        """
        handler = make_handler()
        prefix = handler.get_prefix(channel_type)
        text = f"{prefix}{command}"

        name, args = handler.parse_command(text, channel_type)
        assert name == command
        assert args == []

    @given(command=known_commands, channel_type=channel_types)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_known_commands_return_nonempty(self, command, channel_type):
        """
        Feature: openclaw-integration, Property 56: Command parsing and execution

        Executing any known command should return a non-empty string.
        """
        handler = make_handler()
        session = make_mock_session()
        result = await handler.execute(command, session)
        assert isinstance(result, str)
        assert len(result) > 0

    @given(command=known_commands, channel_type=channel_types)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_handle_message_returns_response_for_commands(
        self, command, channel_type
    ):
        """
        Feature: openclaw-integration, Property 56: Command parsing and execution

        handle_message should return a string for valid commands (not None).
        """
        handler = make_handler()
        session = make_mock_session()
        prefix = handler.get_prefix(channel_type)
        text = f"{prefix}{command}"

        result = await handler.handle_message(text, session, channel_type)
        assert result is not None
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_status_includes_session_info(self):
        """
        Feature: openclaw-integration, Property 56: Command parsing and execution

        /status should include session_id and message count.
        """
        handler = make_handler()
        session = make_mock_session(
            session_id="abc:user:chat", message_count=42
        )
        result = await handler.execute("status", session)
        assert "abc:user:chat" in result
        assert "42" in result

    @pytest.mark.asyncio
    async def test_reset_clears_history(self):
        """
        Feature: openclaw-integration, Property 56: Command parsing and execution

        /reset should call session.clear_history().
        """
        handler = make_handler()
        session = make_mock_session()
        result = await handler.execute("reset", session)
        session.clear_history.assert_called_once()
        assert "reset" in result.lower() or "cleared" in result.lower()

    @pytest.mark.asyncio
    async def test_new_creates_session(self):
        """
        Feature: openclaw-integration, Property 56: Command parsing and execution

        /new should call session_manager.create_session().
        """
        sm = make_mock_session_manager()
        handler = make_handler(session_manager=sm)
        session = make_mock_session()
        result = await handler.execute("new", session)
        sm.create_session.assert_called_once()
        assert "new session" in result.lower() or "created" in result.lower()

    @pytest.mark.asyncio
    async def test_compact_calls_session_compact(self):
        """
        Feature: openclaw-integration, Property 56: Command parsing and execution

        /compact should call session.compact().
        """
        handler = make_handler()
        session = make_mock_session()
        result = await handler.execute("compact", session)
        session.compact.assert_called_once()
        assert "compact" in result.lower()

    @pytest.mark.asyncio
    async def test_think_toggles_verbose_reasoning(self):
        """
        Feature: openclaw-integration, Property 56: Command parsing and execution

        /think should toggle verbose_reasoning in token_usage.
        """
        handler = make_handler()
        session = make_mock_session(token_usage={})
        result = await handler.execute("think", session)
        session.update_token_usage.assert_called_once()
        call_args = session.update_token_usage.call_args[0][0]
        assert call_args["verbose_reasoning"] is True
        assert "enabled" in result

    @pytest.mark.asyncio
    async def test_verbose_toggles_tool_output(self):
        """
        Feature: openclaw-integration, Property 56: Command parsing and execution

        /verbose should toggle verbose_tools in token_usage.
        """
        handler = make_handler()
        session = make_mock_session(token_usage={})
        result = await handler.execute("verbose", session)
        session.update_token_usage.assert_called_once()
        call_args = session.update_token_usage.call_args[0][0]
        assert call_args["verbose_tools"] is True
        assert "enabled" in result

    @pytest.mark.asyncio
    async def test_usage_shows_token_stats(self):
        """
        Feature: openclaw-integration, Property 56: Command parsing and execution

        /usage should show token counts.
        """
        handler = make_handler()
        session = make_mock_session(
            token_usage={"input_tokens": 1000, "output_tokens": 500}
        )
        result = await handler.execute("usage", session)
        assert "1,000" in result
        assert "500" in result

    @given(command=known_commands)
    @settings(max_examples=50, deadline=None)
    def test_parse_with_args(self, command):
        """
        Feature: openclaw-integration, Property 56: Command parsing and execution

        Commands with arguments should parse the args correctly.
        """
        handler = make_handler()
        text = f"/{command} arg1 arg2"
        name, args = handler.parse_command(text, "slack")
        assert name == command
        assert args == ["arg1", "arg2"]


# ===========================================================================
# Property 57: Command error handling
# ===========================================================================


class TestCommandErrorHandling:
    """Property 57: Unrecognized commands return help, invalid args handled."""

    @given(
        cmd_name=st.text(
            alphabet=string.ascii_lowercase, min_size=1, max_size=20
        ).filter(lambda s: s not in AVAILABLE_COMMANDS)
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_unrecognized_command_returns_help(self, cmd_name):
        """
        Feature: openclaw-integration, Property 57: Command error handling

        Unrecognized commands should return the help message.
        """
        handler = make_handler()
        session = make_mock_session()
        result = await handler.execute(cmd_name, session)
        assert "Available commands" in result

    @pytest.mark.asyncio
    async def test_command_exception_returns_error_message(self):
        """
        Feature: openclaw-integration, Property 57: Command error handling

        If a command handler raises, execute() should return an error message.
        """
        handler = make_handler()
        session = make_mock_session()
        session.clear_history = AsyncMock(side_effect=Exception("DB error"))

        result = await handler.execute("reset", session)
        assert "Error" in result

    def test_empty_text_is_not_command(self):
        """
        Feature: openclaw-integration, Property 57: Command error handling

        Empty text should not be detected as a command.
        """
        handler = make_handler()
        assert handler.is_command("", "slack") is False
        assert handler.is_command("   ", "slack") is False

    def test_parse_empty_returns_empty(self):
        """
        Feature: openclaw-integration, Property 57: Command error handling

        Parsing empty text should return empty command name.
        """
        handler = make_handler()
        name, args = handler.parse_command("", "slack")
        assert name == ""
        assert args == []

    def test_parse_prefix_only_returns_empty(self):
        """
        Feature: openclaw-integration, Property 57: Command error handling

        Parsing just the prefix (e.g. "/") should return empty command.
        """
        handler = make_handler()
        name, args = handler.parse_command("/", "slack")
        assert name == ""
        assert args == []

    @pytest.mark.asyncio
    async def test_handle_message_returns_none_for_noncommand(self):
        """
        Feature: openclaw-integration, Property 57: Command error handling

        Non-command text should return None from handle_message.
        """
        handler = make_handler()
        session = make_mock_session()
        result = await handler.handle_message("hello world", session, "slack")
        assert result is None

    @pytest.mark.asyncio
    async def test_new_without_session_manager(self):
        """
        Feature: openclaw-integration, Property 57: Command error handling

        /new with no session_manager should return error message.
        """
        handler = ChatCommandHandler(session_manager=None)
        session = make_mock_session()
        result = await handler.execute("new", session)
        assert "not available" in result.lower()


# ===========================================================================
# Property 58: Channel-specific command prefixes
# ===========================================================================


class TestChannelSpecificPrefixes:
    """Property 58: Channel-specific command prefixes work correctly."""

    def test_slack_uses_slash(self):
        """
        Feature: openclaw-integration, Property 58: Channel-specific command prefixes

        Slack should use / as command prefix.
        """
        handler = make_handler()
        assert handler.get_prefix("slack") == "/"
        assert handler.is_command("/status", "slack") is True
        assert handler.is_command("!status", "slack") is False

    def test_telegram_uses_slash(self):
        """
        Feature: openclaw-integration, Property 58: Channel-specific command prefixes

        Telegram should use / as command prefix.
        """
        handler = make_handler()
        assert handler.get_prefix("telegram") == "/"
        assert handler.is_command("/status", "telegram") is True

    def test_discord_uses_bang(self):
        """
        Feature: openclaw-integration, Property 58: Channel-specific command prefixes

        Discord should use ! as command prefix.
        """
        handler = make_handler()
        assert handler.get_prefix("discord") == "!"
        assert handler.is_command("!status", "discord") is True
        assert handler.is_command("/status", "discord") is False

    def test_whatsapp_uses_slash(self):
        """
        Feature: openclaw-integration, Property 58: Channel-specific command prefixes

        WhatsApp should use / as command prefix.
        """
        handler = make_handler()
        assert handler.get_prefix("whatsapp") == "/"

    def test_unknown_channel_uses_default(self):
        """
        Feature: openclaw-integration, Property 58: Channel-specific command prefixes

        Unknown channel types should use default prefix /.
        """
        handler = make_handler()
        assert handler.get_prefix("unknown") == DEFAULT_PREFIX
        assert handler.is_command("/status", "unknown") is True

    @given(channel_type=channel_types, command=known_commands)
    @settings(max_examples=100, deadline=None)
    def test_command_detected_with_correct_prefix(self, channel_type, command):
        """
        Feature: openclaw-integration, Property 58: Channel-specific command prefixes

        Commands with the correct prefix should be detected.
        """
        handler = make_handler()
        prefix = CHANNEL_PREFIXES[channel_type]
        text = f"{prefix}{command}"
        assert handler.is_command(text, channel_type) is True

    @given(channel_type=channel_types, command=known_commands)
    @settings(max_examples=100, deadline=None)
    def test_parse_respects_channel_prefix(self, channel_type, command):
        """
        Feature: openclaw-integration, Property 58: Channel-specific command prefixes

        parse_command should use the correct prefix for the channel type.
        """
        handler = make_handler()
        prefix = CHANNEL_PREFIXES[channel_type]
        text = f"{prefix}{command}"
        name, args = handler.parse_command(text, channel_type)
        assert name == command

    def test_discord_slash_not_detected(self):
        """
        Feature: openclaw-integration, Property 58: Channel-specific command prefixes

        Discord should NOT detect / as a command prefix.
        """
        handler = make_handler()
        name, args = handler.parse_command("/status", "discord")
        assert name == ""

    @given(text=safe_text.filter(lambda s: not s.strip().startswith("/") and not s.strip().startswith("!")))
    @settings(max_examples=50, deadline=None)
    def test_nonprefix_text_not_detected(self, text):
        """
        Feature: openclaw-integration, Property 58: Channel-specific command prefixes

        Text without a command prefix should not be detected.
        """
        handler = make_handler()
        assert handler.is_command(text, "slack") is False
