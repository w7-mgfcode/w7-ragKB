"""Conversation and message database queries using asyncpg.

All queries use parameterized inputs ($1, $2, …) to prevent SQL injection.
"""

import hashlib
import inspect
import json
import logging
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)


def generate_session_id(channel_id: str, thread_ts: str) -> str:
    """Derive a deterministic session ID from a Slack channel and thread timestamp.

    Returns a 16-character hex string (first 8 bytes of the SHA-256 digest).
    """
    raw = f"{channel_id}:{thread_ts}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def ensure_slack_user(
    pool: asyncpg.Pool,
    slack_id: str,
    display_name: Optional[str] = None,
) -> None:
    """Upsert a Slack user into the slack_users table.

    Inserts the user if they don't exist, or updates display_name and
    updated_at if they do.
    """
    await pool.execute(
        """
        INSERT INTO slack_users (slack_id, display_name)
        VALUES ($1, $2)
        ON CONFLICT (slack_id) DO UPDATE
            SET display_name = COALESCE(EXCLUDED.display_name, slack_users.display_name),
                updated_at   = NOW()
        """,
        slack_id,
        display_name,
    )


async def create_conversation(
    pool: asyncpg.Pool,
    slack_user_id: str,
    session_id: str,
    slack_channel_id: str,
) -> Dict[str, Any]:
    """Insert a new conversation and return the created row."""
    row = await pool.fetchrow(
        """
        INSERT INTO conversations (session_id, slack_user_id, slack_channel_id)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        session_id,
        slack_user_id,
        slack_channel_id,
    )
    return dict(row)


async def fetch_conversation_history(
    pool: asyncpg.Pool,
    session_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Fetch messages for a session ordered by created_at ascending.

    JSONB ``message`` values that arrive as strings are parsed into dicts.
    """
    rows = await pool.fetch(
        """
        SELECT id, session_id, message, message_data, created_at
        FROM messages
        WHERE session_id = $1
        ORDER BY created_at ASC
        LIMIT $2
        """,
        session_id,
        limit,
    )
    results: List[Dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        # asyncpg normally returns JSONB as a dict, but handle string edge case
        msg = record.get("message")
        if isinstance(msg, str):
            record["message"] = json.loads(msg)
        results.append(record)
    return results


async def update_conversation_title(
    pool: asyncpg.Pool,
    session_id: str,
    title: str,
) -> None:
    """Update the title and last_message_at timestamp of a conversation."""
    await pool.execute(
        """
        UPDATE conversations
        SET title = $1, last_message_at = NOW()
        WHERE session_id = $2
        """,
        title,
        session_id,
    )


async def store_message(
    pool: asyncpg.Pool,
    session_id: str,
    message_type: str,
    content: str,
    message_data: Optional[str] = None,
    data: Optional[Dict] = None,
    files: Optional[List[Dict[str, str]]] = None,
    trace_id: Optional[str] = None,
) -> None:
    """Store a message and update the conversation's last_message_at.

    Runs both statements inside a transaction so they succeed or fail together.
    """
    message_obj: Dict[str, Any] = {
        "type": message_type,
        "content": content,
    }
    if data is not None:
        message_obj["data"] = data
    if files is not None:
        message_obj["files"] = files
    if trace_id is not None:
        message_obj["trace_id"] = trace_id

    message_json = json.dumps(message_obj)

    async def _write_with_conn(conn) -> None:
        tr = conn.transaction()
        # asyncpg transaction() is synchronous, but handle coroutine wrappers
        if inspect.isawaitable(tr):
            tr = await tr
        async with tr:
            await conn.execute(
                """
                INSERT INTO messages (session_id, message, message_data)
                VALUES ($1, $2::jsonb, $3)
                """,
                session_id,
                message_json,
                message_data,
            )
            await conn.execute(
                """
                UPDATE conversations
                SET last_message_at = NOW()
                WHERE session_id = $1
                """,
                session_id,
            )

    acquired = pool.acquire()
    # asyncpg: pool.acquire() returns an async context manager.
    # Some tests/mocks may return an awaitable that resolves either
    # to an async context manager or a raw connection proxy.
    if hasattr(acquired, "__aenter__") and hasattr(acquired, "__aexit__"):
        async with acquired as conn:
            await _write_with_conn(conn)
        return

    if inspect.isawaitable(acquired):
        acquired = await acquired

    if hasattr(acquired, "__aenter__") and hasattr(acquired, "__aexit__"):
        async with acquired as conn:
            await _write_with_conn(conn)
        return

    await _write_with_conn(acquired)
