"""Cron job database queries using asyncpg.

All queries use parameterized inputs ($1, $2, …) to prevent SQL injection.
"""

import logging
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)


def generate_cron_job_id() -> str:
    """Generate a unique cron job ID.
    
    Returns:
        Random 16-character hex string
    """
    return secrets.token_hex(8)


async def create_cron_job(
    pool: asyncpg.Pool,
    schedule: str,
    target_session_id: str,
    message_template: str,
    timezone: str = "UTC",
    enabled: bool = True,
    next_execution_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Create a new cron job and return the created row.
    
    Args:
        pool: Database connection pool
        schedule: Cron expression (e.g., "0 9 * * *" for daily at 9am)
        target_session_id: Session ID to send messages to
        message_template: Message template to send
        timezone: Timezone for schedule (default: UTC)
        enabled: Whether the cron job is enabled
        next_execution_at: Optional next execution timestamp
        
    Returns:
        Dictionary containing the created cron job row
    """
    cron_job_id = generate_cron_job_id()
    
    row = await pool.fetchrow(
        """
        INSERT INTO cron_jobs (
            cron_job_id, schedule, target_session_id, message_template,
            timezone, enabled, next_execution_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        cron_job_id,
        schedule,
        target_session_id,
        message_template,
        timezone,
        enabled,
        next_execution_at,
    )
    return dict(row)


async def get_cron_job(
    pool: asyncpg.Pool,
    cron_job_id: str,
) -> Optional[Dict[str, Any]]:
    """Fetch a cron job by ID.
    
    Args:
        pool: Database connection pool
        cron_job_id: Unique cron job identifier
        
    Returns:
        Dictionary containing the cron job row, or None if not found
    """
    row = await pool.fetchrow(
        """
        SELECT * FROM cron_jobs
        WHERE cron_job_id = $1
        """,
        cron_job_id,
    )
    return dict(row) if row else None


async def list_cron_jobs(
    pool: asyncpg.Pool,
    target_session_id: Optional[str] = None,
    enabled_only: bool = False,
) -> List[Dict[str, Any]]:
    """List cron jobs with optional filters.
    
    Args:
        pool: Database connection pool
        target_session_id: Optional filter by target session
        enabled_only: If True, only return enabled cron jobs
        
    Returns:
        List of cron job dictionaries
    """
    conditions = []
    params = []
    param_count = 1
    
    if target_session_id:
        conditions.append(f"target_session_id = ${param_count}")
        params.append(target_session_id)
        param_count += 1
    
    if enabled_only:
        conditions.append("enabled = TRUE")
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    
    query = f"""
        SELECT * FROM cron_jobs
        {where_clause}
        ORDER BY created_at DESC
    """
    
    rows = await pool.fetch(query, *params)
    return [dict(row) for row in rows]


async def get_due_cron_jobs(
    pool: asyncpg.Pool,
    current_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Get all enabled cron jobs that are due for execution.
    
    Args:
        pool: Database connection pool
        current_time: Optional current time (default: NOW())
        
    Returns:
        List of cron job dictionaries that should be executed
    """
    if current_time:
        query = """
            SELECT * FROM cron_jobs
            WHERE enabled = TRUE
              AND next_execution_at IS NOT NULL
              AND next_execution_at <= $1
            ORDER BY next_execution_at ASC
        """
        rows = await pool.fetch(query, current_time)
    else:
        query = """
            SELECT * FROM cron_jobs
            WHERE enabled = TRUE
              AND next_execution_at IS NOT NULL
              AND next_execution_at <= NOW()
            ORDER BY next_execution_at ASC
        """
        rows = await pool.fetch(query)
    
    return [dict(row) for row in rows]


async def update_cron_job_enabled(
    pool: asyncpg.Pool,
    cron_job_id: str,
    enabled: bool,
) -> None:
    """Enable or disable a cron job.
    
    Args:
        pool: Database connection pool
        cron_job_id: Unique cron job identifier
        enabled: Whether the cron job should be enabled
    """
    await pool.execute(
        """
        UPDATE cron_jobs
        SET enabled = $1
        WHERE cron_job_id = $2
        """,
        enabled,
        cron_job_id,
    )


async def update_cron_job_schedule(
    pool: asyncpg.Pool,
    cron_job_id: str,
    schedule: str,
    next_execution_at: Optional[datetime] = None,
) -> None:
    """Update a cron job's schedule.
    
    Args:
        pool: Database connection pool
        cron_job_id: Unique cron job identifier
        schedule: New cron expression
        next_execution_at: Optional next execution timestamp
    """
    await pool.execute(
        """
        UPDATE cron_jobs
        SET schedule = $1, next_execution_at = $2
        WHERE cron_job_id = $3
        """,
        schedule,
        next_execution_at,
        cron_job_id,
    )


async def update_cron_job_execution(
    pool: asyncpg.Pool,
    cron_job_id: str,
    next_execution_at: Optional[datetime] = None,
) -> None:
    """Update a cron job's execution timestamps after execution.
    
    Args:
        pool: Database connection pool
        cron_job_id: Unique cron job identifier
        next_execution_at: Next execution timestamp
    """
    await pool.execute(
        """
        UPDATE cron_jobs
        SET last_executed_at = NOW(),
            next_execution_at = $1
        WHERE cron_job_id = $2
        """,
        next_execution_at,
        cron_job_id,
    )


async def update_cron_job_message_template(
    pool: asyncpg.Pool,
    cron_job_id: str,
    message_template: str,
) -> None:
    """Update a cron job's message template.
    
    Args:
        pool: Database connection pool
        cron_job_id: Unique cron job identifier
        message_template: New message template
    """
    await pool.execute(
        """
        UPDATE cron_jobs
        SET message_template = $1
        WHERE cron_job_id = $2
        """,
        message_template,
        cron_job_id,
    )


async def delete_cron_job(
    pool: asyncpg.Pool,
    cron_job_id: str,
) -> None:
    """Delete a cron job.
    
    Args:
        pool: Database connection pool
        cron_job_id: Unique cron job identifier
    """
    await pool.execute(
        """
        DELETE FROM cron_jobs
        WHERE cron_job_id = $1
        """,
        cron_job_id,
    )


async def get_cron_job_execution_history(
    pool: asyncpg.Pool,
    cron_job_id: str,
) -> Dict[str, Any]:
    """Get execution history for a cron job.
    
    Args:
        pool: Database connection pool
        cron_job_id: Unique cron job identifier
        
    Returns:
        Dictionary with last_executed_at and next_execution_at
    """
    row = await pool.fetchrow(
        """
        SELECT last_executed_at, next_execution_at
        FROM cron_jobs
        WHERE cron_job_id = $1
        """,
        cron_job_id,
    )
    return dict(row) if row else {}
