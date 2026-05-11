"""Unit tests for the asyncpg connection pool module (db.py)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import backend_agent_api.db as db_module


@pytest.fixture(autouse=True)
def reset_pool():
    """Reset the module-level pool before and after each test."""
    db_module._pool = None
    yield
    db_module._pool = None


@pytest.mark.asyncio
async def test_create_pool_uses_env_defaults(mock_env_vars):
    """create_pool() reads DATABASE_URL, DB_POOL_MIN, DB_POOL_MAX from env."""
    mock_pool = AsyncMock()

    with patch.dict("os.environ", mock_env_vars, clear=False), \
         patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool) as mock_create:
        pool = await db_module.create_pool()

        mock_create.assert_called_once_with(
            mock_env_vars["DATABASE_URL"],
            min_size=2,
            max_size=5,
        )
        assert pool is mock_pool
        assert db_module._pool is mock_pool


@pytest.mark.asyncio
async def test_create_pool_with_explicit_sizes(mock_env_vars):
    """create_pool() uses explicit min_size/max_size when provided."""
    mock_pool = AsyncMock()

    with patch.dict("os.environ", mock_env_vars, clear=False), \
         patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool) as mock_create:
        pool = await db_module.create_pool(min_size=1, max_size=10)

        mock_create.assert_called_once_with(
            mock_env_vars["DATABASE_URL"],
            min_size=1,
            max_size=10,
        )
        assert pool is mock_pool


@pytest.mark.asyncio
async def test_create_pool_reads_custom_env_pool_sizes():
    """create_pool() respects DB_POOL_MIN and DB_POOL_MAX env vars."""
    mock_pool = AsyncMock()
    env = {
        "DATABASE_URL": "postgresql://u:p@host:5432/db",
        "DB_POOL_MIN": "3",
        "DB_POOL_MAX": "8",
    }

    with patch.dict("os.environ", env, clear=False), \
         patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool) as mock_create:
        await db_module.create_pool()

        mock_create.assert_called_once_with(
            env["DATABASE_URL"],
            min_size=3,
            max_size=8,
        )


@pytest.mark.asyncio
async def test_get_pool_returns_initialized_pool():
    """get_pool() returns the pool after create_pool() has been called."""
    mock_pool = AsyncMock()
    db_module._pool = mock_pool

    pool = await db_module.get_pool()
    assert pool is mock_pool


@pytest.mark.asyncio
async def test_get_pool_raises_when_not_initialized():
    """get_pool() raises RuntimeError if pool hasn't been created."""
    with pytest.raises(RuntimeError, match="Database pool not initialized"):
        await db_module.get_pool()


@pytest.mark.asyncio
async def test_close_pool_closes_and_resets():
    """close_pool() calls pool.close() and sets _pool to None."""
    mock_pool = AsyncMock()
    db_module._pool = mock_pool

    await db_module.close_pool()

    mock_pool.close.assert_awaited_once()
    assert db_module._pool is None


@pytest.mark.asyncio
async def test_close_pool_noop_when_no_pool():
    """close_pool() does nothing if pool is already None."""
    assert db_module._pool is None
    await db_module.close_pool()
    assert db_module._pool is None
