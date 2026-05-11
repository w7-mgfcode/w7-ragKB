"""Webhook database queries using asyncpg.

All queries use parameterized inputs ($1, $2, …) to prevent SQL injection.
"""

import json
import logging
import secrets
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)


def generate_webhook_id() -> str:
    """Generate a unique webhook ID.
    
    Returns:
        Random 16-character hex string
    """
    return secrets.token_hex(8)


def generate_webhook_url(webhook_id: str, base_url: str = "/api/webhooks") -> str:
    """Generate a webhook URL from a webhook ID.
    
    Args:
        webhook_id: Unique webhook identifier
        base_url: Base URL for webhooks
        
    Returns:
        Full webhook URL path
    """
    return f"{base_url}/{webhook_id}"


def generate_auth_token() -> str:
    """Generate a secure authentication token for webhooks.
    
    Returns:
        Random 32-character hex string
    """
    return secrets.token_hex(16)


async def create_webhook(
    pool: asyncpg.Pool,
    target_session_id: str,
    payload_schema: Optional[Dict[str, Any]] = None,
    transform_rules: Optional[Dict[str, Any]] = None,
    enabled: bool = True,
    base_url: str = "/api/webhooks",
) -> Dict[str, Any]:
    """Create a new webhook and return the created row.
    
    Args:
        pool: Database connection pool
        target_session_id: Session ID to route webhook messages to
        payload_schema: Optional JSON schema for payload validation
        transform_rules: Optional transformation rules for payload
        enabled: Whether the webhook is enabled
        base_url: Base URL for webhook endpoints
        
    Returns:
        Dictionary containing the created webhook row with webhook_url and auth_token
    """
    webhook_id = generate_webhook_id()
    webhook_url = generate_webhook_url(webhook_id, base_url)
    auth_token = generate_auth_token()
    
    if transform_rules is None:
        transform_rules = {}
    
    payload_schema_json = json.dumps(payload_schema) if payload_schema else None
    transform_rules_json = json.dumps(transform_rules)
    
    row = await pool.fetchrow(
        """
        INSERT INTO webhooks (
            webhook_id, webhook_url, target_session_id, auth_token,
            payload_schema, transform_rules, enabled
        )
        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
        RETURNING *
        """,
        webhook_id,
        webhook_url,
        target_session_id,
        auth_token,
        payload_schema_json,
        transform_rules_json,
        enabled,
    )
    return dict(row)


async def get_webhook(
    pool: asyncpg.Pool,
    webhook_id: str,
) -> Optional[Dict[str, Any]]:
    """Fetch a webhook by ID.
    
    Args:
        pool: Database connection pool
        webhook_id: Unique webhook identifier
        
    Returns:
        Dictionary containing the webhook row, or None if not found
    """
    row = await pool.fetchrow(
        """
        SELECT * FROM webhooks
        WHERE webhook_id = $1
        """,
        webhook_id,
    )
    return dict(row) if row else None


async def get_webhook_by_url(
    pool: asyncpg.Pool,
    webhook_url: str,
) -> Optional[Dict[str, Any]]:
    """Fetch a webhook by URL.
    
    Args:
        pool: Database connection pool
        webhook_url: Webhook URL path
        
    Returns:
        Dictionary containing the webhook row, or None if not found
    """
    row = await pool.fetchrow(
        """
        SELECT * FROM webhooks
        WHERE webhook_url = $1
        """,
        webhook_url,
    )
    return dict(row) if row else None


async def list_webhooks(
    pool: asyncpg.Pool,
    target_session_id: Optional[str] = None,
    enabled_only: bool = False,
) -> List[Dict[str, Any]]:
    """List webhooks with optional filters.
    
    Args:
        pool: Database connection pool
        target_session_id: Optional filter by target session
        enabled_only: If True, only return enabled webhooks
        
    Returns:
        List of webhook dictionaries
    """
    conditions = []
    params = []
    param_count = 1
    
    if target_session_id:
        conditions.append(f"target_session_id = ${param_count}")
        params.append(target_session_id)
        param_count += 1
    
    if enabled_only:
        conditions.append("enabled = TRUE")
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    
    query = f"""
        SELECT * FROM webhooks
        {where_clause}
        ORDER BY created_at DESC
    """
    
    rows = await pool.fetch(query, *params)
    return [dict(row) for row in rows]


async def update_webhook_enabled(
    pool: asyncpg.Pool,
    webhook_id: str,
    enabled: bool,
) -> None:
    """Enable or disable a webhook.
    
    Args:
        pool: Database connection pool
        webhook_id: Unique webhook identifier
        enabled: Whether the webhook should be enabled
    """
    await pool.execute(
        """
        UPDATE webhooks
        SET enabled = $1
        WHERE webhook_id = $2
        """,
        enabled,
        webhook_id,
    )


async def update_webhook_transform_rules(
    pool: asyncpg.Pool,
    webhook_id: str,
    transform_rules: Dict[str, Any],
) -> None:
    """Update a webhook's transformation rules.
    
    Args:
        pool: Database connection pool
        webhook_id: Unique webhook identifier
        transform_rules: New transformation rules
    """
    transform_rules_json = json.dumps(transform_rules)
    
    await pool.execute(
        """
        UPDATE webhooks
        SET transform_rules = $1::jsonb
        WHERE webhook_id = $2
        """,
        transform_rules_json,
        webhook_id,
    )


async def update_webhook_last_triggered(
    pool: asyncpg.Pool,
    webhook_id: str,
) -> None:
    """Update a webhook's last_triggered_at timestamp.
    
    Args:
        pool: Database connection pool
        webhook_id: Unique webhook identifier
    """
    await pool.execute(
        """
        UPDATE webhooks
        SET last_triggered_at = NOW()
        WHERE webhook_id = $1
        """,
        webhook_id,
    )


async def delete_webhook(
    pool: asyncpg.Pool,
    webhook_id: str,
) -> None:
    """Delete a webhook.
    
    Args:
        pool: Database connection pool
        webhook_id: Unique webhook identifier
    """
    await pool.execute(
        """
        DELETE FROM webhooks
        WHERE webhook_id = $1
        """,
        webhook_id,
    )


async def verify_webhook_auth(
    pool: asyncpg.Pool,
    webhook_url: str,
    auth_token: str,
) -> Optional[Dict[str, Any]]:
    """Verify a webhook's authentication token and return the webhook if valid.
    
    Args:
        pool: Database connection pool
        webhook_url: Webhook URL path
        auth_token: Authentication token to verify
        
    Returns:
        Dictionary containing the webhook row if auth is valid, None otherwise
    """
    row = await pool.fetchrow(
        """
        SELECT * FROM webhooks
        WHERE webhook_url = $1 AND auth_token = $2 AND enabled = TRUE
        """,
        webhook_url,
        auth_token,
    )
    return dict(row) if row else None
