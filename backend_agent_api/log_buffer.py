"""Fixed-size circular log buffer for the System Monitor."""

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock


@dataclass
class LogRecord:
    timestamp: str
    logger: str
    level: str
    message: str


class LogBufferHandler(logging.Handler):
    """Logging handler that stores records in a circular buffer."""

    def __init__(self, max_size: int = 500) -> None:
        super().__init__()
        self._buffer: deque[LogRecord] = deque(maxlen=max_size)
        self._lock = Lock()

    def emit(self, record: logging.LogRecord) -> None:
        entry = LogRecord(
            timestamp=datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            logger=record.name,
            level=record.levelname,
            message=self.format(record),
        )
        with self._lock:
            self._buffer.append(entry)

    def get_records(self, min_level: str = "DEBUG") -> list[dict]:
        """Return buffered records at or above the given severity."""
        level_num = getattr(logging, min_level.upper(), logging.DEBUG)
        with self._lock:
            return [
                {
                    "timestamp": r.timestamp,
                    "logger": r.logger,
                    "level": r.level,
                    "message": r.message,
                }
                for r in self._buffer
                if getattr(logging, r.level, 0) >= level_num
            ]


# Module-level singleton
log_handler = LogBufferHandler(max_size=500)
