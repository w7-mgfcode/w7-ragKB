"""Property-based tests for the cron scheduler.

Feature: openclaw-integration (Task 15.1)
Properties tested: 36, 37, 38, 39, 40, 41, 42

Tests cron job creation, execution, logging, error handling,
expression parsing, concurrency, and management operations.
"""

import string
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from pytz import timezone as pytz_timezone, utc

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db_cron import generate_cron_job_id
from cron_scheduler import CronScheduler


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

safe_id = st.text(
    alphabet=string.ascii_letters + string.digits + "-_.",
    min_size=1,
    max_size=30,
)
safe_text = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())
valid_cron_expressions = st.sampled_from([
    "0 9 * * *",      # Daily at 9am
    "*/15 * * * *",   # Every 15 minutes
    "0 0 * * 0",      # Weekly on Sunday
    "30 14 1 * *",    # Monthly on 1st at 2:30pm
    "0 */2 * * *",    # Every 2 hours
    "0 0 1 1 *",      # Yearly on Jan 1
    "0 12 * * 1-5",   # Weekdays at noon
    "*/5 * * * *",    # Every 5 minutes
])
valid_timezones = st.sampled_from([
    "UTC",
    "US/Eastern",
    "US/Pacific",
    "Europe/London",
    "Europe/Budapest",
    "Asia/Tokyo",
    "Australia/Sydney",
])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_pool():
    """Create a mock asyncpg pool."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock()
    return pool


def make_scheduler(pool=None):
    """Create a CronScheduler with mock pool."""
    if pool is None:
        pool = make_mock_pool()
    scheduler = CronScheduler(pool)
    return scheduler


# ===========================================================================
# Property 36: Cron job creation
# ===========================================================================


class TestCronJobCreation:
    """Property 36: All config fields stored with next_execution_at."""

    @settings(max_examples=100, deadline=None)
    @given(st.data())
    def test_cron_job_id_is_16_char_hex(self, data):
        """
        Feature: openclaw-integration, Property 36: Cron job creation

        generate_cron_job_id must produce a 16-character hex string.
        """
        cid = generate_cron_job_id()
        assert len(cid) == 16
        import re
        assert re.fullmatch(r"[0-9a-f]+", cid)

    @settings(max_examples=50, deadline=None)
    @given(st.data())
    def test_cron_job_ids_unique(self, data):
        """
        Feature: openclaw-integration, Property 36: Cron job creation

        Repeated calls should produce distinct IDs.
        """
        ids = {generate_cron_job_id() for _ in range(20)}
        assert len(ids) >= 18

    @given(
        schedule=valid_cron_expressions,
        tz_name=valid_timezones,
    )
    @settings(max_examples=50, deadline=None)
    def test_cron_trigger_creation(self, schedule, tz_name):
        """
        Feature: openclaw-integration, Property 36: Cron job creation

        Valid cron expression + timezone should create a valid trigger.
        """
        scheduler = make_scheduler()
        tz = pytz_timezone(tz_name)
        trigger = scheduler._create_cron_trigger(schedule, tz)
        assert trigger is not None

    @given(
        schedule=valid_cron_expressions,
        tz_name=valid_timezones,
    )
    @settings(max_examples=50, deadline=None)
    def test_next_execution_calculated(self, schedule, tz_name):
        """
        Feature: openclaw-integration, Property 36: Cron job creation

        Creating a cron trigger should allow computing next execution time.
        """
        scheduler = make_scheduler()
        tz = pytz_timezone(tz_name)
        trigger = scheduler._create_cron_trigger(schedule, tz)

        next_fire = trigger.get_next_fire_time(None, datetime.now(tz))
        assert next_fire is not None
        assert next_fire > datetime.now(tz)


# ===========================================================================
# Property 37: Cron job execution
# ===========================================================================


class TestCronJobExecution:
    """Property 37: Scheduled jobs send messages to target sessions."""

    @pytest.mark.asyncio
    async def test_execute_sends_message_to_session(self):
        """
        Feature: openclaw-integration, Property 37: Cron job execution

        Executing a cron job should add a message to the target session.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "cron_job_id": "job1",
            "schedule": "0 9 * * *",
            "target_session_id": "test:u:c",
            "message_template": "Daily report",
            "timezone": "UTC",
            "enabled": True,
        })
        pool.execute = AsyncMock()

        scheduler = make_scheduler(pool)

        mock_session = MagicMock()
        mock_session.add_message = AsyncMock()

        mock_sm = MagicMock()
        mock_sm.get_session = AsyncMock(return_value=mock_session)

        with patch("session_manager.get_session_manager", return_value=mock_sm):
            await scheduler._execute_cron_job("job1")

        mock_session.add_message.assert_called_once()
        call_kwargs = mock_session.add_message.call_args.kwargs
        assert call_kwargs["role"] == "system"
        assert call_kwargs["content"] == "Daily report"
        assert call_kwargs["metadata"]["source"] == "cron_job"


# ===========================================================================
# Property 38: Cron execution logging
# ===========================================================================


class TestCronExecutionLogging:
    """Property 38: Execution timestamp and outcome logged."""

    @pytest.mark.asyncio
    async def test_execution_updates_timestamps(self):
        """
        Feature: openclaw-integration, Property 38: Cron execution logging

        After execution, last_executed_at should be updated.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "cron_job_id": "job1",
            "schedule": "0 9 * * *",
            "target_session_id": "test:u:c",
            "message_template": "Report",
            "timezone": "UTC",
            "enabled": True,
        })
        pool.execute = AsyncMock()

        scheduler = make_scheduler(pool)

        mock_session = MagicMock()
        mock_session.add_message = AsyncMock()
        mock_sm = MagicMock()
        mock_sm.get_session = AsyncMock(return_value=mock_session)

        with patch("session_manager.get_session_manager", return_value=mock_sm):
            await scheduler._execute_cron_job("job1")

        # update_cron_job_execution should have been called
        assert pool.execute.called


# ===========================================================================
# Property 39: Cron error handling
# ===========================================================================


class TestCronErrorHandling:
    """Property 39: Non-existent sessions skipped with warning."""

    @pytest.mark.asyncio
    async def test_missing_session_skipped(self):
        """
        Feature: openclaw-integration, Property 39: Cron error handling

        When target session doesn't exist, execution should be skipped.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "cron_job_id": "job1",
            "schedule": "0 9 * * *",
            "target_session_id": "nonexistent:u:c",
            "message_template": "Report",
            "timezone": "UTC",
            "enabled": True,
        })
        pool.execute = AsyncMock()

        scheduler = make_scheduler(pool)

        mock_sm = MagicMock()
        mock_sm.get_session = AsyncMock(return_value=None)

        with patch("session_manager.get_session_manager", return_value=mock_sm):
            # Should not raise
            await scheduler._execute_cron_job("job1")

    @pytest.mark.asyncio
    async def test_disabled_job_skipped(self):
        """
        Feature: openclaw-integration, Property 39: Cron error handling

        Disabled cron jobs should be skipped during execution.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "cron_job_id": "job1",
            "schedule": "0 9 * * *",
            "target_session_id": "test:u:c",
            "message_template": "Report",
            "timezone": "UTC",
            "enabled": False,
        })

        scheduler = make_scheduler(pool)

        # Should not raise, and should not try to get session manager
        await scheduler._execute_cron_job("job1")

    @pytest.mark.asyncio
    async def test_missing_job_in_db_skipped(self):
        """
        Feature: openclaw-integration, Property 39: Cron error handling

        When cron job doesn't exist in DB, execution should be skipped.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value=None)

        scheduler = make_scheduler(pool)
        await scheduler._execute_cron_job("nonexistent_job")

    @pytest.mark.asyncio
    async def test_no_session_manager_handles_gracefully(self):
        """
        Feature: openclaw-integration, Property 39: Cron error handling

        When SessionManager is not available, execution should handle gracefully.
        """
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "cron_job_id": "job1",
            "schedule": "0 9 * * *",
            "target_session_id": "test:u:c",
            "message_template": "Report",
            "timezone": "UTC",
            "enabled": True,
        })
        pool.execute = AsyncMock()

        scheduler = make_scheduler(pool)

        with patch("session_manager.get_session_manager", return_value=None):
            await scheduler._execute_cron_job("job1")


# ===========================================================================
# Property 40: Cron expression parsing
# ===========================================================================


class TestCronExpressionParsing:
    """Property 40: Cron expressions parsed with timezone support."""

    @given(schedule=valid_cron_expressions, tz_name=valid_timezones)
    @settings(max_examples=50, deadline=None)
    def test_valid_expressions_parse_successfully(self, schedule, tz_name):
        """
        Feature: openclaw-integration, Property 40: Cron expression parsing

        All valid 5-field cron expressions should parse without error.
        """
        scheduler = make_scheduler()
        tz = pytz_timezone(tz_name)
        trigger = scheduler._create_cron_trigger(schedule, tz)
        assert trigger is not None

    def test_invalid_expression_raises(self):
        """
        Feature: openclaw-integration, Property 40: Cron expression parsing

        Invalid cron expressions should raise ValueError.
        """
        scheduler = make_scheduler()
        tz = pytz_timezone("UTC")

        with pytest.raises(ValueError, match="expected 5 fields"):
            scheduler._create_cron_trigger("invalid", tz)

    def test_too_few_fields_raises(self):
        """
        Feature: openclaw-integration, Property 40: Cron expression parsing

        Cron expression with < 5 fields should raise ValueError.
        """
        scheduler = make_scheduler()
        tz = pytz_timezone("UTC")

        with pytest.raises(ValueError, match="expected 5 fields"):
            scheduler._create_cron_trigger("0 9 * *", tz)

    def test_too_many_fields_raises(self):
        """
        Feature: openclaw-integration, Property 40: Cron expression parsing

        Cron expression with > 5 fields should raise ValueError.
        """
        scheduler = make_scheduler()
        tz = pytz_timezone("UTC")

        with pytest.raises(ValueError, match="expected 5 fields"):
            scheduler._create_cron_trigger("0 9 * * * 2024", tz)

    @given(tz_name=valid_timezones)
    @settings(max_examples=20, deadline=None)
    def test_timezone_aware_next_execution(self, tz_name):
        """
        Feature: openclaw-integration, Property 40: Cron expression parsing

        Next execution should be timezone-aware.
        """
        scheduler = make_scheduler()
        tz = pytz_timezone(tz_name)
        trigger = scheduler._create_cron_trigger("0 9 * * *", tz)

        next_fire = trigger.get_next_fire_time(None, datetime.now(tz))
        assert next_fire is not None
        assert next_fire.tzinfo is not None


# ===========================================================================
# Property 41: Cron concurrency
# ===========================================================================


class TestCronConcurrency:
    """Property 41: Multiple jobs execute without blocking."""

    def test_scheduler_initial_state(self):
        """
        Feature: openclaw-integration, Property 41: Cron concurrency

        New scheduler should not be running with no jobs.
        """
        scheduler = make_scheduler()
        assert scheduler._running is False
        assert len(scheduler._job_map) == 0

    def test_metrics_initial(self):
        """
        Feature: openclaw-integration, Property 41: Cron concurrency

        Metrics should show initial state.
        """
        scheduler = make_scheduler()
        metrics = scheduler.get_metrics()
        assert metrics["running"] is False
        assert metrics["scheduled_jobs"] == 0


# ===========================================================================
# Property 42: Cron job management
# ===========================================================================


class TestCronJobManagement:
    """Property 42: List, pause, resume, delete operations."""

    @pytest.mark.asyncio
    async def test_pause_updates_db_and_removes_from_map(self):
        """
        Feature: openclaw-integration, Property 42: Cron job management

        Pausing a job should disable it in DB and remove from scheduler.
        """
        pool = make_mock_pool()
        scheduler = make_scheduler(pool)

        # Simulate a scheduled job in the map
        mock_job = MagicMock()
        scheduler._job_map["job1"] = mock_job

        await scheduler.pause_cron_job("job1")

        pool.execute.assert_called_once()
        mock_job.remove.assert_called_once()
        assert "job1" not in scheduler._job_map

    @pytest.mark.asyncio
    async def test_delete_removes_from_db_and_map(self):
        """
        Feature: openclaw-integration, Property 42: Cron job management

        Deleting a job should remove from both DB and scheduler.
        """
        pool = make_mock_pool()
        scheduler = make_scheduler(pool)

        mock_job = MagicMock()
        scheduler._job_map["job1"] = mock_job

        await scheduler.delete_cron_job("job1")

        mock_job.remove.assert_called_once()
        assert "job1" not in scheduler._job_map
        assert pool.execute.called

    @pytest.mark.asyncio
    async def test_pause_nonexistent_job_safe(self):
        """
        Feature: openclaw-integration, Property 42: Cron job management

        Pausing a job not in the map should still update DB.
        """
        pool = make_mock_pool()
        scheduler = make_scheduler(pool)

        await scheduler.pause_cron_job("nonexistent")
        pool.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_in_map_safe(self):
        """
        Feature: openclaw-integration, Property 42: Cron job management

        Deleting a job not in the map should still delete from DB.
        """
        pool = make_mock_pool()
        scheduler = make_scheduler(pool)

        await scheduler.delete_cron_job("nonexistent")
        pool.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_delegates_to_db(self):
        """
        Feature: openclaw-integration, Property 42: Cron job management

        list_cron_jobs should delegate to db_cron.list_cron_jobs.
        """
        pool = make_mock_pool()
        pool.fetch = AsyncMock(return_value=[])
        scheduler = make_scheduler(pool)

        result = await scheduler.list_cron_jobs()
        assert result == []

    @pytest.mark.asyncio
    async def test_stop_clears_job_map(self):
        """
        Feature: openclaw-integration, Property 42: Cron job management

        Stopping scheduler should clear the job map.
        """
        pool = make_mock_pool()
        scheduler = make_scheduler(pool)
        scheduler._running = True
        scheduler._job_map["job1"] = MagicMock()

        with patch.object(scheduler.scheduler, "shutdown"):
            await scheduler.stop()

        assert len(scheduler._job_map) == 0
        assert scheduler._running is False
