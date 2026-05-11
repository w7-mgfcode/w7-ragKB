"""Web user, refresh token, and password reset token database queries.

All queries use parameterized inputs ($1, $2, …) to prevent SQL injection.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

import asyncpg

logger = logging.getLogger(__name__)


async def create_web_user(
    pool: asyncpg.Pool,
    email: str,
    password_hash: str,
) -> Dict[str, Any]:
    """Insert a new web user and return the created row."""
    row = await pool.fetchrow(
        """
        INSERT INTO web_users (email, password_hash)
        VALUES ($1, $2)
        RETURNING *
        """,
        email,
        password_hash,
    )
    return dict(row)


async def get_web_user_by_email(
    pool: asyncpg.Pool,
    email: str,
) -> Optional[Dict[str, Any]]:
    """Return the web user row matching the email, or None."""
    row = await pool.fetchrow(
        """
        SELECT * FROM web_users WHERE email = $1
        """,
        email,
    )
    return dict(row) if row else None


async def get_web_user_by_id(
    pool: asyncpg.Pool,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """Return the web user row matching the UUID, or None."""
    row = await pool.fetchrow(
        """
        SELECT * FROM web_users WHERE id = $1
        """,
        user_id,
    )
    return dict(row) if row else None


async def list_web_users(pool: asyncpg.Pool) -> list[Dict[str, Any]]:
    """Return all web users for admin management."""
    rows = await pool.fetch(
        """
        SELECT id, email, full_name, is_admin, created_at, updated_at
        FROM web_users
        ORDER BY created_at DESC
        """
    )
    return [dict(r) for r in rows]


async def admin_update_web_user(
    pool: asyncpg.Pool,
    user_id: str,
    email: str,
    full_name: Optional[str],
    is_admin: bool,
) -> Optional[Dict[str, Any]]:
    """Admin update of email/name/admin flag."""
    row = await pool.fetchrow(
        """
        UPDATE web_users
        SET email = $2,
            full_name = $3,
            is_admin = $4,
            updated_at = NOW()
        WHERE id = $1
        RETURNING id, email, full_name, is_admin, created_at, updated_at
        """,
        user_id,
        email,
        full_name,
        is_admin,
    )
    return dict(row) if row else None


async def update_web_user_profile(
    pool: asyncpg.Pool,
    user_id: str,
    full_name: Optional[str],
    avatar_url: Optional[str],
) -> Dict[str, Any]:
    """Update profile fields and return the updated row."""
    row = await pool.fetchrow(
        """
        UPDATE web_users
        SET full_name = $2, avatar_url = $3, updated_at = NOW()
        WHERE id = $1
        RETURNING *
        """,
        user_id,
        full_name,
        avatar_url,
    )
    return dict(row)


async def update_web_user_password(
    pool: asyncpg.Pool,
    user_id: str,
    password_hash: str,
) -> None:
    """Update the password hash for a user."""
    await pool.execute(
        """
        UPDATE web_users
        SET password_hash = $2, updated_at = NOW()
        WHERE id = $1
        """,
        user_id,
        password_hash,
    )


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------


async def store_refresh_token(
    pool: asyncpg.Pool,
    user_id: str,
    token_hash: str,
    expires_at: datetime,
) -> Dict[str, Any]:
    """Insert a refresh token and return the created row."""
    row = await pool.fetchrow(
        """
        INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        user_id,
        token_hash,
        expires_at,
    )
    return dict(row)


async def get_refresh_token(
    pool: asyncpg.Pool,
    token_hash: str,
) -> Optional[Dict[str, Any]]:
    """Return the refresh token row matching the hash, or None."""
    row = await pool.fetchrow(
        """
        SELECT * FROM refresh_tokens WHERE token_hash = $1
        """,
        token_hash,
    )
    return dict(row) if row else None


async def delete_refresh_token(
    pool: asyncpg.Pool,
    token_hash: str,
) -> None:
    """Remove a single refresh token by its hash."""
    await pool.execute(
        """
        DELETE FROM refresh_tokens WHERE token_hash = $1
        """,
        token_hash,
    )


async def delete_all_refresh_tokens(
    pool: asyncpg.Pool,
    user_id: str,
) -> None:
    """Remove all refresh tokens for a user (used on logout / password reset)."""
    await pool.execute(
        """
        DELETE FROM refresh_tokens WHERE user_id = $1
        """,
        user_id,
    )


# ---------------------------------------------------------------------------
# Password reset tokens
# ---------------------------------------------------------------------------


async def store_reset_token(
    pool: asyncpg.Pool,
    user_id: str,
    token_hash: str,
    expires_at: datetime,
) -> Dict[str, Any]:
    """Insert a password reset token and return the created row."""
    row = await pool.fetchrow(
        """
        INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        user_id,
        token_hash,
        expires_at,
    )
    return dict(row)


async def get_reset_token(
    pool: asyncpg.Pool,
    token_hash: str,
) -> Optional[Dict[str, Any]]:
    """Return the password reset token row matching the hash, or None."""
    row = await pool.fetchrow(
        """
        SELECT * FROM password_reset_tokens WHERE token_hash = $1
        """,
        token_hash,
    )
    return dict(row) if row else None


async def mark_reset_token_used(
    pool: asyncpg.Pool,
    token_id: str,
) -> None:
    """Mark a password reset token as used."""
    await pool.execute(
        """
        UPDATE password_reset_tokens
        SET used = TRUE
        WHERE id = $1
        """,
        token_id,
    )


# ---------------------------------------------------------------------------
# Google OAuth users
# ---------------------------------------------------------------------------


async def create_or_update_google_user(
    pool: asyncpg.Pool,
    email: str,
    full_name: Optional[str],
    avatar_url: Optional[str],
) -> Dict[str, Any]:
    """Create a new user or update an existing one for Google OAuth sign-in.

    Uses ON CONFLICT on email to upsert profile fields. password_hash stays
    NULL for OAuth-only accounts.
    """
    row = await pool.fetchrow(
        """
        INSERT INTO web_users (email, full_name, avatar_url)
        VALUES ($1, $2, $3)
        ON CONFLICT (email) DO UPDATE
            SET full_name  = COALESCE(EXCLUDED.full_name, web_users.full_name),
                avatar_url = COALESCE(EXCLUDED.avatar_url, web_users.avatar_url),
                updated_at = NOW()
        RETURNING *
        """,
        email,
        full_name,
        avatar_url,
    )
    return dict(row)
