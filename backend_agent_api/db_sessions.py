"""Session database queries using asyncpg.

All queries use parameterized inputs ($1, $2, …) to prevent SQL injection.
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)


def generate_session_id(
    channel_id: str,
    user_id: str,
    chat_id: str,
    thread_id: Optional[str] = None,
) -> str:
    """Generate a unique session ID from routing components.
    
    Examples:
        - DM: "telegram-bot1:user123:dm"
        - Group: "discord-main:user456:guild789:channel012"
        - Thread: "slack-main:user789:C123:thread456"
    
    Args:
        channel_id: Channel identifier
        user_id: Platform-specific user ID
        chat_id: DM, group, or thread identifier
        thread_id: Optional thread identifier
        
    Returns:
        Deterministic session ID string
    """
    parts = [channel_id, user_id, chat_id]
    if thread_id:
        parts.append(thread_id)
    return ":".join(parts)


def parse_session_id(session_id: str) -> Dict[str, Optional[str]]:
    """Parse session ID back into components.
    
    Args:
        session_id: Session identifier string
        
    Returns:
        Dictionary with channel_id, user_id, chat_id, and optional thread_id
    """
    parts = session_id.split(":")
    return {
        "channel_id": parts[0],
        "user_id": parts[1],
        "chat_id": parts[2],
        "thread_id": parts[3] if len(parts) > 3 else None,
    }


async def create_session(
    pool: asyncpg.Pool,
    session_id: str,
    channel_id: str,
    user_id: str,
    chat_id: str,
    session_type: str,
    activation_mode: str = "mention",
    tool_allowlist: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Insert a new session and return the created row.
    
    Args:
        pool: Database connection pool
        session_id: Unique session identifier
        channel_id: Channel identifier
        user_id: Platform-specific user ID
        chat_id: DM, group, or thread identifier
        session_type: Type of session (main, group, webhook)
        activation_mode: Activation mode (mention, always, manual)
        tool_allowlist: List of allowed tools (default: all tools allowed)
        
    Returns:
        Dictionary containing the created session row
    """
    if tool_allowlist is None:
        tool_allowlist = ["*"]
    
    tool_allowlist_json = json.dumps(tool_allowlist)
    
    row = await pool.fetchrow(
        """
        INSERT INTO sessions (
            session_id, channel_id, user_id, chat_id, session_type,
            activation_mode, tool_allowlist
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        RETURNING *
        """,
        session_id,
        channel_id,
        user_id,
        chat_id,
        session_type,
        activation_mode,
        tool_allowlist_json,
    )
    return dict(row)


async def get_session(
    pool: asyncpg.Pool,
    session_id: str,
) -> Optional[Dict[str, Any]]:
    """Fetch a session by ID.
    
    Args:
        pool: Database connection pool
        session_id: Unique session identifier
        
    Returns:
        Dictionary containing the session row, or None if not found
    """
    row = await pool.fetchrow(
        """
        SELECT * FROM sessions
        WHERE session_id = $1
        """,
        session_id,
    )
    return dict(row) if row else None


async def get_or_create_session(
    pool: asyncpg.Pool,
    session_id: str,
    channel_id: str,
    user_id: str,
    chat_id: str,
    session_type: str,
    activation_mode: str = "mention",
    tool_allowlist: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Get an existing session or create a new one if it doesn't exist.
    
    This implements idempotent session creation.
    
    Args:
        pool: Database connection pool
        session_id: Unique session identifier
        channel_id: Channel identifier
        user_id: Platform-specific user ID
        chat_id: DM, group, or thread identifier
        session_type: Type of session (main, group, webhook)
        activation_mode: Activation mode (mention, always, manual)
        tool_allowlist: List of allowed tools (default: all tools allowed)
        
    Returns:
        Dictionary containing the session row
    """
    existing = await get_session(pool, session_id)
    if existing:
        return existing
    
    return await create_session(
        pool,
        session_id,
        channel_id,
        user_id,
        chat_id,
        session_type,
        activation_mode,
        tool_allowlist,
    )


async def list_sessions(
    pool: asyncpg.Pool,
    channel_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_type: Optional[str] = None,
    include_archived: bool = False,
) -> List[Dict[str, Any]]:
    """List sessions with optional filters.
    
    Args:
        pool: Database connection pool
        channel_id: Optional filter by channel
        user_id: Optional filter by user
        session_type: Optional filter by session type
        include_archived: If True, include archived sessions
        
    Returns:
        List of session dictionaries
    """
    conditions = []
    params = []
    param_count = 1
    
    if channel_id:
        conditions.append(f"channel_id = ${param_count}")
        params.append(channel_id)
        param_count += 1
    
    if user_id:
        conditions.append(f"user_id = ${param_count}")
        params.append(user_id)
        param_count += 1
    
    if session_type:
        conditions.append(f"session_type = ${param_count}")
        params.append(session_type)
        param_count += 1
    
    if not include_archived:
        conditions.append("archived_at IS NULL")
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    
    query = f"""
        SELECT * FROM sessions
        {where_clause}
        ORDER BY last_activity_at DESC
    """
    
    rows = await pool.fetch(query, *params)
    return [dict(row) for row in rows]


async def update_session_activation_mode(
    pool: asyncpg.Pool,
    session_id: str,
    activation_mode: str,
) -> None:
    """Update a session's activation mode.
    
    Args:
        pool: Database connection pool
        session_id: Unique session identifier
        activation_mode: New activation mode (mention, always, manual)
    """
    await pool.execute(
        """
        UPDATE sessions
        SET activation_mode = $1
        WHERE session_id = $2
        """,
        activation_mode,
        session_id,
    )


async def update_session_tool_allowlist(
    pool: asyncpg.Pool,
    session_id: str,
    tool_allowlist: List[str],
) -> None:
    """Update a session's tool allowlist.
    
    Args:
        pool: Database connection pool
        session_id: Unique session identifier
        tool_allowlist: New list of allowed tools
    """
    tool_allowlist_json = json.dumps(tool_allowlist)
    
    await pool.execute(
        """
        UPDATE sessions
        SET tool_allowlist = $1::jsonb
        WHERE session_id = $2
        """,
        tool_allowlist_json,
        session_id,
    )


async def update_session_token_usage(
    pool: asyncpg.Pool,
    session_id: str,
    token_usage: Dict[str, Any],
) -> None:
    """Update a session's token usage statistics.
    
    Args:
        pool: Database connection pool
        session_id: Unique session identifier
        token_usage: Token usage statistics
    """
    token_usage_json = json.dumps(token_usage)
    
    await pool.execute(
        """
        UPDATE sessions
        SET token_usage = $1::jsonb
        WHERE session_id = $2
        """,
        token_usage_json,
        session_id,
    )


async def archive_session(
    pool: asyncpg.Pool,
    session_id: str,
) -> None:
    """Archive a session by setting archived_at timestamp.
    
    Args:
        pool: Database connection pool
        session_id: Unique session identifier
    """
    await pool.execute(
        """
        UPDATE sessions
        SET archived_at = NOW()
        WHERE session_id = $1
        """,
        session_id,
    )


async def delete_session(
    pool: asyncpg.Pool,
    session_id: str,
) -> None:
    """Delete a session and all its messages.
    
    Note: This will cascade delete all session_messages due to foreign key.
    
    Args:
        pool: Database connection pool
        session_id: Unique session identifier
    """
    await pool.execute(
        """
        DELETE FROM sessions
        WHERE session_id = $1
        """,
        session_id,
    )


async def add_session_message(
    pool: asyncpg.Pool,
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Add a message to a session.
    
    This automatically updates the session's last_activity_at and message_count
    via the update_session_activity trigger.
    
    Args:
        pool: Database connection pool
        session_id: Unique session identifier
        role: Message role (user, assistant, system)
        content: Message content
        metadata: Optional metadata (attachments, tool calls, etc.)
        
    Returns:
        Dictionary containing the created message row
    """
    if metadata is None:
        metadata = {}
    
    metadata_json = json.dumps(metadata)
    
    row = await pool.fetchrow(
        """
        INSERT INTO session_messages (session_id, role, content, metadata)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING *
        """,
        session_id,
        role,
        content,
        metadata_json,
    )
    return dict(row)


async def get_session_messages(
    pool: asyncpg.Pool,
    session_id: str,
    limit: int = 50,
    role: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch messages for a session ordered by created_at ascending.
    
    Args:
        pool: Database connection pool
        session_id: Unique session identifier
        limit: Maximum number of messages to return
        role: Optional filter by message role
        
    Returns:
        List of message dictionaries
    """
    if role:
        query = """
            SELECT * FROM session_messages
            WHERE session_id = $1 AND role = $2
            ORDER BY created_at ASC
            LIMIT $3
        """
        rows = await pool.fetch(query, session_id, role, limit)
    else:
        query = """
            SELECT * FROM session_messages
            WHERE session_id = $1
            ORDER BY created_at ASC
            LIMIT $2
        """
        rows = await pool.fetch(query, session_id, limit)
    
    return [dict(row) for row in rows]


async def clear_session_messages(
    pool: asyncpg.Pool,
    session_id: str,
) -> None:
    """Clear all messages from a session (for /reset command).
    
    Args:
        pool: Database connection pool
        session_id: Unique session identifier
    """
    await pool.execute(
        """
        DELETE FROM session_messages
        WHERE session_id = $1
        """,
        session_id,
    )
    
    # Reset message count
    await pool.execute(
        """
        UPDATE sessions
        SET message_count = 0
        WHERE session_id = $1
        """,
        session_id,
    )


async def get_session_message_count(
    pool: asyncpg.Pool,
    session_id: str,
) -> int:
    """Get the total number of messages in a session.
    
    Args:
        pool: Database connection pool
        session_id: Unique session identifier
        
    Returns:
        Total message count
    """
    row = await pool.fetchrow(
        """
        SELECT message_count FROM sessions
        WHERE session_id = $1
        """,
        session_id,
    )
    return row["message_count"] if row else 0
