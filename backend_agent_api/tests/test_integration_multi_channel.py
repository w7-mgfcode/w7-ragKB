"""Integration tests for multi-channel routing.

Feature: openclaw-integration (Task 7.1)
Tests: Slack+Telegram routing through Control Plane,
response delivery to correct channel, concurrent messages,
session creation, cross-channel isolation.
"""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gateway_protocol import (
    ChannelStatusType,
    InboundMessage,
    MessageSerializer,
    OutboundMessage,
)
from gateway_server import (
    ChannelAdapter,
    ControlPlane,
    MAX_QUEUE_SIZE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_websocket():
    """Create a mock WebSocket object."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    ws.close = AsyncMock()
    return ws


def register_channel(cp, channel_id, channel_type, ws=None):
    """Register a channel adapter with the control plane."""
    ws = ws or make_mock_websocket()
    return cp.register_adapter(channel_id, channel_type, ws), ws


def inject_fake_handler():
    """Inject a fake gateway_message_handler into sys.modules.

    Returns the fake handler and a cleanup function.
    """
    fake_handler = MagicMock()
    fake_handler.process_inbound_message = AsyncMock()
    sys.modules["gateway_message_handler"] = fake_handler
    return fake_handler, lambda: sys.modules.pop("gateway_message_handler", None)


# ===========================================================================
# Multi-channel registration
# ===========================================================================


class TestMultiChannelRegistration:
    """Integration: Multiple channels can be registered simultaneously."""

    def test_register_multiple_channels(self):
        """Register Slack, Telegram, Discord adapters."""
        cp = ControlPlane()
        register_channel(cp, "slack-main", "slack")
        register_channel(cp, "telegram-bot1", "telegram")
        register_channel(cp, "discord-main", "discord")

        assert len(cp.adapters) == 3
        assert cp.adapters["slack-main"].channel_type == "slack"
        assert cp.adapters["telegram-bot1"].channel_type == "telegram"
        assert cp.adapters["discord-main"].channel_type == "discord"

    def test_all_channels_connected(self):
        """All registered channels should have status=CONNECTED."""
        cp = ControlPlane()
        register_channel(cp, "slack-main", "slack")
        register_channel(cp, "telegram-bot1", "telegram")

        for adapter in cp.adapters.values():
            assert adapter.is_connected is True
            assert adapter.status == ChannelStatusType.CONNECTED


# ===========================================================================
# Inbound message routing
# ===========================================================================


class TestInboundMessageRouting:
    """Integration: Inbound messages are routed to correct sessions."""

    @pytest.mark.asyncio
    async def test_telegram_message_routed(self):
        """Telegram inbound message should be routed and tracked."""
        cp = ControlPlane()
        register_channel(cp, "telegram-bot1", "telegram")

        msg = MessageSerializer.create_inbound_message(
            message_id="tg1",
            channel_id="telegram-bot1",
            user_id="user100",
            chat_id="chat200",
            text="hello from telegram",
        )

        fake_handler, cleanup = inject_fake_handler()
        try:
            await cp.route_inbound_message(msg)
        finally:
            cleanup()

        assert cp.metrics["total_messages_routed"] == 1
        assert cp.adapters["telegram-bot1"].messages_received == 1
        assert len(cp.active_sessions) == 1

    @pytest.mark.asyncio
    async def test_slack_message_routed(self):
        """Slack inbound message should be routed and tracked."""
        cp = ControlPlane()
        register_channel(cp, "slack-main", "slack")

        msg = MessageSerializer.create_inbound_message(
            message_id="sl1",
            channel_id="slack-main",
            user_id="U123",
            chat_id="C456",
            text="hello from slack",
        )

        fake_handler, cleanup = inject_fake_handler()
        try:
            await cp.route_inbound_message(msg)
        finally:
            cleanup()

        assert cp.metrics["total_messages_routed"] == 1
        assert cp.adapters["slack-main"].messages_received == 1

    @pytest.mark.asyncio
    async def test_different_channels_create_different_sessions(self):
        """Messages from different channels should create separate sessions."""
        cp = ControlPlane()
        register_channel(cp, "telegram-bot1", "telegram")
        register_channel(cp, "slack-main", "slack")

        msg_tg = MessageSerializer.create_inbound_message(
            message_id="tg1",
            channel_id="telegram-bot1",
            user_id="user100",
            chat_id="chat200",
            text="telegram msg",
        )
        msg_sl = MessageSerializer.create_inbound_message(
            message_id="sl1",
            channel_id="slack-main",
            user_id="user100",
            chat_id="chat200",
            text="slack msg",
        )

        fake_handler, cleanup = inject_fake_handler()
        try:
            await cp.route_inbound_message(msg_tg)
            await cp.route_inbound_message(msg_sl)
        finally:
            cleanup()

        # Same user+chat but different channel → different sessions
        assert len(cp.active_sessions) == 2


# ===========================================================================
# Outbound message delivery
# ===========================================================================


class TestOutboundDelivery:
    """Integration: Outbound messages are delivered to correct channel."""

    @pytest.mark.asyncio
    async def test_deliver_to_correct_channel(self):
        """Outbound to channel X should only be sent via channel X's websocket."""
        cp = ControlPlane()
        _, ws_tg = register_channel(cp, "telegram-bot1", "telegram")
        _, ws_sl = register_channel(cp, "slack-main", "slack")

        outbound = MessageSerializer.create_outbound_message(
            message_id="out1",
            channel_id="telegram-bot1",
            chat_id="chat200",
            text="response for telegram",
        )

        result = await cp.deliver_outbound_message(outbound)

        assert result is True
        ws_tg.send.assert_called_once()
        ws_sl.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_deliver_to_unknown_channel_fails(self):
        """Outbound to unknown channel should return False."""
        cp = ControlPlane()

        outbound = MessageSerializer.create_outbound_message(
            message_id="out1",
            channel_id="nonexistent",
            chat_id="chat200",
            text="lost message",
        )

        result = await cp.deliver_outbound_message(outbound)
        assert result is False

    @pytest.mark.asyncio
    async def test_deliver_queued_when_disconnected(self):
        """Outbound to disconnected channel should be queued."""
        cp = ControlPlane()
        adapter, ws = register_channel(cp, "telegram-bot1", "telegram")
        cp.unregister_adapter("telegram-bot1")  # Disconnect

        outbound = MessageSerializer.create_outbound_message(
            message_id="out1",
            channel_id="telegram-bot1",
            chat_id="chat200",
            text="queued message",
        )

        result = await cp.deliver_outbound_message(outbound)

        assert result is True
        assert cp.adapters["telegram-bot1"].queue_depth == 1

    @pytest.mark.asyncio
    async def test_queue_full_drops_message(self):
        """When queue is full, message should be dropped."""
        cp = ControlPlane()
        adapter, ws = register_channel(cp, "telegram-bot1", "telegram")
        cp.unregister_adapter("telegram-bot1")

        # Fill the queue
        for i in range(MAX_QUEUE_SIZE):
            outbound = MessageSerializer.create_outbound_message(
                message_id=f"out{i}",
                channel_id="telegram-bot1",
                chat_id="chat200",
                text=f"msg {i}",
            )
            await cp.deliver_outbound_message(outbound)

        # Next message should be dropped
        outbound = MessageSerializer.create_outbound_message(
            message_id="overflow",
            channel_id="telegram-bot1",
            chat_id="chat200",
            text="this should be dropped",
        )
        result = await cp.deliver_outbound_message(outbound)

        assert result is False
        assert cp.adapters["telegram-bot1"].queue_depth == MAX_QUEUE_SIZE


# ===========================================================================
# Concurrent message handling
# ===========================================================================


class TestConcurrentMessages:
    """Integration: Concurrent messages from multiple channels."""

    @pytest.mark.asyncio
    async def test_concurrent_inbound_from_multiple_channels(self):
        """Concurrent messages from Telegram and Slack should all be routed."""
        cp = ControlPlane()
        register_channel(cp, "telegram-bot1", "telegram")
        register_channel(cp, "slack-main", "slack")
        register_channel(cp, "discord-main", "discord")

        messages = [
            MessageSerializer.create_inbound_message(
                message_id=f"msg{i}",
                channel_id=channel_id,
                user_id=f"user{i}",
                chat_id=f"chat{i}",
                text=f"hello from {channel_id}",
            )
            for i, channel_id in enumerate(
                ["telegram-bot1", "slack-main", "discord-main"]
            )
        ]

        fake_handler, cleanup = inject_fake_handler()
        try:
            # Route all concurrently
            await asyncio.gather(
                *[cp.route_inbound_message(m) for m in messages]
            )
        finally:
            cleanup()

        assert cp.metrics["total_messages_routed"] == 3
        assert len(cp.active_sessions) == 3

    @pytest.mark.asyncio
    async def test_concurrent_outbound_to_multiple_channels(self):
        """Concurrent outbound messages should be delivered to correct channels."""
        cp = ControlPlane()
        _, ws_tg = register_channel(cp, "telegram-bot1", "telegram")
        _, ws_sl = register_channel(cp, "slack-main", "slack")
        _, ws_dc = register_channel(cp, "discord-main", "discord")

        outbounds = [
            MessageSerializer.create_outbound_message(
                message_id=f"out{i}",
                channel_id=channel_id,
                chat_id=f"chat{i}",
                text=f"response to {channel_id}",
            )
            for i, channel_id in enumerate(
                ["telegram-bot1", "slack-main", "discord-main"]
            )
        ]

        results = await asyncio.gather(
            *[cp.deliver_outbound_message(m) for m in outbounds]
        )

        assert all(results)
        ws_tg.send.assert_called_once()
        ws_sl.send.assert_called_once()
        ws_dc.send.assert_called_once()


# ===========================================================================
# Channel fault isolation
# ===========================================================================


class TestChannelFaultIsolation:
    """Integration: Channel failure doesn't affect other channels."""

    @pytest.mark.asyncio
    async def test_failed_channel_doesnt_block_others(self):
        """If Telegram fails, Slack should still receive messages."""
        cp = ControlPlane()
        _, ws_tg = register_channel(cp, "telegram-bot1", "telegram")
        _, ws_sl = register_channel(cp, "slack-main", "slack")

        # Disconnect Telegram
        cp.unregister_adapter("telegram-bot1", error="connection lost")

        # Deliver to Slack - should succeed
        outbound_sl = MessageSerializer.create_outbound_message(
            message_id="out_sl",
            channel_id="slack-main",
            chat_id="chat_sl",
            text="slack ok",
        )
        result = await cp.deliver_outbound_message(outbound_sl)

        assert result is True
        ws_sl.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_channel_metrics_independent(self):
        """Error metrics for one channel don't affect others."""
        cp = ControlPlane()
        register_channel(cp, "telegram-bot1", "telegram")
        register_channel(cp, "slack-main", "slack")

        cp.unregister_adapter("telegram-bot1", error="crash")

        assert cp.adapters["telegram-bot1"].error_count == 1
        assert cp.adapters["slack-main"].error_count == 0


# ===========================================================================
# Reconnection and queue flushing
# ===========================================================================


class TestReconnectionAndQueueFlush:
    """Integration: Reconnection triggers queue flushing."""

    @pytest.mark.asyncio
    async def test_reconnect_flushes_queue(self):
        """Reconnecting a channel should flush queued messages."""
        cp = ControlPlane()
        adapter, ws1 = register_channel(cp, "telegram-bot1", "telegram")

        # Disconnect and queue messages
        cp.unregister_adapter("telegram-bot1")

        for i in range(3):
            outbound = MessageSerializer.create_outbound_message(
                message_id=f"q{i}",
                channel_id="telegram-bot1",
                chat_id="chat200",
                text=f"queued {i}",
            )
            await cp.deliver_outbound_message(outbound)

        assert cp.adapters["telegram-bot1"].queue_depth == 3

        # Reconnect with new websocket
        ws2 = make_mock_websocket()
        cp.register_adapter("telegram-bot1", "telegram", ws2)

        # Flush queue
        await cp._flush_message_queue(cp.adapters["telegram-bot1"])

        assert cp.adapters["telegram-bot1"].queue_depth == 0
        assert ws2.send.call_count == 3


# ===========================================================================
# Metrics
# ===========================================================================


class TestMultiChannelMetrics:
    """Integration: Metrics reflect multi-channel activity."""

    @pytest.mark.asyncio
    async def test_metrics_per_channel(self):
        """Metrics should track per-channel message counts."""
        cp = ControlPlane()
        register_channel(cp, "telegram-bot1", "telegram")
        register_channel(cp, "slack-main", "slack")

        # Route messages
        fake_handler, cleanup = inject_fake_handler()
        try:
            for i in range(3):
                msg = MessageSerializer.create_inbound_message(
                    message_id=f"tg{i}",
                    channel_id="telegram-bot1",
                    user_id=f"u{i}",
                    chat_id=f"c{i}",
                    text=f"msg {i}",
                )
                await cp.route_inbound_message(msg)

            msg_sl = MessageSerializer.create_inbound_message(
                message_id="sl1",
                channel_id="slack-main",
                user_id="u1",
                chat_id="c1",
                text="slack msg",
            )
            await cp.route_inbound_message(msg_sl)
        finally:
            cleanup()

        metrics = cp.get_metrics()
        assert metrics["total_messages_routed"] == 4
        assert metrics["messages_per_channel"]["telegram-bot1"]["received"] == 3
        assert metrics["messages_per_channel"]["slack-main"]["received"] == 1

    def test_channel_status(self):
        """get_channel_status should return full status info."""
        cp = ControlPlane()
        register_channel(cp, "telegram-bot1", "telegram")

        status = cp.get_channel_status("telegram-bot1")

        assert status is not None
        assert status["channel_id"] == "telegram-bot1"
        assert status["channel_type"] == "telegram"
        assert status["is_connected"] is True
        assert status["messages_sent"] == 0
        assert status["messages_received"] == 0

    def test_list_channels(self):
        """list_channels should return all registered channels."""
        cp = ControlPlane()
        register_channel(cp, "telegram-bot1", "telegram")
        register_channel(cp, "slack-main", "slack")

        channels = cp.list_channels()
        assert len(channels) == 2
        channel_ids = {c["channel_id"] for c in channels}
        assert channel_ids == {"telegram-bot1", "slack-main"}
