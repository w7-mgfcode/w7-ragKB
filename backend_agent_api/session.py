"""Session class for isolated conversation contexts.

This module implements the Session class which encapsulates conversation state,
configuration, and tool permissions for a single conversation context.

Each session has:
- Unique session_id generated from routing components
- Independent message history stored in session_messages table
- Configuration (activation_mode, tool_allowlist, session_type)
- Resource tracking (message_count, token_usage)
- Memory limits with automatic compaction

Sessions are isolated from each other and can have different tool permissions,
activation modes, and configurations based on channel, user, and session type.
"""

import asyncio
import fnmatch
import logging
import time
from typing import Any, Dict, List, Optional

import asyncpg
from pydantic import BaseModel, Field

from db_sessions import (
    add_session_message,
    clear_session_messages,
    get_session_messages,
    update_session_activation_mode,
    update_session_token_usage,
    update_session_tool_allowlist,
)

logger = logging.getLogger(__name__)

# Session configuration defaults
DEFAULT_MAX_MESSAGE_HISTORY = 100
DEFAULT_AUTO_COMPACT_THRESHOLD = 80
DEFAULT_TOOL_ALLOWLIST = ["*"]  # Wildcard allows all tools


class SessionConfig(BaseModel):
    """Configuration for a conversation session."""
    
    session_id: str
    channel_id: str
    user_id: str
    chat_id: str
    session_type: str = Field(..., pattern="^(main|group|webhook)$")
    activation_mode: str = Field(default="mention", pattern="^(mention|always|manual)$")
    tool_allowlist: List[str] = Field(default_factory=lambda: DEFAULT_TOOL_ALLOWLIST.copy())
    tool_denylist: List[str] = Field(default_factory=list)
    max_message_history: int = DEFAULT_MAX_MESSAGE_HISTORY
    auto_compact_threshold: int = DEFAULT_AUTO_COMPACT_THRESHOLD
    browser_enabled: bool = False
    session_tools_enabled: bool = False


class Session:
    """Isolated conversation context with independent state and configuration.
    
    A Session represents a single conversation context with:
    - Unique session_id for routing
    - Independent message history
    - Configuration (activation_mode, tool_allowlist)
    - Resource tracking (message_count, token_usage)
    - Memory limits with automatic compaction
    
    Sessions are created by SessionManager and persist in the database.
    """
    
    def __init__(
        self,
        pool: asyncpg.Pool,
        session_id: str,
        channel_id: str,
        user_id: str,
        chat_id: str,
        session_type: str,
        activation_mode: str = "mention",
        tool_allowlist: Optional[List[str]] = None,
        tool_denylist: Optional[List[str]] = None,
        max_message_history: int = DEFAULT_MAX_MESSAGE_HISTORY,
        auto_compact_threshold: int = DEFAULT_AUTO_COMPACT_THRESHOLD,
        browser_enabled: bool = False,
        session_tools_enabled: bool = False,
        message_count: int = 0,
        token_usage: Optional[Dict[str, Any]] = None,
        created_at: Optional[float] = None,
        last_activity_at: Optional[float] = None,
    ):
        """Initialize a Session instance.
        
        Args:
            pool: Database connection pool
            session_id: Unique session identifier
            channel_id: Channel identifier
            user_id: Platform-specific user ID
            chat_id: DM, group, or thread identifier
            session_type: Type of session (main, group, webhook)
            activation_mode: Activation mode (mention, always, manual)
            tool_allowlist: List of allowed tools (default: all tools allowed)
            tool_denylist: List of denied tools (overrides allowlist)
            max_message_history: Maximum number of messages to keep
            auto_compact_threshold: Message count threshold for auto-compaction
            browser_enabled: Whether browser tools are enabled
            session_tools_enabled: Whether session tools are enabled
            message_count: Current message count
            token_usage: Token usage statistics
            created_at: Session creation timestamp
            last_activity_at: Last activity timestamp
        """
        self.pool = pool
        self.session_id = session_id
        self.channel_id = channel_id
        self.user_id = user_id
        self.chat_id = chat_id
        self.session_type = session_type
        self.activation_mode = activation_mode
        self.tool_allowlist = tool_allowlist or DEFAULT_TOOL_ALLOWLIST.copy()
        self.tool_denylist = tool_denylist or []
        self.max_message_history = max_message_history
        self.auto_compact_threshold = auto_compact_threshold
        self.browser_enabled = browser_enabled
        self.session_tools_enabled = session_tools_enabled
        self.message_count = message_count
        self.token_usage = token_usage or {}
        self.created_at = created_at or time.time()
        self.last_activity_at = last_activity_at or time.time()
        
        # In-memory cache for message history
        self._message_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_lock = asyncio.Lock()
    
    @property
    def config(self) -> SessionConfig:
        """Get session configuration as a Pydantic model.
        
        Returns:
            SessionConfig instance
        """
        return SessionConfig(
            session_id=self.session_id,
            channel_id=self.channel_id,
            user_id=self.user_id,
            chat_id=self.chat_id,
            session_type=self.session_type,
            activation_mode=self.activation_mode,
            tool_allowlist=self.tool_allowlist,
            tool_denylist=self.tool_denylist,
            max_message_history=self.max_message_history,
            auto_compact_threshold=self.auto_compact_threshold,
            browser_enabled=self.browser_enabled,
            session_tools_enabled=self.session_tools_enabled,
        )
    
    async def add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store a message in the session history.
        
        This automatically updates last_activity_at and message_count via
        the database trigger.
        
        Args:
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata (attachments, tool calls, etc.)
            
        Returns:
            Dictionary containing the created message row
        """
        message = await add_session_message(
            self.pool,
            self.session_id,
            role,
            content,
            metadata,
        )
        
        # Update local message count
        self.message_count += 1
        self.last_activity_at = time.time()
        
        # Invalidate message cache
        async with self._cache_lock:
            self._message_cache = None
        
        # Check if compaction is needed
        if self.message_count >= self.auto_compact_threshold:
            logger.info(
                f"Session {self.session_id} reached compaction threshold "
                f"({self.message_count}/{self.auto_compact_threshold}), triggering compaction"
            )
            await self.compact()
        
        return message
    
    async def get_history(
        self,
        limit: int = 50,
        role: Optional[str] = None,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """Retrieve recent messages from the session.
        
        Args:
            limit: Maximum number of messages to return
            role: Optional filter by message role
            use_cache: Whether to use cached messages
            
        Returns:
            List of message dictionaries ordered by created_at ascending
        """
        # Use cache if available and no role filter
        if use_cache and role is None and self._message_cache is not None:
            async with self._cache_lock:
                if self._message_cache is not None:
                    return self._message_cache[-limit:] if limit else self._message_cache
        
        # Fetch from database
        messages = await get_session_messages(
            self.pool,
            self.session_id,
            limit=limit,
            role=role,
        )
        
        # Update cache if no role filter
        if role is None:
            async with self._cache_lock:
                self._message_cache = messages
        
        return messages
    
    async def clear_history(self) -> None:
        """Clear all messages from the session (for /reset command).
        
        This resets message_count to 0 and clears the message cache.
        """
        await clear_session_messages(self.pool, self.session_id)
        
        self.message_count = 0
        
        # Clear message cache
        async with self._cache_lock:
            self._message_cache = None
        
        logger.info(f"Cleared message history for session {self.session_id}")
    
    async def compact(self) -> None:
        """Compact message history by summarizing old messages.
        
        This reduces memory usage by:
        1. Fetching all messages
        2. Creating a summary of older messages
        3. Replacing old messages with a single summary message
        4. Keeping recent messages intact
        
        The compaction preserves the last 20% of messages and summarizes the rest.
        """
        if self.message_count < self.auto_compact_threshold:
            logger.debug(f"Session {self.session_id} below compaction threshold, skipping")
            return
        
        logger.info(f"Compacting session {self.session_id} (message_count: {self.message_count})")
        
        # Fetch all messages
        messages = await self.get_history(limit=self.message_count, use_cache=False)
        
        if len(messages) < 10:
            logger.debug(f"Session {self.session_id} has too few messages to compact")
            return
        
        # Calculate split point (keep last 20% of messages)
        keep_count = max(10, int(len(messages) * 0.2))
        compact_count = len(messages) - keep_count
        
        messages_to_compact = messages[:compact_count]
        messages_to_keep = messages[compact_count:]
        
        # Create summary of compacted messages
        summary_parts = []
        for msg in messages_to_compact:
            role = msg["role"]
            content = msg["content"][:200]  # Truncate long messages
            summary_parts.append(f"{role}: {content}")
        
        summary_text = (
            f"[Conversation history summary - {compact_count} messages compacted]\n\n"
            + "\n".join(summary_parts[:50])  # Limit to first 50 messages in summary
            + f"\n\n[... {len(summary_parts) - 50} more messages ...]" if len(summary_parts) > 50 else ""
        )
        
        # Clear all messages and rebuild with summary + kept messages
        await clear_session_messages(self.pool, self.session_id)
        
        # Add summary message
        await add_session_message(
            self.pool,
            self.session_id,
            "system",
            summary_text,
            {"compacted": True, "original_count": compact_count},
        )
        
        # Re-add kept messages
        for msg in messages_to_keep:
            await add_session_message(
                self.pool,
                self.session_id,
                msg["role"],
                msg["content"],
                msg.get("metadata", {}),
            )
        
        # Update local state
        self.message_count = 1 + len(messages_to_keep)
        
        # Clear cache
        async with self._cache_lock:
            self._message_cache = None
        
        logger.info(
            f"Compacted session {self.session_id}: "
            f"{compact_count} messages → 1 summary, kept {keep_count} messages"
        )
    
    async def check_activation(self, text: str, bot_mention: bool) -> bool:
        """Determine if the agent should respond based on activation mode.

        Logs every activation decision for debugging and analytics (Req 12.7).

        Args:
            text: Message text
            bot_mention: Whether the bot was mentioned in the message

        Returns:
            True if the agent should respond, False otherwise
        """
        if self.activation_mode == "always":
            result, reason = True, "always-on mode"

        elif self.activation_mode == "mention":
            result = bot_mention
            reason = "bot mentioned" if bot_mention else "no bot mention"

        elif self.activation_mode == "manual":
            result = text.strip().startswith("/")
            reason = "command prefix detected" if result else "no command prefix"

        else:
            logger.warning(f"Unknown activation mode: {self.activation_mode}, defaulting to mention")
            result = bot_mention
            reason = f"unknown mode '{self.activation_mode}', fell back to mention"

        await self.log_activation_decision(result, reason)
        return result

    async def log_activation_decision(self, responded: bool, reason: str) -> None:
        """Log an activation decision for debugging and analytics.

        Requirement 12.7: Log activation decisions (responded, ignored, reason).

        Args:
            responded: Whether the agent will respond
            reason: Human-readable reason for the decision
        """
        action = "responded" if responded else "ignored"
        logger.info(
            f"Activation decision: session={self.session_id}, "
            f"mode={self.activation_mode}, action={action}, reason={reason}"
        )

        try:
            await self.pool.execute(
                """
                INSERT INTO tool_access_log (
                    session_id, tool_name, user_id, channel_id,
                    access_granted, timestamp
                ) VALUES ($1, $2, $3, $4, $5, to_timestamp($6))
                """,
                self.session_id,
                f"__activation__{self.activation_mode}",
                self.user_id,
                self.channel_id,
                responded,
                time.time(),
            )
        except Exception as e:
            logger.debug(f"Could not log activation decision to DB: {e}")
    
    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is permitted in this session.
        
        Tool access control follows these rules:
        1. If tool is in denylist, it's blocked (denylist takes precedence)
        2. If allowlist contains "*", all tools are allowed (except denylisted)
        3. If tool matches any pattern in allowlist, it's allowed
        4. Otherwise, it's blocked
        
        Args:
            tool_name: Name of the tool to check
            
        Returns:
            True if the tool is allowed, False otherwise
        """
        # Check denylist first (takes precedence)
        for pattern in self.tool_denylist:
            if fnmatch.fnmatch(tool_name, pattern):
                logger.debug(f"Tool {tool_name} blocked by denylist pattern: {pattern}")
                return False
        
        # Check allowlist
        if "*" in self.tool_allowlist:
            return True
        
        for pattern in self.tool_allowlist:
            if fnmatch.fnmatch(tool_name, pattern):
                return True
        
        logger.debug(f"Tool {tool_name} not in allowlist for session {self.session_id}")
        return False
    
    async def log_blocked_tool(self, tool_name: str) -> None:
        """Log a blocked tool attempt for security auditing.
        
        This creates an audit trail of all blocked tool attempts.
        
        Args:
            tool_name: Name of the blocked tool
        """
        timestamp = time.time()
        
        # Log to application logs
        logger.warning(
            f"Blocked tool attempt: session={self.session_id}, tool={tool_name}, "
            f"user={self.user_id}, channel={self.channel_id}, timestamp={timestamp}"
        )
        
        # Store in database for audit trail
        try:
            await self.pool.execute(
                """
                INSERT INTO tool_access_log (
                    session_id,
                    tool_name,
                    user_id,
                    channel_id,
                    access_granted,
                    timestamp
                ) VALUES ($1, $2, $3, $4, $5, to_timestamp($6))
                """,
                self.session_id,
                tool_name,
                self.user_id,
                self.channel_id,
                False,  # access_granted = False for blocked attempts
                timestamp,
            )
        except Exception as e:
            # Don't fail the request if audit logging fails
            logger.error(f"Failed to log blocked tool attempt: {e}", exc_info=True)
    
    async def update_activation_mode(self, activation_mode: str) -> None:
        """Update the session's activation mode.
        
        Args:
            activation_mode: New activation mode (mention, always, manual)
        """
        await update_session_activation_mode(self.pool, self.session_id, activation_mode)
        self.activation_mode = activation_mode
        logger.info(f"Updated activation mode for session {self.session_id}: {activation_mode}")
    
    async def update_tool_allowlist(
        self,
        tool_allowlist: List[str],
        tool_denylist: Optional[List[str]] = None,
    ) -> None:
        """Update the session's tool allowlist and denylist.
        
        Args:
            tool_allowlist: New list of allowed tools
            tool_denylist: Optional new list of denied tools
        """
        await update_session_tool_allowlist(self.pool, self.session_id, tool_allowlist)
        self.tool_allowlist = tool_allowlist
        
        if tool_denylist is not None:
            self.tool_denylist = tool_denylist
        
        logger.info(
            f"Updated tool allowlist for session {self.session_id}: "
            f"allowlist={tool_allowlist}, denylist={self.tool_denylist}"
        )
    
    async def update_token_usage(self, token_usage: Dict[str, Any]) -> None:
        """Update the session's token usage statistics.
        
        Args:
            token_usage: Token usage statistics
        """
        await update_session_token_usage(self.pool, self.session_id, token_usage)
        self.token_usage = token_usage
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary representation.
        
        Returns:
            Dictionary containing session data
        """
        return {
            "session_id": self.session_id,
            "channel_id": self.channel_id,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "session_type": self.session_type,
            "activation_mode": self.activation_mode,
            "tool_allowlist": self.tool_allowlist,
            "tool_denylist": self.tool_denylist,
            "max_message_history": self.max_message_history,
            "auto_compact_threshold": self.auto_compact_threshold,
            "browser_enabled": self.browser_enabled,
            "session_tools_enabled": self.session_tools_enabled,
            "message_count": self.message_count,
            "token_usage": self.token_usage,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
        }
    
    def __repr__(self) -> str:
        """String representation of the session."""
        return (
            f"Session(session_id={self.session_id!r}, "
            f"channel_id={self.channel_id!r}, "
            f"user_id={self.user_id!r}, "
            f"session_type={self.session_type!r}, "
            f"message_count={self.message_count})"
        )
