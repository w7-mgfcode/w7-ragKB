"""Unit tests for the Discord adapter.

Feature: openclaw-integration (Task 9.2)
Tests: REST API calls, embed formatting, slash command detection,
reaction handling, message filtering, thread ID extraction, error handling.
"""

import asyncio
import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adapters.discord import (
    DISCORD_API_BASE,
    INITIAL_BACKOFF,
    MAX_RETRIES,
    DiscordAdapter,
    DiscordRateLimiter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_adapter(**kwargs):
    """Create a DiscordAdapter without calling __init__ fully."""
    adapter = DiscordAdapter.__new__(DiscordAdapter)
    adapter.channel_id = kwargs.get("channel_id", "dc-test")
    adapter.bot_token = kwargs.get("bot_token", "FAKE_TOKEN")
    adapter.bot_user_id = kwargs.get("bot_user_id", "999888777666555444")
    adapter.bot_username = kwargs.get("bot_username", "testbot")
    adapter.api_base = DISCORD_API_BASE
    adapter.session = MagicMock()
    adapter.control_ws = AsyncMock()
    adapter.control_ws_connected = True
    adapter.discord_ws = AsyncMock()
    adapter.discord_ws_connected = True
    adapter.rate_limiter = DiscordRateLimiter()
    adapter._running = True
    adapter.intents = 513
    adapter.sequence = None
    return adapter


def make_discord_message(
    msg_id="1",
    author_id="12345",
    author_username="testuser",
    channel_id="ch1",
    guild_id="g1",
    content="hello",
    **kwargs,
):
    """Create a Discord message dict."""
    msg = {
        "id": msg_id,
        "author": {
            "id": author_id,
            "username": author_username,
            "bot": False,
        },
        "channel_id": channel_id,
        "guild_id": guild_id,
        "content": content,
        "mentions": [],
        "attachments": [],
    }
    msg.update(kwargs)
    return msg


# ===========================================================================
# _parse_discord_message - core fields
# ===========================================================================


class TestParseDiscordMessage:
    """Unit tests for _parse_discord_message."""

    @pytest.mark.asyncio
    async def test_extracts_core_fields(self):
        """Extract message_id, user_id, chat_id, text."""
        adapter = make_adapter()
        msg = make_discord_message(msg_id="42", author_id="100", channel_id="ch200", content="hi")
        result = await adapter._parse_discord_message(msg)

        assert result.message_id == "42"
        assert result.user_id == "100"
        assert result.chat_id == "ch200"
        assert result.text == "hi"
        assert result.channel_id == "dc-test"

    @pytest.mark.asyncio
    async def test_thread_id_extracted(self):
        """Thread ID should be extracted from thread.id."""
        adapter = make_adapter()
        msg = make_discord_message(
            thread={"id": "thread123", "name": "test-thread"},
        )
        result = await adapter._parse_discord_message(msg)
        assert result.thread_id == "thread123"

    @pytest.mark.asyncio
    async def test_no_thread_id_when_absent(self):
        """thread_id should be None when no thread."""
        adapter = make_adapter()
        msg = make_discord_message()
        result = await adapter._parse_discord_message(msg)
        assert result.thread_id is None


# ===========================================================================
# Channel type detection
# ===========================================================================


class TestChannelTypeDetection:
    """Unit tests for _get_channel_type."""

    def test_dm_no_guild_id(self):
        """No guild_id = DM."""
        adapter = make_adapter()
        msg = {"id": "1", "channel_id": "ch1", "content": "hi"}
        assert adapter._get_channel_type(msg) == "dm"

    def test_guild_text_with_guild_id(self):
        """guild_id present, no thread = guild_text."""
        adapter = make_adapter()
        msg = {"id": "1", "channel_id": "ch1", "guild_id": "g1", "content": "hi"}
        assert adapter._get_channel_type(msg) == "guild_text"

    def test_guild_thread_with_thread(self):
        """guild_id + thread = guild_thread."""
        adapter = make_adapter()
        msg = {
            "id": "1",
            "channel_id": "ch1",
            "guild_id": "g1",
            "thread": {"id": "t1"},
            "content": "hi",
        }
        assert adapter._get_channel_type(msg) == "guild_thread"


# ===========================================================================
# Mention detection
# ===========================================================================


class TestDiscordMentionDetection:
    """Unit tests for bot mention detection."""

    @pytest.mark.asyncio
    async def test_bot_in_mentions_array(self):
        """Bot user_id in mentions array → bot_mention=True."""
        adapter = make_adapter()
        msg = make_discord_message(
            mentions=[{"id": adapter.bot_user_id, "username": "testbot"}],
        )
        result = await adapter._parse_discord_message(msg)
        assert result.metadata["bot_mention"] is True

    @pytest.mark.asyncio
    async def test_other_user_in_mentions(self):
        """Other user in mentions → bot_mention=False."""
        adapter = make_adapter()
        msg = make_discord_message(
            mentions=[{"id": "other_id", "username": "otheruser"}],
        )
        result = await adapter._parse_discord_message(msg)
        assert result.metadata["bot_mention"] is False

    @pytest.mark.asyncio
    async def test_empty_mentions(self):
        """Empty mentions array → bot_mention=False."""
        adapter = make_adapter()
        msg = make_discord_message(mentions=[])
        result = await adapter._parse_discord_message(msg)
        assert result.metadata["bot_mention"] is False


# ===========================================================================
# Slash command detection
# ===========================================================================


class TestSlashCommandDetection:
    """Unit tests for slash command detection."""

    @pytest.mark.asyncio
    async def test_slash_command_detected(self):
        """Content starting with / should set is_slash_command=True."""
        adapter = make_adapter()
        msg = make_discord_message(content="/status")
        result = await adapter._parse_discord_message(msg)
        assert result.metadata["is_slash_command"] is True

    @pytest.mark.asyncio
    async def test_non_slash_content(self):
        """Normal content should set is_slash_command=False."""
        adapter = make_adapter()
        msg = make_discord_message(content="hello world")
        result = await adapter._parse_discord_message(msg)
        assert result.metadata["is_slash_command"] is False


# ===========================================================================
# Attachment extraction
# ===========================================================================


class TestDiscordAttachments:
    """Unit tests for attachment extraction."""

    @pytest.mark.asyncio
    async def test_single_attachment(self):
        """Single attachment should be extracted with all fields."""
        adapter = make_adapter()
        msg = make_discord_message(
            attachments=[
                {
                    "id": "att1",
                    "filename": "doc.pdf",
                    "content_type": "application/pdf",
                    "size": 12345,
                    "url": "https://cdn.discordapp.com/attachments/doc.pdf",
                    "proxy_url": "https://media.discordapp.net/attachments/doc.pdf",
                },
            ],
        )
        result = await adapter._parse_discord_message(msg)
        assert len(result.attachments) == 1
        assert result.attachments[0]["filename"] == "doc.pdf"
        assert result.attachments[0]["size"] == 12345

    @pytest.mark.asyncio
    async def test_multiple_attachments(self):
        """Multiple attachments should all be extracted."""
        adapter = make_adapter()
        msg = make_discord_message(
            attachments=[
                {"id": "a1", "filename": "f1.txt", "size": 100},
                {"id": "a2", "filename": "f2.jpg", "size": 2000},
                {"id": "a3", "filename": "f3.mp4", "size": 50000},
            ],
        )
        result = await adapter._parse_discord_message(msg)
        assert len(result.attachments) == 3
        filenames = {a["filename"] for a in result.attachments}
        assert filenames == {"f1.txt", "f2.jpg", "f3.mp4"}

    @pytest.mark.asyncio
    async def test_no_attachments(self):
        """No attachments → empty list."""
        adapter = make_adapter()
        msg = make_discord_message(attachments=[])
        result = await adapter._parse_discord_message(msg)
        assert result.attachments == []


# ===========================================================================
# Metadata extraction
# ===========================================================================


class TestDiscordMetadata:
    """Unit tests for metadata extraction."""

    @pytest.mark.asyncio
    async def test_metadata_includes_guild_id(self):
        """Metadata should include guild_id."""
        adapter = make_adapter()
        msg = make_discord_message(guild_id="guild123")
        result = await adapter._parse_discord_message(msg)
        assert result.metadata["guild_id"] == "guild123"

    @pytest.mark.asyncio
    async def test_metadata_includes_channel_type(self):
        """Metadata should include channel_type."""
        adapter = make_adapter()
        msg = make_discord_message(guild_id="g1")
        result = await adapter._parse_discord_message(msg)
        assert result.metadata["channel_type"] == "guild_text"

    @pytest.mark.asyncio
    async def test_metadata_includes_author_info(self):
        """Metadata should include author_username."""
        adapter = make_adapter()
        msg = make_discord_message(author_username="alice")
        result = await adapter._parse_discord_message(msg)
        assert result.metadata["author_username"] == "alice"

    @pytest.mark.asyncio
    async def test_metadata_includes_referenced_message(self):
        """Metadata should include referenced_message id when present."""
        adapter = make_adapter()
        msg = make_discord_message(
            referenced_message={"id": "ref123", "content": "original"},
        )
        result = await adapter._parse_discord_message(msg)
        assert result.metadata["referenced_message"] == "ref123"


# ===========================================================================
# Outbound message handling
# ===========================================================================


class TestDiscordOutboundMessage:
    """Unit tests for _handle_outbound_message."""

    @pytest.mark.asyncio
    async def test_basic_send(self):
        """Basic message should POST to /channels/{id}/messages."""
        adapter = make_adapter()
        captured = []

        async def mock_api_call(method, endpoint, json_data=None, files=None):
            captured.append((method, endpoint, json_data))
            return {"id": "sent1"}

        adapter._api_call = mock_api_call

        from gateway_protocol import MessageSerializer

        outbound = MessageSerializer.create_outbound_message(
            message_id="out1",
            channel_id="dc-test",
            chat_id="ch200",
            text="hello back",
        )
        await adapter._handle_outbound_message(outbound)

        assert len(captured) == 1
        assert captured[0][0] == "POST"
        assert "/channels/ch200/messages" in captured[0][1]
        assert captured[0][2]["content"] == "hello back"

    @pytest.mark.asyncio
    async def test_reply_to_message_reference(self):
        """reply_to should be included as message_reference."""
        adapter = make_adapter()
        captured = []

        async def mock_api_call(method, endpoint, json_data=None, files=None):
            captured.append(json_data)
            return {"id": "sent1"}

        adapter._api_call = mock_api_call

        from gateway_protocol import MessageSerializer

        outbound = MessageSerializer.create_outbound_message(
            message_id="out1",
            channel_id="dc-test",
            chat_id="ch200",
            text="reply",
            reply_to="orig42",
        )
        await adapter._handle_outbound_message(outbound)

        assert captured[0]["message_reference"] == {"message_id": "orig42"}

    @pytest.mark.asyncio
    async def test_embed_from_metadata(self):
        """Embed from metadata should be included in embeds array."""
        adapter = make_adapter()
        captured = []

        async def mock_api_call(method, endpoint, json_data=None, files=None):
            captured.append(json_data)
            return {"id": "sent1"}

        adapter._api_call = mock_api_call

        from gateway_protocol import MessageSerializer

        embed = {"title": "Test", "description": "A test embed", "color": 0xFF0000}
        outbound = MessageSerializer.create_outbound_message(
            message_id="out1",
            channel_id="dc-test",
            chat_id="ch200",
            text="check this out",
            metadata={"embed": embed},
        )
        await adapter._handle_outbound_message(outbound)

        assert captured[0]["embeds"] == [embed]

    @pytest.mark.asyncio
    async def test_reactions_added(self):
        """Reactions from metadata should trigger _add_reaction calls."""
        adapter = make_adapter()
        api_calls = []

        async def mock_api_call(method, endpoint, json_data=None, files=None):
            api_calls.append((method, endpoint))
            return {"id": "sent1"}

        adapter._api_call = mock_api_call

        from gateway_protocol import MessageSerializer

        outbound = MessageSerializer.create_outbound_message(
            message_id="out1",
            channel_id="dc-test",
            chat_id="ch200",
            text="nice",
            metadata={"reactions": ["👍", "❤️"]},
        )
        await adapter._handle_outbound_message(outbound)

        # 1 POST for message + 2 PUTs for reactions
        assert len(api_calls) == 3
        assert api_calls[1][0] == "PUT"
        assert "reactions" in api_calls[1][1]


# ===========================================================================
# _handle_message_create
# ===========================================================================


class TestHandleMessageCreate:
    """Unit tests for _handle_message_create."""

    @pytest.mark.asyncio
    async def test_ignores_bot_messages(self):
        """Bot messages should be ignored."""
        adapter = make_adapter()
        adapter._parse_discord_message = AsyncMock()
        msg = make_discord_message()
        msg["author"]["bot"] = True

        await adapter._handle_message_create(msg)
        adapter._parse_discord_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_empty_content(self):
        """Messages with empty content should be ignored."""
        adapter = make_adapter()
        adapter._parse_discord_message = AsyncMock()
        msg = make_discord_message(content="")

        await adapter._handle_message_create(msg)
        adapter._parse_discord_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_whitespace_content(self):
        """Messages with whitespace-only content should be ignored."""
        adapter = make_adapter()
        adapter._parse_discord_message = AsyncMock()
        msg = make_discord_message(content="   \t\n  ")

        await adapter._handle_message_create(msg)
        adapter._parse_discord_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_processes_valid_message(self):
        """Valid user messages should be parsed and sent to CP."""
        adapter = make_adapter()
        msg = make_discord_message(content="hello world")

        await adapter._handle_message_create(msg)
        adapter.control_ws.send.assert_called_once()


# ===========================================================================
# Rate limiter
# ===========================================================================


class TestDiscordRateLimiterUnit:
    """Unit tests for DiscordRateLimiter."""

    def test_initial_state(self):
        """Rate limiter should start with no retry_after."""
        limiter = DiscordRateLimiter()
        assert limiter.retry_after is None
        assert limiter.request_count == 0

    def test_set_retry_after_float(self):
        """set_retry_after should accept float values."""
        import time
        limiter = DiscordRateLimiter()
        before = time.time()
        limiter.set_retry_after(5.5)
        assert limiter.retry_after >= before + 5.5

    @pytest.mark.asyncio
    async def test_wait_if_needed_no_retry(self):
        """wait_if_needed with no retry_after should return immediately."""
        limiter = DiscordRateLimiter()
        # Should not hang or raise
        await limiter.wait_if_needed()
        assert limiter.retry_after is None
