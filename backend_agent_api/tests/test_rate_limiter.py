"""Unit and property tests for rate_limiter module."""

import time
from unittest.mock import patch

import pytest
from hypothesis import given, settings, strategies as st

import rate_limiter
from rate_limiter import (
    MAX_ATTEMPTS,
    WINDOW_SECONDS,
    check_rate_limit,
    record_failed_attempt,
    reset_attempts,
)


@pytest.fixture(autouse=True)
def clear_state():
    """Reset the internal attempts dict before each test."""
    rate_limiter._attempts.clear()
    yield
    rate_limiter._attempts.clear()


class TestCheckRateLimit:
    def test_not_blocked_with_no_attempts(self):
        assert check_rate_limit("user@example.com") is False

    def test_not_blocked_under_threshold(self):
        for _ in range(MAX_ATTEMPTS - 1):
            record_failed_attempt("user@example.com")
        assert check_rate_limit("user@example.com") is False

    def test_blocked_at_threshold(self):
        for _ in range(MAX_ATTEMPTS):
            record_failed_attempt("user@example.com")
        assert check_rate_limit("user@example.com") is True

    def test_blocked_above_threshold(self):
        for _ in range(MAX_ATTEMPTS + 3):
            record_failed_attempt("user@example.com")
        assert check_rate_limit("user@example.com") is True

    def test_different_emails_are_independent(self):
        for _ in range(MAX_ATTEMPTS):
            record_failed_attempt("blocked@example.com")
        assert check_rate_limit("blocked@example.com") is True
        assert check_rate_limit("other@example.com") is False


class TestRecordFailedAttempt:
    def test_increments_count(self):
        record_failed_attempt("user@example.com")
        assert len(rate_limiter._attempts["user@example.com"]) == 1
        record_failed_attempt("user@example.com")
        assert len(rate_limiter._attempts["user@example.com"]) == 2


class TestResetAttempts:
    def test_clears_attempts(self):
        for _ in range(MAX_ATTEMPTS):
            record_failed_attempt("user@example.com")
        assert check_rate_limit("user@example.com") is True
        reset_attempts("user@example.com")
        assert check_rate_limit("user@example.com") is False

    def test_reset_nonexistent_email_is_safe(self):
        reset_attempts("nobody@example.com")  # should not raise


class TestSlidingWindow:
    def test_old_attempts_expire(self):
        """Attempts older than the window should be pruned."""
        now = time.monotonic()
        # Inject timestamps that are outside the window
        rate_limiter._attempts["user@example.com"] = [
            now - WINDOW_SECONDS - 1 for _ in range(MAX_ATTEMPTS)
        ]
        # All attempts are expired, so should not be blocked
        assert check_rate_limit("user@example.com") is False

    def test_mix_of_old_and_new_attempts(self):
        """Only recent attempts within the window should count."""
        now = time.monotonic()
        old = [now - WINDOW_SECONDS - 10 for _ in range(3)]
        recent = [now - 1 for _ in range(3)]
        rate_limiter._attempts["user@example.com"] = old + recent
        # 3 recent attempts < MAX_ATTEMPTS (5), so not blocked
        assert check_rate_limit("user@example.com") is False

    def test_window_boundary_exact(self):
        """Attempts exactly at the cutoff boundary should be pruned."""
        now = time.monotonic()
        # Timestamps exactly at the cutoff (cutoff = now - WINDOW_SECONDS)
        # _prune_expired keeps only t > cutoff, so t == cutoff is pruned
        rate_limiter._attempts["user@example.com"] = [
            now - WINDOW_SECONDS for _ in range(MAX_ATTEMPTS)
        ]
        assert check_rate_limit("user@example.com") is False


# --- Property-based tests ---

email_strategy = st.emails()


class TestRateLimiterProperties:
    """Property-based tests for rate limiter correctness.

    **Validates: Requirements 2.4**
    """

    @given(email=email_strategy, n=st.integers(min_value=0, max_value=20))
    @settings(max_examples=100)
    def test_blocked_iff_at_least_max_attempts(self, email: str, n: int):
        """After n failed attempts, blocked iff n >= MAX_ATTEMPTS."""
        rate_limiter._attempts.clear()
        for _ in range(n):
            record_failed_attempt(email)
        assert check_rate_limit(email) == (n >= MAX_ATTEMPTS)

    @given(email=email_strategy)
    @settings(max_examples=100)
    def test_reset_always_unblocks(self, email: str):
        """After reset, the email should never be blocked."""
        rate_limiter._attempts.clear()
        for _ in range(MAX_ATTEMPTS + 1):
            record_failed_attempt(email)
        reset_attempts(email)
        assert check_rate_limit(email) is False
