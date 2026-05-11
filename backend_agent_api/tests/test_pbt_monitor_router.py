"""Property-based tests for health endpoint structure and status values.

# Feature: admin-system-monitor, Property 1: Health endpoint returns all services with valid statuses
# Validates: Requirements 1.1, 1.2

Property 1: For any system state, the health endpoint response SHALL contain
exactly 4 Service_Health objects (Slack bot, Database pool, HTTP server,
RAG pipeline), and each object's status field SHALL be one of: "healthy",
"degraded", or "down".
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from auth_middleware import get_current_user
from monitor_router import router

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

EXPECTED_SERVICE_NAMES = {"Slack bot", "Database pool", "HTTP server", "RAG pipeline"}

VALID_STATUSES = {"healthy", "degraded", "down"}

# ---------------------------------------------------------------------------
# Strategies — generate all meaningful service state combinations
# ---------------------------------------------------------------------------

slack_states = st.sampled_from(["has_listeners", "no_listeners", "import_error"])
db_pool_states = st.sampled_from(["idle_available", "no_idle", "not_initialized"])
rag_states = st.sampled_from(["has_documents", "no_documents", "query_error"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN_USER = {
    "id": USER_ID,
    "email": "admin@test.com",
    "is_admin": True,
}


def _build_app() -> FastAPI:
    """Create a FastAPI app with the monitor router and overridden auth."""
    app = FastAPI()
    app.include_router(router)

    async def _override_auth():
        return {"sub": USER_ID, "email": "admin@test.com"}

    app.dependency_overrides[get_current_user] = _override_auth
    return app


def _make_pool(idle_size: int) -> MagicMock:
    """Build a mock asyncpg pool with sync methods returning plain values.

    asyncpg pool's get_idle_size() is synchronous, so we use MagicMock
    (not AsyncMock) to avoid returning coroutines for sync calls.
    Only fetchval is async and gets an AsyncMock explicitly.
    """
    pool = MagicMock()
    pool.get_idle_size.return_value = idle_size
    # fetchval is async in asyncpg — set a default; callers override as needed
    pool.fetchval = AsyncMock(return_value=0)
    return pool


def _build_get_pool_side_effect(admin_pool: MagicMock, health_pool, db_is_down: bool):
    """Return an async callable for patching get_pool.

    _require_admin always needs a working pool. _collect_health calls get_pool
    twice (once for DB status, once for RAG). When db_is_down, the second and
    third calls raise RuntimeError to simulate an uninitialized pool.

    Call sequence:
      1. _require_admin → always returns admin_pool
      2. _collect_health DB check → returns health_pool or raises
      3. _collect_health RAG check → returns health_pool or raises
    """
    call_count = 0

    async def _get_pool():
        nonlocal call_count
        call_count += 1
        # First call is always from _require_admin
        if call_count == 1:
            return admin_pool
        # Subsequent calls are from _collect_health
        if db_is_down:
            raise RuntimeError("Pool not initialized")
        return health_pool

    return _get_pool


def _build_slack_patches(slack_state: str) -> dict:
    """Return a sys.modules patch dict for the slack_bot module."""
    if slack_state == "import_error":
        # Setting module to None makes `from slack_bot import ...` raise ImportError
        return {"slack_bot": None}

    mock_app = MagicMock()
    if slack_state == "has_listeners":
        mock_app._listeners = [MagicMock()]
    else:  # no_listeners
        mock_app._listeners = []

    slack_module = MagicMock()
    slack_module.app = mock_app
    return {"slack_bot": slack_module}


# ---------------------------------------------------------------------------
# Property 1: Health endpoint returns all services with valid statuses
# ---------------------------------------------------------------------------


class TestHealthEndpointStructureAndStatuses:
    """Property 1: Health endpoint returns all services with valid statuses.

    **Validates: Requirements 1.1, 1.2**
    """

    @given(
        slack_state=slack_states,
        db_state=db_pool_states,
        rag_state=rag_states,
    )
    @settings(max_examples=30, deadline=None)
    def test_health_returns_exactly_four_services_with_valid_statuses(
        self,
        slack_state: str,
        db_state: str,
        rag_state: str,
    ):
        """For any combination of service states, the health endpoint returns
        exactly 4 services with the correct names and valid status values."""
        # Feature: admin-system-monitor, Property 1: Health endpoint returns all services with valid statuses
        # Validates: Requirements 1.1, 1.2

        app = _build_app()
        client = TestClient(app)

        # Admin pool — always works (sync get_idle_size, async fetchval)
        admin_pool = _make_pool(idle_size=1)

        # Health-check pool — varies by db_state
        db_is_down = db_state == "not_initialized"
        if not db_is_down:
            idle = 3 if db_state == "idle_available" else 0
            health_pool = _make_pool(idle_size=idle)

            # Configure RAG query on the health pool
            if rag_state == "has_documents":
                health_pool.fetchval = AsyncMock(return_value=5)
            elif rag_state == "no_documents":
                health_pool.fetchval = AsyncMock(return_value=0)
            else:  # query_error
                health_pool.fetchval = AsyncMock(side_effect=Exception("query failed"))
        else:
            health_pool = None

        get_pool_fn = _build_get_pool_side_effect(admin_pool, health_pool, db_is_down)
        slack_modules = _build_slack_patches(slack_state)

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=get_pool_fn),
            patch("monitor_router.collector") as mock_collector,
            patch.dict("sys.modules", slack_modules),
        ):
            mock_collector.get_uptime_seconds.return_value = 123.4
            resp = client.get("/health")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        services = data["services"]

        # Exactly 4 services
        assert len(services) == 4, (
            f"Expected 4 services, got {len(services)}: {[s['name'] for s in services]}"
        )

        # All expected names present
        returned_names = {s["name"] for s in services}
        assert returned_names == EXPECTED_SERVICE_NAMES, (
            f"Expected {EXPECTED_SERVICE_NAMES}, got {returned_names}"
        )

        # Each status is valid
        for svc in services:
            assert svc["status"] in VALID_STATUSES, (
                f"Service '{svc['name']}' has invalid status '{svc['status']}'"
            )

        # Uptime is present and numeric
        assert isinstance(data["uptime_seconds"], (int, float))

    @given(
        slack_state=slack_states,
        db_state=db_pool_states,
        rag_state=rag_states,
    )
    @settings(max_examples=30, deadline=None)
    def test_service_names_are_unique(
        self,
        slack_state: str,
        db_state: str,
        rag_state: str,
    ):
        """For any system state, no two services share the same name."""
        # Feature: admin-system-monitor, Property 1: Health endpoint returns all services with valid statuses
        # Validates: Requirements 1.1, 1.2

        app = _build_app()
        client = TestClient(app)

        admin_pool = _make_pool(idle_size=1)
        db_is_down = db_state == "not_initialized"

        if not db_is_down:
            idle = 3 if db_state == "idle_available" else 0
            health_pool = _make_pool(idle_size=idle)
            if rag_state == "has_documents":
                health_pool.fetchval = AsyncMock(return_value=5)
            elif rag_state == "no_documents":
                health_pool.fetchval = AsyncMock(return_value=0)
            else:
                health_pool.fetchval = AsyncMock(side_effect=Exception("query failed"))
        else:
            health_pool = None

        get_pool_fn = _build_get_pool_side_effect(admin_pool, health_pool, db_is_down)
        slack_modules = _build_slack_patches(slack_state)

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=get_pool_fn),
            patch("monitor_router.collector") as mock_collector,
            patch.dict("sys.modules", slack_modules),
        ):
            mock_collector.get_uptime_seconds.return_value = 42.0
            resp = client.get("/health")

        assert resp.status_code == 200
        names = [s["name"] for s in resp.json()["services"]]
        assert len(names) == len(set(names)), f"Duplicate service names: {names}"


# ---------------------------------------------------------------------------
# Property 2: Database status maps correctly from pool state
# ---------------------------------------------------------------------------


class TestDatabaseStatusMapping:
    """Property 2: Database status maps correctly from pool state.

    **Validates: Requirements 1.4, 1.5, 1.6**

    For any database pool state — where free connections > 0 yields "healthy",
    free connections = 0 but pool exists yields "degraded", and pool is None
    yields "down" — the System_Monitor SHALL return the correct status string.
    This mapping is total: every possible pool state maps to exactly one status.
    """

    @given(idle_count=st.integers(min_value=1, max_value=100))
    @settings(max_examples=30, deadline=None)
    def test_pool_with_idle_connections_reports_healthy(self, idle_count: int):
        """When the pool has idle connections > 0, database status is 'healthy'.

        Validates: Requirement 1.4
        """
        # Feature: admin-system-monitor, Property 2: Database status maps correctly from pool state
        # Validates: Requirements 1.4, 1.5, 1.6

        app = _build_app()
        client = TestClient(app)

        admin_pool = _make_pool(idle_size=1)
        health_pool = _make_pool(idle_size=idle_count)
        # RAG query — doesn't matter for this test, just needs to not crash
        health_pool.fetchval = AsyncMock(return_value=0)

        get_pool_fn = _build_get_pool_side_effect(admin_pool, health_pool, db_is_down=False)
        slack_modules = _build_slack_patches("has_listeners")

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=get_pool_fn),
            patch("monitor_router.collector") as mock_collector,
            patch.dict("sys.modules", slack_modules),
        ):
            mock_collector.get_uptime_seconds.return_value = 100.0
            resp = client.get("/health")

        assert resp.status_code == 200
        services = {s["name"]: s for s in resp.json()["services"]}
        db_svc = services["Database pool"]

        assert db_svc["status"] == "healthy", (
            f"Expected 'healthy' for idle_count={idle_count}, got '{db_svc['status']}'"
        )

    @settings(max_examples=30, deadline=None)
    @given(data=st.data())
    def test_pool_with_zero_idle_reports_degraded(self, data):
        """When the pool exists but has zero idle connections, database status is 'degraded'.

        Validates: Requirement 1.5
        """
        # Feature: admin-system-monitor, Property 2: Database status maps correctly from pool state
        # Validates: Requirements 1.4, 1.5, 1.6

        app = _build_app()
        client = TestClient(app)

        admin_pool = _make_pool(idle_size=1)
        health_pool = _make_pool(idle_size=0)
        health_pool.fetchval = AsyncMock(return_value=0)

        get_pool_fn = _build_get_pool_side_effect(admin_pool, health_pool, db_is_down=False)
        slack_modules = _build_slack_patches("has_listeners")

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=get_pool_fn),
            patch("monitor_router.collector") as mock_collector,
            patch.dict("sys.modules", slack_modules),
        ):
            mock_collector.get_uptime_seconds.return_value = 100.0
            resp = client.get("/health")

        assert resp.status_code == 200
        services = {s["name"]: s for s in resp.json()["services"]}
        db_svc = services["Database pool"]

        assert db_svc["status"] == "degraded", (
            f"Expected 'degraded' for idle_count=0, got '{db_svc['status']}'"
        )
        assert db_svc.get("details") is not None, "Degraded status should include details"

    @settings(max_examples=30, deadline=None)
    @given(data=st.data())
    def test_pool_not_initialized_reports_down(self, data):
        """When the pool is not initialized (RuntimeError), database status is 'down'.

        Validates: Requirement 1.6
        """
        # Feature: admin-system-monitor, Property 2: Database status maps correctly from pool state
        # Validates: Requirements 1.4, 1.5, 1.6

        app = _build_app()
        client = TestClient(app)

        admin_pool = _make_pool(idle_size=1)

        get_pool_fn = _build_get_pool_side_effect(admin_pool, health_pool=None, db_is_down=True)
        slack_modules = _build_slack_patches("has_listeners")

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=get_pool_fn),
            patch("monitor_router.collector") as mock_collector,
            patch.dict("sys.modules", slack_modules),
        ):
            mock_collector.get_uptime_seconds.return_value = 100.0
            resp = client.get("/health")

        assert resp.status_code == 200
        services = {s["name"]: s for s in resp.json()["services"]}
        db_svc = services["Database pool"]

        assert db_svc["status"] == "down", (
            f"Expected 'down' for uninitialized pool, got '{db_svc['status']}'"
        )
        assert db_svc.get("details") is not None, "Down status should include details"

    @given(idle_count=st.integers(min_value=0, max_value=100), pool_exists=st.booleans())
    @settings(max_examples=30, deadline=None)
    def test_mapping_is_total_and_deterministic(self, idle_count: int, pool_exists: bool):
        """For any pool state, exactly one status is returned — the mapping is total.

        Validates: Requirements 1.4, 1.5, 1.6
        """
        # Feature: admin-system-monitor, Property 2: Database status maps correctly from pool state
        # Validates: Requirements 1.4, 1.5, 1.6

        app = _build_app()
        client = TestClient(app)

        admin_pool = _make_pool(idle_size=1)
        db_is_down = not pool_exists

        if pool_exists:
            health_pool = _make_pool(idle_size=idle_count)
            health_pool.fetchval = AsyncMock(return_value=0)
        else:
            health_pool = None

        get_pool_fn = _build_get_pool_side_effect(admin_pool, health_pool, db_is_down)
        slack_modules = _build_slack_patches("has_listeners")

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=get_pool_fn),
            patch("monitor_router.collector") as mock_collector,
            patch.dict("sys.modules", slack_modules),
        ):
            mock_collector.get_uptime_seconds.return_value = 100.0
            resp = client.get("/health")

        assert resp.status_code == 200
        services = {s["name"]: s for s in resp.json()["services"]}
        db_svc = services["Database pool"]

        # Verify the mapping is correct for every generated state
        if not pool_exists:
            expected = "down"
        elif idle_count > 0:
            expected = "healthy"
        else:
            expected = "degraded"

        assert db_svc["status"] == expected, (
            f"pool_exists={pool_exists}, idle_count={idle_count}: "
            f"expected '{expected}', got '{db_svc['status']}'"
        )

        # Status is always one of the valid values (total mapping)
        assert db_svc["status"] in VALID_STATUSES


# ---------------------------------------------------------------------------
# Property 3: Model configuration response contains all required fields
# ---------------------------------------------------------------------------


class TestModelConfigResponseFields:
    """Property 3: Model configuration response contains all required fields.

    **Validates: Requirements 2.1, 2.2**

    For any set of environment variable values for LLM_CHOICE,
    EMBEDDING_MODEL_CHOICE, EMBEDDING_DIMENSIONS, GOOGLE_CLOUD_PROJECT,
    and GOOGLE_CLOUD_REGION, the model configuration endpoint SHALL return
    a response containing all five fields with values matching the current
    environment.
    """

    REQUIRED_FIELDS = {
        "llm_model",
        "embedding_model",
        "embedding_dimensions",
        "gcp_project",
        "gcp_region",
    }

    @given(
        llm_choice=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "P"))),
        embedding_model=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "P"))),
        embedding_dims=st.integers(min_value=1, max_value=10000),
        gcp_project=st.one_of(st.none(), st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "P")))),
        gcp_region=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "P"))),
    )
    @settings(max_examples=30, deadline=None)
    def test_model_config_returns_all_fields_matching_env(
        self,
        llm_choice: str,
        embedding_model: str,
        embedding_dims: int,
        gcp_project,
        gcp_region: str,
    ):
        """For any valid env var values, the /models endpoint returns all five
        fields with values matching the current environment variables."""
        # Feature: admin-system-monitor, Property 3: Model configuration response contains all required fields
        # Validates: Requirements 2.1, 2.2

        app = _build_app()
        client = TestClient(app)

        admin_pool = _make_pool(idle_size=1)

        env_patch = {
            "LLM_CHOICE": llm_choice,
            "EMBEDDING_MODEL_CHOICE": embedding_model,
            "EMBEDDING_DIMENSIONS": str(embedding_dims),
            "GOOGLE_CLOUD_REGION": gcp_region,
        }
        if gcp_project is not None:
            env_patch["GOOGLE_CLOUD_PROJECT"] = gcp_project

        async def _get_pool():
            return admin_pool

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
            patch.dict(os.environ, env_patch, clear=False),
        ):
            # Ensure GOOGLE_CLOUD_PROJECT is absent when gcp_project is None
            if gcp_project is None:
                os.environ.pop("GOOGLE_CLOUD_PROJECT", None)

            resp = client.get("/models")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()

        # All five required fields are present
        assert set(data.keys()) == self.REQUIRED_FIELDS, (
            f"Expected fields {self.REQUIRED_FIELDS}, got {set(data.keys())}"
        )

        # Values match the environment
        assert data["llm_model"] == llm_choice
        assert data["embedding_model"] == embedding_model
        assert data["embedding_dimensions"] == embedding_dims
        assert data["gcp_project"] == gcp_project
        assert data["gcp_region"] == gcp_region

    @given(
        invalid_dims=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("L", "P")),
        ),
    )
    @settings(max_examples=30, deadline=None)
    def test_invalid_embedding_dimensions_falls_back_to_default(
        self,
        invalid_dims: str,
    ):
        """When EMBEDDING_DIMENSIONS is not a valid integer, the endpoint
        falls back to the default value of 768."""
        # Feature: admin-system-monitor, Property 3: Model configuration response contains all required fields
        # Validates: Requirements 2.1, 2.2

        app = _build_app()
        client = TestClient(app)

        admin_pool = _make_pool(idle_size=1)

        env_patch = {
            "EMBEDDING_DIMENSIONS": invalid_dims,
        }

        async def _get_pool():
            return admin_pool

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
            patch.dict(os.environ, env_patch, clear=False),
        ):
            resp = client.get("/models")

        assert resp.status_code == 200
        data = resp.json()

        # All fields still present
        assert set(data.keys()) == self.REQUIRED_FIELDS

        # Invalid dimension string falls back to 768
        assert data["embedding_dimensions"] == 768, (
            f"Expected fallback 768 for invalid dims '{invalid_dims}', "
            f"got {data['embedding_dimensions']}"
        )


# ---------------------------------------------------------------------------
# Property 6: Slack token presence reported without value exposure
# ---------------------------------------------------------------------------


class TestSlackTokenPresenceReporting:
    """Property 6: Slack token presence reported without value exposure.

    **Validates: Requirements 5.1, 5.2**

    For any combination of SLACK_BOT_TOKEN and SLACK_APP_TOKEN environment
    variable states (set or unset), the Slack status response SHALL report
    bot_token_configured and app_token_configured as booleans matching
    whether each token is set, and the response body SHALL NOT contain the
    actual token string values.
    """

    # Strategy: generate either a realistic token string or None (unset).
    # min_size=8 avoids false positives where trivially short tokens (e.g. "0")
    # coincidentally appear in the JSON response structure.
    _token_strategy = st.one_of(
        st.none(),
        st.text(min_size=8, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "P"))),
    )

    @given(
        bot_token=_token_strategy,
        app_token=_token_strategy,
    )
    @settings(max_examples=30, deadline=None)
    def test_slack_token_presence_matches_env_and_values_not_exposed(
        self,
        bot_token,
        app_token,
    ):
        """For any combination of token states, bot_token_configured and
        app_token_configured match whether each token is set, and the
        response body does not contain the actual token values."""
        # Feature: admin-system-monitor, Property 6: Slack token presence reported without value exposure
        # Validates: Requirements 5.1, 5.2

        app = _build_app()
        client = TestClient(app)

        admin_pool = _make_pool(idle_size=1)

        async def _get_pool():
            return admin_pool

        # Build env patch — only include tokens that are "set"
        env_patch = {}
        if bot_token is not None:
            env_patch["SLACK_BOT_TOKEN"] = bot_token
        if app_token is not None:
            env_patch["SLACK_APP_TOKEN"] = app_token

        slack_modules = _build_slack_patches("no_listeners")

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
            patch.dict(os.environ, env_patch, clear=False),
            patch.dict("sys.modules", slack_modules),
        ):
            # Remove tokens from env when they should be unset
            if bot_token is None:
                os.environ.pop("SLACK_BOT_TOKEN", None)
            if app_token is None:
                os.environ.pop("SLACK_APP_TOKEN", None)

            resp = client.get("/slack")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()

        # bot_token_configured matches whether the token was set
        expected_bot = bot_token is not None
        assert data["bot_token_configured"] is expected_bot, (
            f"bot_token_configured: expected {expected_bot}, got {data['bot_token_configured']}"
        )

        # app_token_configured matches whether the token was set
        expected_app = app_token is not None
        assert data["app_token_configured"] is expected_app, (
            f"app_token_configured: expected {expected_app}, got {data['app_token_configured']}"
        )

        # The response body must NOT contain the actual token values
        raw_body = resp.text
        if bot_token is not None and len(bot_token) > 0:
            assert bot_token not in raw_body, (
                f"Response body contains the actual SLACK_BOT_TOKEN value"
            )
        if app_token is not None and len(app_token) > 0:
            assert app_token not in raw_body, (
                f"Response body contains the actual SLACK_APP_TOKEN value"
            )

    @given(
        bot_token=_token_strategy,
        app_token=_token_strategy,
    )
    @settings(max_examples=30, deadline=None)
    def test_slack_response_fields_are_booleans(
        self,
        bot_token,
        app_token,
    ):
        """For any token state, bot_token_configured and app_token_configured
        are always boolean values (not strings, ints, or other types)."""
        # Feature: admin-system-monitor, Property 6: Slack token presence reported without value exposure
        # Validates: Requirements 5.1, 5.2

        app = _build_app()
        client = TestClient(app)

        admin_pool = _make_pool(idle_size=1)

        async def _get_pool():
            return admin_pool

        env_patch = {}
        if bot_token is not None:
            env_patch["SLACK_BOT_TOKEN"] = bot_token
        if app_token is not None:
            env_patch["SLACK_APP_TOKEN"] = app_token

        slack_modules = _build_slack_patches("no_listeners")

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
            patch.dict(os.environ, env_patch, clear=False),
            patch.dict("sys.modules", slack_modules),
        ):
            if bot_token is None:
                os.environ.pop("SLACK_BOT_TOKEN", None)
            if app_token is None:
                os.environ.pop("SLACK_APP_TOKEN", None)

            resp = client.get("/slack")

        assert resp.status_code == 200
        data = resp.json()

        assert isinstance(data["bot_token_configured"], bool), (
            f"bot_token_configured is {type(data['bot_token_configured'])}, expected bool"
        )
        assert isinstance(data["app_token_configured"], bool), (
            f"app_token_configured is {type(data['app_token_configured'])}, expected bool"
        )


# ---------------------------------------------------------------------------
# Property 11: All monitor endpoints enforce admin authentication
# ---------------------------------------------------------------------------

# All monitor endpoint paths (relative to the router, no prefix)
MONITOR_ENDPOINT_PATHS = [
    "/health",
    "/models",
    "/database",
    "/logs",
    "/slack",
    "/resources",
    "/rag",
    "/api-metrics",
    "/environment",
    "/all",
]

# Strategy: pick any monitor endpoint path
endpoint_path_strategy = st.sampled_from(MONITOR_ENDPOINT_PATHS)


class TestAdminAuthEnforcement:
    """Property 11: All monitor endpoints enforce admin authentication.

    **Validates: Requirements 11.1, 11.2, 11.3, 11.4**

    For any monitoring endpoint path under /api/admin/monitor/*, an
    unauthenticated request SHALL receive HTTP 401, and a request from
    a non-admin user SHALL receive HTTP 403 with "Admin access required".
    """

    @given(endpoint=endpoint_path_strategy)
    @settings(max_examples=30, deadline=None)
    def test_unauthenticated_request_returns_401(self, endpoint: str):
        """For any monitor endpoint, a request without a valid JWT token
        SHALL receive HTTP 401.

        Validates: Requirement 11.1, 11.4
        """
        # Feature: admin-system-monitor, Property 11: All monitor endpoints enforce admin authentication
        # Validates: Requirements 11.1, 11.2, 11.3, 11.4

        app = FastAPI()
        app.include_router(router)

        # Do NOT override get_current_user — let the real dependency reject
        # the request. Override it to raise 401 explicitly since the real
        # decode_access_token needs a real JWT secret.
        async def _reject_no_token():
            raise HTTPException(status_code=401, detail="Missing or invalid token")

        app.dependency_overrides[get_current_user] = _reject_no_token

        client = TestClient(app)
        resp = client.get(endpoint)

        assert resp.status_code == 401, (
            f"Endpoint {endpoint}: expected 401 for unauthenticated request, "
            f"got {resp.status_code}: {resp.text}"
        )

    @given(endpoint=endpoint_path_strategy)
    @settings(max_examples=30, deadline=None)
    def test_non_admin_user_returns_403(self, endpoint: str):
        """For any monitor endpoint, a request from an authenticated but
        non-admin user SHALL receive HTTP 403 with 'Admin access required'.

        Validates: Requirement 11.2, 11.3
        """
        # Feature: admin-system-monitor, Property 11: All monitor endpoints enforce admin authentication
        # Validates: Requirements 11.1, 11.2, 11.3, 11.4

        app = FastAPI()
        app.include_router(router)

        # Override auth to return a valid user (authenticated)
        async def _override_auth():
            return {"sub": USER_ID, "email": "user@test.com"}

        app.dependency_overrides[get_current_user] = _override_auth

        client = TestClient(app)

        # Mock get_web_user_by_id to return a non-admin user
        non_admin_user = {
            "id": USER_ID,
            "email": "user@test.com",
            "is_admin": False,
        }

        admin_pool = _make_pool(idle_size=1)

        async def _get_pool():
            return admin_pool

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=non_admin_user),
            patch("monitor_router.get_pool", side_effect=_get_pool),
        ):
            resp = client.get(endpoint)

        assert resp.status_code == 403, (
            f"Endpoint {endpoint}: expected 403 for non-admin user, "
            f"got {resp.status_code}: {resp.text}"
        )
        assert resp.json()["detail"] == "Admin access required", (
            f"Endpoint {endpoint}: expected 'Admin access required' detail, "
            f"got '{resp.json()['detail']}'"
        )

    @given(endpoint=endpoint_path_strategy)
    @settings(max_examples=30, deadline=None)
    def test_admin_user_does_not_get_401_or_403(self, endpoint: str):
        """For any monitor endpoint, a request from an authenticated admin
        user SHALL NOT receive 401 or 403 — auth is the only barrier.

        Validates: Requirements 11.1, 11.2
        """
        # Feature: admin-system-monitor, Property 11: All monitor endpoints enforce admin authentication
        # Validates: Requirements 11.1, 11.2, 11.3, 11.4

        app = _build_app()
        client = TestClient(app)

        admin_pool = _make_pool(idle_size=1)
        # Set up fetchval for endpoints that query the DB
        admin_pool.fetchval = AsyncMock(return_value=0)
        admin_pool.get_size = MagicMock(return_value=5)
        admin_pool.get_min_size = MagicMock(return_value=2)
        admin_pool.get_max_size = MagicMock(return_value=10)

        async def _get_pool():
            return admin_pool

        slack_modules = _build_slack_patches("has_listeners")

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
            patch("monitor_router.collector") as mock_collector,
            patch.dict("sys.modules", slack_modules),
        ):
            mock_collector.get_uptime_seconds.return_value = 100.0
            mock_collector.get_endpoint_metrics.return_value = {}
            mock_collector.get_system_resources.return_value = {
                "process_memory_mb": 50.0,
                "system_memory_total_mb": 4096.0,
                "system_memory_used_mb": 2048.0,
                "system_memory_available_mb": 2048.0,
                "cpu_percent": 25.0,
                "disk_total_gb": 50.0,
                "disk_used_gb": 20.0,
                "disk_free_gb": 30.0,
            }
            resp = client.get(endpoint)

        assert resp.status_code not in (401, 403), (
            f"Endpoint {endpoint}: admin user got {resp.status_code}, "
            f"expected neither 401 nor 403: {resp.text}"
        )


# ---------------------------------------------------------------------------
# Property 12: No secrets exposed in any monitoring response
# ---------------------------------------------------------------------------

# Secret environment variable names that must never leak into responses
SECRET_ENV_VARS = [
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    "JWT_SECRET_KEY",
    "DATABASE_URL",
    "BRAVE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
]

# Strategy: generate a random secret value with a "SECRET_" prefix so that
# generated values never accidentally match JSON field names or numeric
# literals in the response body (e.g. "process_me" ⊂ "process_memory_mb").
_secret_strategy = st.text(
    min_size=12,
    max_size=80,
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
).map(lambda s: f"SECRET_{s}")


class TestNoSecretsInResponses:
    """Property 12: No secrets exposed in any monitoring response.

    **Validates: Requirements 2.3, 11.5**

    For any monitoring endpoint response, the serialized JSON body SHALL NOT
    contain the values of any secret environment variables (SLACK_BOT_TOKEN,
    SLACK_APP_TOKEN, JWT_SECRET_KEY, DATABASE_URL, BRAVE_API_KEY,
    GOOGLE_APPLICATION_CREDENTIALS).
    """

    @given(
        endpoint=endpoint_path_strategy,
        slack_bot_token=_secret_strategy,
        slack_app_token=_secret_strategy,
        jwt_secret=_secret_strategy,
        database_url=_secret_strategy,
        brave_api_key=_secret_strategy,
        gcp_creds=_secret_strategy,
    )
    @settings(max_examples=30, deadline=None)
    def test_no_secret_values_in_any_endpoint_response(
        self,
        endpoint: str,
        slack_bot_token: str,
        slack_app_token: str,
        jwt_secret: str,
        database_url: str,
        brave_api_key: str,
        gcp_creds: str,
    ):
        """For any monitor endpoint and any set of secret env var values,
        the response body SHALL NOT contain any of the secret values.

        Feature: admin-system-monitor, Property 12: No secrets exposed in any monitoring response
        Validates: Requirements 2.3, 11.5
        """
        # Feature: admin-system-monitor, Property 12: No secrets exposed in any monitoring response
        # Validates: Requirements 2.3, 11.5

        app = _build_app()
        client = TestClient(app)

        secrets = {
            "SLACK_BOT_TOKEN": slack_bot_token,
            "SLACK_APP_TOKEN": slack_app_token,
            "JWT_SECRET_KEY": jwt_secret,
            "DATABASE_URL": database_url,
            "BRAVE_API_KEY": brave_api_key,
            "GOOGLE_APPLICATION_CREDENTIALS": gcp_creds,
        }

        admin_pool = _make_pool(idle_size=1)
        admin_pool.fetchval = AsyncMock(return_value=0)
        admin_pool.get_size = MagicMock(return_value=5)
        admin_pool.get_min_size = MagicMock(return_value=2)
        admin_pool.get_max_size = MagicMock(return_value=10)

        async def _get_pool():
            return admin_pool

        slack_modules = _build_slack_patches("has_listeners")

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
            patch("monitor_router.collector") as mock_collector,
            patch.dict("sys.modules", slack_modules),
            patch.dict(os.environ, secrets, clear=False),
        ):
            mock_collector.get_uptime_seconds.return_value = 100.0
            mock_collector.get_endpoint_metrics.return_value = {}
            mock_collector.get_system_resources.return_value = {
                "process_memory_mb": 50.0,
                "system_memory_total_mb": 4096.0,
                "system_memory_used_mb": 2048.0,
                "system_memory_available_mb": 2048.0,
                "cpu_percent": 25.0,
                "disk_total_gb": 50.0,
                "disk_used_gb": 20.0,
                "disk_free_gb": 30.0,
            }
            resp = client.get(endpoint)

        # Only check successful responses (non-5xx)
        if resp.status_code >= 500:
            return

        raw_body = resp.text

        for var_name, var_value in secrets.items():
            assert var_value not in raw_body, (
                f"Endpoint {endpoint}: response body contains the value of "
                f"{var_name} ('{var_value[:20]}...')"
            )

    @given(
        slack_bot_token=_secret_strategy,
        slack_app_token=_secret_strategy,
        jwt_secret=_secret_strategy,
        database_url=_secret_strategy,
        brave_api_key=_secret_strategy,
        gcp_creds=_secret_strategy,
    )
    @settings(max_examples=30, deadline=None)
    def test_no_secret_values_in_all_endpoint(
        self,
        slack_bot_token: str,
        slack_app_token: str,
        jwt_secret: str,
        database_url: str,
        brave_api_key: str,
        gcp_creds: str,
    ):
        """The /all aggregated endpoint — which returns data from every
        section — SHALL NOT contain any secret env var values.

        Feature: admin-system-monitor, Property 12: No secrets exposed in any monitoring response
        Validates: Requirements 2.3, 11.5
        """
        # Feature: admin-system-monitor, Property 12: No secrets exposed in any monitoring response
        # Validates: Requirements 2.3, 11.5

        app = _build_app()
        client = TestClient(app)

        secrets = {
            "SLACK_BOT_TOKEN": slack_bot_token,
            "SLACK_APP_TOKEN": slack_app_token,
            "JWT_SECRET_KEY": jwt_secret,
            "DATABASE_URL": database_url,
            "BRAVE_API_KEY": brave_api_key,
            "GOOGLE_APPLICATION_CREDENTIALS": gcp_creds,
        }

        admin_pool = _make_pool(idle_size=1)
        admin_pool.fetchval = AsyncMock(return_value=0)
        admin_pool.get_size = MagicMock(return_value=5)
        admin_pool.get_min_size = MagicMock(return_value=2)
        admin_pool.get_max_size = MagicMock(return_value=10)

        async def _get_pool():
            return admin_pool

        slack_modules = _build_slack_patches("has_listeners")

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
            patch("monitor_router.collector") as mock_collector,
            patch.dict("sys.modules", slack_modules),
            patch.dict(os.environ, secrets, clear=False),
        ):
            mock_collector.get_uptime_seconds.return_value = 100.0
            mock_collector.get_endpoint_metrics.return_value = {}
            mock_collector.get_system_resources.return_value = {
                "process_memory_mb": 50.0,
                "system_memory_total_mb": 4096.0,
                "system_memory_used_mb": 2048.0,
                "system_memory_available_mb": 2048.0,
                "cpu_percent": 25.0,
                "disk_total_gb": 50.0,
                "disk_used_gb": 20.0,
                "disk_free_gb": 30.0,
            }
            resp = client.get("/all")

        assert resp.status_code == 200, (
            f"Expected 200 from /all, got {resp.status_code}: {resp.text}"
        )

        raw_body = resp.text

        for var_name, var_value in secrets.items():
            assert var_value not in raw_body, (
                f"/all endpoint: response body contains the value of "
                f"{var_name} ('{var_value[:20]}...')"
            )


# ---------------------------------------------------------------------------
# Property 8: RAG document and chunk counts match database state
# ---------------------------------------------------------------------------


class TestRagDocumentAndChunkCounts:
    """Property 8: RAG document and chunk counts match database state.

    **Validates: Requirements 7.1, 7.2, 7.3**

    For any database state with N documents and M chunks, the RAG status
    endpoint SHALL return total_documents = N and total_chunks = M, and
    last_indexed_at SHALL equal the most recent document's timestamp
    (or null if N = 0).
    """

    @given(
        doc_count=st.integers(min_value=1, max_value=100_000),
        chunk_count=st.integers(min_value=0, max_value=1_000_000),
        year=st.integers(min_value=2020, max_value=2030),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
        second=st.integers(min_value=0, max_value=59),
    )
    @settings(max_examples=30, deadline=None)
    def test_rag_counts_match_database_with_documents(
        self,
        doc_count: int,
        chunk_count: int,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int,
        second: int,
    ):
        """When documents exist (N > 0), total_documents = N, total_chunks = M,
        and last_indexed_at equals the most recent document's timestamp.

        Feature: admin-system-monitor, Property 8: RAG document and chunk counts match database state
        Validates: Requirements 7.1, 7.2
        """
        # Feature: admin-system-monitor, Property 8: RAG document and chunk counts match database state
        # Validates: Requirements 7.1, 7.2, 7.3
        from datetime import datetime, timezone

        app = _build_app()
        client = TestClient(app)

        timestamp = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)

        admin_pool = _make_pool(idle_size=1)
        rag_pool = MagicMock()
        # fetchval is called 3 times: doc count, chunk count, max timestamp
        rag_pool.fetchval = AsyncMock(
            side_effect=[doc_count, chunk_count, timestamp]
        )

        call_count = 0

        async def _get_pool():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return admin_pool  # _require_admin
            return rag_pool  # _collect_rag

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
        ):
            resp = client.get("/rag")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert data["total_documents"] == doc_count, (
            f"Expected total_documents={doc_count}, got {data['total_documents']}"
        )
        assert data["total_chunks"] == chunk_count, (
            f"Expected total_chunks={chunk_count}, got {data['total_chunks']}"
        )
        assert data["last_indexed_at"] == timestamp.isoformat(), (
            f"Expected last_indexed_at={timestamp.isoformat()}, got {data['last_indexed_at']}"
        )

    @given(
        chunk_count=st.integers(min_value=0, max_value=1_000_000),
    )
    @settings(max_examples=30, deadline=None)
    def test_rag_empty_database_returns_zeros_and_null(
        self,
        chunk_count: int,
    ):
        """When no documents exist (N = 0), total_documents = 0 and
        last_indexed_at is null. Chunk count can be any value (including 0).

        Feature: admin-system-monitor, Property 8: RAG document and chunk counts match database state
        Validates: Requirement 7.3
        """
        # Feature: admin-system-monitor, Property 8: RAG document and chunk counts match database state
        # Validates: Requirements 7.1, 7.2, 7.3

        app = _build_app()
        client = TestClient(app)

        admin_pool = _make_pool(idle_size=1)
        rag_pool = MagicMock()
        # N=0 documents, M chunks, no timestamp (None)
        rag_pool.fetchval = AsyncMock(
            side_effect=[0, chunk_count, None]
        )

        call_count = 0

        async def _get_pool():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return admin_pool
            return rag_pool

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
        ):
            resp = client.get("/rag")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert data["total_documents"] == 0, (
            f"Expected total_documents=0, got {data['total_documents']}"
        )
        assert data["total_chunks"] == chunk_count, (
            f"Expected total_chunks={chunk_count}, got {data['total_chunks']}"
        )
        assert data["last_indexed_at"] is None, (
            f"Expected last_indexed_at=null when N=0, got {data['last_indexed_at']}"
        )

    @given(
        doc_count=st.integers(min_value=0, max_value=100_000),
        chunk_count=st.integers(min_value=0, max_value=1_000_000),
    )
    @settings(max_examples=30, deadline=None)
    def test_rag_counts_are_non_negative_integers(
        self,
        doc_count: int,
        chunk_count: int,
    ):
        """For any database state, total_documents and total_chunks are
        always non-negative integers in the response.

        Feature: admin-system-monitor, Property 8: RAG document and chunk counts match database state
        Validates: Requirements 7.1, 7.2, 7.3
        """
        # Feature: admin-system-monitor, Property 8: RAG document and chunk counts match database state
        # Validates: Requirements 7.1, 7.2, 7.3

        app = _build_app()
        client = TestClient(app)

        admin_pool = _make_pool(idle_size=1)
        rag_pool = MagicMock()
        timestamp = None if doc_count == 0 else MagicMock(isoformat=MagicMock(return_value="2024-01-01T00:00:00+00:00"))
        rag_pool.fetchval = AsyncMock(
            side_effect=[doc_count, chunk_count, timestamp]
        )

        call_count = 0

        async def _get_pool():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return admin_pool
            return rag_pool

        with (
            patch("monitor_router.get_web_user_by_id", new_callable=AsyncMock, return_value=ADMIN_USER),
            patch("monitor_router.get_pool", side_effect=_get_pool),
        ):
            resp = client.get("/rag")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert isinstance(data["total_documents"], int) and data["total_documents"] >= 0
        assert isinstance(data["total_chunks"], int) and data["total_chunks"] >= 0
