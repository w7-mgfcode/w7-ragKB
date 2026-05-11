"""Gateway admin router for managing channels, sessions, webhooks, and cron jobs.

Exposes /api/gateway/* endpoints consumed by the frontend admin dashboard.
All endpoints require admin authentication.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_middleware import get_current_user
from db import get_pool
from db_web_users import get_web_user_by_id
from db_channels import (
    create_channel as db_create_channel,
    delete_channel as db_delete_channel,
    get_channel as db_get_channel,
    list_channels as db_list_channels,
    update_channel_config,
    update_channel_enabled,
)
from db_sessions import (
    add_session_message,
    archive_session as db_archive_session,
    get_session as db_get_session,
    get_session_messages,
    list_sessions as db_list_sessions,
    update_session_activation_mode,
    update_session_tool_allowlist,
)
from db_webhooks import (
    create_webhook as db_create_webhook,
    delete_webhook as db_delete_webhook,
    get_webhook as db_get_webhook,
    list_webhooks as db_list_webhooks,
    update_webhook_enabled,
    update_webhook_transform_rules,
)
from db_cron import (
    create_cron_job as db_create_cron_job,
    delete_cron_job as db_delete_cron_job,
    get_cron_job as db_get_cron_job,
    list_cron_jobs as db_list_cron_jobs,
    update_cron_job_enabled,
    update_cron_job_message_template,
    update_cron_job_schedule,
)
from gateway_server import get_control_plane
from session_manager import get_session_manager
from cron_scheduler import get_cron_scheduler
from webhook_handler import validate_payload_schema, transform_payload

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------


class ChannelCreateRequest(BaseModel):
    channel_id: str
    channel_type: str
    config: Optional[Dict[str, Any]] = None
    # Flat fields that get merged into config
    api_token: Optional[str] = None
    webhook_url: Optional[str] = None
    rate_limit_per_minute: int = 60
    enabled: bool = True


class ChannelUpdateRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    api_token: Optional[str] = None
    webhook_url: Optional[str] = None
    rate_limit_per_minute: Optional[int] = None


class SessionMessageCreateRequest(BaseModel):
    message: str
    metadata: Optional[str] = None  # JSON string


class SessionConfigUpdateRequest(BaseModel):
    activation_mode: Optional[str] = None
    tool_allowlist: Optional[List[str]] = None
    tool_denylist: Optional[List[str]] = None


class WebhookCreateRequest(BaseModel):
    target_session_id: str
    payload_schema: Optional[str] = None  # JSON string
    transform_rules: Optional[str] = None  # JSON string
    enabled: bool = True


class WebhookUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    transform_rules: Optional[str] = None  # JSON string


class WebhookTestRequest(BaseModel):
    payload: str  # JSON string
    auth_token: str


class CronJobCreateRequest(BaseModel):
    schedule: str
    target_session_id: str
    message_template: str
    timezone: str = "UTC"
    enabled: bool = True


class CronJobUpdateRequest(BaseModel):
    schedule: Optional[str] = None
    target_session_id: Optional[str] = None
    message_template: Optional[str] = None
    timezone: Optional[str] = None
    enabled: Optional[bool] = None


class CronSchedulePreviewRequest(BaseModel):
    schedule: str
    timezone: str = "UTC"


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


async def _require_admin(current_user: dict) -> dict:
    """Return DB user row for current user and enforce admin access."""
    pool = await get_pool()
    user = await get_web_user_by_id(pool, current_user["sub"])
    if user is None:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _ts(val) -> str:
    """Convert a datetime or None to ISO string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _ensure_dict(val) -> dict:
    """Ensure a JSONB value is a Python dict."""
    if val is None:
        return {}
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return {}
    return val


def _ensure_list(val) -> list:
    """Ensure a JSONB value is a Python list."""
    if val is None:
        return []
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    return val


def _get_channel_cp_status(channel_id: str) -> Optional[Dict]:
    """Get live channel status from ControlPlane."""
    cp = get_control_plane()
    if cp is None:
        return None
    return cp.get_channel_status(channel_id)


def _serialize_channel(row: dict, cp_status: Optional[dict] = None) -> dict:
    status = "disconnected"
    error_message = None
    if cp_status:
        if cp_status.get("is_connected"):
            status = "connected"
        elif cp_status.get("status") == "error":
            status = "error"
            error_message = cp_status.get("last_error")
        else:
            status = cp_status.get("status", "disconnected")
            error_message = cp_status.get("last_error")

    config = _ensure_dict(row.get("config"))
    # Ensure frontend-expected config fields have defaults
    config.setdefault("api_token", "")
    config.setdefault("rate_limit_per_minute", 60)
    config.setdefault("max_message_length", 4096)
    config.setdefault("supports_threads", False)
    config.setdefault("supports_buttons", False)
    config.setdefault("supports_embeds", False)
    config.setdefault("custom_config", {})

    return {
        "channel_id": row["channel_id"],
        "channel_type": row["channel_type"],
        "status": status,
        "config": config,
        "enabled": row.get("enabled", False),
        "created_at": _ts(row.get("created_at")),
        "updated_at": _ts(row.get("updated_at", row.get("created_at"))),
        "error_message": error_message,
    }


def _serialize_session(row: dict) -> dict:
    message_count = row.get("message_count", 0) or 0
    memory_usage = min(100, int((message_count / 100) * 100)) if message_count else 0

    return {
        "session_id": row["session_id"],
        "channel_id": row.get("channel_id", ""),
        "user_id": row.get("user_id", ""),
        "chat_id": row.get("chat_id", ""),
        "session_type": row.get("session_type", "main"),
        "activation_mode": row.get("activation_mode", "mention"),
        "tool_allowlist": _ensure_list(row.get("tool_allowlist")),
        "tool_denylist": _ensure_list(row.get("tool_denylist")),
        "message_count": message_count,
        "token_usage": _ensure_dict(row.get("token_usage")),
        "memory_usage": memory_usage,
        "created_at": _ts(row.get("created_at")),
        "last_activity_at": _ts(row.get("last_activity_at")),
        "archived_at": _ts(row.get("archived_at")),
    }


def _serialize_session_message(row: dict) -> dict:
    metadata = _ensure_dict(row.get("metadata"))
    return {
        "message_id": row["message_id"],
        "session_id": row["session_id"],
        "role": row["role"],
        "content": row.get("content", ""),
        "metadata": metadata,
        "source_session": metadata.get("source_session"),
        "created_at": _ts(row.get("created_at")),
    }


def _serialize_webhook(row: dict) -> dict:
    return {
        "webhook_id": row["webhook_id"],
        "webhook_url": row.get("webhook_url", ""),
        "target_session_id": row.get("target_session_id", ""),
        "auth_token": row.get("auth_token", ""),
        "payload_schema": _ensure_dict(row.get("payload_schema")),
        "transform_rules": _ensure_dict(row.get("transform_rules")),
        "enabled": row.get("enabled", False),
        "created_at": _ts(row.get("created_at")),
        "last_triggered_at": _ts(row.get("last_triggered_at")),
    }


def _serialize_cron_job(row: dict) -> dict:
    return {
        "cron_job_id": row["cron_job_id"],
        "schedule": row.get("schedule", ""),
        "target_session_id": row.get("target_session_id", ""),
        "message_template": row.get("message_template", ""),
        "timezone": row.get("timezone", "UTC"),
        "enabled": row.get("enabled", False),
        "created_at": _ts(row.get("created_at")),
        "last_executed_at": _ts(row.get("last_executed_at")),
        "next_execution_at": _ts(row.get("next_execution_at")),
    }


# =========================================================================
# Channel endpoints
# =========================================================================


@router.get("/channels")
async def list_channels(
    channel_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    enabled_only = enabled is True
    channels = await db_list_channels(pool, channel_type=channel_type, enabled_only=enabled_only)

    result = []
    for ch in channels:
        cp_status = _get_channel_cp_status(ch["channel_id"])
        serialized = _serialize_channel(ch, cp_status)

        # Python-side filters
        if status and serialized["status"] != status:
            continue
        if search and search.lower() not in serialized["channel_id"].lower():
            continue

        result.append(serialized)

    return result


@router.get("/channels/{channel_id}")
async def get_channel(
    channel_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()
    row = await db_get_channel(pool, channel_id)
    if not row:
        raise HTTPException(status_code=404, detail="Channel not found")
    cp_status = _get_channel_cp_status(channel_id)
    return _serialize_channel(row, cp_status)


@router.post("/channels", status_code=201)
async def create_channel(
    data: ChannelCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    # Build config JSONB from flat fields or provided config dict
    config = data.config if data.config else {}
    if data.api_token is not None:
        config["api_token"] = data.api_token
    if data.webhook_url is not None:
        config["webhook_url"] = data.webhook_url
    config.setdefault("rate_limit_per_minute", data.rate_limit_per_minute)

    try:
        row = await db_create_channel(pool, data.channel_id, data.channel_type, config, data.enabled)
    except Exception as e:
        if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Channel '{data.channel_id}' already exists")
        raise HTTPException(status_code=400, detail=str(e))

    return _serialize_channel(row)


@router.put("/channels/{channel_id}")
async def update_channel(
    channel_id: str,
    data: ChannelUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    existing = await db_get_channel(pool, channel_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Update config if any config-related fields provided
    if data.config is not None or data.api_token is not None or data.webhook_url is not None or data.rate_limit_per_minute is not None:
        config = _ensure_dict(existing.get("config"))
        if data.config is not None:
            config.update(data.config)
        if data.api_token is not None:
            config["api_token"] = data.api_token
        if data.webhook_url is not None:
            config["webhook_url"] = data.webhook_url
        if data.rate_limit_per_minute is not None:
            config["rate_limit_per_minute"] = data.rate_limit_per_minute
        await update_channel_config(pool, channel_id, config)

    if data.enabled is not None:
        await update_channel_enabled(pool, channel_id, data.enabled)

    updated = await db_get_channel(pool, channel_id)
    cp_status = _get_channel_cp_status(channel_id)
    return _serialize_channel(updated, cp_status)


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    existing = await db_get_channel(pool, channel_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Channel not found")

    try:
        await db_delete_channel(pool, channel_id)
    except Exception as e:
        if "foreign key" in str(e).lower() or "violates" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail="Cannot delete channel with active sessions. Archive or delete sessions first.",
            )
        raise


@router.post("/channels/{channel_id}/test")
async def test_channel(
    channel_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    existing = await db_get_channel(pool, channel_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Channel not found")

    cp = get_control_plane()
    if cp is None:
        return {"success": False, "message": "Control plane not running"}

    cp_status = cp.get_channel_status(channel_id)
    if cp_status is None:
        return {"success": False, "message": "Channel adapter not registered with control plane"}

    is_connected = cp_status.get("is_connected", False)
    if is_connected:
        msgs_sent = cp_status.get("messages_sent", 0)
        msgs_recv = cp_status.get("messages_received", 0)
        return {
            "success": True,
            "message": f"Connected ({msgs_sent} sent, {msgs_recv} received)",
        }
    else:
        error = cp_status.get("last_error", "Unknown")
        return {"success": False, "message": f"Disconnected: {error}"}


# =========================================================================
# Session endpoints
# =========================================================================


@router.get("/sessions")
async def list_sessions(
    channel_id: Optional[str] = Query(None),
    session_type: Optional[str] = Query(None),
    activation_mode: Optional[str] = Query(None),
    archived: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    include_archived = archived is not False  # Include archived unless explicitly False
    sessions = await db_list_sessions(
        pool,
        channel_id=channel_id,
        session_type=session_type,
        include_archived=include_archived,
    )

    result = []
    for s in sessions:
        serialized = _serialize_session(s)

        # Python-side filters
        if activation_mode and serialized["activation_mode"] != activation_mode:
            continue
        if search:
            search_lower = search.lower()
            searchable = f"{serialized['session_id']} {serialized['user_id']} {serialized['chat_id']}".lower()
            if search_lower not in searchable:
                continue

        result.append(serialized)

    return result


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()
    row = await db_get_session(pool, session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return _serialize_session(row)


@router.get("/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    session = await db_get_session(pool, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # DB function doesn't support offset; fetch more and slice
    fetch_limit = limit + offset
    messages = await get_session_messages(pool, session_id, limit=fetch_limit)
    sliced = messages[offset : offset + limit]

    return [_serialize_session_message(m) for m in sliced]


@router.post("/sessions/{session_id}/messages", status_code=201)
async def send_session_message(
    session_id: str,
    data: SessionMessageCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    session = await db_get_session(pool, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    metadata = None
    if data.metadata:
        try:
            metadata = json.loads(data.metadata)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid metadata JSON")

    row = await add_session_message(pool, session_id, "user", data.message, metadata)
    return _serialize_session_message(row)


@router.put("/sessions/{session_id}")
async def update_session(
    session_id: str,
    data: SessionConfigUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    existing = await db_get_session(pool, session_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Session not found")

    if data.activation_mode is not None:
        if data.activation_mode not in ("mention", "always", "manual"):
            raise HTTPException(status_code=400, detail="Invalid activation mode")
        await update_session_activation_mode(pool, session_id, data.activation_mode)

    if data.tool_allowlist is not None:
        await update_session_tool_allowlist(pool, session_id, data.tool_allowlist)

    if data.tool_denylist is not None:
        denylist_json = json.dumps(data.tool_denylist)
        await pool.execute(
            "UPDATE sessions SET tool_denylist = $2::jsonb WHERE session_id = $1",
            session_id,
            denylist_json,
        )

    updated = await db_get_session(pool, session_id)
    return _serialize_session(updated)


@router.post("/sessions/{session_id}/archive", status_code=200)
async def archive_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    existing = await db_get_session(pool, session_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Session not found")

    # Prefer SessionManager for cache eviction; fall back to DB direct
    sm = get_session_manager()
    if sm:
        try:
            await sm.archive_session(session_id)
        except Exception:
            await db_archive_session(pool, session_id)
    else:
        await db_archive_session(pool, session_id)

    return {"status": "archived", "session_id": session_id}


# =========================================================================
# Webhook endpoints
# =========================================================================


@router.get("/webhooks")
async def list_webhooks(
    enabled: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    enabled_only = enabled is True
    webhooks = await db_list_webhooks(pool, enabled_only=enabled_only)

    result = []
    for wh in webhooks:
        serialized = _serialize_webhook(wh)
        if search:
            search_lower = search.lower()
            searchable = f"{serialized['webhook_id']} {serialized['webhook_url']} {serialized['target_session_id']}".lower()
            if search_lower not in searchable:
                continue
        result.append(serialized)

    return result


@router.get("/webhooks/{webhook_id}")
async def get_webhook(
    webhook_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()
    row = await db_get_webhook(pool, webhook_id)
    if not row:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return _serialize_webhook(row)


@router.post("/webhooks", status_code=201)
async def create_webhook(
    data: WebhookCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    payload_schema = None
    if data.payload_schema:
        try:
            payload_schema = json.loads(data.payload_schema)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid payload_schema JSON")

    transform_rules = None
    if data.transform_rules:
        try:
            transform_rules = json.loads(data.transform_rules)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid transform_rules JSON")

    row = await db_create_webhook(
        pool,
        target_session_id=data.target_session_id,
        payload_schema=payload_schema,
        transform_rules=transform_rules,
        enabled=data.enabled,
    )
    return _serialize_webhook(row)


@router.put("/webhooks/{webhook_id}")
async def update_webhook(
    webhook_id: str,
    data: WebhookUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    existing = await db_get_webhook(pool, webhook_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if data.enabled is not None:
        await update_webhook_enabled(pool, webhook_id, data.enabled)

    if data.transform_rules is not None:
        try:
            rules = json.loads(data.transform_rules)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid transform_rules JSON")
        await update_webhook_transform_rules(pool, webhook_id, rules)

    updated = await db_get_webhook(pool, webhook_id)
    return _serialize_webhook(updated)


@router.delete("/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    existing = await db_get_webhook(pool, webhook_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Webhook not found")

    await db_delete_webhook(pool, webhook_id)


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(
    webhook_id: str,
    data: WebhookTestRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    webhook = await db_get_webhook(pool, webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    now = datetime.now(timezone.utc).isoformat()

    # Verify auth token
    if data.auth_token != webhook.get("auth_token"):
        return {"status": 401, "body": "Invalid auth token", "timestamp": now}

    # Parse payload
    try:
        payload = json.loads(data.payload)
    except json.JSONDecodeError:
        return {"status": 400, "body": "Invalid payload JSON", "timestamp": now}

    # Validate against schema (dry-run)
    schema = _ensure_dict(webhook.get("payload_schema"))
    if schema:
        try:
            validate_payload_schema(payload, schema)
        except Exception as e:
            return {"status": 400, "body": f"Schema validation failed: {e}", "timestamp": now}

    # Apply transform rules (dry-run)
    rules = _ensure_dict(webhook.get("transform_rules"))
    if rules:
        try:
            payload = transform_payload(payload, rules)
        except Exception as e:
            return {"status": 400, "body": f"Transform failed: {e}", "timestamp": now}

    return {
        "status": 200,
        "body": json.dumps(payload),
        "timestamp": now,
    }


# =========================================================================
# Cron Job endpoints
# CRITICAL: /cron-jobs/preview MUST be defined BEFORE /{cron_job_id}
# =========================================================================


@router.post("/cron-jobs/preview")
async def preview_cron_schedule(
    data: CronSchedulePreviewRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)

    try:
        from apscheduler.triggers.cron import CronTrigger
        import pytz
    except ImportError:
        return {
            "next_executions": [],
            "is_valid": False,
            "error_message": "APScheduler not available",
        }

    try:
        # Parse cron expression into APScheduler CronTrigger fields
        parts = data.schedule.strip().split()
        if len(parts) != 5:
            return {
                "next_executions": [],
                "is_valid": False,
                "error_message": "Cron expression must have exactly 5 fields (minute hour day month day_of_week)",
            }

        tz = pytz.timezone(data.timezone)
        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone=tz,
        )

        # Compute next 5 fire times
        next_executions = []
        reference = datetime.now(tz)
        for _ in range(5):
            next_time = trigger.get_next_fire_time(None, reference)
            if next_time is None:
                break
            next_executions.append(next_time.isoformat())
            reference = next_time + timedelta(seconds=1)

        return {
            "next_executions": next_executions,
            "is_valid": True,
        }
    except Exception as e:
        return {
            "next_executions": [],
            "is_valid": False,
            "error_message": str(e),
        }


@router.get("/cron-jobs")
async def list_cron_jobs(
    enabled: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    enabled_only = enabled is True
    cron_jobs = await db_list_cron_jobs(pool, enabled_only=enabled_only)

    result = []
    for cj in cron_jobs:
        serialized = _serialize_cron_job(cj)
        if search:
            search_lower = search.lower()
            searchable = f"{serialized['cron_job_id']} {serialized['schedule']} {serialized['target_session_id']} {serialized['message_template']}".lower()
            if search_lower not in searchable:
                continue
        result.append(serialized)

    return result


@router.get("/cron-jobs/{cron_job_id}")
async def get_cron_job(
    cron_job_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()
    row = await db_get_cron_job(pool, cron_job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Cron job not found")
    return _serialize_cron_job(row)


@router.post("/cron-jobs", status_code=201)
async def create_cron_job(
    data: CronJobCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    scheduler = get_cron_scheduler()
    if scheduler:
        try:
            row = await scheduler.register_cron_job(
                schedule=data.schedule,
                target_session_id=data.target_session_id,
                message_template=data.message_template,
                timezone=data.timezone,
                enabled=data.enabled,
            )
            return _serialize_cron_job(row)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        # Fallback: write to DB directly without scheduling
        row = await db_create_cron_job(
            pool,
            schedule=data.schedule,
            target_session_id=data.target_session_id,
            message_template=data.message_template,
            timezone=data.timezone,
            enabled=data.enabled,
        )
        return _serialize_cron_job(row)


@router.put("/cron-jobs/{cron_job_id}")
async def update_cron_job(
    cron_job_id: str,
    data: CronJobUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    existing = await db_get_cron_job(pool, cron_job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Cron job not found")

    scheduler = get_cron_scheduler()

    if data.schedule is not None:
        if scheduler:
            try:
                await scheduler.update_cron_job_schedule(cron_job_id, data.schedule)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        else:
            await update_cron_job_schedule(pool, cron_job_id, data.schedule)

    if data.message_template is not None:
        await update_cron_job_message_template(pool, cron_job_id, data.message_template)

    if data.enabled is not None:
        if scheduler:
            if data.enabled:
                await scheduler.resume_cron_job(cron_job_id)
            else:
                await scheduler.pause_cron_job(cron_job_id)
        else:
            await update_cron_job_enabled(pool, cron_job_id, data.enabled)

    updated = await db_get_cron_job(pool, cron_job_id)
    return _serialize_cron_job(updated)


@router.delete("/cron-jobs/{cron_job_id}", status_code=204)
async def delete_cron_job(
    cron_job_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    existing = await db_get_cron_job(pool, cron_job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Cron job not found")

    scheduler = get_cron_scheduler()
    if scheduler:
        await scheduler.delete_cron_job(cron_job_id)
    else:
        await db_delete_cron_job(pool, cron_job_id)


@router.post("/cron-jobs/{cron_job_id}/pause")
async def pause_cron_job(
    cron_job_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    existing = await db_get_cron_job(pool, cron_job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Cron job not found")

    scheduler = get_cron_scheduler()
    if scheduler:
        await scheduler.pause_cron_job(cron_job_id)
    else:
        await update_cron_job_enabled(pool, cron_job_id, False)

    updated = await db_get_cron_job(pool, cron_job_id)
    return _serialize_cron_job(updated)


@router.post("/cron-jobs/{cron_job_id}/resume")
async def resume_cron_job(
    cron_job_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    existing = await db_get_cron_job(pool, cron_job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Cron job not found")

    scheduler = get_cron_scheduler()
    if scheduler:
        await scheduler.resume_cron_job(cron_job_id)
    else:
        await update_cron_job_enabled(pool, cron_job_id, True)

    updated = await db_get_cron_job(pool, cron_job_id)
    return _serialize_cron_job(updated)


@router.post("/cron-jobs/{cron_job_id}/execute")
async def execute_cron_job(
    cron_job_id: str,
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    existing = await db_get_cron_job(pool, cron_job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Cron job not found")

    scheduler = get_cron_scheduler()
    if not scheduler:
        return {"success": False, "message": "Cron scheduler not running"}

    try:
        await scheduler._execute_cron_job(cron_job_id)
        return {"success": True, "message": f"Cron job {cron_job_id} executed successfully"}
    except Exception as e:
        logger.error(f"Manual cron execution failed for {cron_job_id}: {e}")
        return {"success": False, "message": str(e)}


@router.get("/cron-jobs/{cron_job_id}/history")
async def get_cron_execution_history(
    cron_job_id: str,
    outcome: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    await _require_admin(current_user)
    pool = await get_pool()

    existing = await db_get_cron_job(pool, cron_job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Cron job not found")

    # No persistent cron_executions table exists yet — return empty list
    return []
