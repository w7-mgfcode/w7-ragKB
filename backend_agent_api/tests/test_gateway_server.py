"""Unit tests for Control Plane WebSocket server."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway_protocol import (
    ChannelStatus,
    ChannelStatusType,
    InboundMessage,
    MessageSerializer,
    OutboundMessage,
)
from gateway_server import ChannelAdapter, ControlPlane


class TestChannelAdapter:
    """Test ChannelAdapter class."""
    
    def test_adapter_initialization(self):
        """Test adapter is initialized with correct defaults."""
        adapter = ChannelAdapter(channel_id="test-channel", channel_type="telegram")
        
        assert adapter.channel_id == "test-channel"
        assert adapter.channel_type == "telegram"
        assert adapter.status == ChannelStatusType.DISCONNECTED
        assert adapter.websocket is None
        assert adapter.messages_sent == 0
        assert adapter.messages_received == 0
        assert adapter.error_count == 0
        assert adapter.queue_depth == 0
        assert not adapter.is_connected
    
    def test_adapter_mark_connected(self):
        """Test marking adapter as connected."""
        adapter = ChannelAdapter(channel_id="test-channel", channel_type="telegram")
        mock_websocket = MagicMock()
        
        adapter.mark_connected(mock_websocket)
        
        assert adapter.is_connected
        assert adapter.status == ChannelStatusType.CONNECTED
        assert adapter.websocket == mock_websocket
        assert adapter.connected_at is not None
        assert adapter.last_heartbeat is not None
    
    def test_adapter_mark_disconnected(self):
        """Test marking adapter as disconnected."""
        adapter = ChannelAdapter(channel_id="test-channel", channel_type="telegram")
        mock_websocket = MagicMock()
        adapter.mark_connected(mock_websocket)
        
        adapter.mark_disconnected(error="Connection lost")
        
        assert not adapter.is_connected
        assert adapter.status == ChannelStatusType.DISCONNECTED
        assert adapter.websocket is None
        assert adapter.last_error == "Connection lost"
        assert adapter.error_count == 1
    
    def test_adapter_mark_error(self):
        """Test marking adapter as in error state."""
        adapter = ChannelAdapter(channel_id="test-channel", channel_type="telegram")
        
        adapter.mark_error("Test error")
        
        assert adapter.status == ChannelStatusType.ERROR
        assert adapter.last_error == "Test error"
        assert adapter.error_count == 1
    
    def test_adapter_queue_depth(self):
        """Test queue depth tracking."""
        adapter = ChannelAdapter(channel_id="test-channel", channel_type="telegram")
        
        message = MessageSerializer.create_outbound_message(
            message_id="msg1",
            channel_id="test-channel",
            chat_id="chat1",
            text="Test message",
        )
        
        adapter.message_queue.append(message)
        assert adapter.queue_depth == 1
        
        adapter.message_queue.append(message)
        assert adapter.queue_depth == 2


class TestControlPlane:
    """Test ControlPlane class."""
    
    @pytest.fixture
    def control_plane(self):
        """Create a ControlPlane instance for testing."""
        return ControlPlane()
    
    def test_control_plane_initialization(self, control_plane):
        """Test control plane is initialized correctly."""
        assert len(control_plane.adapters) == 0
        assert len(control_plane.active_sessions) == 0
        assert control_plane.metrics["total_messages_routed"] == 0
        assert control_plane.metrics["total_messages_delivered"] == 0
        assert not control_plane._running
    
    def test_register_adapter(self, control_plane):
        """Test registering a new channel adapter."""
        mock_websocket = MagicMock()
        
        adapter = control_plane.register_adapter(
            channel_id="test-channel",
            channel_type="telegram",
            websocket=mock_websocket,
        )
        
        assert adapter.channel_id == "test-channel"
        assert adapter.channel_type == "telegram"
        assert adapter.is_connected
        assert "test-channel" in control_plane.adapters
        assert control_plane.metrics["total_connections"] == 1
    
    def test_register_adapter_reconnect(self, control_plane):
        """Test reconnecting an existing adapter."""
        mock_websocket1 = MagicMock()
        mock_websocket2 = MagicMock()
        
        # First connection
        adapter1 = control_plane.register_adapter(
            channel_id="test-channel",
            channel_type="telegram",
            websocket=mock_websocket1,
        )
        
        # Disconnect
        control_plane.unregister_adapter("test-channel")
        
        # Reconnect
        adapter2 = control_plane.register_adapter(
            channel_id="test-channel",
            channel_type="telegram",
            websocket=mock_websocket2,
        )
        
        # Should be the same adapter instance
        assert adapter1 is adapter2
        assert adapter2.is_connected
        assert adapter2.websocket == mock_websocket2
        assert control_plane.metrics["total_connections"] == 1  # Not incremented on reconnect
    
    def test_unregister_adapter(self, control_plane):
        """Test unregistering a channel adapter."""
        mock_websocket = MagicMock()
        
        control_plane.register_adapter(
            channel_id="test-channel",
            channel_type="telegram",
            websocket=mock_websocket,
        )
        
        control_plane.unregister_adapter("test-channel", error="Test error")
        
        adapter = control_plane.adapters["test-channel"]
        assert not adapter.is_connected
        assert adapter.last_error == "Test error"
        assert control_plane.metrics["total_disconnections"] == 1
        assert control_plane.metrics["total_errors"] == 1
    
    @pytest.mark.asyncio
    async def test_route_inbound_message(self, control_plane):
        """Test routing an inbound message."""
        mock_websocket = MagicMock()
        control_plane.register_adapter(
            channel_id="test-channel",
            channel_type="telegram",
            websocket=mock_websocket,
        )
        
        message = MessageSerializer.create_inbound_message(
            message_id="msg1",
            channel_id="test-channel",
            user_id="user1",
            chat_id="chat1",
            text="Test message",
        )
        
        await control_plane.route_inbound_message(message)
        
        adapter = control_plane.adapters["test-channel"]
        assert adapter.messages_received == 1
        assert control_plane.metrics["total_messages_routed"] == 1
        assert "test-channel:user1:chat1" in control_plane.active_sessions
    
    @pytest.mark.asyncio
    async def test_deliver_outbound_message_connected(self, control_plane):
        """Test delivering an outbound message to a connected adapter."""
        mock_websocket = AsyncMock()
        control_plane.register_adapter(
            channel_id="test-channel",
            channel_type="telegram",
            websocket=mock_websocket,
        )
        
        message = MessageSerializer.create_outbound_message(
            message_id="msg1",
            channel_id="test-channel",
            chat_id="chat1",
            text="Test response",
        )
        
        result = await control_plane.deliver_outbound_message(message)
        
        assert result is True
        adapter = control_plane.adapters["test-channel"]
        assert adapter.messages_sent == 1
        assert control_plane.metrics["total_messages_delivered"] == 1
        mock_websocket.send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_deliver_outbound_message_disconnected(self, control_plane):
        """Test delivering an outbound message to a disconnected adapter."""
        mock_websocket = MagicMock()
        control_plane.register_adapter(
            channel_id="test-channel",
            channel_type="telegram",
            websocket=mock_websocket,
        )
        control_plane.unregister_adapter("test-channel")
        
        message = MessageSerializer.create_outbound_message(
            message_id="msg1",
            channel_id="test-channel",
            chat_id="chat1",
            text="Test response",
        )
        
        result = await control_plane.deliver_outbound_message(message)
        
        assert result is True  # Queued successfully
        adapter = control_plane.adapters["test-channel"]
        assert adapter.queue_depth == 1
        assert adapter.messages_sent == 0  # Not sent yet
    
    @pytest.mark.asyncio
    async def test_deliver_outbound_message_channel_not_found(self, control_plane):
        """Test delivering a message to a non-existent channel."""
        message = MessageSerializer.create_outbound_message(
            message_id="msg1",
            channel_id="nonexistent-channel",
            chat_id="chat1",
            text="Test response",
        )
        
        result = await control_plane.deliver_outbound_message(message)
        
        assert result is False
    
    def test_get_metrics(self, control_plane):
        """Test getting control plane metrics."""
        mock_websocket = MagicMock()
        control_plane.register_adapter(
            channel_id="test-channel",
            channel_type="telegram",
            websocket=mock_websocket,
        )
        
        metrics = control_plane.get_metrics()
        
        assert metrics["active_channels"] == 1
        assert metrics["total_channels"] == 1
        assert metrics["active_sessions"] == 0
        assert metrics["total_messages_routed"] == 0
        assert metrics["total_messages_delivered"] == 0
        assert "messages_per_channel" in metrics
        assert "test-channel" in metrics["messages_per_channel"]
    
    def test_get_channel_status(self, control_plane):
        """Test getting status for a specific channel."""
        mock_websocket = MagicMock()
        control_plane.register_adapter(
            channel_id="test-channel",
            channel_type="telegram",
            websocket=mock_websocket,
        )
        
        status = control_plane.get_channel_status("test-channel")
        
        assert status is not None
        assert status["channel_id"] == "test-channel"
        assert status["channel_type"] == "telegram"
        assert status["status"] == "connected"
        assert status["is_connected"] is True
        assert status["messages_sent"] == 0
        assert status["messages_received"] == 0
        assert status["queue_depth"] == 0
    
    def test_get_channel_status_not_found(self, control_plane):
        """Test getting status for a non-existent channel."""
        status = control_plane.get_channel_status("nonexistent-channel")
        assert status is None
    
    def test_list_channels(self, control_plane):
        """Test listing all channels."""
        mock_websocket1 = MagicMock()
        mock_websocket2 = MagicMock()
        
        control_plane.register_adapter(
            channel_id="channel1",
            channel_type="telegram",
            websocket=mock_websocket1,
        )
        control_plane.register_adapter(
            channel_id="channel2",
            channel_type="discord",
            websocket=mock_websocket2,
        )
        
        channels = control_plane.list_channels()
        
        assert len(channels) == 2
        channel_ids = [ch["channel_id"] for ch in channels]
        assert "channel1" in channel_ids
        assert "channel2" in channel_ids
