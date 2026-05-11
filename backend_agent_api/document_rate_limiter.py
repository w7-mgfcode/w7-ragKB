"""Rate limiter for document mutation endpoints.

Limits document write operations to prevent abuse.
Uses sliding window approach keyed by user_id.
"""

import time
from collections import defaultdict

MAX_REQUESTS = 100
WINDOW_SECONDS = 60  # 1 minute

_requests: dict[str, list[float]] = defaultdict(list)


def _prune_expired(user_id: str) -> None:
    """Remove timestamps outside the sliding window."""
    cutoff = time.monotonic() - WINDOW_SECONDS
    _requests[user_id] = [t for t in _requests[user_id] if t > cutoff]
    if not _requests[user_id]:
        del _requests[user_id]


def check_document_rate_limit(user_id: str) -> bool:
    """Return True if user_id has exceeded document operation rate limit."""
    _prune_expired(user_id)
    return len(_requests.get(user_id, [])) >= MAX_REQUESTS


def record_document_request(user_id: str) -> None:
    """Record a document mutation request."""
    _requests[user_id].append(time.monotonic())


def get_retry_after(user_id: str) -> int:
    """Return seconds until rate limit resets."""
    if not _requests.get(user_id):
        return 0
    oldest = min(_requests[user_id])
    return max(1, int(WINDOW_SECONDS - (time.monotonic() - oldest)))
