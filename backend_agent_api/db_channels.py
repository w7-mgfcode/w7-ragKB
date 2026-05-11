"""Channel database queries using asyncpg.

All queries use parameterized inputs ($1, $2, …) to prevent SQL injection.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)


async def create_channel(
    pool: asyncpg.Pool,
    channel_id: str,
    channel_type: str,
    config: Dict[str, Any],
    enabled: bool = True,
) -> Dict[str, Any]:
    """Insert a new channel and return the created row.
    
    Args:
        pool: Database connection pool
        channel_id: Unique identifier for the channel (e.g., "slack-main", "telegram-bot1")
        channel_type: Type of channel (slack, telegram, discord, whatsapp)
        config: Channel configuration (API tokens, webhook URLs, rate limits)
        enabled: Whether the channel is enabled
        
    Returns:
        Dictionary containing the created channel row
    """
    config_json = json.dumps(config)
    
    row = await pool.fetchrow(
        """
        INSERT INTO channels (channel_id, channel_type, config, enabled)
        VALUES ($1, $2, $3::jsonb, $4)
        RETURNING *
        """,
        channel_id,
        channel_type,
        config_json,
        enabled,
    )
    return dict(row)


async def get_channel(
    pool: asyncpg.Pool,
    channel_id: str,
) -> Optional[Dict[str, Any]]:
    """Fetch a channel by ID.
    
    Args:
        pool: Database connection pool
        channel_id: Unique identifier for the channel
        
    Returns:
        Dictionary containing the channel row, or None if not found
    """
    row = await pool.fetchrow(
        """
        SELECT * FROM channels
        WHERE channel_id = $1
        """,
        channel_id,
    )
    return dict(row) if row else None


async def list_channels(
    pool: asyncpg.Pool,
    channel_type: Optional[str] = None,
    enabled_only: bool = False,
) -> List[Dict[str, Any]]:
    """List all channels, optionally filtered by type and enabled status.
    
    Args:
        pool: Database connection pool
        channel_type: Optional filter by channel type
        enabled_only: If True, only return enabled channels
        
    Returns:
        List of channel dictionaries
    """
    conditions = []
    params = []
    param_count = 1
    
    if channel_type:
        conditions.append(f"channel_type = ${param_count}")
        params.append(channel_type)
        param_count += 1
    
    if enabled_only:
        conditions.append("enabled = TRUE")
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    
    query = f"""
        SELECT * FROM channels
        {where_clause}
        ORDER BY created_at DESC
    """
    
    rows = await pool.fetch(query, *params)
    return [dict(row) for row in rows]


async def update_channel_config(
    pool: asyncpg.Pool,
    channel_id: str,
    config: Dict[str, Any],
) -> None:
    """Update a channel's configuration.
    
    Args:
        pool: Database connection pool
        channel_id: Unique identifier for the channel
        config: New channel configuration
    """
    config_json = json.dumps(config)
    
    await pool.execute(
        """
        UPDATE channels
        SET config = $1::jsonb, updated_at = NOW()
        WHERE channel_id = $2
        """,
        config_json,
        channel_id,
    )


async def update_channel_enabled(
    pool: asyncpg.Pool,
    channel_id: str,
    enabled: bool,
) -> None:
    """Enable or disable a channel.
    
    Args:
        pool: Database connection pool
        channel_id: Unique identifier for the channel
        enabled: Whether the channel should be enabled
    """
    await pool.execute(
        """
        UPDATE channels
        SET enabled = $1, updated_at = NOW()
        WHERE channel_id = $2
        """,
        enabled,
        channel_id,
    )


async def delete_channel(
    pool: asyncpg.Pool,
    channel_id: str,
) -> None:
    """Delete a channel.
    
    Note: This will fail if there are sessions referencing this channel
    due to foreign key constraints.
    
    Args:
        pool: Database connection pool
        channel_id: Unique identifier for the channel
    """
    await pool.execute(
        """
        DELETE FROM channels
        WHERE channel_id = $1
        """,
        channel_id,
    )


async def ensure_channel_user(
    pool: asyncpg.Pool,
    channel_id: str,
    user_id: str,
    user_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Upsert a channel user into the channel_users table.
    
    Inserts the user if they don't exist, or updates user_name if they do.
    
    Args:
        pool: Database connection pool
        channel_id: Channel identifier
        user_id: Platform-specific user ID
        user_name: Optional user display name
        
    Returns:
        Dictionary containing the channel user row
    """
    channel_user_id = f"{channel_id}:{user_id}"
    
    row = await pool.fetchrow(
        """
        INSERT INTO channel_users (channel_user_id, channel_id, user_id, user_name)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (channel_user_id) DO UPDATE
            SET user_name = COALESCE(EXCLUDED.user_name, channel_users.user_name)
        RETURNING *
        """,
        channel_user_id,
        channel_id,
        user_id,
        user_name,
    )
    return dict(row)


async def get_channel_user(
    pool: asyncpg.Pool,
    channel_id: str,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """Fetch a channel user by channel and user ID.
    
    Args:
        pool: Database connection pool
        channel_id: Channel identifier
        user_id: Platform-specific user ID
        
    Returns:
        Dictionary containing the channel user row, or None if not found
    """
    channel_user_id = f"{channel_id}:{user_id}"
    
    row = await pool.fetchrow(
        """
        SELECT * FROM channel_users
        WHERE channel_user_id = $1
        """,
        channel_user_id,
    )
    return dict(row) if row else None


async def update_channel_user_approval(
    pool: asyncpg.Pool,
    channel_id: str,
    user_id: str,
    approved: bool,
    approval_code: Optional[str] = None,
    approval_code_expires_at: Optional[str] = None,
) -> None:
    """Update a channel user's approval status and code.
    
    Args:
        pool: Database connection pool
        channel_id: Channel identifier
        user_id: Platform-specific user ID
        approved: Whether the user is approved
        approval_code: Optional approval code
        approval_code_expires_at: Optional approval code expiration timestamp
    """
    channel_user_id = f"{channel_id}:{user_id}"
    
    await pool.execute(
        """
        UPDATE channel_users
        SET approved = $1,
            approval_code = $2,
            approval_code_expires_at = $3
        WHERE channel_user_id = $4
        """,
        approved,
        approval_code,
        approval_code_expires_at,
        channel_user_id,
    )


async def list_channel_users(
    pool: asyncpg.Pool,
    channel_id: str,
    approved_only: bool = False,
) -> List[Dict[str, Any]]:
    """List all users for a channel.
    
    Args:
        pool: Database connection pool
        channel_id: Channel identifier
        approved_only: If True, only return approved users
        
    Returns:
        List of channel user dictionaries
    """
    where_clause = "WHERE channel_id = $1"
    if approved_only:
        where_clause += " AND approved = TRUE"
    
    query = f"""
        SELECT * FROM channel_users
        {where_clause}
        ORDER BY created_at DESC
    """
    
    rows = await pool.fetch(query, channel_id)
    return [dict(row) for row in rows]
