"""Property-based tests for the Control Plane (gateway_server.py).

Feature: openclaw-integration
Properties tested: 3, 4, 5

Tests adapter registration, fault isolation, and concurrent message handling.
"""

import asyncio
import string
from collections import deque
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from hypothesis import HealthCheck, given, settings, strategies as st

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gateway_protocol import (
    ChannelStatusType,
    InboundMessage,
    MessageSerializer,
    OutboundMessage,
)
from gateway_server import ChannelAdapter, ControlPlane, MAX_QUEUE_SIZE


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

channel_id_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + "-_",
    min_size=1,
    max_size=30,
)
channel_type_strategy = st.sampled_from(["slack", "telegram", "discord", "whatsapp"])
safe_text = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())
id_text = st.text(
    alphabet=string.ascii_letters + string.digits + "-_",
    min_size=1,
    max_size=30,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def control_plane():
    """Create a fresh ControlPlane instance."""
    return ControlPlane()


def make_mock_websocket():
    """Create a mock WebSocket with async send."""
    ws = MagicMock()
    ws.send = AsyncMock()
    return ws


# ===========================================================================
# Property 3: Channel adapter registration
# ===========================================================================


class TestChannelAdapterRegistration:
    """Property 3: Registering a channel results in 'connected' status."""

    @given(channel_id=channel_id_strategy, channel_type=channel_type_strategy)
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_register_adapter_sets_connected(self, channel_id, channel_type):
        """
        Feature: openclaw-integration, Property 3: Channel adapter registration

        Registering a channel adapter must result in status CONNECTED.
        """
        cp = ControlPlane()
        ws = make_mock_websocket()
        adapter = cp.register_adapter(channel_id, channel_type, ws)

        assert adapter.status == ChannelStatusType.CONNECTED
        assert adapter.is_connected
        assert adapter.channel_id == channel_id
        assert adapter.channel_type == channel_type
        assert adapter.websocket is ws

    @given(channel_id=channel_id_strategy, channel_type=channel_type_strategy)
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_register_adapter_appears_in_list(self, channel_id, channel_type):
        """
        Feature: openclaw-integration, Property 3: Channel adapter registration

        Registered channel must appear in the active channels list.
        """
        cp = ControlPlane()
        ws = make_mock_websocket()
        cp.register_adapter(channel_id, channel_type, ws)

        channels = cp.list_channels()
        channel_ids = [ch["channel_id"] for ch in channels]
        assert channel_id in channel_ids

    @given(channel_id=channel_id_strategy, channel_type=channel_type_strategy)
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_register_idempotent_reconnect(self, channel_id, channel_type):
        """
        Feature: openclaw-integration, Property 3: Channel adapter registration

        Registering same channel_id twice should reuse the adapter and update websocket.
        """
        cp = ControlPlane()
        ws1 = make_mock_websocket()
        ws2 = make_mock_websocket()

        adapter1 = cp.register_adapter(channel_id, channel_type, ws1)
        adapter2 = cp.register_adapter(channel_id, channel_type, ws2)

        # Same adapter object, updated websocket
        assert adapter1 is adapter2
        assert adapter2.websocket is ws2
        assert adapter2.status == ChannelStatusType.CONNECTED

        # Only one entry in the adapter dict
        assert len(cp.adapters) == 1


# ===========================================================================
# Property 4: Fault isolation
# ===========================================================================


class TestFaultIsolation:
    """Property 4: One adapter failure doesn't affect others."""

    @given(
        channel_a=channel_id_strategy,
        channel_b=channel_id_strategy,
    )
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_unregister_preserves_other_adapters(self, channel_a, channel_b):
        """
        Feature: openclaw-integration, Property 4: Fault isolation

        Unregistering one adapter should not remove others.
        """
        # Ensure distinct channels
        if channel_a == channel_b:
            return

        cp = ControlPlane()
        ws_a = make_mock_websocket()
        ws_b = make_mock_websocket()

        cp.register_adapter(channel_a, "telegram", ws_a)
        cp.register_adapter(channel_b, "discord", ws_b)

        # "Fail" channel A
        cp.unregister_adapter(channel_a, error="connection lost")

        # Channel B should still be connected
        status_b = cp.get_channel_status(channel_b)
        assert status_b is not None
        assert status_b["status"] == ChannelStatusType.CONNECTED

    @given(channel_id=channel_id_strategy)
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_unregister_marks_disconnected_not_removed(self, channel_id):
        """
        Feature: openclaw-integration, Property 4: Fault isolation

        Unregistering an adapter marks it disconnected but does NOT remove it.
        """
        cp = ControlPlane()
        ws = make_mock_websocket()
        cp.register_adapter(channel_id, "telegram", ws)
        initial_count = len(cp.adapters)

        cp.unregister_adapter(channel_id)

        # Adapter still exists in dict
        assert len(cp.adapters) == initial_count
        assert channel_id in cp.adapters
        assert cp.adapters[channel_id].status == ChannelStatusType.DISCONNECTED

    @given(channel_id=channel_id_strategy)
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_error_state_records_error_info(self, channel_id):
        """
        Feature: openclaw-integration, Property 4: Fault isolation

        Marking an adapter with an error should record the error message.
        """
        cp = ControlPlane()
        ws = make_mock_websocket()
        adapter = cp.register_adapter(channel_id, "slack", ws)

        adapter.mark_error("test failure")

        assert adapter.status == ChannelStatusType.ERROR
        assert adapter.error_count >= 1
        assert adapter.last_error == "test failure"


# ===========================================================================
# Property 5: Concurrent message handling (outbound queue)
# ===========================================================================


class TestConcurrentMessageHandling:
    """Property 5: Messages queued for disconnected adapters; bounded by MAX_QUEUE_SIZE."""

    @given(
        channel_id=channel_id_strategy,
        text=safe_text,
        chat_id=id_text,
    )
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.asyncio
    async def test_outbound_queued_when_disconnected(self, channel_id, text, chat_id):
        """
        Feature: openclaw-integration, Property 5: Concurrent message handling

        Outbound messages to disconnected adapters should be queued.
        """
        cp = ControlPlane()
        ws = make_mock_websocket()
        cp.register_adapter(channel_id, "telegram", ws)
        cp.unregister_adapter(channel_id)

        msg = MessageSerializer.create_outbound_message(
            message_id="out1",
            channel_id=channel_id,
            chat_id=chat_id,
            text=text,
        )

        result = await cp.deliver_outbound_message(msg)

        adapter = cp.adapters[channel_id]
        assert adapter.queue_depth >= 1

    @given(channel_id=channel_id_strategy)
    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.asyncio
    async def test_outbound_queue_bounded(self, channel_id):
        """
        Feature: openclaw-integration, Property 5: Concurrent message handling

        Outbound queue should never exceed MAX_QUEUE_SIZE.
        """
        cp = ControlPlane()
        ws = make_mock_websocket()
        cp.register_adapter(channel_id, "telegram", ws)
        cp.unregister_adapter(channel_id)

        # Enqueue more than MAX_QUEUE_SIZE messages
        for i in range(MAX_QUEUE_SIZE + 50):
            msg = MessageSerializer.create_outbound_message(
                message_id=f"out{i}",
                channel_id=channel_id,
                chat_id="chat1",
                text=f"message {i}",
            )
            await cp.deliver_outbound_message(msg)

        adapter = cp.adapters[channel_id]
        assert adapter.queue_depth <= MAX_QUEUE_SIZE

    @given(
        channel_id=channel_id_strategy,
        text=safe_text,
        chat_id=id_text,
    )
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.asyncio
    async def test_metrics_increment_on_inbound(self, channel_id, text, chat_id):
        """
        Feature: openclaw-integration, Property 5: Concurrent message handling

        Routing an inbound message should increment the total_messages_routed
        metrics counter and the adapter's messages_received counter.
        """
        cp = ControlPlane()
        ws = make_mock_websocket()
        cp.register_adapter(channel_id, "telegram", ws)

        msg = MessageSerializer.create_inbound_message(
            message_id="in1",
            channel_id=channel_id,
            user_id="u1",
            chat_id=chat_id,
            text=text,
        )

        initial_routed = cp.metrics.get("total_messages_routed", 0)
        initial_received = cp.adapters[channel_id].messages_received

        # Mock the gateway_message_handler to avoid pulling in the agent chain.
        # The lazy import inside route_inbound_message uses:
        #   from gateway_message_handler import process_inbound_message
        # We inject a fake module into sys.modules BEFORE the call.
        fake_handler = MagicMock()
        fake_handler.process_inbound_message = AsyncMock()
        import sys as _sys
        _sys.modules["gateway_message_handler"] = fake_handler
        try:
            await cp.route_inbound_message(msg)
        finally:
            _sys.modules.pop("gateway_message_handler", None)

        assert cp.metrics["total_messages_routed"] > initial_routed
        assert cp.adapters[channel_id].messages_received > initial_received
