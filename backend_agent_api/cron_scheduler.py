"""Cron job scheduler for scheduled agent tasks.

This module implements the CronScheduler class which handles:
- Cron job registration with schedule, target_session_id, message_template
- Cron expression parsing with timezone support
- Scheduled message delivery to target sessions
- Execution logging with timestamp and outcome
- Error handling for non-existent target sessions
- Concurrent execution of multiple cron jobs
- Job management (list, pause, resume, delete)

The scheduler uses APScheduler for cron expression parsing and job scheduling.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone as pytz_timezone, utc

from db_cron import (
    create_cron_job,
    delete_cron_job,
    get_cron_job,
    get_due_cron_jobs,
    list_cron_jobs,
    update_cron_job_enabled,
    update_cron_job_execution,
    update_cron_job_schedule,
)

logger = logging.getLogger(__name__)


class CronScheduler:
    """Scheduler for cron-based agent tasks.
    
    The CronScheduler provides:
    - Cron job registration with schedule, target_session_id, message_template
    - Timezone-aware cron expression parsing
    - Scheduled message delivery to target sessions via SessionManager
    - Execution logging with timestamp and outcome
    - Error handling for non-existent sessions
    - Concurrent execution of simultaneous cron jobs
    - Job management (list, pause, resume, delete)
    
    Uses APScheduler for robust cron expression parsing and scheduling.
    """
    
    def __init__(self, pool: asyncpg.Pool):
        """Initialize the CronScheduler.
        
        Args:
            pool: Database connection pool
        """
        self.pool = pool
        self.scheduler = AsyncIOScheduler(timezone=utc)
        self._running = False
        self._job_map: Dict[str, Any] = {}  # Maps cron_job_id to APScheduler job
    
    async def start(self) -> None:
        """Start the cron scheduler.
        
        Loads all enabled cron jobs from the database and schedules them.
        """
        if self._running:
            logger.warning("CronScheduler already running")
            return
        
        logger.info("Starting CronScheduler")
        
        # Start APScheduler
        self.scheduler.start()
        self._running = True
        
        # Load and schedule all enabled cron jobs
        await self._load_cron_jobs()
        
        logger.info("CronScheduler started")
    
    async def stop(self) -> None:
        """Stop the cron scheduler.
        
        Shuts down APScheduler and clears all scheduled jobs.
        """
        if not self._running:
            return
        
        logger.info("Stopping CronScheduler")
        
        self._running = False
        
        # Shutdown APScheduler
        self.scheduler.shutdown(wait=False)
        
        # Clear job map
        self._job_map.clear()
        
        logger.info("CronScheduler stopped")
    
    async def register_cron_job(
        self,
        schedule: str,
        target_session_id: str,
        message_template: str,
        timezone: str = "UTC",
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """Register a new cron job.
        
        Args:
            schedule: Cron expression (e.g., "0 9 * * *" for daily at 9am)
            target_session_id: Session ID to send messages to
            message_template: Message template to send
            timezone: Timezone for schedule (default: UTC)
            enabled: Whether the cron job is enabled
            
        Returns:
            Dictionary containing the created cron job
            
        Raises:
            ValueError: If the cron expression is invalid
        """
        # Validate cron expression by creating a trigger
        try:
            tz = pytz_timezone(timezone)
            trigger = self._create_cron_trigger(schedule, tz)
            
            # Calculate next execution time
            next_execution_at = trigger.get_next_fire_time(None, datetime.now(tz))
            
        except Exception as e:
            logger.error(f"Invalid cron expression '{schedule}': {e}")
            raise ValueError(f"Invalid cron expression: {e}")
        
        # Create cron job in database
        cron_job = await create_cron_job(
            self.pool,
            schedule,
            target_session_id,
            message_template,
            timezone,
            enabled,
            next_execution_at,
        )
        
        cron_job_id = cron_job["cron_job_id"]
        
        # Schedule the job if enabled
        if enabled and self._running:
            await self._schedule_job(cron_job)
        
        logger.info(
            f"Registered cron job {cron_job_id} "
            f"(schedule: {schedule}, timezone: {timezone}, target: {target_session_id})"
        )
        
        return cron_job
    
    async def pause_cron_job(self, cron_job_id: str) -> None:
        """Pause a cron job (disable it).
        
        Args:
            cron_job_id: Unique cron job identifier
        """
        await update_cron_job_enabled(self.pool, cron_job_id, False)
        
        # Remove from scheduler
        if cron_job_id in self._job_map:
            job = self._job_map[cron_job_id]
            job.remove()
            del self._job_map[cron_job_id]
        
        logger.info(f"Paused cron job {cron_job_id}")
    
    async def resume_cron_job(self, cron_job_id: str) -> None:
        """Resume a paused cron job (enable it).
        
        Args:
            cron_job_id: Unique cron job identifier
        """
        await update_cron_job_enabled(self.pool, cron_job_id, True)
        
        # Reload and schedule the job
        cron_job = await get_cron_job(self.pool, cron_job_id)
        
        if cron_job and self._running:
            await self._schedule_job(cron_job)
        
        logger.info(f"Resumed cron job {cron_job_id}")
    
    async def delete_cron_job(self, cron_job_id: str) -> None:
        """Delete a cron job.
        
        Args:
            cron_job_id: Unique cron job identifier
        """
        # Remove from scheduler
        if cron_job_id in self._job_map:
            job = self._job_map[cron_job_id]
            job.remove()
            del self._job_map[cron_job_id]
        
        # Delete from database
        await delete_cron_job(self.pool, cron_job_id)
        
        logger.info(f"Deleted cron job {cron_job_id}")
    
    async def update_cron_job_schedule(
        self,
        cron_job_id: str,
        schedule: str,
        timezone: Optional[str] = None,
    ) -> None:
        """Update a cron job's schedule.
        
        Args:
            cron_job_id: Unique cron job identifier
            schedule: New cron expression
            timezone: Optional new timezone (if None, keeps existing)
            
        Raises:
            ValueError: If the cron expression is invalid
        """
        # Get existing cron job
        cron_job = await get_cron_job(self.pool, cron_job_id)
        
        if not cron_job:
            raise ValueError(f"Cron job {cron_job_id} not found")
        
        # Use existing timezone if not provided
        tz_str = timezone if timezone is not None else cron_job["timezone"]
        
        # Validate cron expression
        try:
            tz = pytz_timezone(tz_str)
            trigger = self._create_cron_trigger(schedule, tz)
            
            # Calculate next execution time
            next_execution_at = trigger.get_next_fire_time(None, datetime.now(tz))
            
        except Exception as e:
            logger.error(f"Invalid cron expression '{schedule}': {e}")
            raise ValueError(f"Invalid cron expression: {e}")
        
        # Update in database
        await update_cron_job_schedule(
            self.pool,
            cron_job_id,
            schedule,
            next_execution_at,
        )
        
        # Reschedule if enabled
        if cron_job["enabled"] and self._running:
            # Remove old job
            if cron_job_id in self._job_map:
                job = self._job_map[cron_job_id]
                job.remove()
                del self._job_map[cron_job_id]
            
            # Reload and schedule with new schedule
            updated_cron_job = await get_cron_job(self.pool, cron_job_id)
            if updated_cron_job:
                await self._schedule_job(updated_cron_job)
        
        logger.info(f"Updated cron job {cron_job_id} schedule to '{schedule}'")
    
    async def list_cron_jobs(
        self,
        target_session_id: Optional[str] = None,
        enabled_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """List cron jobs with optional filters.
        
        Args:
            target_session_id: Optional filter by target session
            enabled_only: If True, only return enabled cron jobs
            
        Returns:
            List of cron job dictionaries
        """
        return await list_cron_jobs(self.pool, target_session_id, enabled_only)
    
    async def _load_cron_jobs(self) -> None:
        """Load all enabled cron jobs from the database and schedule them."""
        cron_jobs = await list_cron_jobs(self.pool, enabled_only=True)
        
        logger.info(f"Loading {len(cron_jobs)} enabled cron jobs")
        
        for cron_job in cron_jobs:
            try:
                await self._schedule_job(cron_job)
            except Exception as e:
                logger.error(
                    f"Failed to schedule cron job {cron_job['cron_job_id']}: {e}",
                    exc_info=True,
                )
    
    async def _schedule_job(self, cron_job: Dict[str, Any]) -> None:
        """Schedule a cron job with APScheduler.
        
        Args:
            cron_job: Cron job dictionary from database
        """
        cron_job_id = cron_job["cron_job_id"]
        schedule = cron_job["schedule"]
        timezone_str = cron_job["timezone"]
        
        # Create timezone-aware trigger
        tz = pytz_timezone(timezone_str)
        trigger = self._create_cron_trigger(schedule, tz)
        
        # Schedule the job
        job = self.scheduler.add_job(
            self._execute_cron_job,
            trigger=trigger,
            args=[cron_job_id],
            id=cron_job_id,
            replace_existing=True,
            max_instances=1,  # Prevent concurrent executions of the same job
        )
        
        self._job_map[cron_job_id] = job
        
        logger.debug(
            f"Scheduled cron job {cron_job_id} "
            f"(schedule: {schedule}, timezone: {timezone_str})"
        )
    
    def _create_cron_trigger(self, schedule: str, timezone: Any) -> CronTrigger:
        """Create a CronTrigger from a cron expression.
        
        Args:
            schedule: Cron expression (e.g., "0 9 * * *")
            timezone: Timezone object
            
        Returns:
            CronTrigger instance
            
        Raises:
            ValueError: If the cron expression is invalid
        """
        # Parse cron expression (minute hour day month day_of_week)
        parts = schedule.split()
        
        if len(parts) != 5:
            raise ValueError(
                f"Invalid cron expression: expected 5 fields, got {len(parts)}"
            )
        
        minute, hour, day, month, day_of_week = parts
        
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=timezone,
        )
    
    async def _execute_cron_job(self, cron_job_id: str) -> None:
        """Execute a cron job by sending the message to the target session.
        
        This is called by APScheduler when a cron job is due.
        
        Args:
            cron_job_id: Unique cron job identifier
        """
        logger.info(f"Executing cron job {cron_job_id}")
        
        try:
            # Fetch cron job from database
            cron_job = await get_cron_job(self.pool, cron_job_id)
            
            if not cron_job:
                logger.warning(f"Cron job {cron_job_id} not found in database")
                return
            
            if not cron_job["enabled"]:
                logger.info(f"Cron job {cron_job_id} is disabled, skipping execution")
                return
            
            target_session_id = cron_job["target_session_id"]
            message_template = cron_job["message_template"]
            
            # Get session manager
            from session_manager import get_session_manager
            session_manager = get_session_manager()
            
            if not session_manager:
                logger.error("SessionManager not available, cannot execute cron job")
                return
            
            # Get target session
            session = await session_manager.get_session(target_session_id)
            
            if not session:
                logger.warning(
                    f"Target session {target_session_id} not found for cron job {cron_job_id}, "
                    f"skipping execution"
                )
                # Update execution timestamp even though we skipped
                await self._update_next_execution(cron_job)
                return
            
            # Send message to session
            await session.add_message(
                role="system",
                content=message_template,
                metadata={
                    "source": "cron_job",
                    "cron_job_id": cron_job_id,
                    "executed_at": datetime.utcnow().isoformat(),
                },
            )
            
            logger.info(
                f"Cron job {cron_job_id} executed successfully, "
                f"message sent to session {target_session_id}"
            )
            
            # Update execution timestamp and calculate next execution
            await self._update_next_execution(cron_job)
            
        except Exception as e:
            logger.error(
                f"Error executing cron job {cron_job_id}: {e}",
                exc_info=True,
            )
            
            # Still update next execution time to avoid getting stuck
            try:
                cron_job = await get_cron_job(self.pool, cron_job_id)
                if cron_job:
                    await self._update_next_execution(cron_job)
            except Exception as update_error:
                logger.error(
                    f"Failed to update next execution for cron job {cron_job_id}: {update_error}"
                )
    
    async def _update_next_execution(self, cron_job: Dict[str, Any]) -> None:
        """Update the next execution time for a cron job.
        
        Args:
            cron_job: Cron job dictionary from database
        """
        cron_job_id = cron_job["cron_job_id"]
        schedule = cron_job["schedule"]
        timezone_str = cron_job["timezone"]
        
        try:
            # Calculate next execution time
            tz = pytz_timezone(timezone_str)
            trigger = self._create_cron_trigger(schedule, tz)
            next_execution_at = trigger.get_next_fire_time(None, datetime.now(tz))
            
            # Update in database
            await update_cron_job_execution(
                self.pool,
                cron_job_id,
                next_execution_at,
            )
            
            logger.debug(
                f"Updated next execution for cron job {cron_job_id} to {next_execution_at}"
            )
            
        except Exception as e:
            logger.error(
                f"Failed to calculate next execution for cron job {cron_job_id}: {e}",
                exc_info=True,
            )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cron scheduler metrics.
        
        Returns:
            Dictionary containing metrics
        """
        return {
            "running": self._running,
            "scheduled_jobs": len(self._job_map),
            "scheduler_state": self.scheduler.state if self.scheduler else None,
        }


# Global cron scheduler instance
_cron_scheduler: Optional[CronScheduler] = None


async def start_cron_scheduler(pool: asyncpg.Pool) -> CronScheduler:
    """Start the global cron scheduler.
    
    Args:
        pool: Database connection pool
        
    Returns:
        CronScheduler instance
    """
    global _cron_scheduler
    
    if _cron_scheduler is None:
        _cron_scheduler = CronScheduler(pool)
    
    await _cron_scheduler.start()
    return _cron_scheduler


async def stop_cron_scheduler() -> None:
    """Stop the global cron scheduler."""
    global _cron_scheduler
    
    if _cron_scheduler:
        await _cron_scheduler.stop()


def get_cron_scheduler() -> Optional[CronScheduler]:
    """Get the global cron scheduler instance.
    
    Returns:
        CronScheduler instance, or None if not started
    """
    return _cron_scheduler
