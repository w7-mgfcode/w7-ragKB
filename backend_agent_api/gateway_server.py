"""Control Plane WebSocket server for multi-channel gateway.

This module implements the central WebSocket server that manages channel adapters,
routes messages between channels and sessions, and provides metrics for monitoring.

The Control Plane runs on ws://127.0.0.1:18789 and handles:
- Channel adapter registration and health tracking
- Inbound message routing (channel → session)
- Outbound message delivery (session → channel)
- Connection lifecycle (connect, disconnect, reconnect)
- Metrics collection (messages per channel, active sessions, queue depth)

Architecture:
    - WebSocket server accepts connections from channel adapters
    - Each adapter registers with a unique channel_id
    - Messages are routed based on channel_id and session_id
    - Adapters can disconnect/reconnect without losing queued messages
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional, Set

import websockets
from websockets.server import WebSocketServerProtocol

from gateway_protocol import (
    ChannelStatus,
    ChannelStatusType,
    GatewayMessage,
    InboundMessage,
    MessageParser,
    OutboundMessage,
    SessionCommand,
)

logger = logging.getLogger(__name__)

# WebSocket server configuration
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 18789
MAX_QUEUE_SIZE = 1000  # Maximum queued messages per channel
MESSAGE_TIMEOUT = 30.0  # Seconds to wait for message delivery


@dataclass
class ChannelAdapter:
    """Represents a connected channel adapter with health tracking."""
    
    channel_id: str
    channel_type: str
    websocket: Optional[WebSocketServerProtocol] = None
    status: ChannelStatusType = ChannelStatusType.DISCONNECTED
    connected_at: Optional[float] = None
    last_heartbeat: Optional[float] = None
    message_queue: Deque[OutboundMessage] = field(default_factory=deque)
    messages_sent: int = 0
    messages_received: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    
    @property
    def is_connected(self) -> bool:
        """Check if adapter is currently connected."""
        return self.websocket is not None and self.status == ChannelStatusType.CONNECTED
    
    @property
    def queue_depth(self) -> int:
        """Get current message queue depth."""
        return len(self.message_queue)
    
    def mark_connected(self, websocket: WebSocketServerProtocol) -> None:
        """Mark adapter as connected."""
        self.websocket = websocket
        self.status = ChannelStatusType.CONNECTED
        self.connected_at = time.time()
        self.last_heartbeat = time.time()
        logger.info(f"Channel {self.channel_id} connected")
    
    def mark_disconnected(self, error: Optional[str] = None) -> None:
        """Mark adapter as disconnected."""
        self.websocket = None
        self.status = ChannelStatusType.DISCONNECTED
        if error:
            self.last_error = error
            self.error_count += 1
        logger.info(f"Channel {self.channel_id} disconnected" + (f": {error}" if error else ""))
    
    def mark_error(self, error: str) -> None:
        """Mark adapter as in error state."""
        self.status = ChannelStatusType.ERROR
        self.last_error = error
        self.error_count += 1
        logger.error(f"Channel {self.channel_id} error: {error}")


class ControlPlane:
    """Central control plane for managing channel adapters and message routing."""
    
    def __init__(self):
        """Initialize the control plane."""
        self.adapters: Dict[str, ChannelAdapter] = {}
        self.active_sessions: Set[str] = set()
        self.message_handlers: Dict[str, asyncio.Queue] = {}  # session_id -> queue
        self.metrics = {
            "total_messages_routed": 0,
            "total_messages_delivered": 0,
            "total_connections": 0,
            "total_disconnections": 0,
            "total_errors": 0,
        }
        self._running = False
        self._server: Optional[websockets.WebSocketServer] = None
    
    async def start(self) -> None:
        """Start the WebSocket server."""
        if self._running:
            logger.warning("Control Plane already running")
            return
        
        self._running = True
        logger.info(f"Starting Control Plane WebSocket server on ws://{GATEWAY_HOST}:{GATEWAY_PORT}")
        
        self._server = await websockets.serve(
            self._handle_connection,
            GATEWAY_HOST,
            GATEWAY_PORT,
            ping_interval=20,
            ping_timeout=10,
        )
        
        logger.info("Control Plane WebSocket server started")
    
    async def stop(self) -> None:
        """Stop the WebSocket server."""
        if not self._running:
            return
        
        self._running = False
        logger.info("Stopping Control Plane WebSocket server")
        
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        
        # Disconnect all adapters
        for adapter in self.adapters.values():
            if adapter.websocket:
                await adapter.websocket.close()
        
        logger.info("Control Plane WebSocket server stopped")
    
    def register_adapter(
        self,
        channel_id: str,
        channel_type: str,
        websocket: WebSocketServerProtocol,
    ) -> ChannelAdapter:
        """Register a channel adapter with the control plane.
        
        Args:
            channel_id: Unique channel identifier
            channel_type: Type of channel (slack, telegram, discord, whatsapp)
            websocket: WebSocket connection
            
        Returns:
            Registered ChannelAdapter instance
        """
        if channel_id in self.adapters:
            # Existing adapter reconnecting
            adapter = self.adapters[channel_id]
            adapter.mark_connected(websocket)
            logger.info(f"Channel {channel_id} reconnected (queue depth: {adapter.queue_depth})")
        else:
            # New adapter
            adapter = ChannelAdapter(channel_id=channel_id, channel_type=channel_type)
            adapter.mark_connected(websocket)
            self.adapters[channel_id] = adapter
            self.metrics["total_connections"] += 1
            logger.info(f"Channel {channel_id} registered (type: {channel_type})")
        
        return adapter
    
    def unregister_adapter(self, channel_id: str, error: Optional[str] = None) -> None:
        """Unregister a channel adapter.
        
        Args:
            channel_id: Channel identifier
            error: Optional error message
        """
        if channel_id in self.adapters:
            adapter = self.adapters[channel_id]
            adapter.mark_disconnected(error)
            self.metrics["total_disconnections"] += 1
            
            if error:
                self.metrics["total_errors"] += 1
    
    async def route_inbound_message(self, message: InboundMessage) -> None:
        """Route an inbound message to the appropriate session handler.
        
        Args:
            message: Inbound message from channel adapter
        """
        # Update adapter metrics
        if message.channel_id in self.adapters:
            self.adapters[message.channel_id].messages_received += 1
        
        self.metrics["total_messages_routed"] += 1
        
        # Generate session_id from routing components
        from db_sessions import generate_session_id
        
        session_id = generate_session_id(
            message.channel_id,
            message.user_id,
            message.chat_id,
            message.thread_id,
        )
        
        # Track active session
        self.active_sessions.add(session_id)
        
        # Process message through gateway message handler
        # Import here to avoid circular dependency
        from gateway_message_handler import process_inbound_message
        
        # Process message asynchronously (don't block routing)
        task = asyncio.create_task(process_inbound_message(message))
        task.add_done_callback(
            lambda t: logger.error(
                "Unhandled exception in process_inbound_message: %s",
                t.exception(),
                exc_info=t.exception(),
            )
            if not t.cancelled() and t.exception()
            else None
        )

        logger.debug(f"Routed message {message.message_id} to session {session_id}")
    
    async def deliver_outbound_message(self, message: OutboundMessage) -> bool:
        """Deliver an outbound message to the appropriate channel adapter.
        
        Args:
            message: Outbound message to deliver
            
        Returns:
            True if delivered successfully, False otherwise
        """
        adapter = self.adapters.get(message.channel_id)
        
        if not adapter:
            logger.error(f"Channel {message.channel_id} not found, cannot deliver message")
            return False
        
        if adapter.is_connected:
            # Deliver immediately
            try:
                await self._send_message(adapter.websocket, message)
                adapter.messages_sent += 1
                self.metrics["total_messages_delivered"] += 1
                logger.debug(f"Delivered message {message.message_id} to channel {message.channel_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to deliver message to {message.channel_id}: {e}")
                adapter.mark_error(str(e))
                # Fall through to queue
        
        # Queue for later delivery
        if adapter.queue_depth >= MAX_QUEUE_SIZE:
            logger.error(
                f"Message queue full for channel {message.channel_id} "
                f"(depth: {adapter.queue_depth}), dropping message"
            )
            return False
        
        adapter.message_queue.append(message)
        logger.info(
            f"Queued message {message.message_id} for channel {message.channel_id} "
            f"(queue depth: {adapter.queue_depth})"
        )
        return True
    
    async def _send_message(
        self,
        websocket: WebSocketServerProtocol,
        message: GatewayMessage,
    ) -> None:
        """Send a message over WebSocket.
        
        Args:
            websocket: WebSocket connection
            message: Message to send
        """
        data = MessageParser.serialize(message)
        await websocket.send(data)
    
    async def _flush_message_queue(self, adapter: ChannelAdapter) -> None:
        """Flush queued messages to a reconnected adapter.
        
        Args:
            adapter: Channel adapter with queued messages
        """
        if not adapter.is_connected or not adapter.message_queue:
            return
        
        logger.info(f"Flushing {adapter.queue_depth} queued messages for channel {adapter.channel_id}")
        
        while adapter.message_queue and adapter.is_connected:
            message = adapter.message_queue.popleft()
            try:
                await self._send_message(adapter.websocket, message)
                adapter.messages_sent += 1
                self.metrics["total_messages_delivered"] += 1
            except Exception as e:
                logger.error(f"Failed to flush message to {adapter.channel_id}: {e}")
                # Put message back at front of queue
                adapter.message_queue.appendleft(message)
                adapter.mark_error(str(e))
                break
    
    async def _handle_connection(self, websocket: WebSocketServerProtocol) -> None:
        """Handle a WebSocket connection from a channel adapter.
        
        Args:
            websocket: WebSocket connection
        """
        channel_id: Optional[str] = None
        adapter: Optional[ChannelAdapter] = None
        
        try:
            # Wait for initial registration message (ChannelStatus with connected status)
            data = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            message = MessageParser.parse(data)
            
            if not isinstance(message, ChannelStatus):
                logger.error(f"Expected ChannelStatus for registration, got {type(message)}")
                await websocket.close(1008, "Expected ChannelStatus for registration")
                return
            
            if message.status != ChannelStatusType.CONNECTED:
                logger.error(f"Expected status=connected, got {message.status}")
                await websocket.close(1008, "Expected status=connected")
                return
            
            # Extract channel type from metadata
            channel_type = message.metadata.get("channel_type", "unknown")
            
            # Register the adapter
            channel_id = message.channel_id
            adapter = self.register_adapter(channel_id, channel_type, websocket)
            
            # Flush any queued messages
            await self._flush_message_queue(adapter)
            
            # Handle messages from this adapter
            async for data in websocket:
                try:
                    message = MessageParser.parse(data)
                    
                    if isinstance(message, InboundMessage):
                        await self.route_inbound_message(message)
                    
                    elif isinstance(message, ChannelStatus):
                        # Update adapter status
                        adapter.status = message.status
                        adapter.last_heartbeat = time.time()
                        
                        if message.status == ChannelStatusType.ERROR:
                            adapter.mark_error(message.error_message or "Unknown error")
                    
                    elif isinstance(message, SessionCommand):
                        # Handle session commands (future implementation)
                        logger.info(f"Received session command: {message.command}")
                    
                    else:
                        logger.warning(f"Unexpected message type from {channel_id}: {type(message)}")
                
                except Exception as e:
                    logger.error(f"Error processing message from {channel_id}: {e}", exc_info=True)
                    if adapter:
                        adapter.mark_error(str(e))
        
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for channel registration")
        
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"WebSocket connection closed: {e}")
        
        except Exception as e:
            logger.error(f"Error handling WebSocket connection: {e}", exc_info=True)
        
        finally:
            # Unregister adapter on disconnect
            if channel_id:
                self.unregister_adapter(channel_id)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current control plane metrics.
        
        Returns:
            Dictionary containing metrics
        """
        return {
            **self.metrics,
            "active_channels": len([a for a in self.adapters.values() if a.is_connected]),
            "total_channels": len(self.adapters),
            "active_sessions": len(self.active_sessions),
            "messages_per_channel": {
                channel_id: {
                    "sent": adapter.messages_sent,
                    "received": adapter.messages_received,
                    "queue_depth": adapter.queue_depth,
                    "error_count": adapter.error_count,
                }
                for channel_id, adapter in self.adapters.items()
            },
        }
    
    def get_channel_status(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Get status for a specific channel.
        
        Args:
            channel_id: Channel identifier
            
        Returns:
            Dictionary containing channel status, or None if not found
        """
        adapter = self.adapters.get(channel_id)
        if not adapter:
            return None
        
        return {
            "channel_id": adapter.channel_id,
            "channel_type": adapter.channel_type,
            "status": adapter.status.value,
            "is_connected": adapter.is_connected,
            "connected_at": adapter.connected_at,
            "last_heartbeat": adapter.last_heartbeat,
            "messages_sent": adapter.messages_sent,
            "messages_received": adapter.messages_received,
            "queue_depth": adapter.queue_depth,
            "error_count": adapter.error_count,
            "last_error": adapter.last_error,
        }
    
    def list_channels(self) -> list[Dict[str, Any]]:
        """List all registered channels.
        
        Returns:
            List of channel status dictionaries
        """
        return [
            self.get_channel_status(channel_id)
            for channel_id in self.adapters.keys()
        ]


# Global control plane instance
_control_plane: Optional[ControlPlane] = None


async def start_control_plane() -> ControlPlane:
    """Start the control plane WebSocket server.
    
    Returns:
        ControlPlane instance
    """
    global _control_plane
    
    if _control_plane is None:
        _control_plane = ControlPlane()
    
    await _control_plane.start()
    return _control_plane


async def stop_control_plane() -> None:
    """Stop the control plane WebSocket server."""
    global _control_plane
    
    if _control_plane:
        await _control_plane.stop()


def get_control_plane() -> Optional[ControlPlane]:
    """Get the global control plane instance.
    
    Returns:
        ControlPlane instance, or None if not started
    """
    return _control_plane
