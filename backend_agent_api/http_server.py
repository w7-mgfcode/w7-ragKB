"""FastAPI application factory and HTTP server coroutine.

Creates the FastAPI app with auth, data, and admin routers, configures
CORS middleware, and provides ``run_http_server()`` for running uvicorn
alongside the Slack Socket Mode bot via ``asyncio.gather``.
"""

import asyncio
import os
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth_router import router as auth_router
from data_router import router as data_router
from admin_router import router as admin_router
from chat_router import router as chat_router
from monitor_router import router as monitor_router
from webhook_handler import router as webhook_router
from gateway_router import router as gateway_router
from documents_router import router as documents_router
from metrics_collector import MetricsMiddleware


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(title="w7-ragKB API", docs_url=None, redoc_url=None)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:8080")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(MetricsMiddleware)

    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(data_router, prefix="/api")
    app.include_router(admin_router, prefix="/api/admin")
    app.include_router(chat_router, prefix="/api")
    app.include_router(monitor_router, prefix="/api/admin/monitor")
    app.include_router(gateway_router, prefix="/api/gateway")
    app.include_router(webhook_router)  # No prefix - handles both /api/webhooks and /webhooks/{id}
    app.include_router(documents_router, prefix="/api/documents")

    return app


async def run_http_server(stop_event: Optional[asyncio.Event] = None) -> None:
    """Start the uvicorn server for the FastAPI app.

    If ``stop_event`` is provided, the server is shut down gracefully
    when the event is set instead of hard-cancelling the task.
    """
    import uvicorn

    app = create_app()
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    if stop_event is None:
        await server.serve()
        return

    async def _watch_stop() -> None:
        await stop_event.wait()
        server.should_exit = True

    stop_task = asyncio.create_task(_watch_stop())
    try:
        await server.serve()
    finally:
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass
