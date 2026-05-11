"""Property-based test for auto-refresh on expired access token.

# Feature: frontend-supabase-removal, Property 14: Auto-refresh on expired access token

Validates that the server-side endpoints support the client-side auto-refresh
flow: when an API request fails with 401 due to an expired Access_Token, the
refresh endpoint can issue a new valid Access_Token (given a valid Refresh_Token),
and the retried request with the new token succeeds.

Since vitest is not set up in the frontend, this tests the server-side contract
that enables the Auth_Client's authFetch auto-retry logic in auth-client.ts.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pbt-auto-refresh-32bytes!")

from auth_middleware import get_current_user
from auth_router import router as auth_router
from data_router import router as data_router
from token_manager import (
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JWT_SECRET = "test-secret-key-for-pbt-auto-refresh-32bytes!"

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_email_local = st.from_regex(r"[a-z][a-z0-9]{0,19}", fullmatch=True)
_email_domain = st.from_regex(r"[a-z]{2,8}\.[a-z]{2,4}", fullmatch=True)
valid_emails = st.builds(lambda l, d: f"{l}@{d}", _email_local, _email_domain)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    """Ensure JWT_SECRET_KEY is set and the module-level constant is patched."""
    monkeypatch.setenv("JWT_SECRET_KEY", JWT_SECRET)
    import token_manager
    monkeypatch.setattr(token_manager, "JWT_SECRET", JWT_SECRET)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_client() -> TestClient:
    """Build a fresh FastAPI app with auth + data routers."""
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(data_router, prefix="/api")
    return TestClient(app)


def _make_expired_access_token(user_id: str, email: str) -> str:
    """Create a JWT that expired 1 minute ago."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": now - timedelta(minutes=1),
        "iat": now - timedelta(minutes=16),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _make_user_row(user_id: uuid.UUID, email: str) -> dict:
    """Build a fake user DB row."""
    return {
        "id": user_id,
        "email": email,
        "password_hash": "not-used",
        "full_name": None,
        "avatar_url": None,
        "is_admin": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def _seed_refresh_token(stored_tokens: dict, user_id: uuid.UUID) -> str:
    """Create a raw refresh token, store its hash, return the raw value."""
    raw = secrets.token_urlsafe(48)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    stored_tokens[hashed] = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "token_hash": hashed,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "created_at": datetime.now(timezone.utc),
    }
    return raw


def _build_token_mocks(stored_tokens: dict, user_id: uuid.UUID, user_row: dict):
    """Return side-effect callables for refresh-token DB operations."""

    async def store(pool, uid, token_hash, expires_at):
        stored_tokens[token_hash] = {
            "id": uuid.uuid4(),
            "user_id": uuid.UUID(uid) if isinstance(uid, str) else uid,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc),
        }
        return stored_tokens[token_hash]

    async def get(pool, token_hash):
        return stored_tokens.get(token_hash)

    async def delete_one(pool, token_hash):
        stored_tokens.pop(token_hash, None)

    async def get_user_by_id(pool, uid):
        return user_row if str(uid) == str(user_id) else None

    return {
        "store": store,
        "get": get,
        "delete_one": delete_one,
        "get_user_by_id": get_user_by_id,
    }


# ---------------------------------------------------------------------------
# Property 14: Auto-refresh on expired access token
# ---------------------------------------------------------------------------


class TestAutoRefreshOnExpiredAccessToken:
    """Property 14: Auto-refresh on expired access token.

    **Validates: Requirements 9.3**

    For any API request made with an expired Access_Token but a valid
    Refresh_Token, the Auth_Client should automatically refresh the token
    and retry the request, resulting in a successful response rather than
    a 401 error.

    This test validates the server-side contract that enables the
    client-side authFetch auto-retry:
      1. A protected endpoint returns 401 for an expired token
      2. The refresh endpoint issues a new valid Access_Token
      3. Retrying the protected endpoint with the new token succeeds
    """

    @given(email=valid_emails)
    @settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_expired_token_refresh_then_retry_succeeds(self, email: str):
        """Simulate the authFetch auto-refresh flow at the API level."""
        client = _create_test_client()
        user_id = uuid.uuid4()
        user_row = _make_user_row(user_id, email)
        stored_tokens: dict = {}
        mocks = _build_token_mocks(stored_tokens, user_id, user_row)

        # Seed a valid refresh token
        raw_refresh = _seed_refresh_token(stored_tokens, user_id)

        expired_token = _make_expired_access_token(str(user_id), email)

        with (
            patch("auth_router.get_pool", new_callable=AsyncMock) as mock_pool,
            patch("data_router.get_pool", new_callable=AsyncMock) as mock_data_pool,
            patch("auth_router.store_refresh_token", side_effect=mocks["store"]),
            patch("auth_router.get_refresh_token", side_effect=mocks["get"]),
            patch("auth_router.delete_refresh_token", side_effect=mocks["delete_one"]),
            patch("auth_router.get_web_user_by_id", side_effect=mocks["get_user_by_id"]),
        ):
            mock_pool.return_value = AsyncMock()
            # Mock the data pool to return empty conversations list
            pool_instance = AsyncMock()
            pool_instance.fetch = AsyncMock(return_value=[])
            mock_data_pool.return_value = pool_instance

            # Step 1: Request a protected endpoint with the expired token → 401
            resp_expired = client.get(
                "/api/conversations",
                headers={"Authorization": f"Bearer {expired_token}"},
            )
            assert resp_expired.status_code == 401, (
                f"Expected 401 for expired token, got {resp_expired.status_code}"
            )

            # Step 2: Call refresh endpoint with valid refresh cookie → new token
            client.cookies["refresh_token"] = raw_refresh
            resp_refresh = client.post("/api/auth/refresh")
            assert resp_refresh.status_code == 200, (
                f"Refresh failed: {resp_refresh.text}"
            )
            new_access_token = resp_refresh.json()["access_token"]

            # Verify the new token is valid and has correct claims
            claims = decode_access_token(new_access_token)
            assert claims is not None, "New access token should be decodable"
            assert claims["sub"] == str(user_id)
            assert claims["email"] == email

            # Step 3: Retry the protected endpoint with the new token → success
            resp_retry = client.get(
                "/api/conversations",
                headers={"Authorization": f"Bearer {new_access_token}"},
            )
            assert resp_retry.status_code == 200, (
                f"Retry with refreshed token failed: {resp_retry.status_code} {resp_retry.text}"
            )

    @given(email=valid_emails)
    @settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_expired_token_with_invalid_refresh_stays_401(self, email: str):
        """When both access and refresh tokens are invalid, 401 persists.

        This is the complementary case: if the refresh token is also
        expired/invalid, the auto-refresh flow cannot recover and the
        client should redirect to login.
        """
        client = _create_test_client()
        user_id = uuid.uuid4()
        stored_tokens: dict = {}  # Empty — no valid refresh tokens

        expired_token = _make_expired_access_token(str(user_id), email)

        with (
            patch("auth_router.get_pool", new_callable=AsyncMock) as mock_pool,
            patch("auth_router.get_refresh_token", new_callable=AsyncMock, return_value=None),
        ):
            mock_pool.return_value = AsyncMock()

            # Step 1: Protected endpoint rejects expired token
            resp_expired = client.get(
                "/api/conversations",
                headers={"Authorization": f"Bearer {expired_token}"},
            )
            assert resp_expired.status_code == 401

            # Step 2: Refresh also fails (no valid refresh token)
            client.cookies["refresh_token"] = "bogus-token"
            resp_refresh = client.post("/api/auth/refresh")
            assert resp_refresh.status_code == 401

            # The client would redirect to login at this point
