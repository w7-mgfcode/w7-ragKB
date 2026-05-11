"""Unit tests for gateway protocol message models and serialization."""

import base64
import json
import pytest
from datetime import datetime

from gateway_protocol import (
    InboundMessage,
    OutboundMessage,
    ChannelStatus,
    SessionCommand,
    BinaryAttachment,
    MessageParser,
    MessageSerializer,
    MessageType,
    ChannelStatusType,
    SessionCommandType,
    PROTOCOL_VERSION,
    parse_message,
    serialize_message,
    validate_message_version,
)


class TestBinaryAttachment:
    """Tests for BinaryAttachment model."""
    
    def test_from_bytes(self):
        """Test creating attachment from raw bytes."""
        data = b"Hello, World!"
        attachment = BinaryAttachment.from_bytes(
            filename="test.txt",
            content_type="text/plain",
            data=data,
        )
        
        assert attachment.filename == "test.txt"
        assert attachment.content_type == "text/plain"
        assert attachment.size == len(data)
        assert attachment.to_bytes() == data
    
    def test_to_bytes(self):
        """Test decoding attachment to bytes."""
        data = b"Binary data \x00\x01\x02"
        encoded = base64.b64encode(data).decode("utf-8")
        
        attachment = BinaryAttachment(
            filename="binary.dat",
            content_type="application/octet-stream",
            size=len(data),
            data=encoded,
        )
        
        assert attachment.to_bytes() == data
    
    def test_invalid_base64(self):
        """Test validation rejects invalid base64."""
        with pytest.raises(ValueError, match="Invalid base64"):
            BinaryAttachment(
                filename="test.txt",
                content_type="text/plain",
                size=10,
                data="not-valid-base64!!!",
            )
    
    def test_round_trip(self):
        """Test encoding and decoding preserves data."""
        original_data = b"Test data with special chars: \xc3\xa9\xc3\xa0"
        attachment = BinaryAttachment.from_bytes("test.bin", "application/octet-stream", original_data)
        decoded_data = attachment.to_bytes()
        
        assert decoded_data == original_data


class TestInboundMessage:
    """Tests for InboundMessage model."""
    
    def test_create_valid_message(self):
        """Test creating a valid inbound message."""
        msg = InboundMessage(
            message_id="msg123",
            channel_id="telegram-bot1",
            user_id="user456",
            chat_id="chat789",
            text="Hello, agent!",
        )
        
        assert msg.type == MessageType.INBOUND_MESSAGE
        assert msg.schema_version == PROTOCOL_VERSION
        assert msg.message_id == "msg123"
        assert msg.channel_id == "telegram-bot1"
        assert msg.user_id == "user456"
        assert msg.chat_id == "chat789"
        assert msg.text == "Hello, agent!"
        assert msg.thread_id is None
        assert msg.attachments == []
        assert msg.metadata == {}
        assert isinstance(msg.timestamp, float)
    
    def test_with_thread_id(self):
        """Test message with thread identifier."""
        msg = InboundMessage(
            message_id="msg123",
            channel_id="slack-main",
            user_id="U123",
            chat_id="C456",
            thread_id="1234567890.123456",
            text="Thread reply",
        )
        
        assert msg.thread_id == "1234567890.123456"
    
    def test_with_attachments(self):
        """Test message with attachments."""
        attachment = BinaryAttachment.from_bytes(
            "image.png",
            "image/png",
            b"\x89PNG\r\n\x1a\n",
        )
        
        msg = InboundMessage(
            message_id="msg123",
            channel_id="discord-main",
            user_id="user789",
            chat_id="channel123",
            text="Check this image",
            attachments=[attachment.model_dump()],
        )
        
        assert len(msg.attachments) == 1
        assert msg.attachments[0]["filename"] == "image.png"
    
    def test_with_metadata(self):
        """Test message with platform-specific metadata."""
        msg = InboundMessage(
            message_id="msg123",
            channel_id="telegram-bot1",
            user_id="user456",
            chat_id="chat789",
            text="@bot help",
            metadata={
                "mentions": ["@bot"],
                "is_group": True,
                "reply_to_message_id": "msg122",
            },
        )
        
        assert msg.metadata["mentions"] == ["@bot"]
        assert msg.metadata["is_group"] is True
    
    def test_empty_text_rejected(self):
        """Test that empty text is rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            InboundMessage(
                message_id="msg123",
                channel_id="telegram-bot1",
                user_id="user456",
                chat_id="chat789",
                text="",
            )
    
    def test_whitespace_only_text_rejected(self):
        """Test that whitespace-only text is rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            InboundMessage(
                message_id="msg123",
                channel_id="telegram-bot1",
                user_id="user456",
                chat_id="chat789",
                text="   \n\t  ",
            )


class TestOutboundMessage:
    """Tests for OutboundMessage model."""
    
    def test_create_valid_message(self):
        """Test creating a valid outbound message."""
        msg = OutboundMessage(
            message_id="resp123",
            channel_id="telegram-bot1",
            chat_id="chat789",
            text="Here's your answer!",
        )
        
        assert msg.type == MessageType.OUTBOUND_MESSAGE
        assert msg.schema_version == PROTOCOL_VERSION
        assert msg.message_id == "resp123"
        assert msg.channel_id == "telegram-bot1"
        assert msg.chat_id == "chat789"
        assert msg.text == "Here's your answer!"
        assert msg.reply_to is None
        assert msg.attachments == []
        assert msg.metadata == {}
    
    def test_with_reply_to(self):
        """Test message replying to another message."""
        msg = OutboundMessage(
            message_id="resp123",
            channel_id="slack-main",
            chat_id="C456",
            text="Replying to your question",
            reply_to="msg122",
        )
        
        assert msg.reply_to == "msg122"
    
    def test_with_metadata_buttons(self):
        """Test message with interactive buttons."""
        msg = OutboundMessage(
            message_id="resp123",
            channel_id="telegram-bot1",
            chat_id="chat789",
            text="Choose an option:",
            metadata={
                "inline_keyboard": [
                    [{"text": "Option 1", "callback_data": "opt1"}],
                    [{"text": "Option 2", "callback_data": "opt2"}],
                ],
            },
        )
        
        assert "inline_keyboard" in msg.metadata
        assert len(msg.metadata["inline_keyboard"]) == 2


class TestChannelStatus:
    """Tests for ChannelStatus model."""
    
    def test_connected_status(self):
        """Test connected status report."""
        status = ChannelStatus(
            channel_id="telegram-bot1",
            status=ChannelStatusType.CONNECTED,
        )
        
        assert status.type == MessageType.CHANNEL_STATUS
        assert status.channel_id == "telegram-bot1"
        assert status.status == ChannelStatusType.CONNECTED
        assert status.error_message is None
    
    def test_error_status(self):
        """Test error status report."""
        status = ChannelStatus(
            channel_id="discord-main",
            status=ChannelStatusType.ERROR,
            error_message="WebSocket connection failed",
        )
        
        assert status.status == ChannelStatusType.ERROR
        assert status.error_message == "WebSocket connection failed"
    
    def test_with_metadata(self):
        """Test status with additional metadata."""
        status = ChannelStatus(
            channel_id="slack-main",
            status=ChannelStatusType.CONNECTED,
            metadata={
                "queue_depth": 5,
                "rate_limit_remaining": 50,
                "uptime_seconds": 3600,
            },
        )
        
        assert status.metadata["queue_depth"] == 5
        assert status.metadata["uptime_seconds"] == 3600


class TestSessionCommand:
    """Tests for SessionCommand model."""
    
    def test_reset_command(self):
        """Test reset session command."""
        cmd = SessionCommand(
            command=SessionCommandType.RESET,
            session_id="telegram-bot1:user123:chat456",
        )
        
        assert cmd.type == MessageType.SESSION_COMMAND
        assert cmd.command == SessionCommandType.RESET
        assert cmd.session_id == "telegram-bot1:user123:chat456"
    
    def test_list_command(self):
        """Test list sessions command."""
        cmd = SessionCommand(
            command=SessionCommandType.LIST,
            parameters={"filter": "active", "limit": 10},
        )
        
        assert cmd.command == SessionCommandType.LIST
        assert cmd.session_id is None
        assert cmd.parameters["filter"] == "active"
    
    def test_archive_command(self):
        """Test archive session command."""
        cmd = SessionCommand(
            command=SessionCommandType.ARCHIVE,
            session_id="slack-main:U123:C456",
        )
        
        assert cmd.command == SessionCommandType.ARCHIVE
        assert cmd.session_id == "slack-main:U123:C456"


class TestMessageParser:
    """Tests for MessageParser."""
    
    def test_parse_inbound_message(self):
        """Test parsing inbound message from JSON."""
        json_data = json.dumps({
            "type": "inbound_message",
            "schema_version": "1.0",
            "message_id": "msg123",
            "channel_id": "telegram-bot1",
            "user_id": "user456",
            "chat_id": "chat789",
            "text": "Hello!",
            "timestamp": 1234567890.0,
        })
        
        msg = MessageParser.parse(json_data)
        
        assert isinstance(msg, InboundMessage)
        assert msg.message_id == "msg123"
        assert msg.text == "Hello!"
    
    def test_parse_outbound_message(self):
        """Test parsing outbound message from JSON."""
        json_data = json.dumps({
            "type": "outbound_message",
            "schema_version": "1.0",
            "message_id": "resp123",
            "channel_id": "telegram-bot1",
            "chat_id": "chat789",
            "text": "Response!",
            "timestamp": 1234567890.0,
        })
        
        msg = MessageParser.parse(json_data)
        
        assert isinstance(msg, OutboundMessage)
        assert msg.message_id == "resp123"
    
    def test_parse_channel_status(self):
        """Test parsing channel status from JSON."""
        json_data = json.dumps({
            "type": "channel_status",
            "schema_version": "1.0",
            "channel_id": "slack-main",
            "status": "connected",
            "timestamp": 1234567890.0,
        })
        
        msg = MessageParser.parse(json_data)
        
        assert isinstance(msg, ChannelStatus)
        assert msg.status == ChannelStatusType.CONNECTED
    
    def test_parse_session_command(self):
        """Test parsing session command from JSON."""
        json_data = json.dumps({
            "type": "session_command",
            "schema_version": "1.0",
            "command": "reset",
            "session_id": "test-session",
            "timestamp": 1234567890.0,
        })
        
        msg = MessageParser.parse(json_data)
        
        assert isinstance(msg, SessionCommand)
        assert msg.command == SessionCommandType.RESET
    
    def test_parse_invalid_json(self):
        """Test parsing invalid JSON raises error."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            MessageParser.parse("{invalid json")
    
    def test_parse_missing_type(self):
        """Test parsing message without type field."""
        json_data = json.dumps({
            "schema_version": "1.0",
            "message_id": "msg123",
        })
        
        with pytest.raises(ValueError, match="missing 'type' field"):
            MessageParser.parse(json_data)
    
    def test_parse_unknown_type(self):
        """Test parsing message with unknown type."""
        json_data = json.dumps({
            "type": "unknown_message_type",
            "schema_version": "1.0",
        })
        
        with pytest.raises(ValueError, match="Unknown message type"):
            MessageParser.parse(json_data)
    
    def test_parse_missing_required_field(self):
        """Test parsing message missing required fields."""
        json_data = json.dumps({
            "type": "inbound_message",
            "schema_version": "1.0",
            "message_id": "msg123",
            # Missing channel_id, user_id, chat_id, text
        })
        
        with pytest.raises(Exception):  # Pydantic ValidationError
            MessageParser.parse(json_data)
    
    def test_serialize_message(self):
        """Test serializing message to JSON."""
        msg = InboundMessage(
            message_id="msg123",
            channel_id="telegram-bot1",
            user_id="user456",
            chat_id="chat789",
            text="Hello!",
        )
        
        json_str = MessageParser.serialize(msg)
        parsed = json.loads(json_str)
        
        assert parsed["type"] == "inbound_message"
        assert parsed["message_id"] == "msg123"
        assert parsed["text"] == "Hello!"
    
    def test_round_trip_inbound(self):
        """Test parsing then serializing produces equivalent message."""
        original = InboundMessage(
            message_id="msg123",
            channel_id="telegram-bot1",
            user_id="user456",
            chat_id="chat789",
            text="Hello!",
            metadata={"key": "value"},
        )
        
        # Serialize then parse
        json_str = MessageParser.serialize(original)
        parsed = MessageParser.parse(json_str)
        
        # Serialize again
        json_str2 = MessageParser.serialize(parsed)
        
        # Should be equivalent
        assert json.loads(json_str) == json.loads(json_str2)
    
    def test_validate_schema_version_compatible(self):
        """Test schema version validation for compatible versions."""
        msg = InboundMessage(
            message_id="msg123",
            channel_id="telegram-bot1",
            user_id="user456",
            chat_id="chat789",
            text="Hello!",
        )
        
        assert MessageParser.validate_schema_version(msg) is True
    
    def test_validate_schema_version_incompatible(self):
        """Test schema version validation for incompatible versions."""
        msg = InboundMessage(
            message_id="msg123",
            channel_id="telegram-bot1",
            user_id="user456",
            chat_id="chat789",
            text="Hello!",
        )
        msg.schema_version = "2.0"  # Future version
        
        assert MessageParser.validate_schema_version(msg) is False


class TestMessageSerializer:
    """Tests for MessageSerializer utility class."""
    
    def test_encode_attachment(self):
        """Test encoding binary attachment."""
        data = b"Test file content"
        attachment = MessageSerializer.encode_attachment(
            "test.txt",
            "text/plain",
            data,
        )
        
        assert attachment["filename"] == "test.txt"
        assert attachment["content_type"] == "text/plain"
        assert attachment["size"] == len(data)
        assert "data" in attachment
    
    def test_decode_attachment(self):
        """Test decoding binary attachment."""
        data = b"Test file content"
        attachment = MessageSerializer.encode_attachment(
            "test.txt",
            "text/plain",
            data,
        )
        
        filename, content_type, decoded_data = MessageSerializer.decode_attachment(attachment)
        
        assert filename == "test.txt"
        assert content_type == "text/plain"
        assert decoded_data == data
    
    def test_create_inbound_message(self):
        """Test creating inbound message with helper."""
        msg = MessageSerializer.create_inbound_message(
            message_id="msg123",
            channel_id="telegram-bot1",
            user_id="user456",
            chat_id="chat789",
            text="Hello!",
        )
        
        assert isinstance(msg, InboundMessage)
        assert msg.message_id == "msg123"
        assert msg.text == "Hello!"
    
    def test_create_outbound_message(self):
        """Test creating outbound message with helper."""
        msg = MessageSerializer.create_outbound_message(
            message_id="resp123",
            channel_id="telegram-bot1",
            chat_id="chat789",
            text="Response!",
            reply_to="msg122",
        )
        
        assert isinstance(msg, OutboundMessage)
        assert msg.reply_to == "msg122"
    
    def test_create_channel_status(self):
        """Test creating channel status with helper."""
        status = MessageSerializer.create_channel_status(
            channel_id="slack-main",
            status=ChannelStatusType.CONNECTED,
        )
        
        assert isinstance(status, ChannelStatus)
        assert status.status == ChannelStatusType.CONNECTED
    
    def test_create_session_command(self):
        """Test creating session command with helper."""
        cmd = MessageSerializer.create_session_command(
            command=SessionCommandType.RESET,
            session_id="test-session",
        )
        
        assert isinstance(cmd, SessionCommand)
        assert cmd.command == SessionCommandType.RESET


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""
    
    def test_parse_message(self):
        """Test parse_message convenience function."""
        json_data = json.dumps({
            "type": "inbound_message",
            "schema_version": "1.0",
            "message_id": "msg123",
            "channel_id": "telegram-bot1",
            "user_id": "user456",
            "chat_id": "chat789",
            "text": "Hello!",
            "timestamp": 1234567890.0,
        })
        
        msg = parse_message(json_data)
        assert isinstance(msg, InboundMessage)
    
    def test_serialize_message(self):
        """Test serialize_message convenience function."""
        msg = InboundMessage(
            message_id="msg123",
            channel_id="telegram-bot1",
            user_id="user456",
            chat_id="chat789",
            text="Hello!",
        )
        
        json_str = serialize_message(msg)
        assert isinstance(json_str, str)
        assert "msg123" in json_str
    
    def test_validate_message_version(self):
        """Test validate_message_version convenience function."""
        msg = InboundMessage(
            message_id="msg123",
            channel_id="telegram-bot1",
            user_id="user456",
            chat_id="chat789",
            text="Hello!",
        )
        
        assert validate_message_version(msg) is True


class TestBinaryDataHandling:
    """Tests for binary data encoding/decoding."""
    
    def test_image_attachment(self):
        """Test handling image attachment."""
        # Minimal PNG header
        png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        
        attachment = MessageSerializer.encode_attachment(
            "image.png",
            "image/png",
            png_data,
        )
        
        msg = InboundMessage(
            message_id="msg123",
            channel_id="telegram-bot1",
            user_id="user456",
            chat_id="chat789",
            text="Check this image",
            attachments=[attachment],
        )
        
        # Serialize and parse
        json_str = serialize_message(msg)
        parsed = parse_message(json_str)
        
        # Decode attachment
        filename, content_type, decoded_data = MessageSerializer.decode_attachment(
            parsed.attachments[0]
        )
        
        assert decoded_data == png_data
        assert content_type == "image/png"
    
    def test_large_binary_file(self):
        """Test handling large binary file."""
        # 1MB of random data
        large_data = bytes(range(256)) * 4096
        
        attachment = MessageSerializer.encode_attachment(
            "large.bin",
            "application/octet-stream",
            large_data,
        )
        
        assert attachment["size"] == len(large_data)
        
        # Decode and verify
        _, _, decoded = MessageSerializer.decode_attachment(attachment)
        assert decoded == large_data
