"""Entry point for the w7-ragKB Slack Bot Agent Service.

Sets up logging, initialises the asyncpg connection pool, starts the
multi-channel Gateway architecture (Control Plane, SessionManager, channel adapters),
and tears everything down on shutdown signals.

Architecture:
- Control Plane: WebSocket server for channel adapter coordination
- SessionManager: Unified session management across all channels
- SlackAdapter: Slack Socket Mode integration via Gateway
- HTTP Server: FastAPI for web auth, data, and chat endpoints

Replaces the previous direct Slack bot implementation with a multi-channel
gateway that supports Slack, Telegram, Discord, and WhatsApp.
"""

import asyncio
import logging
import signal
import sys

from db import create_pool, close_pool
from log_buffer import log_handler

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Set up root logging with a consistent format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger().addHandler(log_handler)


async def _run() -> None:
    """Async entry: create the DB pool, start Slack, clean up on exit."""
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _request_shutdown() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _request_shutdown)

    logger.info("Creating asyncpg connection pool")
    pool = await create_pool()
    logger.info("Connection pool ready")

    try:
        logger.info("Starting Control Plane, SessionManager, CronScheduler, Slack adapter, and HTTP API server")
        from http_server import run_http_server
        from gateway_server import start_control_plane, stop_control_plane
        from session_manager import start_session_manager, stop_session_manager, get_session_manager
        from resource_manager import start_resource_manager, stop_resource_manager
        from cron_scheduler import start_cron_scheduler, stop_cron_scheduler
        from adapters.slack import create_slack_adapter

        # Start SessionManager
        await start_session_manager(pool)
        logger.info("SessionManager started")

        # Start ResourceManager (memory budget tracking & cleanup)
        await start_resource_manager(pool, get_session_manager())
        logger.info("ResourceManager started")

        # Start SyncManager and WebSocketManager
        from sync_manager import SyncManager
        from websocket_manager import WebSocketManager
        import sync_manager as _sync_mod
        import websocket_manager as _ws_mod

        _sync_mod._instance = SyncManager(pool)
        logger.info("SyncManager started")
        _ws_mod._instance = WebSocketManager()
        logger.info("WebSocketManager started")

        # Start CronScheduler
        await start_cron_scheduler(pool)
        logger.info("CronScheduler started")
        
        # Start Control Plane WebSocket server
        await start_control_plane()
        
        # Start Slack adapter (connects to Control Plane)
        slack_adapter = await create_slack_adapter(channel_id="slack-main")
        
        # Start HTTP server
        http_task = asyncio.create_task(run_http_server(shutdown_event))

        # Wait until a shutdown signal fires
        await shutdown_event.wait()

        # Stop Slack adapter
        await slack_adapter.stop()
        
        # Let HTTP task finish its cancellation cleanup
        try:
            await http_task
        except asyncio.CancelledError:
            pass
        
        # Stop Control Plane
        await stop_control_plane()
        
        # Stop CronScheduler
        await stop_cron_scheduler()
        logger.info("CronScheduler stopped")

        # Stop ResourceManager
        await stop_resource_manager()
        logger.info("ResourceManager stopped")

        # Stop SessionManager
        await stop_session_manager()
        logger.info("SessionManager stopped")
        
        # Cleanup all browser instances
        from tools.browser_tool import cleanup_all_browsers
        await cleanup_all_browsers()
        logger.info("Browser instances cleaned up")
    finally:
        logger.info("Shutting down — closing connection pool")
        await close_pool()
        logger.info("Connection pool closed")


def main() -> None:
    """Synchronous wrapper around the async lifecycle."""
    _configure_logging()
    logger.info("w7-ragKB Agent Service starting")
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — exiting")
    logger.info("w7-ragKB Agent Service stopped")


if __name__ == "__main__":
    main()
