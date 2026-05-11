"""Tool allowlist management for per-session tool access control.

This module implements tool allowlist functionality with wildcard pattern matching,
denylist precedence, dynamic updates, and audit logging for blocked tool attempts.

Tool access control follows these rules:
1. If tool is in denylist, it's blocked (denylist takes precedence)
2. If allowlist contains "*", all tools are allowed (except denylisted)
3. If tool matches any pattern in allowlist, it's allowed
4. Otherwise, it's blocked

All blocked tool attempts are logged for security auditing.
"""

import fnmatch
import logging
import time
from typing import Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)

# Default tool allowlists by session type and channel
DEFAULT_ALLOWLISTS = {
    "main": ["*"],  # Main sessions: all tools allowed by default
    "group": [
        "web_search",
        "retrieve_relevant_documents",
        "list_documents",
        "get_document_content",
        "execute_sql_query",
        "image_analysis",
    ],  # Group sessions: limited tools by default
    "webhook": [
        "web_search",
        "retrieve_relevant_documents",
        "list_documents",
    ],  # Webhook sessions: read-only tools by default
}

# Default denylists by channel type (for security)
DEFAULT_DENYLISTS = {
    "telegram": [],  # No restrictions by default
    "discord": [],  # No restrictions by default
    "slack": [],  # No restrictions by default
    "whatsapp": [],  # No restrictions by default
}


class ToolAllowlist:
    """Manages tool access control for sessions with wildcard pattern matching.
    
    This class provides:
    - Tool allowlist initialization based on channel, user, session type
    - Tool access control checks with wildcard pattern matching
    - Denylist with precedence over allowlist
    - Dynamic allowlist updates for active sessions
    - Audit logging for blocked tool attempts
    
    The allowlist uses fnmatch for wildcard pattern matching, supporting:
    - "*" - matches all tools
    - "read_*" - matches all tools starting with "read_"
    - "web_*" - matches all tools starting with "web_"
    - "execute_*" - matches all tools starting with "execute_"
    """
    
    def __init__(self, pool: asyncpg.Pool):
        """Initialize ToolAllowlist with database connection pool.
        
        Args:
            pool: Database connection pool for audit logging
        """
        self.pool = pool
    
    def initialize_allowlist(
        self,
        channel_id: str,
        user_id: str,
        session_type: str,
    ) -> tuple[List[str], List[str]]:
        """Initialize tool allowlist and denylist based on session context.
        
        This determines the initial tool permissions for a new session based on:
        - Session type (main, group, webhook)
        - Channel type (extracted from channel_id)
        - User-specific overrides (future enhancement)
        
        Args:
            channel_id: Channel identifier (e.g., "slack-main", "telegram-bot1")
            user_id: Platform-specific user ID
            session_type: Type of session (main, group, webhook)
            
        Returns:
            Tuple of (allowlist, denylist) as lists of tool name patterns
        """
        # Get default allowlist for session type
        allowlist = DEFAULT_ALLOWLISTS.get(session_type, ["*"]).copy()
        
        # Extract channel type from channel_id (format: "type-name")
        channel_type = channel_id.split("-")[0] if "-" in channel_id else "unknown"
        
        # Get default denylist for channel type
        denylist = DEFAULT_DENYLISTS.get(channel_type, []).copy()
        
        logger.info(
            f"Initialized tool allowlist for session: "
            f"channel={channel_id}, user={user_id}, type={session_type}, "
            f"allowlist={allowlist}, denylist={denylist}"
        )
        
        return allowlist, denylist
    
    def is_tool_allowed(
        self,
        tool_name: str,
        allowlist: List[str],
        denylist: List[str],
    ) -> bool:
        """Check if a tool is permitted based on allowlist and denylist.
        
        Tool access control follows these rules:
        1. If tool is in denylist, it's blocked (denylist takes precedence)
        2. If allowlist contains "*", all tools are allowed (except denylisted)
        3. If tool matches any pattern in allowlist, it's allowed
        4. Otherwise, it's blocked
        
        Args:
            tool_name: Name of the tool to check
            allowlist: List of allowed tool name patterns
            denylist: List of denied tool name patterns
            
        Returns:
            True if the tool is allowed, False otherwise
        """
        # Check denylist first (takes precedence)
        for pattern in denylist:
            if fnmatch.fnmatch(tool_name, pattern):
                logger.debug(f"Tool {tool_name} blocked by denylist pattern: {pattern}")
                return False
        
        # Check allowlist
        if "*" in allowlist:
            return True
        
        for pattern in allowlist:
            if fnmatch.fnmatch(tool_name, pattern):
                return True
        
        logger.debug(f"Tool {tool_name} not in allowlist: {allowlist}")
        return False
    
    async def log_blocked_tool(
        self,
        session_id: str,
        tool_name: str,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> None:
        """Log a blocked tool attempt for security auditing.
        
        This creates an audit trail of all blocked tool attempts, which can be
        used for security monitoring, policy refinement, and incident investigation.
        
        Args:
            session_id: Session identifier
            tool_name: Name of the blocked tool
            user_id: Optional user identifier
            channel_id: Optional channel identifier
        """
        timestamp = time.time()
        
        # Log to application logs
        logger.warning(
            f"Blocked tool attempt: session={session_id}, tool={tool_name}, "
            f"user={user_id}, channel={channel_id}, timestamp={timestamp}"
        )
        
        # Store in database for audit trail
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
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
                    session_id,
                    tool_name,
                    user_id,
                    channel_id,
                    False,  # access_granted = False for blocked attempts
                    timestamp,
                )
        except Exception as e:
            # Don't fail the request if audit logging fails
            logger.error(f"Failed to log blocked tool attempt: {e}", exc_info=True)
    
    async def update_allowlist(
        self,
        session_id: str,
        allowlist: List[str],
        denylist: Optional[List[str]] = None,
    ) -> None:
        """Update tool allowlist for an active session.
        
        This allows dynamic changes to tool permissions without requiring
        session restart. Changes take effect immediately for subsequent
        tool invocations.
        
        Args:
            session_id: Session identifier
            allowlist: New list of allowed tool name patterns
            denylist: Optional new list of denied tool name patterns
        """
        # Update in database
        try:
            async with self.pool.acquire() as conn:
                if denylist is not None:
                    await conn.execute(
                        """
                        UPDATE sessions
                        SET tool_allowlist = $1,
                            tool_denylist = $2,
                            updated_at = NOW()
                        WHERE session_id = $3
                        """,
                        allowlist,
                        denylist,
                        session_id,
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE sessions
                        SET tool_allowlist = $1,
                            updated_at = NOW()
                        WHERE session_id = $2
                        """,
                        allowlist,
                        session_id,
                    )
            
            logger.info(
                f"Updated tool allowlist for session {session_id}: "
                f"allowlist={allowlist}, denylist={denylist}"
            )
        
        except Exception as e:
            logger.error(f"Failed to update tool allowlist: {e}", exc_info=True)
            raise


# Global instance (initialized in main.py)
_tool_allowlist_instance: Optional[ToolAllowlist] = None


def get_tool_allowlist() -> ToolAllowlist:
    """Get the global ToolAllowlist instance.
    
    Returns:
        ToolAllowlist instance
        
    Raises:
        RuntimeError: If ToolAllowlist has not been initialized
    """
    if _tool_allowlist_instance is None:
        raise RuntimeError("ToolAllowlist not initialized. Call init_tool_allowlist() first.")
    return _tool_allowlist_instance


def init_tool_allowlist(pool: asyncpg.Pool) -> ToolAllowlist:
    """Initialize the global ToolAllowlist instance.
    
    Args:
        pool: Database connection pool
        
    Returns:
        ToolAllowlist instance
    """
    global _tool_allowlist_instance
    _tool_allowlist_instance = ToolAllowlist(pool)
    logger.info("ToolAllowlist initialized")
    return _tool_allowlist_instance
