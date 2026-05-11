"""Unit tests for Telegram channel adapter.

Tests cover:
- Telegram Bot API calls (sendMessage, getFile, etc.)
- Inline keyboard formatting
- Event parsing (text, attachments, mentions)
- Rate limit handling with exponential backoff
- WebSocket connection to Control Plane
- Message routing (inbound and outbound)
"""

import asyncio
import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp
import pytest
import websockets

from adapters.telegram import (
    INITIAL_BACKOFF,
    MAX_RETRIES,
    TelegramAdapter,
    TelegramRateLimiter,
)
from gateway_protocol import (
    ChannelStatusType,
    InboundMessage,
    OutboundMessage,
    parse_message,
)


@pytest.fixture
def bot_token():
    """Telegram bot token for testing."""
    return "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"


@pytest.fixture
def channel_id():
    """Channel ID for testing."""
    return "telegram-test"


@pytest.fixture
def control_plane_url():
    """Control Plane WebSocket URL for testing."""
    return "ws://127.0.0.1:18789"


@pytest.fixture
def telegram_adapter(bot_token, channel_id, control_plane_url):
    """Create a TelegramAdapter instance for testing."""
    return TelegramAdapter(
        channel_id=channel_id,
        bot_token=bot_token,
        control_plane_url=control_plane_url,
        polling_timeout=1,  # Short timeout for tests
    )


@pytest.fixture
def sample_telegram_message():
    """Sample Telegram message for testing."""
    return {
        "message_id": 123,
        "from": {
            "id": 456,
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User",
        },
        "chat": {
            "id": 789,
            "type": "private",
        },
        "text": "Hello, bot!",
    }


@pytest.fixture
def sample_group_message_with_mention():
    """Sample Telegram group message with bot mention."""
    return {
        "message_id": 124,
        "from": {
            "id": 456,
            "username": "testuser",
            "first_name": "Test",
        },
        "chat": {
            "id": 999,
            "type": "group",
            "title": "Test Group",
        },
        "text": "@testbot Hello!",
        "entities": [
            {
                "type": "mention",
                "offset": 0,
                "length": 8,
            }
        ],
    }


@pytest.fixture
def sample_message_with_photo():
    """Sample Telegram message with photo attachment."""
    return {
        "message_id": 125,
        "from": {"id": 456, "username": "testuser"},
        "chat": {"id": 789, "type": "private"},
        "caption": "Check this out!",
        "photo": [
            {
                "file_id": "photo_small",
                "file_size": 1000,
                "width": 100,
                "height": 100,
            },
            {
                "file_id": "photo_large",
                "file_size": 5000,
                "width": 800,
                "height": 600,
            },
        ],
    }


class TestTelegramRateLimiter:
    """Tests for TelegramRateLimiter."""
    
    @pytest.mark.asyncio
    async def test_no_wait_when_no_rate_limit(self):
        """Test that wait_if_needed returns immediately when no rate limit is active."""
        limiter = TelegramRateLimiter()
        
        # Should return immediately
        await limiter.wait_if_needed()
        
        assert limiter.retry_after is None
    
    @pytest.mark.asyncio
    async def test_wait_when_rate_limit_active(self):
        """Test that wait_if_needed waits when rate limit is active."""
        limiter = TelegramRateLimiter()
        
        # Set retry_after to 0.1 seconds in the future
        limiter.set_retry_after(1)
        
        # Should wait
        start = asyncio.get_event_loop().time()
        await limiter.wait_if_needed()
        elapsed = asyncio.get_event_loop().time() - start
        
        # Should have waited approximately 1 second
        assert elapsed >= 0.9
        assert limiter.retry_after is None  # Cleared after waiting
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_on_rate_limit(self):
        """Test exponential backoff on repeated rate limit errors."""
        limiter = TelegramRateLimiter()
        
        attempt_count = 0
        backoff_delays = []
        
        async def failing_coro():
            nonlocal attempt_count
            attempt_count += 1
            
            if attempt_count < 3:
                # Simulate rate limit error
                error = aiohttp.ClientResponseError(
                    request_info=Mock(),
                    history=(),
                    status=429,
                    message="Too Many Requests",
                    headers={"Retry-After": "1"},
                )
                raise error
            
            return "success"
        
        # Execute with backoff
        result = await limiter.execute_with_backoff(failing_coro(), max_retries=5)
        
        assert result == "success"
        assert attempt_count == 3  # Should succeed on 3rd attempt
    
    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """Test that max retries are respected."""
        limiter = TelegramRateLimiter()
        
        async def always_failing_coro():
            error = aiohttp.ClientResponseError(
                request_info=Mock(),
                history=(),
                status=429,
                message="Too Many Requests",
                headers={"Retry-After": "1"},
            )
            raise error
        
        # Should raise after max retries
        with pytest.raises(aiohttp.ClientResponseError):
            await limiter.execute_with_backoff(always_failing_coro(), max_retries=2)
    
    @pytest.mark.asyncio
    async def test_non_rate_limit_error_raises_immediately(self):
        """Test that non-rate-limit errors are raised immediately."""
        limiter = TelegramRateLimiter()
        
        async def failing_coro():
            raise ValueError("Some other error")
        
        # Should raise immediately without retries
        with pytest.raises(ValueError, match="Some other error"):
            await limiter.execute_with_backoff(failing_coro(), max_retries=5)


class TestTelegramAdapter:
    """Tests for TelegramAdapter."""
    
    @pytest.mark.asyncio
    async def test_initialization(self, telegram_adapter, bot_token, channel_id):
        """Test adapter initialization."""
        assert telegram_adapter.channel_id == channel_id
        assert telegram_adapter.bot_token == bot_token
        assert telegram_adapter.api_base.endswith(bot_token)
        assert telegram_adapter.ws is None
        assert not telegram_adapter.ws_connected
        assert not telegram_adapter._running
    
    @pytest.mark.asyncio
    async def test_fetch_bot_info(self, telegram_adapter):
        """Test fetching bot information from Telegram API."""
        mock_response = {
            "ok": True,
            "result": {
                "id": 123456789,
                "username": "testbot",
                "first_name": "Test Bot",
            },
        }
        
        with patch.object(telegram_adapter, "_api_call", return_value=mock_response["result"]):
            await telegram_adapter._fetch_bot_info()
        
        assert telegram_adapter.bot_username == "testbot"
        assert telegram_adapter.bot_id == 123456789
    
    @pytest.mark.asyncio
    async def test_parse_simple_message(self, telegram_adapter, sample_telegram_message):
        """Test parsing a simple text message."""
        inbound_msg = await telegram_adapter._parse_telegram_message(sample_telegram_message)
        
        assert isinstance(inbound_msg, InboundMessage)
        assert inbound_msg.message_id == "123"
        assert inbound_msg.user_id == "456"
        assert inbound_msg.chat_id == "789"
        assert inbound_msg.text == "Hello, bot!"
        assert inbound_msg.channel_id == telegram_adapter.channel_id
        assert len(inbound_msg.attachments) == 0
        assert inbound_msg.metadata["chat_type"] == "private"
        assert inbound_msg.metadata["user_username"] == "testuser"
    
    @pytest.mark.asyncio
    async def test_parse_group_message_with_mention(
        self, telegram_adapter, sample_group_message_with_mention
    ):
        """Test parsing a group message with bot mention."""
        telegram_adapter.bot_username = "testbot"
        
        inbound_msg = await telegram_adapter._parse_telegram_message(
            sample_group_message_with_mention
        )
        
        assert inbound_msg.chat_id == "999"
        assert inbound_msg.text == "@testbot Hello!"
        assert inbound_msg.metadata["bot_mention"] is True
        assert inbound_msg.metadata["chat_type"] == "group"
        assert inbound_msg.metadata["chat_title"] == "Test Group"
    
    @pytest.mark.asyncio
    async def test_parse_message_with_photo(
        self, telegram_adapter, sample_message_with_photo
    ):
        """Test parsing a message with photo attachment."""
        inbound_msg = await telegram_adapter._parse_telegram_message(
            sample_message_with_photo
        )
        
        assert inbound_msg.text == "Check this out!"
        assert len(inbound_msg.attachments) == 1
        
        photo = inbound_msg.attachments[0]
        assert photo["type"] == "photo"
        assert photo["file_id"] == "photo_large"  # Should select largest photo
        assert photo["file_size"] == 5000
        assert photo["width"] == 800
        assert photo["height"] == 600
    
    @pytest.mark.asyncio
    async def test_parse_message_with_document(self, telegram_adapter):
        """Test parsing a message with document attachment."""
        message = {
            "message_id": 126,
            "from": {"id": 456},
            "chat": {"id": 789, "type": "private"},
            "text": "Here's a file",
            "document": {
                "file_id": "doc123",
                "file_name": "report.pdf",
                "mime_type": "application/pdf",
                "file_size": 50000,
            },
        }
        
        inbound_msg = await telegram_adapter._parse_telegram_message(message)
        
        assert len(inbound_msg.attachments) == 1
        doc = inbound_msg.attachments[0]
        assert doc["type"] == "document"
        assert doc["file_id"] == "doc123"
        assert doc["file_name"] == "report.pdf"
        assert doc["mime_type"] == "application/pdf"
    
    @pytest.mark.asyncio
    async def test_api_call_success(self, telegram_adapter):
        """Test successful API call."""
        mock_response = {
            "ok": True,
            "result": {"message_id": 123, "text": "Hello"},
        }
        
        telegram_adapter.session = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value=mock_response)
        mock_resp.raise_for_status = Mock()
        mock_resp.request_info = Mock()
        mock_resp.history = ()
        mock_resp.headers = {}
        
        telegram_adapter.session.post = AsyncMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_resp))
        )
        
        result = await telegram_adapter._api_call("sendMessage", {"chat_id": 123})
        
        assert result == mock_response["result"]
    
    @pytest.mark.asyncio
    async def test_api_call_rate_limit(self, telegram_adapter):
        """Test API call with rate limit error."""
        telegram_adapter.session = AsyncMock()
        
        # First call: rate limit error
        mock_resp_error = AsyncMock()
        mock_resp_error.status = 429
        mock_resp_error.json = AsyncMock(
            return_value={"ok": False, "error_code": 429, "description": "Too Many Requests"}
        )
        mock_resp_error.raise_for_status = Mock(
            side_effect=aiohttp.ClientResponseError(
                request_info=Mock(),
                history=(),
                status=429,
                message="Too Many Requests",
                headers={"Retry-After": "1"},
            )
        )
        mock_resp_error.request_info = Mock()
        mock_resp_error.history = ()
        mock_resp_error.headers = {"Retry-After": "1"}
        
        # Second call: success
        mock_resp_success = AsyncMock()
        mock_resp_success.json = AsyncMock(
            return_value={"ok": True, "result": {"message_id": 123}}
        )
        mock_resp_success.raise_for_status = Mock()
        mock_resp_success.request_info = Mock()
        mock_resp_success.history = ()
        mock_resp_success.headers = {}
        
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AsyncMock(__aenter__=AsyncMock(return_value=mock_resp_error))
            else:
                return AsyncMock(__aenter__=AsyncMock(return_value=mock_resp_success))
        
        telegram_adapter.session.post = mock_post
        
        # Should succeed after retry
        result = await telegram_adapter._api_call("sendMessage", {"chat_id": 123})
        
        assert result == {"message_id": 123}
        assert call_count == 2  # Should have retried once
    
    @pytest.mark.asyncio
    async def test_download_file(self, telegram_adapter):
        """Test file download from Telegram."""
        file_content = b"fake file content"
        
        telegram_adapter.session = AsyncMock()
        
        # Mock getFile response
        telegram_adapter._api_call = AsyncMock(
            return_value={"file_path": "documents/file.pdf"}
        )
        
        # Mock file download
        mock_resp = AsyncMock()
        mock_resp.read = AsyncMock(return_value=file_content)
        mock_resp.raise_for_status = Mock()
        
        telegram_adapter.session.get = AsyncMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_resp))
        )
        
        result = await telegram_adapter.download_file("file123")
        
        assert result == file_content
        telegram_adapter._api_call.assert_called_once_with("getFile", {"file_id": "file123"})
    
    @pytest.mark.asyncio
    async def test_send_simple_message(self, telegram_adapter):
        """Test sending a simple text message."""
        outbound_msg = OutboundMessage(
            message_id="msg123",
            channel_id=telegram_adapter.channel_id,
            chat_id="789",
            text="Hello from bot!",
        )
        
        telegram_adapter._api_call = AsyncMock(
            return_value={"message_id": 456, "text": "Hello from bot!"}
        )
        
        await telegram_adapter._handle_outbound_message(outbound_msg)
        
        # Verify API call
        telegram_adapter._api_call.assert_called_once()
        call_args = telegram_adapter._api_call.call_args
        assert call_args[0][0] == "sendMessage"
        assert call_args[0][1]["chat_id"] == "789"
        assert call_args[0][1]["text"] == "Hello from bot!"
    
    @pytest.mark.asyncio
    async def test_send_message_with_inline_keyboard(self, telegram_adapter):
        """Test sending a message with inline keyboard."""
        inline_keyboard = [
            [
                {"text": "Option 1", "callback_data": "opt1"},
                {"text": "Option 2", "callback_data": "opt2"},
            ]
        ]
        
        outbound_msg = OutboundMessage(
            message_id="msg124",
            channel_id=telegram_adapter.channel_id,
            chat_id="789",
            text="Choose an option:",
            metadata={"inline_keyboard": inline_keyboard},
        )
        
        telegram_adapter._api_call = AsyncMock(return_value={"message_id": 457})
        
        await telegram_adapter._handle_outbound_message(outbound_msg)
        
        # Verify inline keyboard was included
        call_args = telegram_adapter._api_call.call_args
        assert "reply_markup" in call_args[0][1]
        assert call_args[0][1]["reply_markup"]["inline_keyboard"] == inline_keyboard
    
    @pytest.mark.asyncio
    async def test_send_message_with_reply(self, telegram_adapter):
        """Test sending a message as a reply."""
        outbound_msg = OutboundMessage(
            message_id="msg125",
            channel_id=telegram_adapter.channel_id,
            chat_id="789",
            text="This is a reply",
            reply_to="123",
        )
        
        telegram_adapter._api_call = AsyncMock(return_value={"message_id": 458})
        
        await telegram_adapter._handle_outbound_message(outbound_msg)
        
        # Verify reply_to was included
        call_args = telegram_adapter._api_call.call_args
        assert call_args[0][1]["reply_to_message_id"] == "123"
    
    @pytest.mark.asyncio
    async def test_send_message_truncates_long_text(self, telegram_adapter):
        """Test that long messages are truncated to MAX_MESSAGE_LENGTH."""
        long_text = "x" * 5000  # Exceeds MAX_MESSAGE_LENGTH (4096)
        
        outbound_msg = OutboundMessage(
            message_id="msg126",
            channel_id=telegram_adapter.channel_id,
            chat_id="789",
            text=long_text,
        )
        
        telegram_adapter._api_call = AsyncMock(return_value={"message_id": 459})
        
        await telegram_adapter._handle_outbound_message(outbound_msg)
        
        # Verify text was truncated
        call_args = telegram_adapter._api_call.call_args
        assert len(call_args[0][1]["text"]) == 4096
    
    @pytest.mark.asyncio
    async def test_mention_detection_in_text(self, telegram_adapter):
        """Test mention detection from text content."""
        telegram_adapter.bot_username = "mybot"
        
        message = {
            "message_id": 127,
            "from": {"id": 456},
            "chat": {"id": 999, "type": "group"},
            "text": "Hey @mybot, can you help?",
        }
        
        inbound_msg = await telegram_adapter._parse_telegram_message(message)
        
        assert inbound_msg.metadata["bot_mention"] is True
    
    @pytest.mark.asyncio
    async def test_no_mention_in_private_chat(self, telegram_adapter):
        """Test that bot_mention is False in private chats."""
        telegram_adapter.bot_username = "mybot"
        
        message = {
            "message_id": 128,
            "from": {"id": 456},
            "chat": {"id": 789, "type": "private"},
            "text": "@mybot hello",  # Mention in text but private chat
        }
        
        inbound_msg = await telegram_adapter._parse_telegram_message(message)
        
        # bot_mention should be False for private chats
        assert inbound_msg.metadata["bot_mention"] is False
    
    @pytest.mark.asyncio
    async def test_parse_message_with_multiple_attachments(self, telegram_adapter):
        """Test parsing a message with multiple attachment types."""
        message = {
            "message_id": 129,
            "from": {"id": 456},
            "chat": {"id": 789, "type": "private"},
            "caption": "Media bundle",
            "photo": [{"file_id": "photo1", "file_size": 1000, "width": 100, "height": 100}],
            "document": {
                "file_id": "doc1",
                "file_name": "file.pdf",
                "mime_type": "application/pdf",
                "file_size": 5000,
            },
        }
        
        inbound_msg = await telegram_adapter._parse_telegram_message(message)
        
        # Should have both photo and document
        assert len(inbound_msg.attachments) == 2
        assert inbound_msg.attachments[0]["type"] == "photo"
        assert inbound_msg.attachments[1]["type"] == "document"
    
    @pytest.mark.asyncio
    async def test_empty_text_uses_caption(self, telegram_adapter):
        """Test that caption is used when text is empty."""
        message = {
            "message_id": 130,
            "from": {"id": 456},
            "chat": {"id": 789, "type": "private"},
            "caption": "Photo caption",
            "photo": [{"file_id": "photo1", "file_size": 1000, "width": 100, "height": 100}],
        }
        
        inbound_msg = await telegram_adapter._parse_telegram_message(message)
        
        assert inbound_msg.text == "Photo caption"


class TestTelegramAdapterIntegration:
    """Integration tests for TelegramAdapter with mocked WebSocket and HTTP."""
    
    @pytest.mark.asyncio
    async def test_start_and_stop(self, telegram_adapter):
        """Test starting and stopping the adapter."""
        # Mock dependencies
        with patch("websockets.connect", new_callable=AsyncMock) as mock_ws_connect, \
             patch.object(telegram_adapter, "_fetch_bot_info", new_callable=AsyncMock), \
             patch("aiohttp.ClientSession", return_value=AsyncMock()):
            
            mock_ws = AsyncMock()
            mock_ws.send = AsyncMock()
            mock_ws.recv = AsyncMock(side_effect=asyncio.CancelledError)
            mock_ws.close = AsyncMock()
            mock_ws_connect.return_value = mock_ws
            
            # Start adapter
            await telegram_adapter.start()
            
            assert telegram_adapter._running
            assert telegram_adapter.ws_connected
            assert telegram_adapter._polling_task is not None
            
            # Give tasks time to start
            await asyncio.sleep(0.1)
            
            # Stop adapter
            await telegram_adapter.stop()
            
            assert not telegram_adapter._running
            assert telegram_adapter.ws is None
    
    @pytest.mark.asyncio
    async def test_polling_loop_processes_updates(self, telegram_adapter):
        """Test that polling loop processes updates correctly."""
        update = {
            "update_id": 1,
            "message": {
                "message_id": 123,
                "from": {"id": 456, "username": "testuser"},
                "chat": {"id": 789, "type": "private"},
                "text": "Test message",
            },
        }
        
        # Mock API call to return one update then empty
        call_count = 0
        
        async def mock_api_call(method, params=None, files=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [update]
            else:
                # Stop the loop by raising CancelledError
                raise asyncio.CancelledError
        
        telegram_adapter._api_call = mock_api_call
        telegram_adapter._running = True
        telegram_adapter.ws_connected = True
        telegram_adapter.ws = AsyncMock()
        telegram_adapter.ws.send = AsyncMock()
        
        # Run polling loop
        try:
            await telegram_adapter._polling_loop()
        except asyncio.CancelledError:
            pass
        
        # Verify update was processed
        assert telegram_adapter.last_update_id == 1
        telegram_adapter.ws.send.assert_called_once()
