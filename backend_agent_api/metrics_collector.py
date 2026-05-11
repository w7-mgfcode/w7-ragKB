"""In-process metrics collection for the System Monitor."""

import time
import psutil
import os
from collections import defaultdict
from dataclasses import dataclass
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


@dataclass
class EndpointMetrics:
    request_count: int = 0
    total_response_time_ms: float = 0.0

    @property
    def avg_response_time_ms(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.total_response_time_ms / self.request_count


class MetricsCollector:
    """Collects API request metrics, system resources, and sync metrics."""

    def __init__(self) -> None:
        self._start_time = time.monotonic()
        self._process_start_time = time.time()
        self._endpoint_metrics: dict[str, EndpointMetrics] = defaultdict(EndpointMetrics)
        self._lock = Lock()
        # Document sync metrics
        self._sync_metrics = {
            "reindex_count": 0,
            "reindex_errors": 0,
            "reindex_total_time_ms": 0.0,
            "ws_connections": 0,
            "ws_messages_sent": 0,
            "sync_status_updates": 0,
            "watcher_files_processed": 0,
            "watcher_errors": 0,
        }

    def record_request(self, path: str, elapsed_ms: float) -> None:
        """Record a completed API request."""
        with self._lock:
            m = self._endpoint_metrics[path]
            m.request_count += 1
            m.total_response_time_ms += elapsed_ms

    def get_endpoint_metrics(self) -> dict[str, dict]:
        """Return metrics for all tracked endpoints."""
        with self._lock:
            return {
                path: {
                    "path": path,
                    "request_count": m.request_count,
                    "avg_response_time_ms": round(m.avg_response_time_ms, 2),
                }
                for path, m in self._endpoint_metrics.items()
            }

    def get_uptime_seconds(self) -> float:
        """Return seconds since the collector was initialized."""
        return time.monotonic() - self._start_time

    # ---- Sync metrics ----

    def record_reindex(self, elapsed_ms: float, success: bool) -> None:
        """Record a completed reindex operation."""
        with self._lock:
            self._sync_metrics["reindex_count"] += 1
            self._sync_metrics["reindex_total_time_ms"] += elapsed_ms
            if not success:
                self._sync_metrics["reindex_errors"] += 1

    def record_ws_connection(self, delta: int) -> None:
        """Track WebSocket connection count changes (+1 connect, -1 disconnect)."""
        with self._lock:
            self._sync_metrics["ws_connections"] += delta

    def record_ws_message(self) -> None:
        """Record a WebSocket message sent."""
        with self._lock:
            self._sync_metrics["ws_messages_sent"] += 1

    def record_sync_status_update(self) -> None:
        """Record a sync status update."""
        with self._lock:
            self._sync_metrics["sync_status_updates"] += 1

    def record_watcher_event(self, success: bool) -> None:
        """Record a file watcher processing event."""
        with self._lock:
            if success:
                self._sync_metrics["watcher_files_processed"] += 1
            else:
                self._sync_metrics["watcher_errors"] += 1

    def get_sync_metrics(self) -> dict:
        """Return copy of sync metrics."""
        with self._lock:
            metrics = dict(self._sync_metrics)
            if metrics["reindex_count"] > 0:
                metrics["reindex_avg_time_ms"] = round(
                    metrics["reindex_total_time_ms"] / metrics["reindex_count"], 2
                )
            else:
                metrics["reindex_avg_time_ms"] = 0.0
            return metrics

    def get_system_resources(self) -> dict:
        """Read current system resource usage via psutil."""
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        sys_mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return {
            "process_memory_mb": round(mem_info.rss / (1024 * 1024), 1),
            "system_memory_total_mb": round(sys_mem.total / (1024 * 1024), 1),
            "system_memory_used_mb": round(sys_mem.used / (1024 * 1024), 1),
            "system_memory_available_mb": round(sys_mem.available / (1024 * 1024), 1),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
            "disk_used_gb": round(disk.used / (1024**3), 1),
            "disk_free_gb": round(disk.free / (1024**3), 1),
        }


# Module-level singleton
collector = MetricsCollector()


class MetricsMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for recording API request metrics."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        collector.record_request(request.url.path, elapsed_ms)
        return response
