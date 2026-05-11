"""Unit tests for the cron scheduler.

Feature: openclaw-integration (Task 15.2)
Tests: Cron expression parsing, timezone conversion,
next execution time calculation, job lifecycle.
"""

import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytz import timezone as pytz_timezone, utc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db_cron import generate_cron_job_id
from cron_scheduler import CronScheduler


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
    return CronScheduler(pool)


# ===========================================================================
# Cron expression parsing
# ===========================================================================


class TestCronExpressionParsing:
    """Unit tests for _create_cron_trigger."""

    def test_daily_at_9am(self):
        """Daily at 9am: 0 9 * * *."""
        scheduler = make_scheduler()
        trigger = scheduler._create_cron_trigger("0 9 * * *", utc)
        assert trigger is not None

    def test_every_15_minutes(self):
        """Every 15 minutes: */15 * * * *."""
        scheduler = make_scheduler()
        trigger = scheduler._create_cron_trigger("*/15 * * * *", utc)
        assert trigger is not None

    def test_weekdays_at_noon(self):
        """Weekdays at noon: 0 12 * * 1-5."""
        scheduler = make_scheduler()
        trigger = scheduler._create_cron_trigger("0 12 * * 1-5", utc)
        assert trigger is not None

    def test_monthly_first_day(self):
        """Monthly on 1st: 0 0 1 * *."""
        scheduler = make_scheduler()
        trigger = scheduler._create_cron_trigger("0 0 1 * *", utc)
        assert trigger is not None

    def test_yearly_jan_1(self):
        """Yearly on Jan 1: 0 0 1 1 *."""
        scheduler = make_scheduler()
        trigger = scheduler._create_cron_trigger("0 0 1 1 *", utc)
        assert trigger is not None

    def test_invalid_single_field(self):
        """Single field should raise ValueError."""
        scheduler = make_scheduler()
        with pytest.raises(ValueError, match="expected 5 fields"):
            scheduler._create_cron_trigger("invalid", utc)

    def test_empty_string_raises(self):
        """Empty string should raise ValueError."""
        scheduler = make_scheduler()
        with pytest.raises(ValueError, match="expected 5 fields"):
            scheduler._create_cron_trigger("", utc)

    def test_six_fields_raises(self):
        """Six fields should raise ValueError (not standard cron)."""
        scheduler = make_scheduler()
        with pytest.raises(ValueError, match="expected 5 fields"):
            scheduler._create_cron_trigger("0 0 * * * 2024", utc)


# ===========================================================================
# Timezone conversion
# ===========================================================================


class TestTimezoneConversion:
    """Unit tests for timezone handling in cron triggers."""

    def test_utc_timezone(self):
        """UTC timezone should work."""
        scheduler = make_scheduler()
        tz = pytz_timezone("UTC")
        trigger = scheduler._create_cron_trigger("0 9 * * *", tz)
        next_fire = trigger.get_next_fire_time(None, datetime.now(tz))
        assert next_fire.tzinfo is not None

    def test_eastern_timezone(self):
        """US/Eastern timezone should work."""
        scheduler = make_scheduler()
        tz = pytz_timezone("US/Eastern")
        trigger = scheduler._create_cron_trigger("0 9 * * *", tz)
        next_fire = trigger.get_next_fire_time(None, datetime.now(tz))
        assert next_fire is not None

    def test_tokyo_timezone(self):
        """Asia/Tokyo timezone should work."""
        scheduler = make_scheduler()
        tz = pytz_timezone("Asia/Tokyo")
        trigger = scheduler._create_cron_trigger("0 9 * * *", tz)
        next_fire = trigger.get_next_fire_time(None, datetime.now(tz))
        assert next_fire is not None

    def test_budapest_timezone(self):
        """Europe/Budapest timezone should work."""
        scheduler = make_scheduler()
        tz = pytz_timezone("Europe/Budapest")
        trigger = scheduler._create_cron_trigger("0 9 * * *", tz)
        next_fire = trigger.get_next_fire_time(None, datetime.now(tz))
        assert next_fire is not None

    def test_different_timezones_different_next_fire(self):
        """Same schedule in different timezones should give different UTC times."""
        scheduler = make_scheduler()
        tz_utc = pytz_timezone("UTC")
        tz_tokyo = pytz_timezone("Asia/Tokyo")
        now_utc = datetime.now(tz_utc)
        now_tokyo = datetime.now(tz_tokyo)

        trigger_utc = scheduler._create_cron_trigger("0 9 * * *", tz_utc)
        trigger_tokyo = scheduler._create_cron_trigger("0 9 * * *", tz_tokyo)

        next_utc = trigger_utc.get_next_fire_time(None, now_utc)
        next_tokyo = trigger_tokyo.get_next_fire_time(None, now_tokyo)

        # The UTC equivalents should differ (9am UTC != 9am JST)
        assert next_utc != next_tokyo


# ===========================================================================
# Next execution time calculation
# ===========================================================================


class TestNextExecutionTime:
    """Unit tests for next execution time calculation."""

    def test_next_fire_is_in_future(self):
        """Next execution should always be in the future."""
        scheduler = make_scheduler()
        tz = pytz_timezone("UTC")
        now = datetime.now(tz)

        for expr in ["*/5 * * * *", "0 9 * * *", "0 0 * * 0", "0 0 1 * *"]:
            trigger = scheduler._create_cron_trigger(expr, tz)
            next_fire = trigger.get_next_fire_time(None, now)
            assert next_fire > now, f"Failed for expression: {expr}"

    def test_every_minute_next_fire_within_60s(self):
        """*/1 * * * * should fire within 60 seconds."""
        scheduler = make_scheduler()
        tz = pytz_timezone("UTC")
        now = datetime.now(tz)

        trigger = scheduler._create_cron_trigger("* * * * *", tz)
        next_fire = trigger.get_next_fire_time(None, now)

        delta = (next_fire - now).total_seconds()
        assert 0 < delta <= 60

    def test_hourly_next_fire_within_3600s(self):
        """0 * * * * should fire within 3600 seconds."""
        scheduler = make_scheduler()
        tz = pytz_timezone("UTC")
        now = datetime.now(tz)

        trigger = scheduler._create_cron_trigger("0 * * * *", tz)
        next_fire = trigger.get_next_fire_time(None, now)

        delta = (next_fire - now).total_seconds()
        assert 0 < delta <= 3600


# ===========================================================================
# Job lifecycle
# ===========================================================================


class TestJobLifecycle:
    """Unit tests for job lifecycle operations."""

    @pytest.mark.asyncio
    async def test_register_creates_db_entry(self):
        """register_cron_job should create DB entry."""
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "cron_job_id": "new_job",
            "schedule": "0 9 * * *",
            "target_session_id": "test:u:c",
            "message_template": "Hello",
            "timezone": "UTC",
            "enabled": True,
            "next_execution_at": datetime.now(utc),
        })

        scheduler = make_scheduler(pool)
        result = await scheduler.register_cron_job(
            schedule="0 9 * * *",
            target_session_id="test:u:c",
            message_template="Hello",
        )

        assert result["cron_job_id"] == "new_job"
        pool.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_invalid_expression_raises(self):
        """Invalid cron expression should raise ValueError."""
        scheduler = make_scheduler()

        with pytest.raises(ValueError):
            await scheduler.register_cron_job(
                schedule="invalid",
                target_session_id="test:u:c",
                message_template="Hello",
            )

    @pytest.mark.asyncio
    async def test_resume_enables_and_reschedules(self):
        """resume_cron_job should enable in DB and reschedule."""
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "cron_job_id": "job1",
            "schedule": "0 9 * * *",
            "target_session_id": "test:u:c",
            "message_template": "Hello",
            "timezone": "UTC",
            "enabled": True,
        })

        scheduler = make_scheduler(pool)
        scheduler._running = True

        with patch.object(scheduler, "_schedule_job", new_callable=AsyncMock) as mock_schedule:
            await scheduler.resume_cron_job("job1")

        pool.execute.assert_called_once()  # update_cron_job_enabled
        mock_schedule.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_schedule_validates_expression(self):
        """update_cron_job_schedule should validate cron expression."""
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value={
            "cron_job_id": "job1",
            "schedule": "0 9 * * *",
            "timezone": "UTC",
            "enabled": True,
        })

        scheduler = make_scheduler(pool)

        with pytest.raises(ValueError):
            await scheduler.update_cron_job_schedule("job1", "invalid_expr")

    @pytest.mark.asyncio
    async def test_update_schedule_nonexistent_raises(self):
        """Updating a nonexistent job should raise ValueError."""
        pool = make_mock_pool()
        pool.fetchrow = AsyncMock(return_value=None)

        scheduler = make_scheduler(pool)

        with pytest.raises(ValueError, match="not found"):
            await scheduler.update_cron_job_schedule("nonexistent", "0 9 * * *")

    def test_metrics_shows_running_state(self):
        """Metrics should reflect running state."""
        scheduler = make_scheduler()
        scheduler._running = True
        scheduler._job_map["a"] = MagicMock()
        scheduler._job_map["b"] = MagicMock()

        metrics = scheduler.get_metrics()
        assert metrics["running"] is True
        assert metrics["scheduled_jobs"] == 2

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Stopping a non-running scheduler should be safe."""
        scheduler = make_scheduler()
        await scheduler.stop()
        assert scheduler._running is False
