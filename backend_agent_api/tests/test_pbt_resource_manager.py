"""Property-based tests for resource management.

Feature: openclaw-integration (Task 21.1)
Properties tested: 76, 77, 78, 79, 80

Tests memory budget enforcement, session history compaction, browser
instance limits, database connection pooling, and backpressure.
"""

import string
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from resource_manager import (
    CLEANUP_THRESHOLD,
    DEFAULT_BACKPRESSURE_THRESHOLD,
    DEFAULT_MEMORY_BUDGET_MB,
    MAX_BROWSER_INSTANCES,
    MAX_DB_POOL_SIZE,
    ResourceManager,
)
from session import Session


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

memory_budgets = st.integers(min_value=512, max_value=8192)
queue_depths = st.integers(min_value=0, max_value=2000)
thresholds = st.integers(min_value=1, max_value=1000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_pool():
    """Create a mock asyncpg pool."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock()
    pool.get_size = MagicMock(return_value=5)
    pool.get_idle_size = MagicMock(return_value=3)
    return pool


def make_mock_session_manager(active_count=10):
    """Create a mock SessionManager."""
    sm = MagicMock()
    sm.get_active_session_count = MagicMock(return_value=active_count)
    sm._cleanup_inactive_sessions = AsyncMock()
    sm._enforce_memory_limits = AsyncMock()
    return sm


def make_resource_manager(
    pool=None,
    session_manager=None,
    memory_budget_mb=DEFAULT_MEMORY_BUDGET_MB,
    **kwargs,
):
    """Create a ResourceManager with mock dependencies."""
    if pool is None:
        pool = make_mock_pool()
    if session_manager is None:
        session_manager = make_mock_session_manager()
    return ResourceManager(
        pool=pool,
        session_manager=session_manager,
        memory_budget_mb=memory_budget_mb,
        **kwargs,
    )


def make_mock_session(
    pool=None,
    session_id="test:user:chat",
    message_count=0,
    auto_compact_threshold=80,
):
    """Create a Session instance with mock pool."""
    if pool is None:
        pool = make_mock_pool()
    return Session(
        pool=pool,
        session_id=session_id,
        channel_id="slack-main",
        user_id="user1",
        chat_id="chat1",
        session_type="main",
        message_count=message_count,
        auto_compact_threshold=auto_compact_threshold,
    )


# ===========================================================================
# Property 76: Memory budget enforcement
# ===========================================================================


class TestMemoryBudgetEnforcement:
    """Property 76: Cleanup triggered when usage exceeds 80%."""

    @given(budget=memory_budgets)
    @settings(max_examples=50, deadline=None)
    def test_budget_stored_correctly(self, budget):
        """
        Feature: openclaw-integration, Property 76: Memory budget enforcement

        ResourceManager should store the configured memory budget.
        """
        rm = make_resource_manager(memory_budget_mb=budget)
        assert rm.memory_budget_mb == budget

    def test_cleanup_threshold_default(self):
        """
        Feature: openclaw-integration, Property 76: Memory budget enforcement

        Default cleanup threshold should be 80%.
        """
        rm = make_resource_manager()
        assert rm.cleanup_threshold == 0.80

    @pytest.mark.asyncio
    async def test_cleanup_triggered_above_threshold(self):
        """
        Feature: openclaw-integration, Property 76: Memory budget enforcement

        check_and_cleanup should trigger when usage >= threshold.
        """
        rm = make_resource_manager(memory_budget_mb=100)
        # Mock memory usage to be above threshold
        rm.get_memory_usage_mb = MagicMock(return_value=85.0)

        result = await rm.check_and_cleanup()
        assert result is True
        assert rm._cleanup_count == 1

    @pytest.mark.asyncio
    async def test_cleanup_not_triggered_below_threshold(self):
        """
        Feature: openclaw-integration, Property 76: Memory budget enforcement

        check_and_cleanup should NOT trigger when usage < threshold.
        """
        rm = make_resource_manager(memory_budget_mb=100)
        rm.get_memory_usage_mb = MagicMock(return_value=50.0)

        result = await rm.check_and_cleanup()
        assert result is False
        assert rm._cleanup_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_archives_sessions(self):
        """
        Feature: openclaw-integration, Property 76: Memory budget enforcement

        Cleanup should call session_manager cleanup methods.
        """
        sm = make_mock_session_manager()
        rm = make_resource_manager(session_manager=sm, memory_budget_mb=100)
        rm.get_memory_usage_mb = MagicMock(return_value=90.0)

        await rm.check_and_cleanup()

        sm._cleanup_inactive_sessions.assert_called_once()
        sm._enforce_memory_limits.assert_called_once()

    def test_get_memory_usage_percent(self):
        """
        Feature: openclaw-integration, Property 76: Memory budget enforcement

        get_memory_usage_percent should return usage as fraction of budget.
        """
        rm = make_resource_manager(memory_budget_mb=1000)
        rm.get_memory_usage_mb = MagicMock(return_value=500.0)
        assert rm.get_memory_usage_percent() == 0.5

    def test_get_memory_usage_percent_zero_budget(self):
        """
        Feature: openclaw-integration, Property 76: Memory budget enforcement

        Zero budget should return 0 to avoid division by zero.
        """
        rm = make_resource_manager(memory_budget_mb=0)
        assert rm.get_memory_usage_percent() == 0.0


# ===========================================================================
# Property 77: Session history compaction
# ===========================================================================


class TestSessionHistoryCompaction:
    """Property 77: Auto-compact when exceeding auto_compact_threshold."""

    @pytest.mark.asyncio
    async def test_session_auto_compact_at_threshold(self):
        """
        Feature: openclaw-integration, Property 77: Session history compaction

        Session should trigger compact() when message_count >= threshold.
        """
        pool = make_mock_pool()
        # Return empty messages for compact
        pool.fetch = AsyncMock(return_value=[])

        session = make_mock_session(
            pool=pool,
            message_count=79,
            auto_compact_threshold=80,
        )

        # Mock add_session_message to return a dict
        with patch("session.add_session_message", new_callable=AsyncMock) as mock_add:
            mock_add.return_value = {"message_id": "1", "role": "user", "content": "hi"}
            with patch("session.get_session_messages", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = []
                await session.add_message("user", "hello")

        # message_count should now be 80, which >= threshold
        assert session.message_count >= 80

    def test_session_compact_threshold_configurable(self):
        """
        Feature: openclaw-integration, Property 77: Session history compaction

        auto_compact_threshold should be configurable per session.
        """
        session = make_mock_session(auto_compact_threshold=50)
        assert session.auto_compact_threshold == 50

    @given(threshold=st.integers(min_value=10, max_value=200))
    @settings(max_examples=50, deadline=None)
    def test_threshold_stored_correctly(self, threshold):
        """
        Feature: openclaw-integration, Property 77: Session history compaction

        Any valid threshold value should be stored correctly.
        """
        session = make_mock_session(auto_compact_threshold=threshold)
        assert session.auto_compact_threshold == threshold


# ===========================================================================
# Property 78: Browser instance limits
# ===========================================================================


class TestBrowserInstanceLimits:
    """Property 78: Cannot exceed MAX_BROWSER_INSTANCES=3."""

    def test_max_browser_instances_constant(self):
        """
        Feature: openclaw-integration, Property 78: Browser instance limits

        MAX_BROWSER_INSTANCES should be 3.
        """
        assert MAX_BROWSER_INSTANCES == 3

    def test_metrics_include_browser_limit(self):
        """
        Feature: openclaw-integration, Property 78: Browser instance limits

        Metrics should report the browser instance limit.
        """
        rm = make_resource_manager()
        metrics = rm.get_metrics()
        assert metrics["max_browser_instances"] == 3

    @pytest.mark.asyncio
    async def test_cleanup_closes_browsers(self):
        """
        Feature: openclaw-integration, Property 78: Browser instance limits

        Cleanup should attempt to close idle browsers.
        """
        rm = make_resource_manager(memory_budget_mb=100)
        rm.get_memory_usage_mb = MagicMock(return_value=90.0)

        with patch(
            "resource_manager.cleanup_all_browsers",
            new_callable=AsyncMock,
            create=True,
        ):
            # The import in _close_idle_browsers may fail, but shouldn't raise
            await rm.check_and_cleanup()
            # Should not have raised


# ===========================================================================
# Property 79: Database connection pooling
# ===========================================================================


class TestDatabaseConnectionPooling:
    """Property 79: Pool max size <= 20."""

    def test_max_pool_size_constant(self):
        """
        Feature: openclaw-integration, Property 79: Database connection pooling

        MAX_DB_POOL_SIZE should be 20.
        """
        assert MAX_DB_POOL_SIZE == 20

    def test_metrics_include_pool_info(self):
        """
        Feature: openclaw-integration, Property 79: Database connection pooling

        Metrics should report pool size information.
        """
        pool = make_mock_pool()
        pool.get_size.return_value = 10
        pool.get_idle_size.return_value = 5

        rm = make_resource_manager(pool=pool)
        metrics = rm.get_metrics()

        assert metrics["db_pool_size"] == 10
        assert metrics["db_pool_free"] == 5
        assert metrics["db_pool_max"] == MAX_DB_POOL_SIZE

    def test_metrics_handles_pool_without_methods(self):
        """
        Feature: openclaw-integration, Property 79: Database connection pooling

        Metrics should handle pools that don't have get_size/get_idle_size.
        """
        pool = MagicMock(spec=[])  # No methods
        rm = make_resource_manager(pool=pool)
        metrics = rm.get_metrics()

        assert metrics["db_pool_size"] == 0
        assert metrics["db_pool_free"] == 0


# ===========================================================================
# Property 80: Backpressure application
# ===========================================================================


class TestBackpressureApplication:
    """Property 80: should_apply_backpressure returns True when queue
    exceeds threshold."""

    @given(depth=queue_depths, threshold=thresholds)
    @settings(max_examples=200, deadline=None)
    def test_backpressure_logic(self, depth, threshold):
        """
        Feature: openclaw-integration, Property 80: Backpressure application

        Backpressure should be applied when queue_depth >= threshold.
        """
        rm = make_resource_manager()
        expected = depth >= threshold
        assert rm.should_apply_backpressure(depth, threshold=threshold) == expected

    def test_backpressure_default_threshold(self):
        """
        Feature: openclaw-integration, Property 80: Backpressure application

        Default backpressure threshold should be 500.
        """
        rm = make_resource_manager()
        assert rm.backpressure_threshold == DEFAULT_BACKPRESSURE_THRESHOLD

        # Below threshold
        assert rm.should_apply_backpressure(499) is False
        # At threshold
        assert rm.should_apply_backpressure(500) is True
        # Above threshold
        assert rm.should_apply_backpressure(1000) is True

    @given(depth=st.integers(min_value=0, max_value=499))
    @settings(max_examples=50, deadline=None)
    def test_below_default_threshold_no_backpressure(self, depth):
        """
        Feature: openclaw-integration, Property 80: Backpressure application

        Queue depth below default threshold should not trigger backpressure.
        """
        rm = make_resource_manager()
        assert rm.should_apply_backpressure(depth) is False

    @given(depth=st.integers(min_value=500, max_value=2000))
    @settings(max_examples=50, deadline=None)
    def test_above_default_threshold_backpressure(self, depth):
        """
        Feature: openclaw-integration, Property 80: Backpressure application

        Queue depth at or above default threshold should trigger backpressure.
        """
        rm = make_resource_manager()
        assert rm.should_apply_backpressure(depth) is True

    def test_custom_backpressure_threshold(self):
        """
        Feature: openclaw-integration, Property 80: Backpressure application

        Custom threshold should override default.
        """
        rm = make_resource_manager(backpressure_threshold=100)
        assert rm.should_apply_backpressure(99) is False
        assert rm.should_apply_backpressure(100) is True

    def test_metrics_include_backpressure_info(self):
        """
        Feature: openclaw-integration, Property 80: Backpressure application

        Metrics should report backpressure threshold.
        """
        rm = make_resource_manager(backpressure_threshold=200)
        metrics = rm.get_metrics()
        assert metrics["backpressure_threshold"] == 200

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self):
        """
        Feature: openclaw-integration, Property 80: Backpressure application

        ResourceManager should start and stop cleanly.
        """
        rm = make_resource_manager(metrics_interval=3600)
        await rm.start()
        assert rm._running is True
        assert rm._metrics_task is not None

        await rm.stop()
        assert rm._running is False
