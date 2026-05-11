"""Telegram channel adapter for multi-channel gateway.

This module implements the TelegramAdapter class which:
- Connects to the Control Plane via WebSocket
- Integrates with Telegram Bot API (webhook or long polling)
- Parses Telegram events into unified InboundMessage format
- Formats OutboundMessage into Telegram API calls
- Handles file downloads for attachments
- Detects mentions in group chats
- Implements rate limit handling with exponential backoff

The adapter runs as an asyncio task and maintains a persistent WebSocket
connection to the Control Plane for bidirectional message routing.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp
import websockets
from websockets.client import WebSocketClientProtocol

from gateway_protocol import (
    ChannelStatusType,
    InboundMessage,
    MessageParser,
    MessageSerializer,
    OutboundMessage,
    parse_message,
    serialize_message,
)

logger = logging.getLogger(__name__)

# Telegram API configuration
TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024

# Rate limiting configuration
RATE_LIMIT_RETRY_AFTER_DEFAULT = 30  # Default retry delay in seconds
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0  # Initial backoff delay in seconds


class TelegramRateLimiter:
    """Rate limiter with exponential backoff for Telegram API.
    
    Handles 429 Too Many Requests responses from Telegram API by:
    - Respecting Retry-After header when provided
    - Applying exponential backoff (1s, 2s, 4s, 8s, 16s)
    - Queueing messages during rate limit periods
    """
    
    def __init__(self):
        """Initialize the rate limiter."""
        self.retry_after: Optional[float] = None
        self.last_request_time: float = 0
        self.request_count: int = 0
        self._lock = asyncio.Lock()
    
    async def wait_if_needed(self) -> None:
        """Wait if rate limit is active."""
        async with self._lock:
            if self.retry_after:
                now = time.time()
                wait_time = self.retry_after - now
                
                if wait_time > 0:
                    logger.warning(f"Rate limit active, waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
                
                # Clear retry_after after waiting
                self.retry_after = None
    
    def set_retry_after(self, retry_after: int) -> None:
        """Set retry_after timestamp from Telegram API response.
        
        Args:
            retry_after: Seconds to wait before retrying
        """
        self.retry_after = time.time() + retry_after
        logger.info(f"Rate limit set: retry after {retry_after}s")
    
    async def execute_with_backoff(self, coro, max_retries: int = MAX_RETRIES):
        """Execute a coroutine with exponential backoff on rate limit errors.
        
        Args:
            coro: Coroutine to execute
            max_retries: Maximum number of retry attempts
            
        Returns:
            Result of the coroutine
            
        Raises:
            Exception: If all retries are exhausted
        """
        backoff = INITIAL_BACKOFF
        
        for attempt in range(max_retries):
            try:
                # Wait if rate limit is active
                await self.wait_if_needed()
                
                # Execute the coroutine
                return await coro
            
            except aiohttp.ClientResponseError as e:
                if e.status == 429:
                    # Extract Retry-After header if available
                    retry_after = RATE_LIMIT_RETRY_AFTER_DEFAULT
                    if "Retry-After" in e.headers:
                        try:
                            retry_after = int(e.headers["Retry-After"])
                        except ValueError:
                            pass
                    
                    self.set_retry_after(retry_after)
                    
                    # Apply exponential backoff
                    wait_time = min(backoff, retry_after)
                    logger.warning(
                        f"Rate limit hit (attempt {attempt + 1}/{max_retries}), "
                        f"waiting {wait_time:.1f}s"
                    )
                    await asyncio.sleep(wait_time)
                    backoff *= 2  # Exponential backoff
                    
                    if attempt == max_retries - 1:
                        logger.error(f"Max retries exhausted for rate limit")
                        raise
                else:
                    # Non-rate-limit error, re-raise immediately
                    raise
            
            except Exception as e:
                # Other errors, re-raise immediately
                logger.error(f"Error executing request: {e}", exc_info=True)
                raise
        
        raise RuntimeError("Unexpected: max retries reached without exception")


class TelegramAdapter:
    """Telegram channel adapter for the multi-channel gateway.
    
    Connects to the Control Plane via WebSocket and handles bidirectional
    message routing between Telegram Bot API and the agent.
    
    Supports:
    - Long polling for receiving updates
    - Webhook mode (future enhancement)
    - Message formatting (Markdown, HTML)
    - Inline keyboards and buttons
    - File attachments (photos, documents, etc.)
    - Group chat mention detection
    - Rate limit handling with exponential backoff
    """
    
    def __init__(
        self,
        channel_id: str,
        bot_token: str,
        control_plane_url: str = "ws://127.0.0.1:18789",
        polling_timeout: int = 30,
        use_webhook: bool = False,
        webhook_url: Optional[str] = None,
    ):
        """Initialize the Telegram adapter.
        
        Args:
            channel_id: Unique identifier for this channel adapter
            bot_token: Telegram Bot API token
            control_plane_url: WebSocket URL of the Control Plane
            polling_timeout: Timeout for long polling requests (seconds)
            use_webhook: If True, use webhook mode instead of polling
            webhook_url: Webhook URL for receiving updates (required if use_webhook=True)
        """
        self.channel_id = channel_id
        self.bot_token = bot_token
        self.control_plane_url = control_plane_url
        self.polling_timeout = polling_timeout
        self.use_webhook = use_webhook
        self.webhook_url = webhook_url
        
        # API configuration
        self.api_base = f"{TELEGRAM_API_BASE}/bot{bot_token}"
        
        # WebSocket connection
        self.ws: Optional[WebSocketClientProtocol] = None
        self.ws_connected = False
        
        # HTTP session for API calls
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Rate limiter
        self.rate_limiter = TelegramRateLimiter()
        
        # Polling state
        self.last_update_id: int = 0
        
        # Bot info (fetched on startup)
        self.bot_username: Optional[str] = None
        self.bot_id: Optional[int] = None
        
        # Running state
        self._running = False
        self._polling_task: Optional[asyncio.Task] = None
        self._ws_receive_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the Telegram adapter.
        
        This:
        1. Creates HTTP session
        2. Fetches bot info
        3. Connects to Control Plane
        4. Starts polling or webhook listener
        """
        if self._running:
            logger.warning(f"TelegramAdapter {self.channel_id} already running")
            return
        
        self._running = True
        
        # Create HTTP session
        self.session = aiohttp.ClientSession()
        
        # Fetch bot info
        await self._fetch_bot_info()
        
        # Connect to Control Plane
        await self._connect_to_control_plane()
        
        # Start message handling
        if self.use_webhook:
            # Webhook mode: set webhook URL
            await self._set_webhook()
            logger.info(f"TelegramAdapter {self.channel_id} started in webhook mode")
        else:
            # Polling mode: start polling task
            self._polling_task = asyncio.create_task(self._polling_loop())
            logger.info(f"TelegramAdapter {self.channel_id} started in polling mode")
        
        # Start WebSocket receive task
        self._ws_receive_task = asyncio.create_task(self._ws_receive_loop())
    
    async def stop(self) -> None:
        """Stop the Telegram adapter."""
        if not self._running:
            return
        
        self._running = False
        
        # Cancel tasks
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        
        if self._ws_receive_task:
            self._ws_receive_task.cancel()
            try:
                await self._ws_receive_task
            except asyncio.CancelledError:
                pass
        
        # Close WebSocket
        if self.ws:
            await self.ws.close()
            self.ws = None
            self.ws_connected = False
        
        # Close HTTP session
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info(f"TelegramAdapter {self.channel_id} stopped")
    
    async def _fetch_bot_info(self) -> None:
        """Fetch bot information from Telegram API."""
        try:
            result = await self._api_call("getMe")
            self.bot_username = result.get("username")
            self.bot_id = result.get("id")
            logger.info(
                f"Bot info fetched: @{self.bot_username} (ID: {self.bot_id})"
            )
        except Exception as e:
            logger.error(f"Failed to fetch bot info: {e}", exc_info=True)
            raise
    
    async def _connect_to_control_plane(self) -> None:
        """Establish WebSocket connection to Control Plane."""
        try:
            self.ws = await websockets.connect(self.control_plane_url)
            self.ws_connected = True
            
            # Send initial status message
            await self._send_status(ChannelStatusType.CONNECTED)
            
            logger.info(
                f"TelegramAdapter {self.channel_id} connected to Control Plane"
            )
        except Exception as e:
            logger.error(
                f"Failed to connect to Control Plane: {e}", exc_info=True
            )
            raise
    
    async def _send_status(
        self,
        status: ChannelStatusType,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send channel status to Control Plane.
        
        Args:
            status: Channel status
            error_message: Optional error details
            metadata: Optional additional status information
        """
        if not self.ws_connected or not self.ws:
            return
        
        status_msg = MessageSerializer.create_channel_status(
            channel_id=self.channel_id,
            status=status,
            error_message=error_message,
            metadata=metadata,
        )
        
        try:
            await self.ws.send(serialize_message(status_msg))
        except Exception as e:
            logger.error(f"Failed to send status: {e}", exc_info=True)
    
    async def _api_call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a Telegram Bot API call with rate limiting.
        
        Args:
            method: API method name (e.g., "sendMessage")
            params: Optional parameters
            files: Optional files for multipart upload
            
        Returns:
            API response result
            
        Raises:
            aiohttp.ClientResponseError: If API call fails
        """
        url = urljoin(self.api_base + "/", method)
        
        async def _make_request():
            if files:
                # Multipart upload
                data = aiohttp.FormData()
                if params:
                    for key, value in params.items():
                        data.add_field(key, str(value))
                for key, value in files.items():
                    data.add_field(key, value)
                
                async with self.session.post(url, data=data) as resp:
                    resp.raise_for_status()
                    result = await resp.json()
            else:
                # JSON request
                async with self.session.post(url, json=params) as resp:
                    resp.raise_for_status()
                    result = await resp.json()
            
            if not result.get("ok"):
                error_code = result.get("error_code")
                description = result.get("description", "Unknown error")
                raise aiohttp.ClientResponseError(
                    request_info=resp.request_info,
                    history=resp.history,
                    status=error_code or 500,
                    message=description,
                    headers=resp.headers,
                )
            
            return result.get("result", {})
        
        # Execute with rate limiting and backoff
        return await self.rate_limiter.execute_with_backoff(_make_request())
    
    async def _set_webhook(self) -> None:
        """Set webhook URL for receiving updates."""
        if not self.webhook_url:
            raise ValueError("webhook_url is required for webhook mode")
        
        await self._api_call("setWebhook", {"url": self.webhook_url})
        logger.info(f"Webhook set to {self.webhook_url}")
    
    async def _polling_loop(self) -> None:
        """Long polling loop for receiving updates."""
        logger.info("Starting Telegram polling loop")
        
        while self._running:
            try:
                # Get updates
                updates = await self._api_call(
                    "getUpdates",
                    {
                        "offset": self.last_update_id + 1,
                        "timeout": self.polling_timeout,
                        "allowed_updates": ["message", "edited_message"],
                    },
                )
                
                # Process each update
                for update in updates:
                    update_id = update.get("update_id")
                    if update_id:
                        self.last_update_id = max(self.last_update_id, update_id)
                    
                    await self._handle_update(update)
            
            except asyncio.CancelledError:
                break
            
            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying
        
        logger.info("Telegram polling loop stopped")
    
    async def _handle_update(self, update: Dict[str, Any]) -> None:
        """Handle a Telegram update by converting it to InboundMessage.
        
        Args:
            update: Telegram update object
        """
        # Extract message from update
        message = update.get("message") or update.get("edited_message")
        
        if not message:
            logger.debug(f"Update {update.get('update_id')} has no message, skipping")
            return
        
        try:
            # Parse message into InboundMessage
            inbound_msg = await self._parse_telegram_message(message)
            
            # Send to Control Plane
            if self.ws_connected and self.ws:
                await self.ws.send(serialize_message(inbound_msg))
                logger.debug(
                    f"Sent inbound message {inbound_msg.message_id} to Control Plane"
                )
        
        except Exception as e:
            logger.error(f"Failed to handle update: {e}", exc_info=True)
    
    async def _parse_telegram_message(
        self, message: Dict[str, Any]
    ) -> InboundMessage:
        """Parse Telegram message into InboundMessage format.
        
        Args:
            message: Telegram message object
            
        Returns:
            InboundMessage instance
        """
        message_id = str(message["message_id"])
        user = message.get("from", {})
        user_id = str(user.get("id", "unknown"))
        chat = message.get("chat", {})
        chat_id = str(chat.get("id"))
        
        # Extract text
        text = message.get("text") or message.get("caption") or ""
        
        # Check for bot mention in group chats
        bot_mention = False
        if chat.get("type") in ["group", "supergroup"]:
            # Check for @username mention
            if self.bot_username and f"@{self.bot_username}" in text:
                bot_mention = True
            
            # Check for mention entities
            entities = message.get("entities", []) + message.get("caption_entities", [])
            for entity in entities:
                if entity.get("type") == "mention":
                    # Extract mentioned username
                    offset = entity.get("offset", 0)
                    length = entity.get("length", 0)
                    mentioned = text[offset:offset + length]
                    if mentioned == f"@{self.bot_username}":
                        bot_mention = True
                        break
        
        # Extract attachments
        attachments = []
        
        # Photo
        if "photo" in message:
            # Get largest photo
            photos = message["photo"]
            largest_photo = max(photos, key=lambda p: p.get("file_size", 0))
            attachments.append({
                "type": "photo",
                "file_id": largest_photo["file_id"],
                "file_size": largest_photo.get("file_size"),
                "width": largest_photo.get("width"),
                "height": largest_photo.get("height"),
            })
        
        # Document
        if "document" in message:
            doc = message["document"]
            attachments.append({
                "type": "document",
                "file_id": doc["file_id"],
                "file_name": doc.get("file_name"),
                "mime_type": doc.get("mime_type"),
                "file_size": doc.get("file_size"),
            })
        
        # Audio
        if "audio" in message:
            audio = message["audio"]
            attachments.append({
                "type": "audio",
                "file_id": audio["file_id"],
                "duration": audio.get("duration"),
                "mime_type": audio.get("mime_type"),
                "file_size": audio.get("file_size"),
            })
        
        # Voice
        if "voice" in message:
            voice = message["voice"]
            attachments.append({
                "type": "voice",
                "file_id": voice["file_id"],
                "duration": voice.get("duration"),
                "mime_type": voice.get("mime_type"),
                "file_size": voice.get("file_size"),
            })
        
        # Video
        if "video" in message:
            video = message["video"]
            attachments.append({
                "type": "video",
                "file_id": video["file_id"],
                "duration": video.get("duration"),
                "mime_type": video.get("mime_type"),
                "file_size": video.get("file_size"),
                "width": video.get("width"),
                "height": video.get("height"),
            })
        
        # Metadata
        metadata = {
            "bot_mention": bot_mention,
            "chat_type": chat.get("type"),
            "chat_title": chat.get("title"),
            "user_username": user.get("username"),
            "user_first_name": user.get("first_name"),
            "user_last_name": user.get("last_name"),
        }
        
        # Create InboundMessage
        return MessageSerializer.create_inbound_message(
            message_id=message_id,
            channel_id=self.channel_id,
            user_id=user_id,
            chat_id=chat_id,
            text=text,
            attachments=attachments,
            metadata=metadata,
        )
    
    async def download_file(self, file_id: str) -> bytes:
        """Download a file from Telegram.
        
        Args:
            file_id: Telegram file_id
            
        Returns:
            File content as bytes
        """
        # Get file path
        file_info = await self._api_call("getFile", {"file_id": file_id})
        file_path = file_info.get("file_path")
        
        if not file_path:
            raise ValueError(f"No file_path in response for file_id {file_id}")
        
        # Download file
        file_url = f"{TELEGRAM_API_BASE}/file/bot{self.bot_token}/{file_path}"
        
        async with self.session.get(file_url) as resp:
            resp.raise_for_status()
            return await resp.read()
    
    async def _ws_receive_loop(self) -> None:
        """Receive and handle outbound messages from Control Plane."""
        logger.info("Starting WebSocket receive loop")
        
        while self._running and self.ws_connected and self.ws:
            try:
                # Receive message from Control Plane
                data = await self.ws.recv()
                
                # Parse message
                message = parse_message(data)
                
                # Handle outbound messages
                if isinstance(message, OutboundMessage):
                    await self._handle_outbound_message(message)
            
            except asyncio.CancelledError:
                break
            
            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed")
                self.ws_connected = False
                
                # Attempt reconnection
                if self._running:
                    await asyncio.sleep(5)
                    try:
                        await self._connect_to_control_plane()
                    except Exception as e:
                        logger.error(f"Reconnection failed: {e}", exc_info=True)
                break
            
            except Exception as e:
                logger.error(f"Error in WebSocket receive loop: {e}", exc_info=True)
        
        logger.info("WebSocket receive loop stopped")
    
    async def _handle_outbound_message(self, message: OutboundMessage) -> None:
        """Handle an outbound message by sending it via Telegram API.
        
        Args:
            message: OutboundMessage to send
        """
        try:
            # Extract parameters
            chat_id = message.chat_id
            text = message.text
            reply_to = message.reply_to
            metadata = message.metadata
            
            # Prepare API parameters
            params = {
                "chat_id": chat_id,
                "text": text[:MAX_MESSAGE_LENGTH],  # Truncate if needed
            }
            
            # Add reply_to if specified
            if reply_to:
                params["reply_to_message_id"] = reply_to
            
            # Add parse_mode if specified
            parse_mode = metadata.get("parse_mode", "Markdown")
            if parse_mode:
                params["parse_mode"] = parse_mode
            
            # Add inline keyboard if specified
            if "inline_keyboard" in metadata:
                params["reply_markup"] = {
                    "inline_keyboard": metadata["inline_keyboard"]
                }
            
            # Send message
            result = await self._api_call("sendMessage", params)
            
            logger.debug(
                f"Sent outbound message {message.message_id} to chat {chat_id}"
            )
        
        except Exception as e:
            logger.error(
                f"Failed to send outbound message {message.message_id}: {e}",
                exc_info=True,
            )
            
            # Send error status to Control Plane
            await self._send_status(
                ChannelStatusType.ERROR,
                error_message=f"Failed to send message: {str(e)}",
            )
