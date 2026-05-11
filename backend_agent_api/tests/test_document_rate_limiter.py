"""Unit tests for document rate limiter."""

import time
from unittest.mock import patch

from document_rate_limiter import (
    MAX_REQUESTS,
    WINDOW_SECONDS,
    _requests,
    check_document_rate_limit,
    get_retry_after,
    record_document_request,
)


class TestDocumentRateLimiter:
    """Tests for document-specific rate limiter."""

    def setup_method(self):
        """Clear rate limiter state before each test."""
        _requests.clear()

    def test_under_limit_allows(self):
        """Should allow requests under the limit."""
        for _ in range(MAX_REQUESTS - 1):
            record_document_request("user1")
        assert check_document_rate_limit("user1") is False

    def test_at_limit_blocks(self):
        """Should block at exactly the limit."""
        for _ in range(MAX_REQUESTS):
            record_document_request("user1")
        assert check_document_rate_limit("user1") is True

    def test_window_expiry_resets(self):
        """Should allow requests after window expires."""
        base_time = 1000.0
        with patch("document_rate_limiter.time") as mock_time:
            mock_time.monotonic.return_value = base_time

            for _ in range(MAX_REQUESTS):
                record_document_request("user1")

            assert check_document_rate_limit("user1") is True

            # Advance time past window
            mock_time.monotonic.return_value = base_time + WINDOW_SECONDS + 1
            assert check_document_rate_limit("user1") is False

    def test_different_users_independent(self):
        """Should track users independently."""
        for _ in range(MAX_REQUESTS):
            record_document_request("user_a")

        assert check_document_rate_limit("user_a") is True
        assert check_document_rate_limit("user_b") is False

    def test_retry_after_value(self):
        """Should return reasonable retry-after seconds."""
        record_document_request("user1")
        retry = get_retry_after("user1")
        assert 1 <= retry <= WINDOW_SECONDS

    def test_retry_after_no_requests(self):
        """Should return 0 when no requests recorded."""
        assert get_retry_after("nonexistent") == 0

    def test_fresh_user_not_limited(self):
        """New users should never be rate limited."""
        assert check_document_rate_limit("brand_new_user") is False
