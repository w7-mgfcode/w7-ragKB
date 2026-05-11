"""System monitoring endpoints for the Admin Dashboard.

All endpoints require JWT authentication and admin privileges.
No secret values are ever exposed in responses.
"""

import importlib.metadata
import logging
import os
import sys
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth_middleware import get_current_user
from db import get_pool
from db_web_users import get_web_user_by_id
from log_buffer import log_handler
from metrics_collector import collector

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class ServiceHealth(BaseModel):
    name: str
    status: str  # "healthy" | "degraded" | "down"
    details: Optional[str] = None


class HealthResponse(BaseModel):
    services: list[ServiceHealth]
    uptime_seconds: float


class ModelConfigResponse(BaseModel):
    llm_model: str
    embedding_model: str
    embedding_dimensions: int
    gcp_project: Optional[str]
    gcp_region: str


class DatabaseMetricsResponse(BaseModel):
    pool_size: int
    pool_min: int
    pool_max: int
    pool_free: int
    pool_used: int
    db_version: str
    total_conversations: int
    total_messages: int
    total_documents: int
    total_web_users: int


class LogEntry(BaseModel):
    timestamp: str
    logger: str
    level: str
    message: str


class LogsResponse(BaseModel):
    records: list[LogEntry]
    total_buffered: int


class SlackStatusResponse(BaseModel):
    bot_token_configured: bool
    app_token_configured: bool
    socket_handlers_count: int


class SystemResourcesResponse(BaseModel):
    process_memory_mb: float
    system_memory_total_mb: float
    system_memory_used_mb: float
    system_memory_available_mb: float
    cpu_percent: float
    disk_total_gb: float
    disk_used_gb: float
    disk_free_gb: float


class RagStatusResponse(BaseModel):
    total_documents: int
    total_chunks: int
    last_indexed_at: Optional[str]


class EndpointMetric(BaseModel):
    path: str
    request_count: int
    avg_response_time_ms: float


class ApiMetricsResponse(BaseModel):
    endpoints: list[EndpointMetric]


class DependencyVersion(BaseModel):
    name: str
    version: str


class EnvironmentResponse(BaseModel):
    python_version: str
    dependencies: list[DependencyVersion]
    config: dict[str, str]


class ChannelMetric(BaseModel):
    channel_id: str
    channel_type: str
    status: str
    is_connected: bool
    messages_sent: int
    messages_received: int
    queue_depth: int
    error_count: int


class GatewayMetricsResponse(BaseModel):
    active_channels: int
    total_channels: int
    active_sessions: int
    total_messages_routed: int
    total_messages_delivered: int
    channels: list[ChannelMetric]


class MonitorAllResponse(BaseModel):
    health: HealthResponse
    models: ModelConfigResponse
    database: Optional[DatabaseMetricsResponse]
    logs: LogsResponse
    slack: SlackStatusResponse
    resources: Optional[SystemResourcesResponse]
    rag: Optional[RagStatusResponse]
    api_metrics: ApiMetricsResponse
    environment: EnvironmentResponse
    gateway: Optional[GatewayMetricsResponse]


# ---------------------------------------------------------------------------
# Admin auth helper (mirrors admin_router.py)
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
# Helper: collect individual sections
# ---------------------------------------------------------------------------


async def _collect_health() -> HealthResponse:
    """Gather service health for Slack bot, DB pool, HTTP server, RAG pipeline."""
    services: list[ServiceHealth] = []

    # Control Plane (Gateway)
    try:
        from gateway_server import get_control_plane
        
        control_plane = get_control_plane()
        if control_plane and control_plane._running:
            metrics = control_plane.get_metrics()
            active_channels = metrics.get("active_channels", 0)
            if active_channels > 0:
                services.append(
                    ServiceHealth(
                        name="Control Plane",
                        status="healthy",
                        details=f"{active_channels} channel(s) connected"
                    )
                )
            else:
                services.append(
                    ServiceHealth(
                        name="Control Plane",
                        status="degraded",
                        details="No channels connected"
                    )
                )
        else:
            services.append(
                ServiceHealth(
                    name="Control Plane",
                    status="down",
                    details="Not running"
                )
            )
    except Exception as e:
        services.append(
            ServiceHealth(
                name="Control Plane",
                status="down",
                details=f"Error: {str(e)}"
            )
        )

    # Slack adapter (legacy check for backward compatibility)
    try:
        from gateway_server import get_control_plane
        
        control_plane = get_control_plane()
        if control_plane:
            slack_status = control_plane.get_channel_status("slack-main")
            if slack_status and slack_status["is_connected"]:
                services.append(ServiceHealth(name="Slack adapter", status="healthy"))
            else:
                services.append(
                    ServiceHealth(
                        name="Slack adapter",
                        status="down",
                        details="Not connected to Control Plane"
                    )
                )
        else:
            services.append(
                ServiceHealth(
                    name="Slack adapter",
                    status="down",
                    details="Control Plane not available"
                )
            )
    except Exception:
        services.append(
            ServiceHealth(
                name="Slack adapter",
                status="down",
                details="Module not available"
            )
        )

    # Database pool
    try:
        pool = await get_pool()
        idle = pool.get_idle_size()
        if idle > 0:
            services.append(ServiceHealth(name="Database pool", status="healthy"))
        else:
            services.append(ServiceHealth(name="Database pool", status="degraded", details="No idle connections"))
    except RuntimeError:
        services.append(ServiceHealth(name="Database pool", status="down", details="Pool not initialized"))

    # HTTP server — always healthy since we're responding
    services.append(ServiceHealth(name="HTTP server", status="healthy"))

    # RAG pipeline — check if documents exist
    try:
        pool = await get_pool()
        doc_count = await pool.fetchval("SELECT COUNT(*) FROM documents")
        if doc_count and doc_count > 0:
            services.append(ServiceHealth(name="RAG pipeline", status="healthy"))
        else:
            services.append(ServiceHealth(name="RAG pipeline", status="degraded", details="No documents indexed"))
    except Exception:
        services.append(ServiceHealth(name="RAG pipeline", status="down", details="Cannot query documents"))

    return HealthResponse(
        services=services,
        uptime_seconds=round(collector.get_uptime_seconds(), 1),
    )


def _collect_models() -> ModelConfigResponse:
    """Read AI model configuration from environment variables."""
    dim_str = os.getenv("EMBEDDING_DIMENSIONS", "768")
    try:
        dimensions = int(dim_str)
    except ValueError:
        dimensions = 768

    return ModelConfigResponse(
        llm_model=os.getenv("LLM_CHOICE", "gemini-2.0-flash"),
        embedding_model=os.getenv("EMBEDDING_MODEL_CHOICE", "text-embedding-005"),
        embedding_dimensions=dimensions,
        gcp_project=os.getenv("GOOGLE_CLOUD_PROJECT") or None,
        gcp_region=os.getenv("GOOGLE_CLOUD_REGION", "us-central1"),
    )


async def _collect_database() -> DatabaseMetricsResponse:
    """Query asyncpg pool stats and table count aggregates."""
    pool = await get_pool()

    pool_size = pool.get_size()
    pool_min = pool.get_min_size()
    pool_max = pool.get_max_size()
    pool_idle = pool.get_idle_size()
    pool_used = pool_size - pool_idle

    db_version = await pool.fetchval("SELECT version()")

    total_conversations = await pool.fetchval("SELECT COUNT(*) FROM conversations")
    total_messages = await pool.fetchval("SELECT COUNT(*) FROM messages")
    total_documents = await pool.fetchval("SELECT COUNT(*) FROM documents")
    total_web_users = await pool.fetchval("SELECT COUNT(*) FROM web_users")

    return DatabaseMetricsResponse(
        pool_size=pool_size,
        pool_min=pool_min,
        pool_max=pool_max,
        pool_free=pool_idle,
        pool_used=pool_used,
        db_version=db_version or "",
        total_conversations=total_conversations or 0,
        total_messages=total_messages or 0,
        total_documents=total_documents or 0,
        total_web_users=total_web_users or 0,
    )


def _collect_logs(level: str) -> LogsResponse:
    """Return log records filtered by severity level."""
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    min_level = level.upper() if level.upper() in valid_levels else "DEBUG"

    records = log_handler.get_records(min_level=min_level)
    return LogsResponse(
        records=[LogEntry(**r) for r in records],
        total_buffered=len(log_handler._buffer),
    )


def _collect_slack() -> SlackStatusResponse:
    """Report Slack token presence and Control Plane channel status."""
    bot_configured = bool(os.getenv("SLACK_BOT_TOKEN"))
    app_configured = bool(os.getenv("SLACK_APP_TOKEN"))

    socket_handlers = 0
    try:
        from gateway_server import get_control_plane
        
        control_plane = get_control_plane()
        if control_plane:
            slack_status = control_plane.get_channel_status("slack-main")
            if slack_status and slack_status["is_connected"]:
                socket_handlers = 2  # SlackAdapter uses 2 Socket Mode handlers for HA
    except Exception:
        pass

    return SlackStatusResponse(
        bot_token_configured=bot_configured,
        app_token_configured=app_configured,
        socket_handlers_count=socket_handlers,
    )


def _count_slack_listeners(slack_app: object) -> int:
    """Support both AsyncApp internals and legacy test mocks."""
    async_listeners = getattr(slack_app, "_async_listeners", None)
    if async_listeners is not None:
        return len(async_listeners)

    listeners = getattr(slack_app, "_listeners", None)
    if listeners is not None:
        return len(listeners)

    return 0


async def _collect_rag() -> RagStatusResponse:
    """Query document and chunk counts from the database."""
    pool = await get_pool()

    total_documents = await pool.fetchval("SELECT COUNT(*) FROM document_metadata")
    total_chunks = await pool.fetchval("SELECT COUNT(*) FROM documents")

    last_indexed_row = await pool.fetchval(
        "SELECT MAX(created_at) FROM document_metadata"
    )
    last_indexed_at = last_indexed_row.isoformat() if last_indexed_row else None

    return RagStatusResponse(
        total_documents=total_documents or 0,
        total_chunks=total_chunks or 0,
        last_indexed_at=last_indexed_at,
    )


def _collect_api_metrics() -> ApiMetricsResponse:
    """Return per-endpoint request metrics."""
    raw = collector.get_endpoint_metrics()
    endpoints = [EndpointMetric(**v) for v in raw.values()]
    return ApiMetricsResponse(endpoints=endpoints)


def _collect_environment() -> EnvironmentResponse:
    """Read Python version, dependency versions, and non-sensitive config."""
    packages = ["fastapi", "pydantic-ai", "slack-bolt", "asyncpg", "uvicorn"]
    deps: list[DependencyVersion] = []
    for pkg in packages:
        try:
            ver = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            ver = "unknown"
        deps.append(DependencyVersion(name=pkg, version=ver))

    config = {
        "LLM_CHOICE": os.getenv("LLM_CHOICE", "gemini-2.0-flash"),
        "EMBEDDING_MODEL_CHOICE": os.getenv("EMBEDDING_MODEL_CHOICE", "text-embedding-005"),
        "EMBEDDING_DIMENSIONS": os.getenv("EMBEDDING_DIMENSIONS", "768"),
        "DB_POOL_MIN": os.getenv("DB_POOL_MIN", "2"),
        "DB_POOL_MAX": os.getenv("DB_POOL_MAX", "5"),
    }

    return EnvironmentResponse(
        python_version=sys.version,
        dependencies=deps,
        config=config,
    )


def _collect_gateway() -> Optional[GatewayMetricsResponse]:
    """Collect Control Plane gateway metrics."""
    try:
        from gateway_server import get_control_plane

        control_plane = get_control_plane()
        if not control_plane:
            return None

        metrics = control_plane.get_metrics()

        channels = []
        for channel_id in control_plane.adapters.keys():
            status = control_plane.get_channel_status(channel_id)
            if status:
                channels.append(ChannelMetric(
                    channel_id=status["channel_id"],
                    channel_type=status["channel_type"],
                    status=status["status"],
                    is_connected=status["is_connected"],
                    messages_sent=status["messages_sent"],
                    messages_received=status["messages_received"],
                    queue_depth=status["queue_depth"],
                    error_count=status["error_count"],
                ))

        return GatewayMetricsResponse(
            active_channels=metrics["active_channels"],
            total_channels=metrics["total_channels"],
            active_sessions=metrics["active_sessions"],
            total_messages_routed=metrics["total_messages_routed"],
            total_messages_delivered=metrics["total_messages_delivered"],
            channels=channels,
        )
    except Exception as e:
        logger.warning(f"Failed to collect gateway metrics: {e}")
        return None



# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
async def get_health(
    current_user: dict = Depends(get_current_user),
) -> HealthResponse:
    """Return service health for all platform services."""
    await _require_admin(current_user)
    return await _collect_health()


@router.get("/models", response_model=ModelConfigResponse)
async def get_models(
    current_user: dict = Depends(get_current_user),
) -> ModelConfigResponse:
    """Return current AI model configuration from env vars."""
    await _require_admin(current_user)
    return _collect_models()


@router.get("/database", response_model=DatabaseMetricsResponse)
async def get_database(
    current_user: dict = Depends(get_current_user),
) -> DatabaseMetricsResponse:
    """Return database pool stats and table count aggregates."""
    await _require_admin(current_user)
    try:
        return await _collect_database()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception:
        logger.exception("Failed to collect database metrics")
        raise HTTPException(status_code=503, detail="Database query failed")


@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    level: str = Query(default="INFO"),
    current_user: dict = Depends(get_current_user),
) -> LogsResponse:
    """Return log records filtered by severity level."""
    await _require_admin(current_user)
    return _collect_logs(level)


@router.get("/slack", response_model=SlackStatusResponse)
async def get_slack(
    current_user: dict = Depends(get_current_user),
) -> SlackStatusResponse:
    """Return Slack bot connectivity status."""
    await _require_admin(current_user)
    return _collect_slack()


@router.get("/resources", response_model=SystemResourcesResponse)
async def get_resources(
    current_user: dict = Depends(get_current_user),
) -> SystemResourcesResponse:
    """Return current CPU, memory, and disk usage."""
    await _require_admin(current_user)
    try:
        data = collector.get_system_resources()
        return SystemResourcesResponse(**data)
    except Exception:
        logger.exception("Failed to collect system resources")
        raise HTTPException(status_code=503, detail="Resource metrics unavailable")


@router.get("/rag", response_model=RagStatusResponse)
async def get_rag(
    current_user: dict = Depends(get_current_user),
) -> RagStatusResponse:
    """Return RAG pipeline document and chunk statistics."""
    await _require_admin(current_user)
    try:
        return await _collect_rag()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception:
        logger.exception("Failed to collect RAG status")
        raise HTTPException(status_code=503, detail="RAG status unavailable")


@router.get("/api-metrics", response_model=ApiMetricsResponse)
async def get_api_metrics(
    current_user: dict = Depends(get_current_user),
) -> ApiMetricsResponse:
    """Return per-endpoint request count and average response time."""
    await _require_admin(current_user)
    return _collect_api_metrics()


@router.get("/environment", response_model=EnvironmentResponse)
async def get_environment(
    current_user: dict = Depends(get_current_user),
) -> EnvironmentResponse:
    """Return Python version, dependency versions, and non-sensitive config."""
    await _require_admin(current_user)
    return _collect_environment()


@router.get("/gateway", response_model=GatewayMetricsResponse)
async def get_gateway(
    current_user: dict = Depends(get_current_user),
) -> GatewayMetricsResponse:
    """Return Control Plane gateway metrics."""
    await _require_admin(current_user)
    gateway = _collect_gateway()
    if gateway is None:
        raise HTTPException(status_code=503, detail="Gateway not available")
    return gateway


@router.get("/all", response_model=MonitorAllResponse)
async def get_all(
    current_user: dict = Depends(get_current_user),
) -> MonitorAllResponse:
    """Aggregate all monitoring data into a single response."""
    await _require_admin(current_user)

    # Collect each section independently so one failure doesn't block others
    health = await _collect_health()
    models = _collect_models()
    logs = _collect_logs("INFO")
    slack = _collect_slack()
    api_metrics = _collect_api_metrics()
    environment = _collect_environment()

    database: Optional[DatabaseMetricsResponse] = None
    try:
        database = await _collect_database()
    except Exception:
        logger.warning("Database metrics unavailable for /all endpoint")

    resources: Optional[SystemResourcesResponse] = None
    try:
        data = collector.get_system_resources()
        resources = SystemResourcesResponse(**data)
    except Exception:
        logger.warning("System resources unavailable for /all endpoint")

    rag: Optional[RagStatusResponse] = None
    try:
        rag = await _collect_rag()
    except Exception:
        logger.warning("RAG status unavailable for /all endpoint")

    gateway: Optional[GatewayMetricsResponse] = None
    try:
        gateway = _collect_gateway()
    except Exception:
        logger.warning("Gateway metrics unavailable for /all endpoint")

    return MonitorAllResponse(
        health=health,
        models=models,
        database=database,
        logs=logs,
        slack=slack,
        resources=resources,
        rag=rag,
        api_metrics=api_metrics,
        environment=environment,
        gateway=gateway,
    )
