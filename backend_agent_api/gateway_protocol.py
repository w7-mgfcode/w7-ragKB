"""Gateway protocol message models and serialization.

This module defines the WebSocket message protocol for communication between
the Control Plane and Channel Adapters. All messages use JSON serialization
with schema versioning for backward compatibility.

Message Types:
    - InboundMessage: User message from channel to agent
    - OutboundMessage: Agent response from agent to channel
    - ChannelStatus: Channel adapter health report
    - SessionCommand: Control commands for session management

Binary data (images, files) is base64-encoded within JSON payloads.
"""

import base64
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# Current protocol schema version
PROTOCOL_VERSION = "1.0"


class MessageType(str, Enum):
    """WebSocket message types."""
    INBOUND_MESSAGE = "inbound_message"
    OUTBOUND_MESSAGE = "outbound_message"
    CHANNEL_STATUS = "channel_status"
    SESSION_COMMAND = "session_command"


class ChannelStatusType(str, Enum):
    """Channel adapter health status."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class SessionCommandType(str, Enum):
    """Session control commands."""
    RESET = "reset"
    ARCHIVE = "archive"
    LIST = "list"


class BinaryAttachment(BaseModel):
    """Binary attachment with base64 encoding."""
    filename: str
    content_type: str
    size: int
    data: str = Field(..., description="Base64-encoded binary data")
    
    @field_validator("data")
    @classmethod
    def validate_base64(cls, v: str) -> str:
        """Validate that data is valid base64."""
        try:
            base64.b64decode(v, validate=True)
            return v
        except Exception as e:
            raise ValueError(f"Invalid base64 data: {e}")
    
    @classmethod
    def from_bytes(cls, filename: str, content_type: str, data: bytes) -> "BinaryAttachment":
        """Create attachment from raw bytes."""
        return cls(
            filename=filename,
            content_type=content_type,
            size=len(data),
            data=base64.b64encode(data).decode("utf-8"),
        )
    
    def to_bytes(self) -> bytes:
        """Decode attachment data to bytes."""
        return base64.b64decode(self.data)


class InboundMessage(BaseModel):
    """Message from user to agent via channel adapter.
    
    Represents a message received from a messaging platform that needs to be
    routed to the appropriate session and processed by the agent.
    """
    type: Literal[MessageType.INBOUND_MESSAGE] = MessageType.INBOUND_MESSAGE
    schema_version: str = PROTOCOL_VERSION
    message_id: str = Field(..., description="Platform-specific message ID")
    channel_id: str = Field(..., description="Identifies the channel adapter")
    user_id: str = Field(..., description="Platform-specific user ID")
    chat_id: str = Field(..., description="DM, group, or thread identifier")
    thread_id: Optional[str] = Field(None, description="Optional thread identifier")
    text: str = Field(..., description="Message text content")
    attachments: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Files, images, etc. with base64-encoded data",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Platform-specific data (mentions, reactions, etc.)",
    )
    timestamp: float = Field(
        default_factory=lambda: datetime.utcnow().timestamp(),
        description="Unix timestamp when message was received",
    )
    
    @field_validator("text")
    @classmethod
    def validate_text_not_empty(cls, v: str) -> str:
        """Ensure message text is not empty."""
        if not v or not v.strip():
            raise ValueError("Message text cannot be empty")
        return v


class OutboundMessage(BaseModel):
    """Message from agent to user via channel adapter.
    
    Represents a response from the agent that needs to be delivered through
    the originating channel using the platform's API.
    """
    type: Literal[MessageType.OUTBOUND_MESSAGE] = MessageType.OUTBOUND_MESSAGE
    schema_version: str = PROTOCOL_VERSION
    message_id: str = Field(..., description="For tracking/correlation")
    channel_id: str = Field(..., description="Target channel adapter")
    chat_id: str = Field(..., description="Target chat/group/DM")
    thread_id: Optional[str] = Field(None, description="Optional thread identifier")
    text: str = Field(..., description="Response text content")
    reply_to: Optional[str] = Field(None, description="Message ID to reply to")
    attachments: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Files, images, etc. with base64-encoded data",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Buttons, embeds, formatting, etc.",
    )
    timestamp: float = Field(
        default_factory=lambda: datetime.utcnow().timestamp(),
        description="Unix timestamp when message was created",
    )


class ChannelStatus(BaseModel):
    """Channel adapter health report.
    
    Sent by channel adapters to report their connection status and any errors.
    """
    type: Literal[MessageType.CHANNEL_STATUS] = MessageType.CHANNEL_STATUS
    schema_version: str = PROTOCOL_VERSION
    channel_id: str = Field(..., description="Channel adapter identifier")
    status: ChannelStatusType = Field(..., description="Current health status")
    error_message: Optional[str] = Field(None, description="Error details if status is error")
    timestamp: float = Field(
        default_factory=lambda: datetime.utcnow().timestamp(),
        description="Unix timestamp of status report",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional status information (queue depth, rate limits, etc.)",
    )


class SessionCommand(BaseModel):
    """Control commands for session management.
    
    Used to control session lifecycle and retrieve session information.
    """
    type: Literal[MessageType.SESSION_COMMAND] = MessageType.SESSION_COMMAND
    schema_version: str = PROTOCOL_VERSION
    command: SessionCommandType = Field(..., description="Command to execute")
    session_id: Optional[str] = Field(None, description="Target session (required for reset/archive)")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Command-specific parameters",
    )
    timestamp: float = Field(
        default_factory=lambda: datetime.utcnow().timestamp(),
        description="Unix timestamp when command was issued",
    )


# Union type for all message types
GatewayMessage = Union[InboundMessage, OutboundMessage, ChannelStatus, SessionCommand]


class MessageParser:
    """Parser for WebSocket messages with validation and error handling."""
    
    @staticmethod
    def parse(data: str) -> GatewayMessage:
        """Parse JSON string into a message object.
        
        Args:
            data: JSON string containing the message
            
        Returns:
            Parsed message object (InboundMessage, OutboundMessage, etc.)
            
        Raises:
            ValueError: If JSON is malformed or message type is invalid
            ValidationError: If message fails Pydantic validation
        """
        try:
            raw = json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            raise ValueError(f"Invalid JSON: {e}")
        
        if not isinstance(raw, dict):
            raise ValueError("Message must be a JSON object")
        
        message_type = raw.get("type")
        if not message_type:
            raise ValueError("Message missing 'type' field")
        
        # Route to appropriate model based on type
        try:
            if message_type == MessageType.INBOUND_MESSAGE:
                return InboundMessage(**raw)
            elif message_type == MessageType.OUTBOUND_MESSAGE:
                return OutboundMessage(**raw)
            elif message_type == MessageType.CHANNEL_STATUS:
                return ChannelStatus(**raw)
            elif message_type == MessageType.SESSION_COMMAND:
                return SessionCommand(**raw)
            else:
                raise ValueError(f"Unknown message type: {message_type}")
        except Exception as e:
            logger.error(f"Message validation failed: {e}", exc_info=True)
            raise
    
    @staticmethod
    def serialize(message: GatewayMessage) -> str:
        """Serialize message object to JSON string.
        
        Args:
            message: Message object to serialize
            
        Returns:
            JSON string representation
        """
        return message.model_dump_json()
    
    @staticmethod
    def validate_schema_version(message: GatewayMessage) -> bool:
        """Check if message schema version is compatible.
        
        Args:
            message: Message to validate
            
        Returns:
            True if version is compatible, False otherwise
        """
        # Extract major version (e.g., "1.0" -> "1")
        message_major = message.schema_version.split(".")[0]
        current_major = PROTOCOL_VERSION.split(".")[0]
        
        if message_major != current_major:
            logger.warning(
                f"Schema version mismatch: message={message.schema_version}, "
                f"current={PROTOCOL_VERSION}"
            )
            return False
        
        return True
    
    @staticmethod
    def migrate_message(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate message from older schema version to current version.
        
        This enables backward compatibility with older channel adapters.
        
        Args:
            raw: Raw message dictionary with old schema version
            
        Returns:
            Migrated message dictionary compatible with current schema
        """
        schema_version = raw.get("schema_version", "1.0")
        
        # Currently only version 1.0 exists, but this provides the framework
        # for future migrations
        if schema_version == "1.0":
            # No migration needed
            return raw
        
        # Future migrations would go here
        # Example:
        # if schema_version == "0.9":
        #     # Migrate 0.9 -> 1.0
        #     raw["schema_version"] = "1.0"
        #     # Add new required fields with defaults
        #     raw.setdefault("thread_id", None)
        #     return raw
        
        logger.warning(f"Unknown schema version: {schema_version}, attempting to parse as-is")
        return raw


class MessageSerializer:
    """Utility class for message serialization with binary data handling."""
    
    @staticmethod
    def encode_attachment(filename: str, content_type: str, data: bytes) -> Dict[str, Any]:
        """Encode binary attachment for inclusion in message.
        
        Args:
            filename: Original filename
            content_type: MIME type
            data: Raw binary data
            
        Returns:
            Dictionary with base64-encoded data
        """
        attachment = BinaryAttachment.from_bytes(filename, content_type, data)
        return attachment.model_dump()
    
    @staticmethod
    def decode_attachment(attachment: Dict[str, Any]) -> tuple[str, str, bytes]:
        """Decode binary attachment from message.
        
        Args:
            attachment: Attachment dictionary from message
            
        Returns:
            Tuple of (filename, content_type, data)
        """
        att = BinaryAttachment(**attachment)
        return att.filename, att.content_type, att.to_bytes()
    
    @staticmethod
    def create_inbound_message(
        message_id: str,
        channel_id: str,
        user_id: str,
        chat_id: str,
        text: str,
        thread_id: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InboundMessage:
        """Create an inbound message with validation.
        
        Args:
            message_id: Platform-specific message ID
            channel_id: Channel adapter identifier
            user_id: Platform-specific user ID
            chat_id: Chat/group/DM identifier
            text: Message text
            thread_id: Optional thread identifier
            attachments: Optional list of attachments
            metadata: Optional platform-specific metadata
            
        Returns:
            Validated InboundMessage object
        """
        return InboundMessage(
            message_id=message_id,
            channel_id=channel_id,
            user_id=user_id,
            chat_id=chat_id,
            text=text,
            thread_id=thread_id,
            attachments=attachments or [],
            metadata=metadata or {},
        )
    
    @staticmethod
    def create_outbound_message(
        message_id: str,
        channel_id: str,
        chat_id: str,
        text: str,
        thread_id: Optional[str] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OutboundMessage:
        """Create an outbound message with validation.
        
        Args:
            message_id: Message ID for tracking
            channel_id: Target channel adapter
            chat_id: Target chat/group/DM
            text: Response text
            thread_id: Optional thread identifier
            reply_to: Optional message ID to reply to
            attachments: Optional list of attachments
            metadata: Optional platform-specific metadata (buttons, embeds, etc.)
            
        Returns:
            Validated OutboundMessage object
        """
        return OutboundMessage(
            message_id=message_id,
            channel_id=channel_id,
            chat_id=chat_id,
            text=text,
            thread_id=thread_id,
            reply_to=reply_to,
            attachments=attachments or [],
            metadata=metadata or {},
        )
    
    @staticmethod
    def create_channel_status(
        channel_id: str,
        status: ChannelStatusType,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ChannelStatus:
        """Create a channel status report.
        
        Args:
            channel_id: Channel adapter identifier
            status: Current health status
            error_message: Optional error details
            metadata: Optional additional status information
            
        Returns:
            Validated ChannelStatus object
        """
        return ChannelStatus(
            channel_id=channel_id,
            status=status,
            error_message=error_message,
            metadata=metadata or {},
        )
    
    @staticmethod
    def create_session_command(
        command: SessionCommandType,
        session_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> SessionCommand:
        """Create a session control command.
        
        Args:
            command: Command to execute
            session_id: Optional target session
            parameters: Optional command-specific parameters
            
        Returns:
            Validated SessionCommand object
        """
        return SessionCommand(
            command=command,
            session_id=session_id,
            parameters=parameters or {},
        )


# Convenience functions for common operations
def parse_message(data: str) -> GatewayMessage:
    """Parse JSON string into a message object."""
    return MessageParser.parse(data)


def serialize_message(message: GatewayMessage) -> str:
    """Serialize message object to JSON string."""
    return MessageParser.serialize(message)


def validate_message_version(message: GatewayMessage) -> bool:
    """Check if message schema version is compatible."""
    return MessageParser.validate_schema_version(message)
