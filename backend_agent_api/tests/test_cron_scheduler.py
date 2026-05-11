"""Unit tests for cron scheduler.

Tests cron job creation, scheduling, execution, and management.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytz import timezone as pytz_timezone, utc

from cron_scheduler import CronScheduler


@pytest.fixture
async def mock_pool():
    """Create a mock database pool."""
    pool = AsyncMock()
    return pool


@pytest.fixture
async def mock_session_manager():
    """Create a mock session manager."""
    session_manager = MagicMock()
    session_manager.get_session = AsyncMock()
    return session_manager


@pytest.fixture
async def cron_scheduler(mock_pool):
    """Create a CronScheduler instance."""
    scheduler = CronScheduler(mock_pool)
    yield scheduler
    # Cleanup
    if scheduler._running:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_cron_scheduler_start_stop(cron_scheduler):
    """Test starting and stopping the cron scheduler."""
    assert not cron_scheduler._running
    
    # Mock list_cron_jobs to return empty list
    with patch("cron_scheduler.list_cron_jobs", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = []
        
        await cron_scheduler.start()
        assert cron_scheduler._running
        assert cron_scheduler.scheduler.running
        
        await cron_scheduler.stop()
        assert not cron_scheduler._running
        assert not cron_scheduler.scheduler.running


@pytest.mark.asyncio
async def test_register_cron_job_valid_expression(cron_scheduler, mock_pool):
    """Test registering a cron job with a valid cron expression."""
    # Mock create_cron_job
    with patch("cron_scheduler.create_cron_job", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {
            "cron_job_id": "test_job_1",
            "schedule": "0 9 * * *",
            "target_session_id": "session_1",
            "message_template": "Good morning!",
            "timezone": "UTC",
            "enabled": True,
            "next_execution_at": datetime.now(utc) + timedelta(hours=1),
        }
        
        # Start scheduler
        with patch("cron_scheduler.list_cron_jobs", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []
            await cron_scheduler.start()
        
        # Register cron job
        cron_job = await cron_scheduler.register_cron_job(
            schedule="0 9 * * *",
            target_session_id="session_1",
            message_template="Good morning!",
            timezone="UTC",
            enabled=True,
        )
        
        assert cron_job["cron_job_id"] == "test_job_1"
        assert cron_job["schedule"] == "0 9 * * *"
        assert "test_job_1" in cron_scheduler._job_map


@pytest.mark.asyncio
async def test_register_cron_job_invalid_expression(cron_scheduler):
    """Test registering a cron job with an invalid cron expression."""
    with pytest.raises(ValueError, match="Invalid cron expression"):
        await cron_scheduler.register_cron_job(
            schedule="invalid",
            target_session_id="session_1",
            message_template="Test",
            timezone="UTC",
        )


@pytest.mark.asyncio
async def test_register_cron_job_with_timezone(cron_scheduler):
    """Test registering a cron job with a specific timezone."""
    with patch("cron_scheduler.create_cron_job", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {
            "cron_job_id": "test_job_2",
            "schedule": "0 14 * * *",
            "target_session_id": "session_1",
            "message_template": "Afternoon reminder",
            "timezone": "America/New_York",
            "enabled": True,
            "next_execution_at": datetime.now(pytz_timezone("America/New_York")) + timedelta(hours=1),
        }
        
        with patch("cron_scheduler.list_cron_jobs", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []
            await cron_scheduler.start()
        
        cron_job = await cron_scheduler.register_cron_job(
            schedule="0 14 * * *",
            target_session_id="session_1",
            message_template="Afternoon reminder",
            timezone="America/New_York",
        )
        
        assert cron_job["timezone"] == "America/New_York"


@pytest.mark.asyncio
async def test_pause_cron_job(cron_scheduler):
    """Test pausing a cron job."""
    with patch("cron_scheduler.update_cron_job_enabled", new_callable=AsyncMock) as mock_update:
        with patch("cron_scheduler.list_cron_jobs", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []
            await cron_scheduler.start()
        
        # Add a mock job to the job map
        mock_job = MagicMock()
        mock_job.remove = MagicMock()
        cron_scheduler._job_map["test_job_1"] = mock_job
        
        await cron_scheduler.pause_cron_job("test_job_1")
        
        mock_update.assert_called_once_with(cron_scheduler.pool, "test_job_1", False)
        mock_job.remove.assert_called_once()
        assert "test_job_1" not in cron_scheduler._job_map


@pytest.mark.asyncio
async def test_resume_cron_job(cron_scheduler):
    """Test resuming a paused cron job."""
    with patch("cron_scheduler.update_cron_job_enabled", new_callable=AsyncMock) as mock_update:
        with patch("cron_scheduler.get_cron_job", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "cron_job_id": "test_job_1",
                "schedule": "0 9 * * *",
                "target_session_id": "session_1",
                "message_template": "Test",
                "timezone": "UTC",
                "enabled": True,
            }
            
            with patch("cron_scheduler.list_cron_jobs", new_callable=AsyncMock) as mock_list:
                mock_list.return_value = []
                await cron_scheduler.start()
            
            await cron_scheduler.resume_cron_job("test_job_1")
            
            mock_update.assert_called_once_with(cron_scheduler.pool, "test_job_1", True)
            assert "test_job_1" in cron_scheduler._job_map


@pytest.mark.asyncio
async def test_delete_cron_job(cron_scheduler):
    """Test deleting a cron job."""
    with patch("cron_scheduler.delete_cron_job", new_callable=AsyncMock) as mock_delete:
        with patch("cron_scheduler.list_cron_jobs", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []
            await cron_scheduler.start()
        
        # Add a mock job to the job map
        mock_job = MagicMock()
        mock_job.remove = MagicMock()
        cron_scheduler._job_map["test_job_1"] = mock_job
        
        await cron_scheduler.delete_cron_job("test_job_1")
        
        mock_delete.assert_called_once_with(cron_scheduler.pool, "test_job_1")
        mock_job.remove.assert_called_once()
        assert "test_job_1" not in cron_scheduler._job_map


@pytest.mark.asyncio
async def test_update_cron_job_schedule(cron_scheduler):
    """Test updating a cron job's schedule."""
    with patch("cron_scheduler.get_cron_job", new_callable=AsyncMock) as mock_get:
        with patch("cron_scheduler.update_cron_job_schedule", new_callable=AsyncMock) as mock_update:
            mock_get.side_effect = [
                # First call: get existing job
                {
                    "cron_job_id": "test_job_1",
                    "schedule": "0 9 * * *",
                    "target_session_id": "session_1",
                    "message_template": "Test",
                    "timezone": "UTC",
                    "enabled": True,
                },
                # Second call: get updated job
                {
                    "cron_job_id": "test_job_1",
                    "schedule": "0 10 * * *",
                    "target_session_id": "session_1",
                    "message_template": "Test",
                    "timezone": "UTC",
                    "enabled": True,
                },
            ]
            
            with patch("cron_scheduler.list_cron_jobs", new_callable=AsyncMock) as mock_list:
                mock_list.return_value = []
                await cron_scheduler.start()
            
            await cron_scheduler.update_cron_job_schedule(
                "test_job_1",
                "0 10 * * *",
            )
            
            # Verify update was called
            assert mock_update.called


@pytest.mark.asyncio
async def test_execute_cron_job_success(cron_scheduler, mock_session_manager):
    """Test successful execution of a cron job."""
    with patch("cron_scheduler.get_cron_job", new_callable=AsyncMock) as mock_get:
        with patch("cron_scheduler.get_session_manager") as mock_get_sm:
            with patch("cron_scheduler.update_cron_job_execution", new_callable=AsyncMock):
                mock_get.return_value = {
                    "cron_job_id": "test_job_1",
                    "schedule": "0 9 * * *",
                    "target_session_id": "session_1",
                    "message_template": "Good morning!",
                    "timezone": "UTC",
                    "enabled": True,
                }
                
                # Mock session
                mock_session = MagicMock()
                mock_session.add_message = AsyncMock()
                mock_session_manager.get_session.return_value = mock_session
                mock_get_sm.return_value = mock_session_manager
                
                await cron_scheduler._execute_cron_job("test_job_1")
                
                # Verify message was sent to session
                mock_session.add_message.assert_called_once()
                call_args = mock_session.add_message.call_args
                assert call_args[1]["role"] == "system"
                assert call_args[1]["content"] == "Good morning!"
                assert call_args[1]["metadata"]["source"] == "cron_job"


@pytest.mark.asyncio
async def test_execute_cron_job_session_not_found(cron_scheduler, mock_session_manager):
    """Test cron job execution when target session doesn't exist."""
    with patch("cron_scheduler.get_cron_job", new_callable=AsyncMock) as mock_get:
        with patch("cron_scheduler.get_session_manager") as mock_get_sm:
            with patch("cron_scheduler.update_cron_job_execution", new_callable=AsyncMock) as mock_update:
                mock_get.return_value = {
                    "cron_job_id": "test_job_1",
                    "schedule": "0 9 * * *",
                    "target_session_id": "nonexistent_session",
                    "message_template": "Test",
                    "timezone": "UTC",
                    "enabled": True,
                }
                
                # Mock session manager returns None (session not found)
                mock_session_manager.get_session.return_value = None
                mock_get_sm.return_value = mock_session_manager
                
                await cron_scheduler._execute_cron_job("test_job_1")
                
                # Verify execution was still updated (skipped)
                assert mock_update.called


@pytest.mark.asyncio
async def test_execute_cron_job_disabled(cron_scheduler):
    """Test that disabled cron jobs are not executed."""
    with patch("cron_scheduler.get_cron_job", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "cron_job_id": "test_job_1",
            "schedule": "0 9 * * *",
            "target_session_id": "session_1",
            "message_template": "Test",
            "timezone": "UTC",
            "enabled": False,  # Disabled
        }
        
        with patch("cron_scheduler.get_session_manager") as mock_get_sm:
            mock_session_manager = MagicMock()
            mock_session = MagicMock()
            mock_session.add_message = AsyncMock()
            mock_session_manager.get_session.return_value = mock_session
            mock_get_sm.return_value = mock_session_manager
            
            await cron_scheduler._execute_cron_job("test_job_1")
            
            # Verify message was NOT sent
            mock_session.add_message.assert_not_called()


@pytest.mark.asyncio
async def test_list_cron_jobs(cron_scheduler):
    """Test listing cron jobs."""
    with patch("cron_scheduler.list_cron_jobs", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [
            {
                "cron_job_id": "job_1",
                "schedule": "0 9 * * *",
                "target_session_id": "session_1",
                "message_template": "Morning",
                "timezone": "UTC",
                "enabled": True,
            },
            {
                "cron_job_id": "job_2",
                "schedule": "0 17 * * *",
                "target_session_id": "session_1",
                "message_template": "Evening",
                "timezone": "UTC",
                "enabled": True,
            },
        ]
        
        jobs = await cron_scheduler.list_cron_jobs()
        
        assert len(jobs) == 2
        assert jobs[0]["cron_job_id"] == "job_1"
        assert jobs[1]["cron_job_id"] == "job_2"


@pytest.mark.asyncio
async def test_list_cron_jobs_filtered(cron_scheduler):
    """Test listing cron jobs with filters."""
    with patch("cron_scheduler.list_cron_jobs", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [
            {
                "cron_job_id": "job_1",
                "schedule": "0 9 * * *",
                "target_session_id": "session_1",
                "message_template": "Test",
                "timezone": "UTC",
                "enabled": True,
            },
        ]
        
        jobs = await cron_scheduler.list_cron_jobs(
            target_session_id="session_1",
            enabled_only=True,
        )
        
        mock_list.assert_called_once_with(
            cron_scheduler.pool,
            "session_1",
            True,
        )


@pytest.mark.asyncio
async def test_cron_expression_parsing_various_formats(cron_scheduler):
    """Test parsing various cron expression formats."""
    test_cases = [
        ("0 9 * * *", "Daily at 9am"),
        ("*/15 * * * *", "Every 15 minutes"),
        ("0 0 * * 0", "Weekly on Sunday at midnight"),
        ("0 0 1 * *", "Monthly on the 1st at midnight"),
        ("0 12 * * 1-5", "Weekdays at noon"),
    ]
    
    for schedule, description in test_cases:
        try:
            tz = utc
            trigger = cron_scheduler._create_cron_trigger(schedule, tz)
            assert trigger is not None, f"Failed to parse: {description}"
        except Exception as e:
            pytest.fail(f"Failed to parse {description} ({schedule}): {e}")


@pytest.mark.asyncio
async def test_cron_expression_parsing_invalid_formats(cron_scheduler):
    """Test that invalid cron expressions are rejected."""
    invalid_expressions = [
        "invalid",
        "* * *",  # Too few fields
        "* * * * * *",  # Too many fields
        "60 * * * *",  # Invalid minute
        "* 25 * * *",  # Invalid hour
    ]
    
    for schedule in invalid_expressions:
        with pytest.raises(ValueError):
            cron_scheduler._create_cron_trigger(schedule, utc)


@pytest.mark.asyncio
async def test_concurrent_cron_job_execution(cron_scheduler, mock_session_manager):
    """Test that multiple cron jobs can execute concurrently."""
    with patch("cron_scheduler.get_cron_job", new_callable=AsyncMock) as mock_get:
        with patch("cron_scheduler.get_session_manager") as mock_get_sm:
            with patch("cron_scheduler.update_cron_job_execution", new_callable=AsyncMock):
                # Mock two different cron jobs
                def get_cron_job_side_effect(pool, cron_job_id):
                    return {
                        "cron_job_id": cron_job_id,
                        "schedule": "0 9 * * *",
                        "target_session_id": f"session_{cron_job_id}",
                        "message_template": f"Message for {cron_job_id}",
                        "timezone": "UTC",
                        "enabled": True,
                    }
                
                mock_get.side_effect = get_cron_job_side_effect
                
                # Mock sessions
                mock_session = MagicMock()
                mock_session.add_message = AsyncMock()
                mock_session_manager.get_session.return_value = mock_session
                mock_get_sm.return_value = mock_session_manager
                
                # Execute two jobs concurrently
                await asyncio.gather(
                    cron_scheduler._execute_cron_job("job_1"),
                    cron_scheduler._execute_cron_job("job_2"),
                )
                
                # Verify both jobs executed
                assert mock_session.add_message.call_count == 2


@pytest.mark.asyncio
async def test_get_metrics(cron_scheduler):
    """Test getting cron scheduler metrics."""
    with patch("cron_scheduler.list_cron_jobs", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = []
        await cron_scheduler.start()
    
    metrics = cron_scheduler.get_metrics()
    
    assert "running" in metrics
    assert "scheduled_jobs" in metrics
    assert "scheduler_state" in metrics
    assert metrics["running"] is True
    assert metrics["scheduled_jobs"] == 0


@pytest.mark.asyncio
async def test_load_cron_jobs_on_start(cron_scheduler):
    """Test that cron jobs are loaded from database on start."""
    with patch("cron_scheduler.list_cron_jobs", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [
            {
                "cron_job_id": "job_1",
                "schedule": "0 9 * * *",
                "target_session_id": "session_1",
                "message_template": "Test",
                "timezone": "UTC",
                "enabled": True,
            },
        ]
        
        await cron_scheduler.start()
        
        # Verify job was scheduled
        assert "job_1" in cron_scheduler._job_map
        assert len(cron_scheduler._job_map) == 1


@pytest.mark.asyncio
async def test_error_handling_in_execution(cron_scheduler, mock_session_manager):
    """Test error handling during cron job execution."""
    with patch("cron_scheduler.get_cron_job", new_callable=AsyncMock) as mock_get:
        with patch("cron_scheduler.get_session_manager") as mock_get_sm:
            with patch("cron_scheduler.update_cron_job_execution", new_callable=AsyncMock) as mock_update:
                mock_get.side_effect = [
                    # First call: get job
                    {
                        "cron_job_id": "test_job_1",
                        "schedule": "0 9 * * *",
                        "target_session_id": "session_1",
                        "message_template": "Test",
                        "timezone": "UTC",
                        "enabled": True,
                    },
                    # Second call: for update_next_execution
                    {
                        "cron_job_id": "test_job_1",
                        "schedule": "0 9 * * *",
                        "target_session_id": "session_1",
                        "message_template": "Test",
                        "timezone": "UTC",
                        "enabled": True,
                    },
                ]
                
                # Mock session that raises an error
                mock_session = MagicMock()
                mock_session.add_message = AsyncMock(side_effect=Exception("Test error"))
                mock_session_manager.get_session.return_value = mock_session
                mock_get_sm.return_value = mock_session_manager
                
                # Should not raise, should handle error gracefully
                await cron_scheduler._execute_cron_job("test_job_1")
                
                # Verify next execution was still updated
                assert mock_update.called
