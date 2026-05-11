"""Property-based test: SQL injection safety via parameterized queries.

**Validates: Requirements 4.3**

Property 3: For any user-supplied string (including strings containing SQL
keywords, quotes, semicolons, and comment sequences), all database query
functions SHALL safely parameterize the input such that executing the query
does not alter the database schema or execute unintended SQL statements.

Uses a disposable PostgreSQL container (testcontainers + pgvector) with the
production migration script applied.  Hypothesis generates adversarial strings
and feeds them through every public query function.
"""

import asyncio
import pathlib
import sys
from typing import Set, Tuple

import asyncpg
import psycopg2
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# Ensure backend_agent_api is importable when running from the repo root
_backend_dir = str(pathlib.Path(__file__).resolve().parents[1].parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from backend_agent_api.db_conversations import (
    ensure_slack_user,
    fetch_conversation_history,
    store_message,
    update_conversation_title,
)
from backend_agent_api.db_documents import (
    execute_custom_sql,
    get_document_content,
)

# ---------------------------------------------------------------------------
# Hypothesis strategy: strings that look like SQL injection attempts
# ---------------------------------------------------------------------------

SQL_INJECTION_FRAGMENTS = [
    "'; DROP TABLE slack_users; --",
    "' OR '1'='1",
    "'; DELETE FROM messages; --",
    "1; ALTER TABLE documents ADD COLUMN evil TEXT; --",
    "' UNION SELECT * FROM slack_users --",
    "'; CREATE TABLE pwned (id int); --",
    "'; TRUNCATE conversations; --",
    "$$; DROP TABLE documents; $$",
    "' ; GRANT ALL ON ALL TABLES TO public; --",
    "'; REVOKE ALL ON ALL TABLES FROM public; --",
    "/**/DROP/**/TABLE/**/messages/**/;",
    "Robert'); DROP TABLE slack_users;--",
    "\\x27; DROP TABLE documents;--",
    "' OR 1=1; UPDATE slack_users SET display_name='hacked'; --",
]

sql_injection_text = st.one_of(
    st.sampled_from(SQL_INJECTION_FRAGMENTS),
    st.text(
        alphabet=st.sampled_from(
            list("abcdefghijABCDEF0123456789 '\";-/*\\$()=,.|!@#%^&_+{}[]<>?~`")
        ),
        min_size=1,
        max_size=200,
    ),
    st.text(min_size=1, max_size=100),
)

# ---------------------------------------------------------------------------
# Fixtures — disposable PostgreSQL with pgvector + migration applied
# ---------------------------------------------------------------------------

INIT_SQL_PATH = pathlib.Path(__file__).resolve().parents[2] / "sql" / "init.sql"


@pytest.fixture(scope="module")
def pg_container():
    """Start a pgvector PostgreSQL container for the entire test module."""
    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="testdb",
    )
    container.start()
    yield container
    container.stop()


@pytest.fixture(scope="module")
def pg_dsn(pg_container):
    """Return the asyncpg-compatible DSN for the test container."""
    host = pg_container.get_container_host_ip()
    port = pg_container.get_exposed_port(5432)
    return f"postgresql://test:test@{host}:{port}/testdb"


@pytest.fixture(scope="module")
def _apply_migration(pg_dsn):
    """Apply the production init.sql migration once per module."""
    conn = psycopg2.connect(pg_dsn)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(INIT_SQL_PATH.read_text())
    cur.close()
    conn.close()


@pytest.fixture(scope="module")
def event_loop():
    """Module-scoped event loop shared by all tests in this file."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def pool(pg_dsn, _apply_migration, event_loop):
    """Module-scoped asyncpg pool connected to the test container."""
    _pool = event_loop.run_until_complete(
        asyncpg.create_pool(pg_dsn, min_size=2, max_size=10)
    )
    yield _pool
    event_loop.run_until_complete(_pool.close())


SchemaSnapshot = Set[Tuple[str, str, str]]


def _snapshot_schema(pool: asyncpg.Pool, loop: asyncio.AbstractEventLoop) -> SchemaSnapshot:
    """Capture the current set of tables and their columns."""

    async def _fetch():
        rows = await pool.fetch(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """
        )
        return {(r["table_name"], r["column_name"], r["data_type"]) for r in rows}

    return loop.run_until_complete(_fetch())


@pytest.fixture(scope="module")
def baseline_schema(pool, event_loop) -> SchemaSnapshot:
    """Schema snapshot taken right after migration — the ground truth."""
    return _snapshot_schema(pool, event_loop)


async def _ensure_seed_data(pool: asyncpg.Pool) -> None:
    """Insert the minimal rows needed for FK-dependent queries."""
    await pool.execute(
        """
        INSERT INTO slack_users (slack_id, display_name)
        VALUES ('U_SEED', 'Seed User')
        ON CONFLICT (slack_id) DO NOTHING
        """
    )
    await pool.execute(
        """
        INSERT INTO conversations (session_id, slack_user_id, slack_channel_id)
        VALUES ('SEED_SESSION', 'U_SEED', 'C_SEED')
        ON CONFLICT (session_id) DO NOTHING
        """
    )


@pytest.fixture(scope="module")
def seed_data(pool, event_loop):
    """Seed data inserted once for the entire module."""
    event_loop.run_until_complete(_ensure_seed_data(pool))
    return True


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

class TestSqlInjectionSafety:
    """Property 3: SQL injection safety via parameterized queries.

    **Validates: Requirements 4.3**
    """

    @given(malicious=sql_injection_text)
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_ensure_slack_user_resists_injection(
        self, malicious, pool, baseline_schema, event_loop
    ):
        """ensure_slack_user parameterizes slack_id and display_name."""

        async def _run():
            try:
                await ensure_slack_user(pool, malicious, malicious)
            except asyncpg.exceptions.PostgresError:
                pass  # query errors are fine — schema must stay intact

        event_loop.run_until_complete(_run())
        assert _snapshot_schema(pool, event_loop) == baseline_schema

    @given(malicious=sql_injection_text)
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_fetch_conversation_history_resists_injection(
        self, malicious, pool, baseline_schema, event_loop
    ):
        """fetch_conversation_history parameterizes session_id."""

        async def _run():
            try:
                await fetch_conversation_history(pool, malicious)
            except asyncpg.exceptions.PostgresError:
                pass

        event_loop.run_until_complete(_run())
        assert _snapshot_schema(pool, event_loop) == baseline_schema

    @given(malicious=sql_injection_text)
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_update_conversation_title_resists_injection(
        self, malicious, pool, baseline_schema, event_loop
    ):
        """update_conversation_title parameterizes session_id and title."""

        async def _run():
            try:
                await update_conversation_title(pool, malicious, malicious)
            except asyncpg.exceptions.PostgresError:
                pass

        event_loop.run_until_complete(_run())
        assert _snapshot_schema(pool, event_loop) == baseline_schema

    @pytest.mark.parametrize("malicious", SQL_INJECTION_FRAGMENTS[:5])
    def test_store_message_resists_injection(
        self, malicious, pool, baseline_schema, event_loop, seed_data
    ):
        """store_message parameterizes session_id, type, content.

        Uses parametrize instead of hypothesis because store_message
        acquires a dedicated connection + transaction per call, which
        can exhaust the small test pool under rapid hypothesis iteration.
        """

        async def _run():
            try:
                await store_message(
                    pool, "SEED_SESSION", malicious, malicious,
                    message_data=malicious,
                )
            except (asyncpg.exceptions.PostgresError, Exception):
                pass

        event_loop.run_until_complete(_run())
        assert _snapshot_schema(pool, event_loop) == baseline_schema

    @given(malicious=sql_injection_text)
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_get_document_content_resists_injection(
        self, malicious, pool, baseline_schema, event_loop
    ):
        """get_document_content parameterizes document_id."""

        async def _run():
            try:
                await get_document_content(pool, malicious)
            except asyncpg.exceptions.PostgresError:
                pass

        event_loop.run_until_complete(_run())
        assert _snapshot_schema(pool, event_loop) == baseline_schema

    @given(malicious=sql_injection_text)
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_execute_custom_sql_resists_injection(
        self, malicious, pool, baseline_schema, event_loop
    ):
        """execute_custom_sql rejects writes; parameterization prevents schema changes."""

        async def _run():
            try:
                await execute_custom_sql(pool, malicious)
            except (asyncpg.exceptions.PostgresError, Exception):
                pass

        event_loop.run_until_complete(_run())
        assert _snapshot_schema(pool, event_loop) == baseline_schema
