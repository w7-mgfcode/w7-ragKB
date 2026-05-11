"""Admin endpoints for web frontend users."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr

from auth_middleware import get_current_user
from db import get_pool
from db_web_users import admin_update_web_user, get_web_user_by_id, list_web_users

logger = logging.getLogger(__name__)

router = APIRouter()


class AdminStatusResponse(BaseModel):
    is_admin: bool


class AdminUserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    is_admin: bool


class AdminUserUpdateRequest(BaseModel):
    email: EmailStr
    full_name: str | None = None
    is_admin: bool


class AdminConversationResponse(BaseModel):
    id: str
    session_id: str
    title: str | None
    user_id: str | None
    created_at: str
    last_message_at: str


class AdminMessageResponse(BaseModel):
    id: int
    session_id: str
    message: dict
    created_at: str


async def _require_admin(current_user: dict) -> dict:
    """Return DB user row for current user and enforce admin access."""
    pool = await get_pool()
    user = await get_web_user_by_id(pool, current_user["sub"])
    if user is None:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/status", response_model=AdminStatusResponse)
async def get_admin_status(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Return the is_admin flag for the authenticated user.

    Looks up the web_users row by the JWT subject claim and returns
    the admin status. Returns 403 if the user record is not found.
    """
    pool = await get_pool()
    user_id = current_user["sub"]

    user = await get_web_user_by_id(pool, user_id)
    if user is None:
        raise HTTPException(status_code=403, detail="Forbidden")

    return {"is_admin": user["is_admin"]}


@router.get("/users", response_model=list[AdminUserResponse])
async def get_admin_users(
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """List all web users (admin only)."""
    await _require_admin(current_user)
    pool = await get_pool()
    users = await list_web_users(pool)
    return [
        {
            "id": str(u["id"]),
            "email": u["email"],
            "full_name": u.get("full_name"),
            "is_admin": bool(u.get("is_admin", False)),
        }
        for u in users
    ]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def patch_admin_user(
    user_id: str,
    body: AdminUserUpdateRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Update a user profile/admin flag (admin only)."""
    await _require_admin(current_user)
    pool = await get_pool()
    updated = await admin_update_web_user(
        pool,
        user_id=user_id,
        email=body.email,
        full_name=body.full_name,
        is_admin=body.is_admin,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": str(updated["id"]),
        "email": updated["email"],
        "full_name": updated.get("full_name"),
        "is_admin": bool(updated.get("is_admin", False)),
    }


@router.get("/conversations", response_model=list[AdminConversationResponse])
async def list_admin_conversations(
    sort: str = Query(default="desc"),
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """List all conversations for admin UI."""
    await _require_admin(current_user)
    pool = await get_pool()
    order = "ASC" if sort.lower() == "asc" else "DESC"
    rows = await pool.fetch(
        f"""
        SELECT
            session_id,
            title,
            COALESCE(web_user_id::text, slack_user_id) AS user_id,
            created_at,
            last_message_at
        FROM conversations
        ORDER BY created_at {order}
        """
    )
    return [
        {
            "id": r["session_id"],
            "session_id": r["session_id"],
            "title": r["title"],
            "user_id": r["user_id"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else "",
            "last_message_at": r["last_message_at"].isoformat() if r["last_message_at"] else "",
        }
        for r in rows
    ]


@router.get(
    "/conversations/{session_id}/messages",
    response_model=list[AdminMessageResponse],
)
async def list_admin_conversation_messages(
    session_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """List messages for any conversation (admin only)."""
    await _require_admin(current_user)
    pool = await get_pool()

    exists = await pool.fetchval(
        "SELECT 1 FROM conversations WHERE session_id = $1",
        session_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Conversation not found")

    rows = await pool.fetch(
        """
        SELECT id, session_id, message, created_at
        FROM messages
        WHERE session_id = $1
        ORDER BY created_at ASC
        """,
        session_id,
    )
    return [
        {
            "id": r["id"],
            "session_id": r["session_id"],
            "message": r["message"]
            if isinstance(r["message"], dict)
            else json.loads(r["message"]) if isinstance(r["message"], str) else {},
            "created_at": r["created_at"].isoformat() if r["created_at"] else "",
        }
        for r in rows
    ]
