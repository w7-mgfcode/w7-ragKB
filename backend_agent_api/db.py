"""Asyncpg connection pool management for the Agent Service."""

import asyncpg
import os
from typing import Optional

_pool: Optional[asyncpg.Pool] = None


async def create_pool(
    min_size: int = None,
    max_size: int = None,
) -> asyncpg.Pool:
    """Create and return a connection pool.

    Pool size is configurable via parameters or environment variables
    DB_POOL_MIN (default 2) and DB_POOL_MAX (default 5).
    """
    global _pool
    dsn = os.getenv("DATABASE_URL")
    _pool = await asyncpg.create_pool(
        dsn,
        min_size=min_size or int(os.getenv("DB_POOL_MIN", "2")),
        max_size=max_size or int(os.getenv("DB_POOL_MAX", "5")),
    )
    return _pool


async def get_pool() -> asyncpg.Pool:
    """Return the current connection pool.

    Raises RuntimeError if the pool has not been initialized.
    """
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


async def close_pool():
    """Close the connection pool and reset the module-level reference."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
