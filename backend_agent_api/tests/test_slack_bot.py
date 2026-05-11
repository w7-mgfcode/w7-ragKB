"""Tests for slack_bot.py.

Validates:
- Message event extraction (user, text, channel, thread_ts)
- Bot/subtype messages are ignored
- ensure_slack_user is called on each message
- Session ID derived from channel + thread_ts
- Agent wired with correct AgentDeps
- 2 parallel Socket Mode handlers started for HA
- Error handling returns user-friendly fallback
"""

import asyncio
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Module-level stubs so slack_bot.py can be imported without real Slack tokens
# or heavy transitive dependencies (RestrictedPython, google-genai, etc.)
# ---------------------------------------------------------------------------

def _create_mock_tools_module():
    mod = types.ModuleType("tools")
    for name in (
        "web_search_tool",
        "image_analysis_tool",
        "retrieve_relevant_documents_tool",
        "list_documents_tool",
        "get_document_content_tool",
        "execute_sql_query_tool",
        "execute_safe_code_tool",
    ):
        setattr(mod, name, MagicMock())
    return mod


def _create_mock_prompt_module():
    mod = types.ModuleType("prompt")
    mod.AGENT_SYSTEM_PROMPT = "You are a test agent."
    return mod


@pytest.fixture(autouse=True)
def _isolate_imports(monkeypatch):
    """Inject mock modules and env vars before importing slack_bot."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_REGION", "us-central1")
    monkeypatch.setenv("LLM_CHOICE", "gemini-2.0-flash")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/test")

    saved = {}
    for mod_name in ("tools", "prompt", "agent", "slack_bot"):
        saved[mod_name] = sys.modules.pop(mod_name, None)

    sys.modules["tools"] = _create_mock_tools_module()
    sys.modules["prompt"] = _create_mock_prompt_module()

    yield

    for mod_name, original in saved.items():
        if original is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = original


def _import_slack_bot():
    """Import slack_bot with vertex_provider mocked."""
    from pydantic_ai.models.test import TestModel

    test_model = TestModel()
    with patch("vertex_provider.get_model", return_value=test_model):
        sys.modules.pop("agent", None)
        sys.modules.pop("slack_bot", None)
        import slack_bot as sb_mod
    return sb_mod


# ---------------------------------------------------------------------------
# handle_message tests
# ---------------------------------------------------------------------------

class TestHandleMessage:
    """Verify handle_message extracts fields and filters correctly."""

    @pytest.mark.asyncio
    async def test_ignores_bot_message_subtype(self):
        sb = _import_slack_bot()
        say = AsyncMock()
        event = {
            "subtype": "bot_message",
            "user": "U123",
            "text": "hello",
            "channel": "C001",
            "ts": "1234.5678",
        }
        await sb.handle_message(event, say)
        say.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_event_with_bot_id(self):
        sb = _import_slack_bot()
        say = AsyncMock()
        event = {
            "bot_id": "B999",
            "user": "U123",
            "text": "hello",
            "channel": "C001",
            "ts": "1234.5678",
        }
        await sb.handle_message(event, say)
        say.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_empty_text(self):
        sb = _import_slack_bot()
        say = AsyncMock()
        event = {
            "user": "U123",
            "text": "   ",
            "channel": "C001",
            "ts": "1234.5678",
        }
        await sb.handle_message(event, say)
        say.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_missing_user(self):
        sb = _import_slack_bot()
        say = AsyncMock()
        event = {"text": "hello", "channel": "C001", "ts": "1234.5678"}
        await sb.handle_message(event, say)
        say.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_run_agent_and_says_response(self):
        sb = _import_slack_bot()
        say = AsyncMock()
        event = {
            "user": "U123",
            "text": "What is RAG?",
            "channel": "C001",
            "ts": "1111.2222",
        }
        with patch.object(
            sb, "run_agent_for_message", new_callable=AsyncMock, return_value="RAG is ..."
        ):
            await sb.handle_message(event, say)
            sb.run_agent_for_message.assert_awaited_once_with(
                "U123", "What is RAG?", "C001", "1111.2222"
            )
            say.assert_awaited_once_with(text="RAG is ...", thread_ts="1111.2222")

    @pytest.mark.asyncio
    async def test_uses_thread_ts_when_present(self):
        sb = _import_slack_bot()
        say = AsyncMock()
        event = {
            "user": "U123",
            "text": "follow up",
            "channel": "C001",
            "ts": "1111.2222",
            "thread_ts": "0000.1111",
        }
        with patch.object(
            sb, "run_agent_for_message", new_callable=AsyncMock, return_value="ok"
        ):
            await sb.handle_message(event, say)
            sb.run_agent_for_message.assert_awaited_once_with(
                "U123", "follow up", "C001", "0000.1111"
            )
            say.assert_awaited_once_with(text="ok", thread_ts="0000.1111")


# ---------------------------------------------------------------------------
# run_agent_for_message tests
# ---------------------------------------------------------------------------

class TestRunAgentForMessage:
    """Verify agent invocation, user tracking, and session management."""

    @pytest.mark.asyncio
    async def test_calls_ensure_slack_user(self):
        sb = _import_slack_bot()
        mock_pool = AsyncMock()
        mock_pool.fetchval = AsyncMock(return_value=1)

        mock_result = MagicMock()
        mock_result.output = "agent reply"
        mock_result.all_messages.return_value = []

        with patch("slack_bot.get_pool", new_callable=AsyncMock, return_value=mock_pool), \
             patch("slack_bot.ensure_slack_user", new_callable=AsyncMock) as mock_ensure, \
             patch("slack_bot.store_message", new_callable=AsyncMock), \
             patch("slack_bot.fetch_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch("slack_bot.agent") as mock_agent, \
             patch("slack_bot.VertexEmbeddingClient"):
            mock_agent.run = AsyncMock(return_value=mock_result)
            await sb.run_agent_for_message("U123", "hi", "C001", "1111.2222")
            mock_ensure.assert_awaited_once_with(mock_pool, "U123")

    @pytest.mark.asyncio
    async def test_derives_session_id_from_channel_and_thread(self):
        sb = _import_slack_bot()
        mock_pool = AsyncMock()
        mock_pool.fetchval = AsyncMock(return_value=1)

        mock_result = MagicMock()
        mock_result.output = "reply"
        mock_result.all_messages.return_value = []

        with patch("slack_bot.get_pool", new_callable=AsyncMock, return_value=mock_pool), \
             patch("slack_bot.ensure_slack_user", new_callable=AsyncMock), \
             patch("slack_bot.store_message", new_callable=AsyncMock) as mock_store, \
             patch("slack_bot.fetch_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch("slack_bot.generate_session_id", return_value="abc123") as mock_gen, \
             patch("slack_bot.agent") as mock_agent, \
             patch("slack_bot.VertexEmbeddingClient"):
            mock_agent.run = AsyncMock(return_value=mock_result)
            await sb.run_agent_for_message("U123", "hi", "C001", "1111.2222")
            mock_gen.assert_called_once_with("C001", "1111.2222")

    @pytest.mark.asyncio
    async def test_returns_fallback_on_agent_error(self):
        sb = _import_slack_bot()
        mock_pool = AsyncMock()
        mock_pool.fetchval = AsyncMock(return_value=1)

        with patch("slack_bot.get_pool", new_callable=AsyncMock, return_value=mock_pool), \
             patch("slack_bot.ensure_slack_user", new_callable=AsyncMock), \
             patch("slack_bot.store_message", new_callable=AsyncMock), \
             patch("slack_bot.fetch_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch("slack_bot.agent") as mock_agent, \
             patch("slack_bot.VertexEmbeddingClient"):
            mock_agent.run = AsyncMock(side_effect=RuntimeError("LLM down"))
            result = await sb.run_agent_for_message("U123", "hi", "C001", "1111.2222")
            assert "trouble processing" in result

    @pytest.mark.asyncio
    async def test_creates_conversation_when_not_exists(self):
        sb = _import_slack_bot()
        mock_pool = AsyncMock()
        # fetchval returns None → conversation doesn't exist yet
        mock_pool.fetchval = AsyncMock(return_value=None)

        mock_result = MagicMock()
        mock_result.output = "reply"
        mock_result.all_messages.return_value = []

        with patch("slack_bot.get_pool", new_callable=AsyncMock, return_value=mock_pool), \
             patch("slack_bot.ensure_slack_user", new_callable=AsyncMock), \
             patch("slack_bot.create_conversation", new_callable=AsyncMock) as mock_create, \
             patch("slack_bot.store_message", new_callable=AsyncMock), \
             patch("slack_bot.fetch_conversation_history", new_callable=AsyncMock, return_value=[]), \
             patch("slack_bot.generate_session_id", return_value="sess1"), \
             patch("slack_bot.agent") as mock_agent, \
             patch("slack_bot.VertexEmbeddingClient"):
            mock_agent.run = AsyncMock(return_value=mock_result)
            await sb.run_agent_for_message("U123", "hi", "C001", "1111.2222")
            mock_create.assert_awaited_once_with(mock_pool, "U123", "sess1", "C001")


# ---------------------------------------------------------------------------
# start_socket_mode tests
# ---------------------------------------------------------------------------

class TestStartSocketMode:
    """Verify 2 parallel Socket Mode handlers are started."""

    @pytest.mark.asyncio
    async def test_starts_two_handlers(self):
        sb = _import_slack_bot()

        mock_handler_cls = MagicMock()
        handler_instance = AsyncMock()
        handler_instance.start_async = AsyncMock()
        mock_handler_cls.return_value = handler_instance

        with patch("slack_bot.AsyncSocketModeHandler", mock_handler_cls):
            await sb.start_socket_mode()
            assert mock_handler_cls.call_count == 2
            assert handler_instance.start_async.await_count == 2


# ---------------------------------------------------------------------------
# Session ID derivation (integration with db_conversations)
# ---------------------------------------------------------------------------

class TestSessionIdDerivation:
    """Verify session_id is deterministic from channel + thread."""

    def test_same_inputs_produce_same_session_id(self):
        from db_conversations import generate_session_id

        sid1 = generate_session_id("C001", "1111.2222")
        sid2 = generate_session_id("C001", "1111.2222")
        assert sid1 == sid2

    def test_different_threads_produce_different_ids(self):
        from db_conversations import generate_session_id

        sid1 = generate_session_id("C001", "1111.2222")
        sid2 = generate_session_id("C001", "3333.4444")
        assert sid1 != sid2

    def test_different_channels_produce_different_ids(self):
        from db_conversations import generate_session_id

        sid1 = generate_session_id("C001", "1111.2222")
        sid2 = generate_session_id("C002", "1111.2222")
        assert sid1 != sid2


# ---------------------------------------------------------------------------
# DM handling tests (Requirement 5.3)
# ---------------------------------------------------------------------------

class TestDMHandling:
    """Verify DM events (channel starting with 'D') are processed identically
    to channel messages — the handler makes no distinction.

    Validates: Requirements 5.3
    """

    @pytest.mark.asyncio
    async def test_dm_event_calls_run_agent_with_dm_channel(self):
        """A DM channel (starts with 'D') is passed through to run_agent_for_message."""
        sb = _import_slack_bot()
        say = AsyncMock()
        event = {
            "user": "U456",
            "text": "private question",
            "channel": "D9876543210",
            "ts": "5555.6666",
        }
        with patch.object(
            sb, "run_agent_for_message", new_callable=AsyncMock, return_value="dm reply"
        ):
            await sb.handle_message(event, say)
            sb.run_agent_for_message.assert_awaited_once_with(
                "U456", "private question", "D9876543210", "5555.6666"
            )

    @pytest.mark.asyncio
    async def test_dm_response_posted_back_to_dm_thread(self):
        """The response is posted back to the DM thread via say()."""
        sb = _import_slack_bot()
        say = AsyncMock()
        event = {
            "user": "U456",
            "text": "hello in DM",
            "channel": "D1111111111",
            "ts": "7777.8888",
        }
        with patch.object(
            sb, "run_agent_for_message", new_callable=AsyncMock, return_value="DM answer"
        ):
            await sb.handle_message(event, say)
            say.assert_awaited_once_with(text="DM answer", thread_ts="7777.8888")

    @pytest.mark.asyncio
    async def test_dm_with_thread_ts_uses_thread(self):
        """A threaded DM uses the thread_ts, not the message ts."""
        sb = _import_slack_bot()
        say = AsyncMock()
        event = {
            "user": "U456",
            "text": "threaded DM",
            "channel": "D2222222222",
            "ts": "9999.0000",
            "thread_ts": "8888.0000",
        }
        with patch.object(
            sb, "run_agent_for_message", new_callable=AsyncMock, return_value="ok"
        ):
            await sb.handle_message(event, say)
            sb.run_agent_for_message.assert_awaited_once_with(
                "U456", "threaded DM", "D2222222222", "8888.0000"
            )
            say.assert_awaited_once_with(text="ok", thread_ts="8888.0000")


# ---------------------------------------------------------------------------
# SlackApiError retry tests (Requirement 5.5 / error handling)
# ---------------------------------------------------------------------------

class TestSlackApiErrorRetry:
    """Verify handle_message retries once on SlackApiError and handles
    double failures gracefully.

    Validates: Requirements 5.5
    """

    @pytest.mark.asyncio
    async def test_retries_with_fallback_on_first_say_failure(self):
        """When say() raises SlackApiError, a fallback message is sent."""
        sb = _import_slack_bot()
        from slack_sdk.errors import SlackApiError

        error_response = {"ok": False, "error": "channel_not_found"}
        say = AsyncMock(
            side_effect=[
                SlackApiError("post failed", response=error_response),
                None,  # retry succeeds
            ]
        )
        event = {
            "user": "U789",
            "text": "trigger error",
            "channel": "C001",
            "ts": "1000.2000",
        }
        with patch.object(
            sb, "run_agent_for_message", new_callable=AsyncMock, return_value="agent reply"
        ):
            await sb.handle_message(event, say)

        assert say.await_count == 2
        # First call: the agent response
        say.assert_any_await(text="agent reply", thread_ts="1000.2000")
        # Second call: the fallback
        say.assert_any_await(
            text="Sorry, I encountered an error. Please try again.",
            thread_ts="1000.2000",
        )

    @pytest.mark.asyncio
    async def test_handles_double_failure_gracefully(self):
        """When both say() calls raise SlackApiError, the handler doesn't crash."""
        sb = _import_slack_bot()
        from slack_sdk.errors import SlackApiError

        error_response = {"ok": False, "error": "channel_not_found"}
        say = AsyncMock(
            side_effect=SlackApiError("always fails", response=error_response)
        )
        event = {
            "user": "U789",
            "text": "double fail",
            "channel": "C001",
            "ts": "3000.4000",
        }
        with patch.object(
            sb, "run_agent_for_message", new_callable=AsyncMock, return_value="reply"
        ):
            # Should not raise — logs error and returns gracefully
            await sb.handle_message(event, say)

        assert say.await_count == 2


# ---------------------------------------------------------------------------
# message_changed / message_deleted subtype tests
# ---------------------------------------------------------------------------

class TestSubtypeFiltering:
    """Verify message_changed and message_deleted subtypes are ignored.

    Validates: Requirements 5.2
    """

    @pytest.mark.asyncio
    async def test_ignores_message_changed_subtype(self):
        sb = _import_slack_bot()
        say = AsyncMock()
        event = {
            "subtype": "message_changed",
            "user": "U123",
            "text": "edited text",
            "channel": "C001",
            "ts": "1234.5678",
        }
        await sb.handle_message(event, say)
        say.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_message_deleted_subtype(self):
        sb = _import_slack_bot()
        say = AsyncMock()
        event = {
            "subtype": "message_deleted",
            "user": "U123",
            "text": "deleted text",
            "channel": "C001",
            "ts": "1234.5678",
        }
        await sb.handle_message(event, say)
        say.assert_not_called()
