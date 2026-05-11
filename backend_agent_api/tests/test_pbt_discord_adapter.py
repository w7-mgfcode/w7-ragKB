"""Property-based tests for the Discord adapter.

Feature: openclaw-integration
Properties tested: 7, 8, 9, 10, 11 (Discord variant)

Tests event parsing, channel type detection, mention detection,
attachment handling, and rate limit backoff for Discord.
"""

import string
import time

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adapters.discord import (
    INITIAL_BACKOFF,
    MAX_RETRIES,
    DiscordAdapter,
    DiscordRateLimiter,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

safe_text = st.text(min_size=1, max_size=500).filter(lambda s: s.strip())
discord_id = st.text(
    alphabet=string.digits,
    min_size=17,
    max_size=20,
)
username = st.text(
    alphabet=string.ascii_letters + string.digits + "_",
    min_size=1,
    max_size=30,
)


def make_adapter():
    """Create a DiscordAdapter without calling __init__ fully."""
    adapter = DiscordAdapter.__new__(DiscordAdapter)
    adapter.channel_id = "dc-test"
    adapter.bot_user_id = "999888777666555444"
    adapter.bot_username = "testbot"
    return adapter


# ===========================================================================
# Property 7 (Discord): Platform event parsing
# ===========================================================================


class TestDiscordEventParsing:
    """Property 7: Discord adapter extracts all required fields."""

    @given(
        msg_id=discord_id,
        author_id=discord_id,
        channel_id=discord_id,
        content=safe_text,
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_parse_extracts_core_fields(
        self, msg_id, author_id, channel_id, content
    ):
        """
        Feature: openclaw-integration, Property 7: Platform event parsing (Discord)

        _parse_discord_message should extract message_id, user_id, chat_id, text.
        """
        adapter = make_adapter()

        message = {
            "id": msg_id,
            "author": {"id": author_id, "username": "testuser"},
            "channel_id": channel_id,
            "content": content,
            "guild_id": "123456789",
            "mentions": [],
            "attachments": [],
        }

        result = await adapter._parse_discord_message(message)

        assert result.message_id == msg_id
        assert result.user_id == author_id
        assert result.chat_id == channel_id
        assert result.text == content
        assert result.channel_id == "dc-test"


# ===========================================================================
# Property 7 (Discord): Channel type detection
# ===========================================================================


class TestChannelTypeDetection:
    """Property 7: _get_channel_type correctly categorizes messages."""

    @given(content=safe_text, channel_id=discord_id)
    @settings(max_examples=50, deadline=None)
    def test_dm_when_no_guild_id(self, content, channel_id):
        """
        Feature: openclaw-integration, Property 7: Platform event parsing (Discord)

        Messages without guild_id should be classified as 'dm'.
        """
        adapter = make_adapter()
        message = {
            "id": "1",
            "channel_id": channel_id,
            "content": content,
        }
        assert adapter._get_channel_type(message) == "dm"

    @given(content=safe_text, guild_id=discord_id)
    @settings(max_examples=50, deadline=None)
    def test_guild_text_with_guild_id(self, content, guild_id):
        """
        Feature: openclaw-integration, Property 7: Platform event parsing (Discord)

        Messages with guild_id and no thread should be 'guild_text'.
        """
        adapter = make_adapter()
        message = {
            "id": "1",
            "channel_id": "123",
            "content": content,
            "guild_id": guild_id,
        }
        assert adapter._get_channel_type(message) == "guild_text"

    @given(guild_id=discord_id, thread_id=discord_id)
    @settings(max_examples=50, deadline=None)
    def test_guild_thread_with_thread(self, guild_id, thread_id):
        """
        Feature: openclaw-integration, Property 7: Platform event parsing (Discord)

        Messages with guild_id and thread should be 'guild_thread'.
        """
        adapter = make_adapter()
        message = {
            "id": "1",
            "channel_id": "123",
            "content": "test",
            "guild_id": guild_id,
            "thread": {"id": thread_id},
        }
        assert adapter._get_channel_type(message) == "guild_thread"


# ===========================================================================
# Property 10 (Discord): Mention detection
# ===========================================================================


class TestDiscordMentionDetection:
    """Property 10: Bot mention detection in Discord messages."""

    @given(content=safe_text)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_mention_detected_when_bot_in_mentions(self, content):
        """
        Feature: openclaw-integration, Property 10: Mention detection (Discord)

        When bot_user_id appears in mentions array, bot_mention should be True.
        """
        adapter = make_adapter()

        message = {
            "id": "1",
            "author": {"id": "12345", "username": "user"},
            "channel_id": "ch1",
            "content": content,
            "guild_id": "g1",
            "mentions": [{"id": adapter.bot_user_id, "username": "testbot"}],
            "attachments": [],
        }

        result = await adapter._parse_discord_message(message)
        assert result.metadata.get("bot_mention") is True

    @given(content=safe_text)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_no_mention_when_bot_not_in_mentions(self, content):
        """
        Feature: openclaw-integration, Property 10: Mention detection (Discord)

        When bot_user_id is not in mentions, bot_mention should be False.
        """
        adapter = make_adapter()

        message = {
            "id": "1",
            "author": {"id": "12345", "username": "user"},
            "channel_id": "ch1",
            "content": content,
            "guild_id": "g1",
            "mentions": [{"id": "other_user_id", "username": "otheruser"}],
            "attachments": [],
        }

        result = await adapter._parse_discord_message(message)
        assert result.metadata.get("bot_mention") is False


# ===========================================================================
# Property 9 (Discord): Attachment handling
# ===========================================================================


class TestDiscordAttachmentHandling:
    """Property 9: Discord attachments are correctly extracted."""

    @given(
        filename=st.text(
            alphabet=string.ascii_letters + string.digits + "-_.",
            min_size=1,
            max_size=50,
        ),
        size=st.integers(min_value=1, max_value=10_000_000),
    )
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_attachments_extracted(self, filename, size):
        """
        Feature: openclaw-integration, Property 9: Attachment handling (Discord)

        Attachments from Discord message should be extracted with metadata.
        """
        adapter = make_adapter()

        message = {
            "id": "1",
            "author": {"id": "12345", "username": "user"},
            "channel_id": "ch1",
            "content": "file",
            "guild_id": "g1",
            "mentions": [],
            "attachments": [
                {
                    "id": "att1",
                    "filename": filename,
                    "content_type": "application/octet-stream",
                    "size": size,
                    "url": "https://cdn.discordapp.com/test",
                    "proxy_url": "https://media.discordapp.net/test",
                },
            ],
        }

        result = await adapter._parse_discord_message(message)
        assert len(result.attachments) == 1
        assert result.attachments[0]["filename"] == filename
        assert result.attachments[0]["size"] == size


# ===========================================================================
# Property 11 (Discord): Rate limit backoff
# ===========================================================================


class TestDiscordRateLimitBackoff:
    """Property 11: Exponential backoff for Discord rate limits."""

    def test_initial_backoff_value(self):
        """
        Feature: openclaw-integration, Property 11: Rate limit backoff (Discord)

        Initial backoff should be INITIAL_BACKOFF (1.0s).
        """
        assert INITIAL_BACKOFF == 1.0

    def test_backoff_doubles_each_attempt(self):
        """
        Feature: openclaw-integration, Property 11: Rate limit backoff (Discord)

        Backoff should double: 1, 2, 4, 8, 16.
        """
        backoff = INITIAL_BACKOFF
        expected = [1.0, 2.0, 4.0, 8.0, 16.0]
        actual = []
        for _ in range(MAX_RETRIES):
            actual.append(backoff)
            backoff *= 2
        assert actual == expected

    @given(retry_seconds=st.floats(min_value=0.1, max_value=300.0, allow_nan=False))
    @settings(max_examples=50, deadline=None)
    def test_set_retry_after_future_timestamp(self, retry_seconds):
        """
        Feature: openclaw-integration, Property 11: Rate limit backoff (Discord)

        set_retry_after should set retry_after to a future timestamp.
        """
        limiter = DiscordRateLimiter()
        now = time.time()
        limiter.set_retry_after(retry_seconds)
        assert limiter.retry_after > now

    def test_max_retries_value(self):
        """
        Feature: openclaw-integration, Property 11: Rate limit backoff (Discord)

        MAX_RETRIES should be 5.
        """
        assert MAX_RETRIES == 5
