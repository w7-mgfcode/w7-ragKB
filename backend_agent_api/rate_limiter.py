"""In-memory rate limiter for failed login attempts.

Tracks failed login attempts per email using a sliding window.
Designed for minimal RAM usage on the 4GB VM.
"""

import time
from collections import defaultdict

# Rate limit configuration
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60  # 15 minutes

# Storage: email -> list of attempt timestamps
_attempts: dict[str, list[float]] = defaultdict(list)


def _prune_expired(email: str) -> None:
    """Remove timestamps outside the sliding window."""
    cutoff = time.monotonic() - WINDOW_SECONDS
    _attempts[email] = [t for t in _attempts[email] if t > cutoff]
    if not _attempts[email]:
        del _attempts[email]


def check_rate_limit(email: str) -> bool:
    """Return True if the email is blocked (too many failed attempts)."""
    _prune_expired(email)
    return len(_attempts.get(email, [])) >= MAX_ATTEMPTS


def record_failed_attempt(email: str) -> None:
    """Record a failed login attempt for the given email."""
    _attempts[email].append(time.monotonic())


def reset_attempts(email: str) -> None:
    """Clear all failed attempts for the given email (e.g. on successful login)."""
    _attempts.pop(email, None)
