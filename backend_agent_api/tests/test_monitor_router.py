"""Unit tests for monitor_router edge cases.

Covers:
- RAG empty database returns zeros and null timestamp (Req 7.3)
- Fresh MetricsCollector has zero counters (Req 8.4)
- Python version matches sys.version (Req 9.1)
- Dependency versions returned for all 5 packages (Req 9.2)
- Invalid log level filter defaults to DEBUG (Req 9.3)
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth_middleware import get_current_user
from metrics_collector import MetricsCollector
from monitor_router import router

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

ADMIN_USER = {
    "id": USER_ID,
    "email": "admin@test.com",
    "is_admin": True,
}

EXPECTED_PACKAGES = {"fastapi", "pydantic-ai", "slack-bolt", "asyncpg", "uvicorn"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_app() -> FastAPI:
    """Create a FastAPI app with the monitor router and overridden auth."""
    app = FastAPI()
    app.include_router(router)

    async def _override_auth():
        return {"sub": USER_ID, "email": "admin@test.com"}

    app.dependency_overrides[get_current_user] = _override_auth
    return app


def _make_pool(idle_size: int = 1) -> MagicMock:
    """Build a mock asyncpg pool."""
    pool = MagicMock()
    pool.get_idle_size.return_value = idle_size
    pool.fetchval = AsyncMock(return_value=0)
    return pool


# ---------------------------------------------------------------------------
# Test: RAG empty database returns zeros and null timestamp (Req 7.3)
# ---------------------------------------------------------------------------


class TestRagEmptyDatabase:
    """When no documents exist, RAG status returns zero counts and null timestamp.

    Validates: Requirement 7.3
    """

    def test_rag_empty_database_returns_zeros_and_null_timestamp(self):
        """Mock pool.fetchval to return 0/0/None and verify the response."""
        app = _build_app()
        client = TestClient(app)

        pool = _make_pool(idle_size=1)
        # _collect_rag calls fetchval three times:
        #   1. SELECT COUNT(*) FROM document_metadata → 0
        #   2. SELECT COUNT(*) FROM documents → 0
        #   3. SELECT MAX(created_at) FROM document_metadata → None
        pool.fetchval = AsyncMock(side_effect=[0, 0, None])

        async def _get_pool():
            return pool

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
        ):
            resp = client.get("/rag")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_documents"] == 0
        assert data["total_chunks"] == 0
        assert data["last_indexed_at"] is None


# ---------------------------------------------------------------------------
# Test: Fresh MetricsCollector has zero counters (Req 8.4)
# ---------------------------------------------------------------------------


class TestFreshMetricsCollector:
    """A newly created MetricsCollector has empty metrics and positive uptime.

    Validates: Requirement 8.4
    """

    def test_fresh_collector_has_empty_endpoint_metrics(self):
        """get_endpoint_metrics() returns an empty dict on a fresh instance."""
        mc = MetricsCollector()
        assert mc.get_endpoint_metrics() == {}

    def test_fresh_collector_has_positive_uptime(self):
        """get_uptime_seconds() returns a small positive number immediately."""
        mc = MetricsCollector()
        uptime = mc.get_uptime_seconds()
        assert uptime >= 0
        # Should be very small (< 1 second) since we just created it
        assert uptime < 5.0


# ---------------------------------------------------------------------------
# Test: Python version matches sys.version (Req 9.1)
# ---------------------------------------------------------------------------


class TestPythonVersion:
    """The /environment endpoint returns the actual Python version.

    Validates: Requirement 9.1
    """

    def test_python_version_matches_sys_version(self):
        app = _build_app()
        client = TestClient(app)

        pool = _make_pool(idle_size=1)

        async def _get_pool():
            return pool

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
        ):
            resp = client.get("/environment")

        assert resp.status_code == 200
        data = resp.json()
        assert data["python_version"] == sys.version


# ---------------------------------------------------------------------------
# Test: Dependency versions returned for all 5 packages (Req 9.2)
# ---------------------------------------------------------------------------


class TestDependencyVersions:
    """The /environment endpoint returns versions for all 5 expected packages.

    Validates: Requirement 9.2
    """

    def test_all_five_dependency_packages_present(self):
        app = _build_app()
        client = TestClient(app)

        pool = _make_pool(idle_size=1)

        async def _get_pool():
            return pool

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
        ):
            resp = client.get("/environment")

        assert resp.status_code == 200
        data = resp.json()

        dep_names = {d["name"] for d in data["dependencies"]}
        assert dep_names == EXPECTED_PACKAGES, (
            f"Expected {EXPECTED_PACKAGES}, got {dep_names}"
        )

    def test_each_dependency_has_a_version_string(self):
        """Every dependency entry has a non-empty version string."""
        app = _build_app()
        client = TestClient(app)

        pool = _make_pool(idle_size=1)

        async def _get_pool():
            return pool

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
        ):
            resp = client.get("/environment")

        assert resp.status_code == 200
        for dep in resp.json()["dependencies"]:
            assert isinstance(dep["version"], str)
            assert len(dep["version"]) > 0, f"Empty version for {dep['name']}"


# ---------------------------------------------------------------------------
# Test: Invalid log level filter defaults to DEBUG (Req 9.3)
# ---------------------------------------------------------------------------


class TestInvalidLogLevelFilter:
    """An invalid log level parameter defaults to DEBUG (returns all records).

    Validates: Requirement 9.3
    """

    def test_invalid_level_does_not_crash_and_returns_records(self):
        """Passing a nonsense level like 'BANANA' should not error out."""
        app = _build_app()
        client = TestClient(app)

        pool = _make_pool(idle_size=1)

        async def _get_pool():
            return pool

        # Inject a few log records into the buffer so we can verify they come back
        from log_buffer import LogBufferHandler
        import logging

        test_handler = LogBufferHandler(max_size=500)
        test_logger = logging.getLogger("test.invalid_level")
        test_logger.addHandler(test_handler)
        test_logger.setLevel(logging.DEBUG)

        test_logger.debug("debug msg")
        test_logger.info("info msg")
        test_logger.warning("warning msg")

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
            patch("monitor_router.log_handler", test_handler),
        ):
            resp = client.get("/logs?level=BANANA")

        assert resp.status_code == 200
        data = resp.json()
        # DEBUG is the lowest level, so all 3 records should be returned
        assert len(data["records"]) == 3

        # Clean up
        test_logger.removeHandler(test_handler)

    def test_empty_level_string_defaults_to_debug(self):
        """An empty string level should also default to DEBUG."""
        app = _build_app()
        client = TestClient(app)

        pool = _make_pool(idle_size=1)

        async def _get_pool():
            return pool

        from log_buffer import LogBufferHandler
        import logging

        test_handler = LogBufferHandler(max_size=500)
        test_logger = logging.getLogger("test.empty_level")
        test_logger.addHandler(test_handler)
        test_logger.setLevel(logging.DEBUG)

        test_logger.error("error msg")

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
            patch("monitor_router.log_handler", test_handler),
        ):
            resp = client.get("/logs?level=")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["records"]) == 1

        # Clean up
        test_logger.removeHandler(test_handler)
