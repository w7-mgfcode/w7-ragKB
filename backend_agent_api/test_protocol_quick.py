#!/usr/bin/env python
"""Quick test to verify gateway protocol models work."""

from gateway_protocol import (
    InboundMessage,
    OutboundMessage,
    ChannelStatus,
    SessionCommand,
    MessageParser,
    MessageSerializer,
    ChannelStatusType,
    SessionCommandType,
)

# Test InboundMessage
print("Testing InboundMessage...")
msg = InboundMessage(
    message_id="msg123",
    channel_id="telegram-bot1",
    user_id="user456",
    chat_id="chat789",
    text="Hello, agent!",
)
print(f"✓ Created InboundMessage: {msg.message_id}")

# Test serialization
print("\nTesting serialization...")
json_str = MessageParser.serialize(msg)
print(f"✓ Serialized to JSON ({len(json_str)} bytes)")

# Test parsing
print("\nTesting parsing...")
parsed = MessageParser.parse(json_str)
print(f"✓ Parsed back: {parsed.message_id}")

# Test OutboundMessage
print("\nTesting OutboundMessage...")
out_msg = OutboundMessage(
    message_id="resp123",
    channel_id="telegram-bot1",
    chat_id="chat789",
    text="Here's your answer!",
)
print(f"✓ Created OutboundMessage: {out_msg.message_id}")

# Test ChannelStatus
print("\nTesting ChannelStatus...")
status = ChannelStatus(
    channel_id="telegram-bot1",
    status=ChannelStatusType.CONNECTED,
)
print(f"✓ Created ChannelStatus: {status.status}")

# Test SessionCommand
print("\nTesting SessionCommand...")
cmd = SessionCommand(
    command=SessionCommandType.RESET,
    session_id="test-session",
)
print(f"✓ Created SessionCommand: {cmd.command}")

# Test binary attachment
print("\nTesting binary attachments...")
data = b"Test file content"
attachment = MessageSerializer.encode_attachment(
    "test.txt",
    "text/plain",
    data,
)
print(f"✓ Encoded attachment: {attachment['filename']}")

filename, content_type, decoded = MessageSerializer.decode_attachment(attachment)
assert decoded == data
print(f"✓ Decoded attachment matches original")

# Test round-trip
print("\nTesting round-trip...")
msg_with_attachment = InboundMessage(
    message_id="msg456",
    channel_id="telegram-bot1",
    user_id="user789",
    chat_id="chat012",
    text="File attached",
    attachments=[attachment],
)
json_str = MessageParser.serialize(msg_with_attachment)
parsed_with_attachment = MessageParser.parse(json_str)
assert len(parsed_with_attachment.attachments) == 1
print(f"✓ Round-trip with attachment successful")

print("\n✅ All tests passed!")
