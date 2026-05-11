"""Property-based test: Slack message handling with user identification.

**Validates: Requirements 5.2, 8.4**

Property 4: For any Slack message event containing a ``user`` field and
``text`` field, the message handler SHALL extract the Slack user ID from
the event, process the text through the agent, and produce a response
posted back to the originating channel/thread.

Uses hypothesis to generate random Slack event dicts with realistic
user IDs (U + alphanumeric), channel IDs (C + alphanumeric), message
text, and timestamps.  ``run_agent_for_message`` is mocked so the test
focuses purely on the handle_message dispatch logic.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Strategies: realistic Slack event fields
# ---------------------------------------------------------------------------

ALPHANUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

slack_user_ids = st.text(
    alphabet=ALPHANUM, min_size=1, max_size=12
).map(lambda s: f"U{s}")

slack_channel_ids = st.text(
    alphabet=ALPHANUM, min_size=1, max_size=12
).map(lambda s: f"C{s}")

# Non-empty, non-whitespace-only message text
slack_text = st.text(min_size=1, max_size=200).filter(lambda t: t.strip())

# Slack timestamps: "NNNNNNNNNN.NNNNNN"
slack_timestamps = st.tuples(
    st.integers(min_value=1000000000, max_value=9999999999),
    st.integers(min_value=100000, max_value=999999),
).map(lambda t: f"{t[0]}.{t[1]}")


# ---------------------------------------------------------------------------
# Module isolation helpers (same pattern as test_slack_bot.py)
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
# Property test
# ---------------------------------------------------------------------------

class TestSlackMessageHandlingProperty:
    """Property 4: Slack message handling with user identification.

    **Validates: Requirements 5.2, 8.4**
    """

    @given(
        user_id=slack_user_ids,
        text=slack_text,
        channel=slack_channel_ids,
        ts=slack_timestamps,
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_handle_message_dispatches_to_agent_and_responds(
        self, user_id: str, text: str, channel: str, ts: str,
    ):
        """For any valid Slack event with user/text/channel, handle_message
        calls run_agent_for_message with the correct fields and posts the
        response back to the originating thread."""
        sb = _import_slack_bot()

        event = {
            "user": user_id,
            "text": text,
            "channel": channel,
            "ts": ts,
        }
        expected_response = f"reply-to-{user_id}"
        say = AsyncMock()

        with patch.object(
            sb,
            "run_agent_for_message",
            new_callable=AsyncMock,
            return_value=expected_response,
        ):
            await sb.handle_message(event, say)

            # Agent was called with the exact user, text, channel, and ts
            sb.run_agent_for_message.assert_awaited_once_with(
                user_id, text, channel, ts,
            )
            # Response posted to the same thread
            say.assert_awaited_once_with(
                text=expected_response, thread_ts=ts,
            )

    @given(
        user_id=slack_user_ids,
        text=slack_text,
        channel=slack_channel_ids,
        ts=slack_timestamps,
        thread_ts=slack_timestamps,
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_handle_message_uses_thread_ts_over_ts(
        self, user_id: str, text: str, channel: str, ts: str, thread_ts: str,
    ):
        """When thread_ts is present, handle_message uses it instead of ts
        for both the agent call and the say response."""
        sb = _import_slack_bot()

        event = {
            "user": user_id,
            "text": text,
            "channel": channel,
            "ts": ts,
            "thread_ts": thread_ts,
        }
        expected_response = f"threaded-reply-{user_id}"
        say = AsyncMock()

        with patch.object(
            sb,
            "run_agent_for_message",
            new_callable=AsyncMock,
            return_value=expected_response,
        ):
            await sb.handle_message(event, say)

            # Agent receives thread_ts, not ts
            sb.run_agent_for_message.assert_awaited_once_with(
                user_id, text, channel, thread_ts,
            )
            # Response posted to the thread_ts thread
            say.assert_awaited_once_with(
                text=expected_response, thread_ts=thread_ts,
            )
