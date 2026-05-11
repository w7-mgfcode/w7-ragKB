"""Property-based tests for the gateway message protocol.

Feature: openclaw-integration
Properties tested: 66, 67, 68, 69, 70

Tests serialization round-trips, validation, base64 encoding,
and schema version handling for all message types.
"""

import base64
import json
import string

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from pydantic import ValidationError

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gateway_protocol import (
    PROTOCOL_VERSION,
    BinaryAttachment,
    ChannelStatus,
    ChannelStatusType,
    InboundMessage,
    MessageParser,
    MessageSerializer,
    MessageType,
    OutboundMessage,
    SessionCommand,
    SessionCommandType,
    parse_message,
    serialize_message,
    validate_message_version,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

safe_text = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())
id_text = st.text(
    alphabet=string.ascii_letters + string.digits + "-_",
    min_size=1,
    max_size=50,
)
timestamp_float = st.floats(min_value=1_000_000_000, max_value=2_000_000_000, allow_nan=False)
metadata_strategy = st.fixed_dictionaries({})

binary_data = st.binary(min_size=1, max_size=5000)
filename_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + "-_.",
    min_size=1,
    max_size=50,
)
content_type_strategy = st.sampled_from([
    "image/png", "image/jpeg", "application/pdf",
    "text/plain", "application/octet-stream",
])


def build_inbound_message(
    message_id, channel_id, user_id, chat_id, text, timestamp
):
    """Helper to build an InboundMessage via MessageSerializer."""
    return MessageSerializer.create_inbound_message(
        message_id=message_id,
        channel_id=channel_id,
        user_id=user_id,
        chat_id=chat_id,
        text=text,
    )


def build_outbound_message(message_id, channel_id, chat_id, text):
    """Helper to build an OutboundMessage via MessageSerializer."""
    return MessageSerializer.create_outbound_message(
        message_id=message_id,
        channel_id=channel_id,
        chat_id=chat_id,
        text=text,
    )


# ===========================================================================
# Property 66: WebSocket message serialization
# ===========================================================================


class TestMessageSerialization:
    """Property 66: Serialized messages include schema_version and required fields."""

    @given(
        message_id=id_text,
        channel_id=id_text,
        user_id=id_text,
        chat_id=id_text,
        text=safe_text,
    )
    @settings(max_examples=100, deadline=None)
    def test_inbound_serialization_has_required_fields(
        self, message_id, channel_id, user_id, chat_id, text
    ):
        """
        Feature: openclaw-integration, Property 66: WebSocket message serialization

        Serialized InboundMessage must contain schema_version and all required fields.
        """
        msg = build_inbound_message(message_id, channel_id, user_id, chat_id, text, 0)
        serialized = serialize_message(msg)
        data = json.loads(serialized)

        assert data["schema_version"] == PROTOCOL_VERSION
        assert data["type"] == MessageType.INBOUND_MESSAGE
        assert data["message_id"] == message_id
        assert data["channel_id"] == channel_id
        assert data["user_id"] == user_id
        assert data["chat_id"] == chat_id
        assert data["text"] == text

    @given(
        message_id=id_text,
        channel_id=id_text,
        chat_id=id_text,
        text=safe_text,
    )
    @settings(max_examples=100, deadline=None)
    def test_outbound_serialization_has_required_fields(
        self, message_id, channel_id, chat_id, text
    ):
        """
        Feature: openclaw-integration, Property 66: WebSocket message serialization

        Serialized OutboundMessage must contain schema_version and all required fields.
        """
        msg = build_outbound_message(message_id, channel_id, chat_id, text)
        serialized = serialize_message(msg)
        data = json.loads(serialized)

        assert data["schema_version"] == PROTOCOL_VERSION
        assert data["type"] == MessageType.OUTBOUND_MESSAGE
        assert data["message_id"] == message_id
        assert data["channel_id"] == channel_id
        assert data["chat_id"] == chat_id
        assert data["text"] == text

    @given(channel_id=id_text)
    @settings(max_examples=50, deadline=None)
    def test_channel_status_serialization(self, channel_id):
        """
        Feature: openclaw-integration, Property 66: WebSocket message serialization

        Serialized ChannelStatus must have schema_version and required fields.
        """
        msg = MessageSerializer.create_channel_status(
            channel_id=channel_id,
            status=ChannelStatusType.CONNECTED,
        )
        serialized = serialize_message(msg)
        data = json.loads(serialized)

        assert data["schema_version"] == PROTOCOL_VERSION
        assert data["type"] == MessageType.CHANNEL_STATUS
        assert data["channel_id"] == channel_id


# ===========================================================================
# Property 67: WebSocket message validation
# ===========================================================================


class TestMessageValidation:
    """Property 67: Malformed messages are rejected with validation errors."""

    @given(garbage=st.text(min_size=1, max_size=500).filter(lambda s: s.strip()))
    @settings(max_examples=50, deadline=None)
    def test_invalid_json_rejected(self, garbage):
        """
        Feature: openclaw-integration, Property 67: WebSocket message validation

        Non-JSON strings should raise an error on parse.
        """
        # Make sure it's actually invalid JSON
        try:
            json.loads(garbage)
            return  # Skip if it happens to be valid JSON
        except json.JSONDecodeError:
            pass

        with pytest.raises(Exception):
            parse_message(garbage)

    @settings(max_examples=50, deadline=None)
    @given(st.data())
    def test_missing_type_field_rejected(self, data):
        """
        Feature: openclaw-integration, Property 67: WebSocket message validation

        JSON missing the 'type' field should be rejected.
        """
        payload = json.dumps({"schema_version": PROTOCOL_VERSION, "message_id": "m1"})
        with pytest.raises(Exception):
            parse_message(payload)

    def test_empty_text_rejected_on_inbound(self):
        """
        Feature: openclaw-integration, Property 67: WebSocket message validation

        InboundMessage with empty or whitespace-only text should be rejected.
        """
        with pytest.raises(ValidationError):
            InboundMessage(
                type=MessageType.INBOUND_MESSAGE,
                schema_version=PROTOCOL_VERSION,
                message_id="m1",
                channel_id="ch1",
                user_id="u1",
                chat_id="c1",
                text="   ",
                attachments=[],
                metadata={},
                timestamp=1700000000.0,
            )

    def test_whitespace_only_text_rejected(self):
        """
        Feature: openclaw-integration, Property 67: WebSocket message validation

        InboundMessage with tab/newline-only text should be rejected.
        """
        with pytest.raises(ValidationError):
            InboundMessage(
                type=MessageType.INBOUND_MESSAGE,
                schema_version=PROTOCOL_VERSION,
                message_id="m1",
                channel_id="ch1",
                user_id="u1",
                chat_id="c1",
                text="\t\n",
                attachments=[],
                metadata={},
                timestamp=1700000000.0,
            )


# ===========================================================================
# Property 68: Message round-trip consistency
# ===========================================================================


class TestMessageRoundTrip:
    """Property 68: parse(serialize(msg)) == msg for all message types."""

    @given(
        message_id=id_text,
        channel_id=id_text,
        user_id=id_text,
        chat_id=id_text,
        text=safe_text,
    )
    @settings(max_examples=100, deadline=None)
    def test_inbound_roundtrip(
        self, message_id, channel_id, user_id, chat_id, text
    ):
        """
        Feature: openclaw-integration, Property 68: Message round-trip consistency

        Serialize then parse an InboundMessage should reconstruct equivalent fields.
        """
        original = build_inbound_message(
            message_id, channel_id, user_id, chat_id, text, 0
        )
        serialized = serialize_message(original)
        restored = parse_message(serialized)

        assert isinstance(restored, InboundMessage)
        assert restored.message_id == original.message_id
        assert restored.channel_id == original.channel_id
        assert restored.user_id == original.user_id
        assert restored.chat_id == original.chat_id
        assert restored.text == original.text
        assert restored.schema_version == PROTOCOL_VERSION

    @given(
        message_id=id_text,
        channel_id=id_text,
        chat_id=id_text,
        text=safe_text,
    )
    @settings(max_examples=100, deadline=None)
    def test_outbound_roundtrip(self, message_id, channel_id, chat_id, text):
        """
        Feature: openclaw-integration, Property 68: Message round-trip consistency

        Serialize then parse an OutboundMessage should reconstruct equivalent fields.
        """
        original = build_outbound_message(message_id, channel_id, chat_id, text)
        serialized = serialize_message(original)
        restored = parse_message(serialized)

        assert isinstance(restored, OutboundMessage)
        assert restored.message_id == original.message_id
        assert restored.channel_id == original.channel_id
        assert restored.chat_id == original.chat_id
        assert restored.text == original.text

    @given(channel_id=id_text)
    @settings(max_examples=50, deadline=None)
    def test_channel_status_roundtrip(self, channel_id):
        """
        Feature: openclaw-integration, Property 68: Message round-trip consistency

        Serialize then parse a ChannelStatus should reconstruct equivalent fields.
        """
        original = MessageSerializer.create_channel_status(
            channel_id=channel_id,
            status=ChannelStatusType.CONNECTED,
        )
        serialized = serialize_message(original)
        restored = parse_message(serialized)

        assert isinstance(restored, ChannelStatus)
        assert restored.channel_id == original.channel_id
        assert restored.status == original.status

    @given(
        command=st.sampled_from(list(SessionCommandType)),
        session_id=st.one_of(st.none(), id_text),
    )
    @settings(max_examples=50, deadline=None)
    def test_session_command_roundtrip(self, command, session_id):
        """
        Feature: openclaw-integration, Property 68: Message round-trip consistency

        Serialize then parse a SessionCommand should reconstruct equivalent fields.
        """
        original = MessageSerializer.create_session_command(
            command=command,
            session_id=session_id,
        )
        serialized = serialize_message(original)
        restored = parse_message(serialized)

        assert isinstance(restored, SessionCommand)
        assert restored.command == original.command


# ===========================================================================
# Property 69: Binary data encoding
# ===========================================================================


class TestBinaryDataEncoding:
    """Property 69: Base64 encode/decode round-trip for binary attachments."""

    @given(
        data=binary_data,
        filename=filename_strategy,
        content_type=content_type_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_binary_attachment_roundtrip(self, data, filename, content_type):
        """
        Feature: openclaw-integration, Property 69: Binary data encoding

        BinaryAttachment.from_bytes(f, ct, data).to_bytes() == data for all bytes.
        """
        attachment = BinaryAttachment.from_bytes(filename, content_type, data)
        restored = attachment.to_bytes()

        assert restored == data
        assert attachment.filename == filename
        assert attachment.content_type == content_type
        assert attachment.size == len(data)

    @given(
        data=binary_data,
        filename=filename_strategy,
        content_type=content_type_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_attachment_encode_decode_roundtrip(self, data, filename, content_type):
        """
        Feature: openclaw-integration, Property 69: Binary data encoding

        MessageSerializer.encode_attachment -> decode_attachment round-trip.
        """
        encoded = MessageSerializer.encode_attachment(filename, content_type, data)
        dec_filename, dec_content_type, dec_data = MessageSerializer.decode_attachment(
            encoded
        )

        assert dec_filename == filename
        assert dec_content_type == content_type
        assert dec_data == data

    @given(data=binary_data)
    @settings(max_examples=50, deadline=None)
    def test_base64_field_is_valid(self, data):
        """
        Feature: openclaw-integration, Property 69: Binary data encoding

        The data field of BinaryAttachment must be valid base64.
        """
        attachment = BinaryAttachment.from_bytes("test.bin", "application/octet-stream", data)
        # Should not raise
        decoded = base64.b64decode(attachment.data)
        assert decoded == data


# ===========================================================================
# Property 70: Protocol backward compatibility
# ===========================================================================


class TestProtocolBackwardCompatibility:
    """Property 70: Messages with current schema_version pass validation."""

    @given(
        message_id=id_text,
        channel_id=id_text,
        user_id=id_text,
        chat_id=id_text,
        text=safe_text,
    )
    @settings(max_examples=50, deadline=None)
    def test_current_version_passes_validation(
        self, message_id, channel_id, user_id, chat_id, text
    ):
        """
        Feature: openclaw-integration, Property 70: Protocol backward compatibility

        Messages with PROTOCOL_VERSION should pass schema version validation.
        """
        msg = build_inbound_message(
            message_id, channel_id, user_id, chat_id, text, 0
        )
        assert validate_message_version(msg) is True

    def test_unknown_message_type_rejected(self):
        """
        Feature: openclaw-integration, Property 70: Protocol backward compatibility

        JSON with unknown type field should be rejected.
        """
        payload = json.dumps({
            "type": "unknown_type",
            "schema_version": PROTOCOL_VERSION,
            "message_id": "m1",
        })
        with pytest.raises(Exception):
            parse_message(payload)
