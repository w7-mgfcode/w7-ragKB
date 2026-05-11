"""Resource management for 4GB VM constraint.

This module implements memory budget tracking, cleanup triggers, session
compaction, browser instance limits, connection pool monitoring, and
backpressure for channel adapters.

Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default resource limits
DEFAULT_MEMORY_BUDGET_MB = 3072  # 3 GB for the application
CLEANUP_THRESHOLD = 0.80  # 80% triggers cleanup
METRICS_INTERVAL_SECONDS = 60
MAX_BROWSER_INSTANCES = 3
MAX_DB_POOL_SIZE = 20
DEFAULT_BACKPRESSURE_THRESHOLD = 500


class ResourceManager:
    """Manages system resources within the 4GB VM memory constraint.

    Tracks memory usage, enforces limits, triggers cleanup, and applies
    backpressure when the system is overloaded.
    """

    def __init__(
        self,
        pool: Any,
        session_manager: Any,
        memory_budget_mb: int = DEFAULT_MEMORY_BUDGET_MB,
        cleanup_threshold: float = CLEANUP_THRESHOLD,
        metrics_interval: int = METRICS_INTERVAL_SECONDS,
        backpressure_threshold: int = DEFAULT_BACKPRESSURE_THRESHOLD,
    ):
        self.pool = pool
        self.session_manager = session_manager
        self.memory_budget_mb = memory_budget_mb
        self.cleanup_threshold = cleanup_threshold
        self.metrics_interval = metrics_interval
        self.backpressure_threshold = backpressure_threshold
        self._metrics_task: Optional[asyncio.Task] = None
        self._running = False
        self._last_cleanup_time = 0.0
        self._cleanup_count = 0

    async def start(self) -> None:
        """Start the resource manager metrics loop."""
        if self._running:
            return
        self._running = True
        self._metrics_task = asyncio.create_task(self._metrics_loop())
        logger.info(
            f"ResourceManager started: budget={self.memory_budget_mb}MB, "
            f"threshold={self.cleanup_threshold:.0%}"
        )

    async def stop(self) -> None:
        """Stop the resource manager."""
        self._running = False
        if self._metrics_task and not self._metrics_task.done():
            self._metrics_task.cancel()
            try:
                await self._metrics_task
            except asyncio.CancelledError:
                pass
        self._metrics_task = None
        logger.info("ResourceManager stopped")

    # -----------------------------------------------------------------
    # Memory monitoring
    # -----------------------------------------------------------------

    def get_memory_usage_mb(self) -> float:
        """Get current process memory usage in MB.

        Uses /proc/self/status on Linux, falls back to rough estimate.
        """
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        kb = int(line.split()[1])
                        return kb / 1024.0
        except (FileNotFoundError, ValueError, IndexError):
            pass

        # Fallback: try resource module
        try:
            import resource
            usage_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            return usage_kb / 1024.0
        except Exception:
            return 0.0

    def get_memory_usage_percent(self) -> float:
        """Get memory usage as a fraction of the budget (0.0 to 1.0+)."""
        if self.memory_budget_mb <= 0:
            return 0.0
        return self.get_memory_usage_mb() / self.memory_budget_mb

    # -----------------------------------------------------------------
    # Cleanup logic
    # -----------------------------------------------------------------

    async def check_and_cleanup(self) -> bool:
        """Check memory usage and trigger cleanup if above threshold.

        Requirement 15.2: Archive inactive sessions and close idle
        browsers when usage exceeds 80%.

        Returns:
            True if cleanup was triggered, False otherwise.
        """
        usage_pct = self.get_memory_usage_percent()

        if usage_pct < self.cleanup_threshold:
            return False

        logger.warning(
            f"Memory usage {usage_pct:.1%} exceeds threshold "
            f"{self.cleanup_threshold:.0%}, triggering cleanup"
        )

        await self._archive_inactive_sessions()
        await self._close_idle_browsers()

        self._last_cleanup_time = time.time()
        self._cleanup_count += 1
        return True

    async def _archive_inactive_sessions(self) -> None:
        """Archive inactive sessions to free memory."""
        if self.session_manager is None:
            return

        try:
            if hasattr(self.session_manager, "_cleanup_inactive_sessions"):
                await self.session_manager._cleanup_inactive_sessions()
            if hasattr(self.session_manager, "_enforce_memory_limits"):
                await self.session_manager._enforce_memory_limits()
        except Exception as e:
            logger.error(f"Error archiving inactive sessions: {e}", exc_info=True)

    async def _close_idle_browsers(self) -> None:
        """Close idle browser instances to free memory."""
        try:
            from tools.browser_tool import cleanup_all_browsers
            await cleanup_all_browsers()
        except ImportError:
            logger.debug("Browser tool not available for cleanup")
        except Exception as e:
            logger.error(f"Error closing idle browsers: {e}", exc_info=True)

    # -----------------------------------------------------------------
    # Backpressure
    # -----------------------------------------------------------------

    def should_apply_backpressure(
        self, queue_depth: int, threshold: Optional[int] = None
    ) -> bool:
        """Check if backpressure should be applied.

        Requirement 15.6: Reject with HTTP 429 when queue exceeds threshold.

        Args:
            queue_depth: Current message queue depth
            threshold: Override for backpressure threshold

        Returns:
            True if messages should be rejected (HTTP 429)
        """
        limit = threshold if threshold is not None else self.backpressure_threshold
        return queue_depth >= limit

    # -----------------------------------------------------------------
    # Metrics
    # -----------------------------------------------------------------

    def get_metrics(self) -> Dict[str, Any]:
        """Get current resource metrics.

        Returns:
            Dictionary of resource metrics for monitoring.
        """
        active_sessions = 0
        if self.session_manager and hasattr(self.session_manager, "get_active_session_count"):
            active_sessions = self.session_manager.get_active_session_count()

        pool_size = 0
        pool_free = 0
        if self.pool and hasattr(self.pool, "get_size"):
            pool_size = self.pool.get_size()
        if self.pool and hasattr(self.pool, "get_idle_size"):
            pool_free = self.pool.get_idle_size()

        return {
            "memory_usage_mb": round(self.get_memory_usage_mb(), 1),
            "memory_budget_mb": self.memory_budget_mb,
            "memory_usage_percent": round(self.get_memory_usage_percent() * 100, 1),
            "cleanup_threshold_percent": round(self.cleanup_threshold * 100, 1),
            "active_sessions": active_sessions,
            "max_browser_instances": MAX_BROWSER_INSTANCES,
            "db_pool_size": pool_size,
            "db_pool_free": pool_free,
            "db_pool_max": MAX_DB_POOL_SIZE,
            "backpressure_threshold": self.backpressure_threshold,
            "cleanup_count": self._cleanup_count,
            "last_cleanup_time": self._last_cleanup_time,
        }

    async def _metrics_loop(self) -> None:
        """Log metrics every metrics_interval seconds.

        Requirement 15.7: Log memory usage metrics every 60 seconds.
        """
        while self._running:
            try:
                await asyncio.sleep(self.metrics_interval)
                if not self._running:
                    break

                metrics = self.get_metrics()
                logger.info(
                    f"Resource metrics: "
                    f"memory={metrics['memory_usage_mb']}MB "
                    f"({metrics['memory_usage_percent']}%), "
                    f"sessions={metrics['active_sessions']}, "
                    f"pool={metrics['db_pool_size']}/{metrics['db_pool_max']}"
                )

                # Check if cleanup is needed
                await self.check_and_cleanup()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics loop: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

_resource_manager: Optional[ResourceManager] = None


def get_resource_manager() -> Optional[ResourceManager]:
    """Get the global ResourceManager instance."""
    return _resource_manager


async def start_resource_manager(
    pool: Any, session_manager: Any, **kwargs
) -> ResourceManager:
    """Initialize and start the global ResourceManager.

    Args:
        pool: Database connection pool
        session_manager: SessionManager instance
        **kwargs: Additional ResourceManager constructor args

    Returns:
        ResourceManager instance
    """
    global _resource_manager
    _resource_manager = ResourceManager(pool, session_manager, **kwargs)
    await _resource_manager.start()
    return _resource_manager


async def stop_resource_manager() -> None:
    """Stop the global ResourceManager."""
    global _resource_manager
    if _resource_manager:
        await _resource_manager.stop()
        _resource_manager = None
