"""Slack channel adapter for multi-channel gateway.

This module implements the SlackAdapter class which:
- Wraps existing Slack Socket Mode logic
- Connects to the Control Plane via WebSocket
- Parses Slack events into unified InboundMessage format
- Formats OutboundMessage into Slack API calls
- Maintains backward compatibility with existing Slack conversations
- Uses SessionManager instead of direct conversation storage

The adapter integrates with the existing slack_bot.py logic while routing
messages through the Gateway architecture for multi-channel support.
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

import websockets
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.errors import SlackApiError

from gateway_protocol import (
    ChannelStatusType,
    InboundMessage,
    MessageSerializer,
    OutboundMessage,
    parse_message,
    serialize_message,
)

logger = logging.getLogger(__name__)

# Slack configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
SLACK_MAX_TEXT_LEN = 3000


class SlackAdapter:
    """Slack channel adapter for the multi-channel gateway.
    
    Wraps the existing Slack Socket Mode bot and integrates it with the
    Control Plane for unified message routing across channels.
    
    Maintains backward compatibility with existing Slack conversations
    while enabling multi-channel coordination through the Gateway.
    """
    
    def __init__(
        self,
        channel_id: str,
        bot_token: str,
        app_token: str,
        control_plane_url: str = "ws://127.0.0.1:18789",
    ):
        """Initialize the Slack adapter.
        
        Args:
            channel_id: Unique identifier for this channel adapter
            bot_token: Slack Bot User OAuth Token
            app_token: Slack App-Level Token for Socket Mode
            control_plane_url: WebSocket URL of the Control Plane
        """
        self.channel_id = channel_id
        self.bot_token = bot_token
        self.app_token = app_token
        self.control_plane_url = control_plane_url
        
        # Slack app
        self.app = AsyncApp(token=bot_token)
        self.socket_handlers = []
        
        # WebSocket connection to Control Plane
        self.ws: Optional[Any] = None  # websockets.WebSocketClientProtocol
        self.ws_connected = False
        
        # Bot identity (resolved in start())
        self._bot_user_id: Optional[str] = None

        # Running state
        self._running = False
        self._socket_tasks = []
        self._ws_receive_task: Optional[asyncio.Task] = None

        # Register Slack event handlers
        self._register_handlers()
    
    def _register_handlers(self) -> None:
        """Register Slack event handlers."""

        async def _forward_inbound_event(
            event: Dict[str, Any], *, is_app_mention: bool = False
        ) -> None:
            """Normalize and forward supported Slack inbound events to Control Plane."""
            # Ignore bot messages and message_changed subtypes
            if event.get("subtype") in ("bot_message", "message_changed", "message_deleted"):
                return
            if event.get("bot_id"):
                return

            user_id = event.get("user")
            if not user_id:
                return

            text = event.get("text", "")
            if not text.strip():
                return

            channel = event["channel"]
            thread_ts = event.get("thread_ts", event["ts"])

            logger.info(
                f"Received Slack message from user={user_id} channel={channel} thread={thread_ts}"
            )

            try:
                # Convert to InboundMessage (pass is_app_mention for metadata)
                inbound_msg = await self._parse_slack_message(
                    event, is_app_mention=is_app_mention,
                )

                # Send to Control Plane
                if self.ws_connected and self.ws:
                    await self.ws.send(serialize_message(inbound_msg))
                    logger.debug(
                        f"Sent inbound message {inbound_msg.message_id} to Control Plane"
                    )

            except Exception as e:
                logger.error(f"Failed to process Slack message: {e}", exc_info=True)

        @self.app.event("message")
        async def handle_message(event, say):
            """Handle standard Slack message events.

            If the message contains a mention of our bot, skip it here —
            the ``app_mention`` event will handle it instead, avoiding
            duplicate processing.
            """
            if self._bot_user_id and f"<@{self._bot_user_id}>" in event.get("text", ""):
                return
            await _forward_inbound_event(event)

        @self.app.event("app_mention")
        async def handle_app_mention(event, say):
            """Handle mentions directed at the app in channels."""
            await _forward_inbound_event(event, is_app_mention=True)
    
    async def start(self) -> None:
        """Start the Slack adapter.
        
        This:
        1. Connects to Control Plane
        2. Starts Slack Socket Mode handlers (2 for HA)
        3. Starts WebSocket receive loop
        """
        if self._running:
            logger.warning(f"SlackAdapter {self.channel_id} already running")
            return
        
        self._running = True

        # Resolve bot user ID for dedup of message vs app_mention events
        try:
            auth_resp = await self.app.client.auth_test()
            self._bot_user_id = auth_resp.get("user_id")
            logger.info(f"Resolved bot user ID: {self._bot_user_id}")
        except Exception:
            logger.warning("Could not resolve bot user ID via auth_test", exc_info=True)

        # Connect to Control Plane
        await self._connect_to_control_plane()
        
        # Create Socket Mode handlers (2 for high availability)
        handler1 = AsyncSocketModeHandler(self.app, self.app_token)
        handler2 = AsyncSocketModeHandler(self.app, self.app_token)
        self.socket_handlers = [handler1, handler2]
        
        # Start Socket Mode handlers
        logger.info(f"Starting 2 Slack Socket Mode handlers for HA")
        self._socket_tasks = [
            asyncio.create_task(handler1.start_async()),
            asyncio.create_task(handler2.start_async()),
        ]
        
        # Start WebSocket receive task
        self._ws_receive_task = asyncio.create_task(self._ws_receive_loop())
        
        logger.info(f"SlackAdapter {self.channel_id} started")
    
    async def stop(self) -> None:
        """Stop the Slack adapter."""
        if not self._running:
            return
        
        self._running = False
        
        # Cancel Socket Mode tasks
        for task in self._socket_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Close Socket Mode handlers
        for handler in self.socket_handlers:
            close_async = getattr(handler, "close_async", None)
            if callable(close_async):
                try:
                    result = close_async()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.debug("Failed to close Socket Mode handler cleanly", exc_info=True)
        
        # Cancel WebSocket receive task
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
        
        logger.info(f"SlackAdapter {self.channel_id} stopped")
    
    async def _connect_to_control_plane(self) -> None:
        """Establish WebSocket connection to Control Plane."""
        try:
            self.ws = await websockets.connect(self.control_plane_url)
            self.ws_connected = True
            
            # Send initial status message
            await self._send_status(ChannelStatusType.CONNECTED)
            
            logger.info(
                f"SlackAdapter {self.channel_id} connected to Control Plane"
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
        
        # Add channel_type to metadata
        if metadata is None:
            metadata = {}
        metadata["channel_type"] = "slack"
        
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
    
    async def _parse_slack_message(
        self, event: Dict[str, Any], *, is_app_mention: bool = False,
    ) -> InboundMessage:
        """Parse Slack message event into InboundMessage format.

        Args:
            event: Slack message event
            is_app_mention: True when the event originated from an app_mention handler

        Returns:
            InboundMessage instance
        """
        message_id = event["ts"]
        user_id = event.get("user", "unknown")
        channel_id = event["channel"]
        thread_ts = event.get("thread_ts", event["ts"])
        text = event.get("text", "")

        # Extract attachments (files)
        attachments = []
        if "files" in event:
            for file in event["files"]:
                attachments.append({
                    "type": "file",
                    "id": file.get("id"),
                    "name": file.get("name"),
                    "mimetype": file.get("mimetype"),
                    "size": file.get("size"),
                    "url_private": file.get("url_private"),
                })

        # Metadata
        metadata = {
            "channel_type": event.get("channel_type"),
            "team": event.get("team"),
            "event_ts": event.get("event_ts"),
            "bot_mention": is_app_mention,
            "source_platform": "slack",
        }
        
        # Create InboundMessage
        return MessageSerializer.create_inbound_message(
            message_id=message_id,
            channel_id=self.channel_id,
            user_id=user_id,
            chat_id=channel_id,
            text=text,
            thread_id=thread_ts if thread_ts != event["ts"] else None,
            attachments=attachments,
            metadata=metadata,
        )
    
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
    
    @staticmethod
    def _split_text_for_slack(text: str, max_len: int = SLACK_MAX_TEXT_LEN) -> list[str]:
        """Split long outbound text into Slack-safe chunks.

        Keeps markdown code fences balanced across chunks.
        """
        text = (text or "").strip()
        if not text:
            return [""]
        if len(text) <= max_len:
            return [text]
        lines = text.splitlines(keepends=True)
        parts: list[str] = []
        current = ""
        in_code_block = False

        def _flush() -> None:
            nonlocal current
            chunk = current.strip()
            if chunk:
                parts.append(chunk)
            current = ""

        for line in lines:
            is_fence = line.lstrip().startswith("```")

            if len(current) + len(line) > max_len and current:
                # Close code block before flush so each chunk renders correctly in Slack.
                if in_code_block:
                    current += "\n```\n"
                _flush()
                # Reopen for next chunk if needed.
                if in_code_block:
                    current = "```\n"

            current += line
            if is_fence:
                in_code_block = not in_code_block

        if current:
            if in_code_block:
                current += "\n```"
            _flush()

        return parts if parts else [text[:max_len]]

    async def _handle_outbound_message(self, message: OutboundMessage) -> None:
        """Handle an outbound message by sending it via Slack API.

        Retries once on failure. If both attempts fail, sends a user-visible
        error message so the failure is never silent.

        Args:
            message: OutboundMessage to send
        """
        chat_id = message.chat_id  # Slack channel ID
        text = message.text
        thread_id = message.thread_id or message.reply_to
        max_attempts = 2
        last_exc: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                parts = self._split_text_for_slack(text)
                sent_count = 0
                for part in parts:
                    await self.app.client.chat_postMessage(
                        channel=chat_id,
                        text=part,
                        thread_ts=thread_id,
                        unfurl_links=False,
                        unfurl_media=False,
                    )
                    sent_count += 1

                logger.debug(
                    "Sent outbound message %s to channel %s in %s part(s)",
                    message.message_id,
                    chat_id,
                    sent_count,
                )
                return  # success

            except (SlackApiError, Exception) as e:
                last_exc = e
                logger.warning(
                    "Attempt %s/%s failed for outbound message %s: %s",
                    attempt,
                    max_attempts,
                    message.message_id,
                    e,
                )
                if attempt < max_attempts:
                    await asyncio.sleep(1)

        # Both attempts failed — notify user and Control Plane
        logger.error(
            f"All {max_attempts} attempts failed for outbound message {message.message_id}",
            exc_info=last_exc,
        )
        await self._send_status(
            ChannelStatusType.ERROR,
            error_message=f"Failed to send message: {last_exc}",
        )
        try:
            await self.app.client.chat_postMessage(
                channel=chat_id,
                text="Sorry, I encountered an error delivering my response. Please try again.",
                thread_ts=thread_id,
                unfurl_links=False,
                unfurl_media=False,
            )
        except Exception:
            logger.error(
                "Failed to send error fallback for %s", message.message_id, exc_info=True,
            )


async def create_slack_adapter(
    channel_id: str = "slack-main",
    bot_token: Optional[str] = None,
    app_token: Optional[str] = None,
    control_plane_url: str = "ws://127.0.0.1:18789",
) -> SlackAdapter:
    """Create and start a Slack adapter.
    
    Args:
        channel_id: Unique identifier for this channel adapter
        bot_token: Slack Bot User OAuth Token (defaults to SLACK_BOT_TOKEN env var)
        app_token: Slack App-Level Token (defaults to SLACK_APP_TOKEN env var)
        control_plane_url: WebSocket URL of the Control Plane
        
    Returns:
        Started SlackAdapter instance
    """
    bot_token = bot_token or SLACK_BOT_TOKEN
    app_token = app_token or SLACK_APP_TOKEN
    
    if not bot_token:
        raise ValueError("bot_token is required (set SLACK_BOT_TOKEN env var)")
    if not app_token:
        raise ValueError("app_token is required (set SLACK_APP_TOKEN env var)")
    
    adapter = SlackAdapter(
        channel_id=channel_id,
        bot_token=bot_token,
        app_token=app_token,
        control_plane_url=control_plane_url,
    )
    
    await adapter.start()
    return adapter
