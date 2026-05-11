"""Session tools for inter-session communication.

This module implements tools that enable the AI agent to:
- List active sessions accessible to the current session
- Retrieve message history from another session
- Send messages to another session

All tools enforce permission checks based on SessionConfig.session_tools_enabled
and implement access control to prevent unauthorized cross-session access.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List

from pydantic_ai import RunContext

if TYPE_CHECKING:
    from typing import Protocol
    
    class SessionToolsDeps(Protocol):
        """Protocol for session tools dependencies."""
        session_manager: Any
        session_id: str

logger = logging.getLogger(__name__)


class SessionToolsError(Exception):
    """Base exception for session tools errors."""
    pass


class PermissionError(SessionToolsError):
    """Raised when a session lacks permission to access another session."""
    pass


class SessionNotFoundError(SessionToolsError):
    """Raised when a target session does not exist."""
    pass


async def can_access_session(
    session_manager,
    current_session_id: str,
    target_session_id: str,
) -> bool:
    """Check if current session can access target session.
    
    Access control rules:
    1. A session can always access itself
    2. Sessions from the same user can access each other
    3. Admin sessions (future) can access all sessions
    
    Args:
        session_manager: SessionManager instance
        current_session_id: ID of the session making the request
        target_session_id: ID of the session being accessed
        
    Returns:
        True if access is allowed, False otherwise
    """
    # Self-access is always allowed
    if current_session_id == target_session_id:
        return True
    
    # Get both sessions
    current_session = await session_manager.get_session(current_session_id)
    target_session = await session_manager.get_session(target_session_id)
    
    if not current_session or not target_session:
        return False
    
    # Same user can access their own sessions
    if current_session.user_id == target_session.user_id:
        return True
    
    # Future: Add admin role check here
    # if current_session.is_admin:
    #     return True
    
    return False


async def sessions_list(ctx: "RunContext[Any]") -> List[Dict[str, Any]]:
    """List all active sessions accessible to the current session.
    
    This tool returns a list of sessions that the current session has
    permission to access, including session metadata like channel, user,
    message count, and last activity timestamp.
    
    Args:
        ctx: RunContext containing session_manager and session_id in deps
        
    Returns:
        List of session dictionaries with metadata
        
    Raises:
        PermissionError: If session_tools_enabled is False
    """
    session_manager = ctx.deps.session_manager  # type: ignore
    current_session_id = ctx.deps.session_id  # type: ignore
    
    # Get current session to check permissions
    current_session = await session_manager.get_session(current_session_id)
    
    if not current_session:
        logger.error(f"Current session {current_session_id} not found")
        raise SessionNotFoundError(f"Session {current_session_id} not found")
    
    # Check if session tools are enabled
    if not current_session.session_tools_enabled:
        logger.warning(
            f"Session tools access denied for session {current_session_id}: "
            "session_tools_enabled is False"
        )
        raise PermissionError(
            "Session tools are not enabled for this session. "
            "Contact an administrator to enable inter-session communication."
        )
    
    # Get all active sessions
    all_sessions = await session_manager.list_sessions(include_archived=False)
    
    # Filter to only accessible sessions
    accessible_sessions = []
    for session in all_sessions:
        if await can_access_session(
            session_manager,
            current_session_id,
            session.session_id,
        ):
            accessible_sessions.append({
                "session_id": session.session_id,
                "channel_id": session.channel_id,
                "user_id": session.user_id,
                "chat_id": session.chat_id,
                "session_type": session.session_type,
                "message_count": session.message_count,
                "last_activity": session.last_activity_at,
                "created_at": session.created_at,
            })
    
    logger.info(
        f"Session {current_session_id} listed {len(accessible_sessions)} "
        f"accessible sessions (out of {len(all_sessions)} total)"
    )
    
    return accessible_sessions


async def sessions_history(
    ctx: "RunContext[Any]",
    session_id: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Retrieve message history from another session.
    
    This tool fetches recent messages from a target session, subject to
    permission checks. The current session must have access to the target
    session based on access control rules.
    
    Args:
        ctx: RunContext containing session_manager and session_id in deps
        session_id: ID of the target session to retrieve history from
        limit: Maximum number of messages to return (default: 10, max: 100)
        
    Returns:
        List of message dictionaries in chronological order
        
    Raises:
        PermissionError: If session_tools_enabled is False or access denied
        SessionNotFoundError: If target session does not exist
    """
    session_manager = ctx.deps.session_manager  # type: ignore
    current_session_id = ctx.deps.session_id  # type: ignore
    
    # Validate limit
    if limit < 1:
        limit = 10
    elif limit > 100:
        limit = 100
    
    # Get current session to check permissions
    current_session = await session_manager.get_session(current_session_id)
    
    if not current_session:
        logger.error(f"Current session {current_session_id} not found")
        raise SessionNotFoundError(f"Session {current_session_id} not found")
    
    # Check if session tools are enabled
    if not current_session.session_tools_enabled:
        logger.warning(
            f"Session tools access denied for session {current_session_id}: "
            "session_tools_enabled is False"
        )
        raise PermissionError(
            "Session tools are not enabled for this session. "
            "Contact an administrator to enable inter-session communication."
        )
    
    # Check access permission
    if not await can_access_session(
        session_manager,
        current_session_id,
        session_id,
    ):
        logger.warning(
            f"Session {current_session_id} denied access to session {session_id}"
        )
        raise PermissionError(
            f"You do not have permission to access session {session_id}"
        )
    
    # Get target session
    target_session = await session_manager.get_session(session_id)
    
    if not target_session:
        logger.error(f"Target session {session_id} not found")
        raise SessionNotFoundError(f"Session {session_id} not found")
    
    # Retrieve message history
    messages = await target_session.get_history(limit=limit)
    
    # Format messages for return
    formatted_messages = []
    for msg in messages:
        formatted_messages.append({
            "role": msg["role"],
            "content": msg["content"],
            "created_at": msg["created_at"].timestamp() if msg.get("created_at") else None,
            "metadata": msg.get("metadata", {}),
        })
    
    logger.info(
        f"Session {current_session_id} retrieved {len(formatted_messages)} "
        f"messages from session {session_id}"
    )
    
    return formatted_messages


async def sessions_send(
    ctx: "RunContext[Any]",
    session_id: str,
    message: str,
) -> Dict[str, Any]:
    """Send a message to another session.
    
    This tool delivers a message to a target session as if it came from
    the agent. The message is marked with metadata indicating the source
    session for audit purposes.
    
    Args:
        ctx: RunContext containing session_manager and session_id in deps
        session_id: ID of the target session to send message to
        message: Message content to send
        
    Returns:
        Dictionary with status and session_id
        
    Raises:
        PermissionError: If session_tools_enabled is False or access denied
        SessionNotFoundError: If target session does not exist
    """
    session_manager = ctx.deps.session_manager  # type: ignore
    current_session_id = ctx.deps.session_id  # type: ignore
    
    # Validate message
    if not message or not message.strip():
        raise ValueError("Message cannot be empty")
    
    # Get current session to check permissions
    current_session = await session_manager.get_session(current_session_id)
    
    if not current_session:
        logger.error(f"Current session {current_session_id} not found")
        raise SessionNotFoundError(f"Session {current_session_id} not found")
    
    # Check if session tools are enabled
    if not current_session.session_tools_enabled:
        logger.warning(
            f"Session tools access denied for session {current_session_id}: "
            "session_tools_enabled is False"
        )
        raise PermissionError(
            "Session tools are not enabled for this session. "
            "Contact an administrator to enable inter-session communication."
        )
    
    # Check access permission
    if not await can_access_session(
        session_manager,
        current_session_id,
        session_id,
    ):
        logger.warning(
            f"Session {current_session_id} denied access to session {session_id}"
        )
        raise PermissionError(
            f"You do not have permission to send messages to session {session_id}"
        )
    
    # Get target session
    target_session = await session_manager.get_session(session_id)
    
    if not target_session:
        logger.error(f"Target session {session_id} not found")
        raise SessionNotFoundError(f"Session {session_id} not found")
    
    # Send message to target session
    await target_session.add_message(
        role="system",
        content=message,
        metadata={
            "source_session": current_session_id,
            "inter_session_message": True,
        },
    )
    
    logger.info(
        f"Session {current_session_id} sent message to session {session_id}: "
        f"{message[:100]}..."
    )
    
    return {
        "status": "delivered",
        "session_id": session_id,
        "message_length": len(message),
    }
