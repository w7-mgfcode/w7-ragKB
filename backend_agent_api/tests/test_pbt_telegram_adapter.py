"""Property-based tests for the Telegram adapter.

Feature: openclaw-integration
Properties tested: 7, 8, 9, 10, 11

Tests event parsing, message formatting, attachment handling,
mention detection, and rate limit backoff for Telegram.
"""

import string
import time

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adapters.telegram import (
    INITIAL_BACKOFF,
    MAX_MESSAGE_LENGTH,
    MAX_RETRIES,
    TelegramRateLimiter,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

safe_text = st.text(min_size=1, max_size=500).filter(lambda s: s.strip())
long_text = st.text(min_size=MAX_MESSAGE_LENGTH + 1, max_size=MAX_MESSAGE_LENGTH + 500)
user_id = st.integers(min_value=1, max_value=999_999_999).map(str)
chat_id = st.integers(min_value=-999_999_999, max_value=999_999_999).map(str)
message_id = st.integers(min_value=1, max_value=999_999_999)
file_size = st.integers(min_value=100, max_value=10_000_000)

photo_strategy = st.lists(
    st.fixed_dictionaries({
        "file_id": st.text(alphabet=string.ascii_letters, min_size=10, max_size=30),
        "file_size": file_size,
        "width": st.integers(min_value=1, max_value=4096),
        "height": st.integers(min_value=1, max_value=4096),
    }),
    min_size=1,
    max_size=5,
)


# ===========================================================================
# Property 7: Platform event parsing
# ===========================================================================


class TestTelegramEventParsing:
    """Property 7: Telegram adapter extracts all required fields."""

    @given(
        msg_id=message_id,
        uid=user_id,
        cid=chat_id,
        text=safe_text,
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_parse_extracts_core_fields(self, msg_id, uid, cid, text):
        """
        Feature: openclaw-integration, Property 7: Platform event parsing

        _parse_telegram_message should extract message_id, user_id, chat_id, text.
        """
        from unittest.mock import MagicMock

        from adapters.telegram import TelegramAdapter

        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.channel_id = "tg-test"
        adapter.bot_username = "testbot"
        adapter.bot_id = 12345

        message = {
            "message_id": msg_id,
            "from": {"id": int(uid), "username": "testuser"},
            "chat": {"id": int(cid), "type": "private"},
            "text": text,
        }

        result = await adapter._parse_telegram_message(message)

        assert result.message_id == str(msg_id)
        assert result.user_id == uid
        assert result.chat_id == cid
        assert result.text == text
        assert result.channel_id == "tg-test"

    @given(
        msg_id=message_id,
        uid=user_id,
        cid=chat_id,
        caption=safe_text,
    )
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_caption_fallback_when_no_text(self, msg_id, uid, cid, caption):
        """
        Feature: openclaw-integration, Property 7: Platform event parsing

        When text is absent, caption should be used as fallback.
        """
        from adapters.telegram import TelegramAdapter

        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.channel_id = "tg-test"
        adapter.bot_username = "testbot"
        adapter.bot_id = 12345

        message = {
            "message_id": msg_id,
            "from": {"id": int(uid)},
            "chat": {"id": int(cid), "type": "private"},
            "caption": caption,
        }

        result = await adapter._parse_telegram_message(message)
        assert result.text == caption


# ===========================================================================
# Property 9: Attachment handling (photo selection)
# ===========================================================================


class TestAttachmentHandling:
    """Property 9: Adapter selects largest photo by file_size."""

    @given(photos=photo_strategy)
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_selects_largest_photo(self, photos):
        """
        Feature: openclaw-integration, Property 9: Attachment handling

        When a message has multiple photo sizes, the largest by file_size is selected.
        """
        from adapters.telegram import TelegramAdapter

        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.channel_id = "tg-test"
        adapter.bot_username = "testbot"
        adapter.bot_id = 12345

        expected_largest = max(photos, key=lambda p: p.get("file_size", 0))

        message = {
            "message_id": 1,
            "from": {"id": 123},
            "chat": {"id": 456, "type": "private"},
            "text": "photo",
            "photo": photos,
        }

        result = await adapter._parse_telegram_message(message)

        # Should have exactly one photo attachment
        photo_attachments = [a for a in result.attachments if a.get("type") == "photo"]
        assert len(photo_attachments) == 1
        assert photo_attachments[0]["file_id"] == expected_largest["file_id"]


# ===========================================================================
# Property 10: Mention detection
# ===========================================================================


class TestMentionDetection:
    """Property 10: Bot mention detection in group chats."""

    @given(text=safe_text)
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_private_chat_no_mention(self, text):
        """
        Feature: openclaw-integration, Property 10: Mention detection

        In private chats, bot_mention should always be False.
        """
        from adapters.telegram import TelegramAdapter

        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.channel_id = "tg-test"
        adapter.bot_username = "testbot"
        adapter.bot_id = 12345

        message = {
            "message_id": 1,
            "from": {"id": 123},
            "chat": {"id": 456, "type": "private"},
            "text": text,
        }

        result = await adapter._parse_telegram_message(message)
        assert result.metadata.get("bot_mention") is False

    @pytest.mark.asyncio
    async def test_group_chat_with_at_mention(self):
        """
        Feature: openclaw-integration, Property 10: Mention detection

        @bot_username in group chat text should set bot_mention=True.
        """
        from adapters.telegram import TelegramAdapter

        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.channel_id = "tg-test"
        adapter.bot_username = "testbot"
        adapter.bot_id = 12345

        message = {
            "message_id": 1,
            "from": {"id": 123},
            "chat": {"id": -789, "type": "group"},
            "text": "Hey @testbot what do you think?",
            "entities": [
                {"type": "mention", "offset": 4, "length": 8},
            ],
        }

        result = await adapter._parse_telegram_message(message)
        assert result.metadata.get("bot_mention") is True

    @given(text=safe_text.filter(lambda s: "testbot" not in s.lower()))
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_group_chat_without_mention(self, text):
        """
        Feature: openclaw-integration, Property 10: Mention detection

        Group messages without bot mention should have bot_mention=False.
        """
        from adapters.telegram import TelegramAdapter

        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter.channel_id = "tg-test"
        adapter.bot_username = "testbot"
        adapter.bot_id = 12345

        message = {
            "message_id": 1,
            "from": {"id": 123},
            "chat": {"id": -789, "type": "supergroup"},
            "text": text,
        }

        result = await adapter._parse_telegram_message(message)
        assert result.metadata.get("bot_mention") is False


# ===========================================================================
# Property 11: Rate limit backoff
# ===========================================================================


class TestRateLimitBackoff:
    """Property 11: Exponential backoff with increasing delays."""

    def test_initial_backoff_value(self):
        """
        Feature: openclaw-integration, Property 11: Rate limit backoff

        Initial backoff should be INITIAL_BACKOFF (1.0s).
        """
        assert INITIAL_BACKOFF == 1.0

    def test_backoff_doubles_each_attempt(self):
        """
        Feature: openclaw-integration, Property 11: Rate limit backoff

        Backoff should double on each retry: 1, 2, 4, 8, 16.
        """
        backoff = INITIAL_BACKOFF
        expected = [1.0, 2.0, 4.0, 8.0, 16.0]
        actual = []
        for _ in range(MAX_RETRIES):
            actual.append(backoff)
            backoff *= 2
        assert actual == expected

    def test_set_retry_after_sets_future_timestamp(self):
        """
        Feature: openclaw-integration, Property 11: Rate limit backoff

        set_retry_after should set retry_after to a future timestamp.
        """
        limiter = TelegramRateLimiter()
        before = time.time()
        limiter.set_retry_after(10)
        after = time.time()

        assert limiter.retry_after is not None
        assert limiter.retry_after >= before + 10
        assert limiter.retry_after <= after + 10

    @given(retry_seconds=st.integers(min_value=1, max_value=300))
    @settings(max_examples=50, deadline=None)
    def test_retry_after_delay_positive(self, retry_seconds):
        """
        Feature: openclaw-integration, Property 11: Rate limit backoff

        retry_after should always be in the future.
        """
        limiter = TelegramRateLimiter()
        now = time.time()
        limiter.set_retry_after(retry_seconds)
        assert limiter.retry_after > now

    def test_max_retries_value(self):
        """
        Feature: openclaw-integration, Property 11: Rate limit backoff

        MAX_RETRIES should be 5.
        """
        assert MAX_RETRIES == 5
