"""Conversation and message REST endpoints for web frontend users.

Provides authenticated access to conversations and messages filtered
by the requesting user's web_user_id.
"""

import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_middleware import get_current_user
from db import get_pool

logger = logging.getLogger(__name__)

router = APIRouter()


class ConversationResponse(BaseModel):
    session_id: str
    title: str | None
    created_at: str
    last_message_at: str


class MessageResponse(BaseModel):
    id: int
    session_id: str
    message: dict
    created_at: str


@router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Return all conversations belonging to the authenticated web user.

    Ordered by last_message_at descending (most recent first).
    """
    pool = await get_pool()
    user_id = str(current_user["sub"])
    rows = await pool.fetch(
        """
        SELECT session_id, title, created_at, last_message_at
        FROM conversations
        WHERE web_user_id = $1
        ORDER BY last_message_at DESC
        """,
        user_id,
    )
    return [
        {
            "session_id": row["session_id"],
            "title": row["title"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            "last_message_at": row["last_message_at"].isoformat() if row["last_message_at"] else "",
        }
        for row in rows
    ]


@router.get(
    "/conversations/{session_id}/messages",
    response_model=List[MessageResponse],
)
async def list_messages(
    session_id: str,
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Return all messages for a conversation session.

    Verifies the session belongs to the requesting user (403 if not).
    Messages are ordered by created_at ascending.
    """
    pool = await get_pool()
    user_id = str(current_user["sub"])

    # Verify the conversation belongs to this user
    conv = await pool.fetchrow(
        """
        SELECT web_user_id FROM conversations WHERE session_id = $1
        """,
        session_id,
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="Not Found")
    if str(conv["web_user_id"]) != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    rows = await pool.fetch(
        """
        SELECT id, session_id, message, created_at
        FROM messages
        WHERE session_id = $1
        ORDER BY created_at ASC
        """,
        session_id,
    )
    results = []
    for row in rows:
        msg = row["message"]
        if isinstance(msg, str):
            msg = json.loads(msg)
        results.append(
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "message": msg,
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            }
        )
    return results
