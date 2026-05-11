"""Discord channel adapter for multi-channel gateway.

This module implements the DiscordAdapter class which:
- Connects to the Control Plane via WebSocket
- Integrates with Discord Gateway for receiving events
- Uses Discord REST API for sending messages
- Parses Discord events into unified InboundMessage format
- Formats OutboundMessage into Discord API calls
- Handles file downloads for attachments
- Detects mentions and slash commands
- Implements rate limit handling with Discord rate limit headers

The adapter runs as an asyncio task and maintains persistent connections
to both Discord Gateway and Control Plane for bidirectional message routing.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import aiohttp
import websockets

from gateway_protocol import (
    ChannelStatusType,
    InboundMessage,
    MessageSerializer,
    OutboundMessage,
    parse_message,
    serialize_message,
)

logger = logging.getLogger(__name__)

# Discord API configuration
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_GATEWAY_VERSION = 10
DISCORD_GATEWAY_ENCODING = "json"

# Discord Gateway opcodes
OPCODE_DISPATCH = 0
OPCODE_HEARTBEAT = 1
OPCODE_IDENTIFY = 2
OPCODE_HELLO = 10
OPCODE_HEARTBEAT_ACK = 11

# Rate limiting configuration
RATE_LIMIT_RETRY_AFTER_DEFAULT = 5  # Default retry delay in seconds
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0  # Initial backoff delay in seconds


class DiscordRateLimiter:
    """Rate limiter with exponential backoff for Discord API.
    
    Handles 429 Too Many Requests responses from Discord API by:
    - Respecting X-RateLimit-Reset-After header when provided
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
    
    def set_retry_after(self, retry_after: float) -> None:
        """Set retry_after timestamp from Discord API response.
        
        Args:
            retry_after: Seconds to wait before retrying
        """
        self.retry_after = time.time() + retry_after
        logger.info(f"Rate limit set: retry after {retry_after:.1f}s")
    
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
                    # Extract X-RateLimit-Reset-After header if available
                    retry_after = RATE_LIMIT_RETRY_AFTER_DEFAULT
                    headers = e.headers if e.headers else {}
                    if "X-RateLimit-Reset-After" in headers:
                        try:
                            retry_after = float(headers["X-RateLimit-Reset-After"])
                        except ValueError:
                            pass
                    elif "Retry-After" in headers:
                        try:
                            retry_after = float(headers["Retry-After"])
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
            
            except Exception:
                # Other errors, re-raise immediately
                raise
        
        raise RuntimeError("Unexpected: max retries reached without exception")



class DiscordAdapter:
    """Discord channel adapter for the multi-channel gateway.
    
    Connects to the Control Plane via WebSocket and handles bidirectional
    message routing between Discord Gateway/REST API and the agent.
    
    Supports:
    - Discord Gateway connection for receiving events
    - Discord REST API for sending messages
    - Message formatting (embeds, reactions, threads)
    - File attachments
    - Mention detection for bot activation
    - Slash command support
    - Rate limit handling with Discord rate limit headers
    """
    
    def __init__(
        self,
        channel_id: str,
        bot_token: str,
        control_plane_url: str = "ws://127.0.0.1:18789",
        intents: int = 513,  # GUILDS + GUILD_MESSAGES
    ):
        """Initialize the Discord adapter.
        
        Args:
            channel_id: Unique identifier for this channel adapter
            bot_token: Discord Bot token
            control_plane_url: WebSocket URL of the Control Plane
            intents: Discord Gateway intents (default: GUILDS + GUILD_MESSAGES)
        """
        self.channel_id = channel_id
        self.bot_token = bot_token
        self.control_plane_url = control_plane_url
        self.intents = intents
        
        # API configuration
        self.api_base = DISCORD_API_BASE
        
        # WebSocket connections
        self.control_ws: Optional[Any] = None  # websockets.WebSocketClientProtocol
        self.control_ws_connected = False
        self.discord_ws: Optional[Any] = None  # websockets.WebSocketClientProtocol
        self.discord_ws_connected = False
        
        # HTTP session for API calls
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Rate limiter
        self.rate_limiter = DiscordRateLimiter()
        
        # Discord Gateway state
        self.gateway_url: Optional[str] = None
        self.session_id: Optional[str] = None
        self.sequence: Optional[int] = None
        self.heartbeat_interval: Optional[float] = None
        self.last_heartbeat_ack: float = 0
        
        # Bot info (fetched on startup)
        self.bot_user_id: Optional[str] = None
        self.bot_username: Optional[str] = None
        
        # Running state
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._discord_receive_task: Optional[asyncio.Task] = None
        self._control_receive_task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the Discord adapter.
        
        This:
        1. Creates HTTP session
        2. Fetches bot info and gateway URL
        3. Connects to Control Plane
        4. Connects to Discord Gateway
        5. Starts heartbeat and receive loops
        """
        if self._running:
            logger.warning(f"DiscordAdapter {self.channel_id} already running")
            return
        
        self._running = True
        
        # Create HTTP session with auth header
        headers = {"Authorization": f"Bot {self.bot_token}"}
        self.session = aiohttp.ClientSession(headers=headers)
        
        # Fetch bot info and gateway URL
        await self._fetch_bot_info()
        await self._fetch_gateway_url()
        
        # Connect to Control Plane
        await self._connect_to_control_plane()
        
        # Connect to Discord Gateway
        await self._connect_to_discord_gateway()
        
        # Start receive loops
        self._discord_receive_task = asyncio.create_task(self._discord_receive_loop())
        self._control_receive_task = asyncio.create_task(self._control_receive_loop())
        
        logger.info(f"DiscordAdapter {self.channel_id} started")

    
    async def stop(self) -> None:
        """Stop the Discord adapter."""
        if not self._running:
            return
        
        self._running = False
        
        # Cancel tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self._discord_receive_task:
            self._discord_receive_task.cancel()
            try:
                await self._discord_receive_task
            except asyncio.CancelledError:
                pass
        
        if self._control_receive_task:
            self._control_receive_task.cancel()
            try:
                await self._control_receive_task
            except asyncio.CancelledError:
                pass
        
        # Close WebSocket connections
        if self.discord_ws:
            await self.discord_ws.close()
            self.discord_ws = None
            self.discord_ws_connected = False
        
        if self.control_ws:
            await self.control_ws.close()
            self.control_ws = None
            self.control_ws_connected = False
        
        # Close HTTP session
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info(f"DiscordAdapter {self.channel_id} stopped")
    
    async def _fetch_bot_info(self) -> None:
        """Fetch bot information from Discord API."""
        try:
            result = await self._api_call("GET", "/users/@me")
            self.bot_user_id = result.get("id")
            self.bot_username = result.get("username")
            logger.info(
                f"Bot info fetched: {self.bot_username} (ID: {self.bot_user_id})"
            )
        except Exception as e:
            logger.error(f"Failed to fetch bot info: {e}", exc_info=True)
            raise
    
    async def _fetch_gateway_url(self) -> None:
        """Fetch Discord Gateway URL."""
        try:
            result = await self._api_call("GET", "/gateway/bot")
            self.gateway_url = result.get("url")
            logger.info(f"Gateway URL fetched: {self.gateway_url}")
        except Exception as e:
            logger.error(f"Failed to fetch gateway URL: {e}", exc_info=True)
            raise
    
    async def _connect_to_control_plane(self) -> None:
        """Establish WebSocket connection to Control Plane."""
        try:
            self.control_ws = await websockets.connect(self.control_plane_url)
            self.control_ws_connected = True
            
            # Send initial status message
            await self._send_status(ChannelStatusType.CONNECTED)
            
            logger.info(
                f"DiscordAdapter {self.channel_id} connected to Control Plane"
            )
        except Exception as e:
            logger.error(
                f"Failed to connect to Control Plane: {e}", exc_info=True
            )
            raise

    
    async def _connect_to_discord_gateway(self) -> None:
        """Establish WebSocket connection to Discord Gateway."""
        if not self.gateway_url:
            raise ValueError("Gateway URL not fetched")
        
        try:
            # Connect to Discord Gateway
            gateway_ws_url = f"{self.gateway_url}?v={DISCORD_GATEWAY_VERSION}&encoding={DISCORD_GATEWAY_ENCODING}"
            self.discord_ws = await websockets.connect(gateway_ws_url)
            self.discord_ws_connected = True
            
            # Wait for HELLO opcode
            hello_data = await self.discord_ws.recv()
            hello_payload = json.loads(hello_data)
            
            if hello_payload.get("op") != OPCODE_HELLO:
                raise ValueError(f"Expected HELLO opcode, got {hello_payload.get('op')}")
            
            # Extract heartbeat interval
            self.heartbeat_interval = hello_payload["d"]["heartbeat_interval"] / 1000.0
            logger.info(f"Heartbeat interval: {self.heartbeat_interval}s")
            
            # Send IDENTIFY payload
            await self._send_identify()
            
            # Start heartbeat task
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            logger.info(f"Connected to Discord Gateway")
        
        except Exception as e:
            logger.error(f"Failed to connect to Discord Gateway: {e}", exc_info=True)
            raise
    
    async def _send_identify(self) -> None:
        """Send IDENTIFY payload to Discord Gateway."""
        if not self.discord_ws:
            raise RuntimeError("Discord WebSocket not connected")
        
        identify_payload = {
            "op": OPCODE_IDENTIFY,
            "d": {
                "token": self.bot_token,
                "intents": self.intents,
                "properties": {
                    "$os": "linux",
                    "$browser": "w7-ragkb",
                    "$device": "w7-ragkb",
                },
            },
        }
        
        await self.discord_ws.send(json.dumps(identify_payload))
        logger.debug("Sent IDENTIFY payload")
    
    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to Discord Gateway."""
        if not self.heartbeat_interval:
            logger.error("Heartbeat interval not set")
            return
        
        logger.info("Starting Discord heartbeat loop")
        
        while self._running and self.discord_ws_connected and self.discord_ws:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                # Send heartbeat
                heartbeat_payload = {
                    "op": OPCODE_HEARTBEAT,
                    "d": self.sequence,
                }
                
                if self.discord_ws:
                    await self.discord_ws.send(json.dumps(heartbeat_payload))
                    logger.debug(f"Sent heartbeat (seq: {self.sequence})")
            
            except asyncio.CancelledError:
                break
            
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}", exc_info=True)
        
        logger.info("Discord heartbeat loop stopped")
    
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
        if not self.control_ws_connected or not self.control_ws:
            return
        
        # Add channel_type to metadata
        if metadata is None:
            metadata = {}
        metadata["channel_type"] = "discord"
        
        status_msg = MessageSerializer.create_channel_status(
            channel_id=self.channel_id,
            status=status,
            error_message=error_message,
            metadata=metadata,
        )
        
        try:
            await self.control_ws.send(serialize_message(status_msg))
        except Exception as e:
            logger.error(f"Failed to send status: {e}", exc_info=True)

    
    async def _api_call(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a Discord REST API call with rate limiting.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            endpoint: API endpoint (e.g., "/channels/{channel_id}/messages")
            json_data: Optional JSON body
            files: Optional files for multipart upload
            
        Returns:
            API response JSON
            
        Raises:
            aiohttp.ClientResponseError: If API call fails
        """
        if not self.session:
            raise RuntimeError("HTTP session not initialized")
        
        url = urljoin(self.api_base, endpoint)
        
        async def _make_request():
            if not self.session:
                raise RuntimeError("HTTP session not initialized")
            
            if files:
                # Multipart upload
                data = aiohttp.FormData()
                if json_data:
                    data.add_field("payload_json", json.dumps(json_data))
                for key, value in files.items():
                    data.add_field(key, value)
                
                async with self.session.request(method, url, data=data) as resp:
                    resp.raise_for_status()
                    if resp.status == 204:  # No Content
                        return {}
                    return await resp.json()
            else:
                # JSON request
                async with self.session.request(method, url, json=json_data) as resp:
                    resp.raise_for_status()
                    if resp.status == 204:  # No Content
                        return {}
                    return await resp.json()
        
        # Execute with rate limiting and backoff
        return await self.rate_limiter.execute_with_backoff(_make_request())
    
    async def _discord_receive_loop(self) -> None:
        """Receive and handle events from Discord Gateway."""
        logger.info("Starting Discord Gateway receive loop")
        
        while self._running and self.discord_ws_connected and self.discord_ws:
            try:
                # Receive event from Discord Gateway
                data = await self.discord_ws.recv()
                payload = json.loads(data)
                
                # Extract opcode and sequence
                opcode = payload.get("op")
                self.sequence = payload.get("s") or self.sequence
                
                # Handle different opcodes
                if opcode == OPCODE_DISPATCH:
                    event_type = payload.get("t")
                    event_data = payload.get("d", {})
                    
                    # Store session_id from READY event
                    if event_type == "READY":
                        self.session_id = event_data.get("session_id")
                        logger.info(f"Discord session ready: {self.session_id}")
                    
                    # Handle MESSAGE_CREATE event
                    elif event_type == "MESSAGE_CREATE":
                        await self._handle_message_create(event_data)
                
                elif opcode == OPCODE_HEARTBEAT_ACK:
                    self.last_heartbeat_ack = time.time()
                    logger.debug("Received heartbeat ACK")
                
                elif opcode == OPCODE_HEARTBEAT:
                    # Server requesting immediate heartbeat
                    heartbeat_payload = {
                        "op": OPCODE_HEARTBEAT,
                        "d": self.sequence,
                    }
                    await self.discord_ws.send(json.dumps(heartbeat_payload))
                    logger.debug("Sent immediate heartbeat")
            
            except asyncio.CancelledError:
                break
            
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Discord Gateway connection closed")
                self.discord_ws_connected = False
                
                # Attempt reconnection
                if self._running:
                    await asyncio.sleep(5)
                    try:
                        await self._connect_to_discord_gateway()
                    except Exception as e:
                        logger.error(f"Reconnection failed: {e}", exc_info=True)
                break
            
            except Exception as e:
                logger.error(f"Error in Discord receive loop: {e}", exc_info=True)
        
        logger.info("Discord Gateway receive loop stopped")

    
    async def _handle_message_create(self, message: Dict[str, Any]) -> None:
        """Handle MESSAGE_CREATE event from Discord Gateway.
        
        Args:
            message: Discord message object
        """
        # Ignore bot messages
        if message.get("author", {}).get("bot"):
            return
        
        # Ignore messages without content
        content = message.get("content", "")
        if not content.strip():
            return
        
        try:
            # Parse message into InboundMessage
            inbound_msg = await self._parse_discord_message(message)
            
            # Send to Control Plane
            if self.control_ws_connected and self.control_ws:
                await self.control_ws.send(serialize_message(inbound_msg))
                logger.debug(
                    f"Sent inbound message {inbound_msg.message_id} to Control Plane"
                )
        
        except Exception as e:
            logger.error(f"Failed to handle MESSAGE_CREATE: {e}", exc_info=True)
    
    async def _parse_discord_message(
        self, message: Dict[str, Any]
    ) -> InboundMessage:
        """Parse Discord message into InboundMessage format.
        
        Args:
            message: Discord message object
            
        Returns:
            InboundMessage instance
        """
        message_id = message["id"]
        author = message.get("author", {})
        user_id = author.get("id", "unknown")
        channel_id = message.get("channel_id", "")
        guild_id = message.get("guild_id")
        content = message.get("content", "")
        
        # Check for bot mention
        bot_mention = False
        mentions = message.get("mentions", [])
        for mention in mentions:
            if mention.get("id") == self.bot_user_id:
                bot_mention = True
                break
        
        # Check for slash command (starts with /)
        is_slash_command = content.startswith("/")
        
        # Extract attachments
        attachments = []
        for attachment in message.get("attachments", []):
            attachments.append({
                "type": "attachment",
                "id": attachment.get("id"),
                "filename": attachment.get("filename"),
                "content_type": attachment.get("content_type"),
                "size": attachment.get("size"),
                "url": attachment.get("url"),
                "proxy_url": attachment.get("proxy_url"),
                "width": attachment.get("width"),
                "height": attachment.get("height"),
            })
        
        # Metadata
        metadata = {
            "bot_mention": bot_mention,
            "is_slash_command": is_slash_command,
            "guild_id": guild_id,
            "channel_type": self._get_channel_type(message),
            "author_username": author.get("username"),
            "author_discriminator": author.get("discriminator"),
            "message_type": message.get("type"),
            "referenced_message": message.get("referenced_message", {}).get("id"),
        }
        
        # Determine thread_id (for thread messages)
        thread_id = None
        if message.get("thread"):
            thread_id = message["thread"].get("id")
        
        # Create InboundMessage
        return MessageSerializer.create_inbound_message(
            message_id=message_id,
            channel_id=self.channel_id,
            user_id=user_id,
            chat_id=channel_id,
            text=content,
            thread_id=thread_id,
            attachments=attachments,
            metadata=metadata,
        )
    
    def _get_channel_type(self, message: Dict[str, Any]) -> str:
        """Determine channel type from message.
        
        Args:
            message: Discord message object
            
        Returns:
            Channel type string (dm, guild_text, guild_thread, etc.)
        """
        # Check if DM
        if not message.get("guild_id"):
            return "dm"
        
        # Check if thread
        if message.get("thread"):
            return "guild_thread"
        
        # Default to guild text channel
        return "guild_text"

    
    async def download_attachment(self, url: str) -> bytes:
        """Download an attachment from Discord.
        
        Args:
            url: Attachment URL
            
        Returns:
            File content as bytes
        """
        if not self.session:
            raise RuntimeError("HTTP session not initialized")
        
        async with self.session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()
    
    async def _control_receive_loop(self) -> None:
        """Receive and handle outbound messages from Control Plane."""
        logger.info("Starting Control Plane receive loop")
        
        while self._running and self.control_ws_connected and self.control_ws:
            try:
                # Receive message from Control Plane
                data = await self.control_ws.recv()
                
                # Parse message
                message = parse_message(data)
                
                # Handle outbound messages
                if isinstance(message, OutboundMessage):
                    await self._handle_outbound_message(message)
            
            except asyncio.CancelledError:
                break
            
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Control Plane connection closed")
                self.control_ws_connected = False
                
                # Attempt reconnection
                if self._running:
                    await asyncio.sleep(5)
                    try:
                        await self._connect_to_control_plane()
                    except Exception as e:
                        logger.error(f"Reconnection failed: {e}", exc_info=True)
                break
            
            except Exception as e:
                logger.error(f"Error in Control Plane receive loop: {e}", exc_info=True)
        
        logger.info("Control Plane receive loop stopped")
    
    async def _handle_outbound_message(self, message: OutboundMessage) -> None:
        """Handle an outbound message by sending it via Discord REST API.
        
        Args:
            message: OutboundMessage to send
        """
        try:
            # Extract parameters
            channel_id = message.chat_id
            content = message.text
            metadata = message.metadata or {}
            
            # Build message payload
            payload: Dict[str, Any] = {"content": content}
            
            # Add message reference (reply)
            if message.reply_to:
                payload["message_reference"] = {
                    "message_id": message.reply_to,
                }
            
            # Add embed if specified
            if "embed" in metadata:
                embed_data = metadata["embed"]
                if isinstance(embed_data, dict):
                    payload["embeds"] = [embed_data]
            
            # Send message via REST API
            endpoint = f"/channels/{channel_id}/messages"
            result = await self._api_call("POST", endpoint, json_data=payload)
            
            logger.debug(
                f"Sent outbound message {message.message_id} to channel {channel_id}"
            )
            
            # Handle reactions if specified
            if "reactions" in metadata:
                sent_message_id = result.get("id")
                if sent_message_id:
                    reactions = metadata["reactions"]
                    if isinstance(reactions, list):
                        for emoji in reactions:
                            await self._add_reaction(channel_id, sent_message_id, emoji)
        
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
    
    async def _add_reaction(
        self, channel_id: str, message_id: str, emoji: str
    ) -> None:
        """Add a reaction to a message.
        
        Args:
            channel_id: Discord channel ID
            message_id: Discord message ID
            emoji: Emoji to add (unicode or custom emoji format)
        """
        try:
            endpoint = f"/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"
            await self._api_call("PUT", endpoint)
            logger.debug(f"Added reaction {emoji} to message {message_id}")
        except Exception as e:
            logger.error(f"Failed to add reaction: {e}", exc_info=True)


async def create_discord_adapter(
    channel_id: str = "discord-main",
    bot_token: Optional[str] = None,
    control_plane_url: str = "ws://127.0.0.1:18789",
    intents: int = 513,  # GUILDS + GUILD_MESSAGES
) -> DiscordAdapter:
    """Create and start a Discord adapter.
    
    Args:
        channel_id: Unique identifier for this channel adapter
        bot_token: Discord Bot token (defaults to DISCORD_BOT_TOKEN env var)
        control_plane_url: WebSocket URL of the Control Plane
        intents: Discord Gateway intents
        
    Returns:
        Started DiscordAdapter instance
    """
    import os
    
    bot_token = bot_token or os.getenv("DISCORD_BOT_TOKEN")
    
    if not bot_token:
        raise ValueError("bot_token is required (set DISCORD_BOT_TOKEN env var)")
    
    adapter = DiscordAdapter(
        channel_id=channel_id,
        bot_token=bot_token,
        control_plane_url=control_plane_url,
        intents=intents,
    )
    
    await adapter.start()
    return adapter
