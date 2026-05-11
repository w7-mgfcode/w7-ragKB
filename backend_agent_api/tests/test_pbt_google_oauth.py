"""Property-based tests for Google OAuth code exchange endpoint.

# Feature: frontend-supabase-removal, Property 15: Google OAuth code exchange

**Validates: Requirements 13.2**

Property 15: For any valid Google authorization code (mocked), the OAuth
callback endpoint should create or update a web_users record and return a
valid Access_Token and Refresh_Token pair with the correct user email from
Google's response.

Google HTTP calls (token exchange + userinfo) are mocked so hypothesis can
generate arbitrary email/name combinations without hitting real APIs.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pbt-google-oauth-32bytes!")
os.environ.setdefault("GOOGLE_CLIENT_ID", "fake-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "fake-client-secret")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")

from auth_router import router
from token_manager import decode_access_token

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JWT_SECRET = "test-secret-key-for-pbt-google-oauth-32bytes!"

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_email_local = st.from_regex(r"[a-z][a-z0-9]{0,19}", fullmatch=True)
_email_domain = st.from_regex(r"[a-z]{2,8}\.[a-z]{2,4}", fullmatch=True)
google_emails = st.builds(lambda l, d: f"{l}@{d}", _email_local, _email_domain)

google_names = st.one_of(
    st.none(),
    st.text(
        min_size=1,
        max_size=60,
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    ),
)

google_avatars = st.one_of(
    st.none(),
    st.from_regex(
        r"https://lh3\.googleusercontent\.com/[a-z0-9]{5,15}",
        fullmatch=True,
    ),
)

auth_codes = st.from_regex(r"4/[A-Za-z0-9_-]{20,40}", fullmatch=True)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_env_vars(monkeypatch):
    """Set JWT secret and Google OAuth env vars for all tests."""
    monkeypatch.setenv("JWT_SECRET_KEY", JWT_SECRET)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:5173")
    import token_manager
    monkeypatch.setattr(token_manager, "JWT_SECRET", JWT_SECRET)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_client() -> TestClient:
    """Build a fresh FastAPI app with the auth router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/auth")
    return TestClient(app, follow_redirects=False)


def _make_user_row(user_id: uuid.UUID, email: str, full_name=None, avatar_url=None):
    """Build a fake user dict matching the DB row shape."""
    return {
        "id": user_id,
        "email": email,
        "password_hash": None,
        "full_name": full_name,
        "avatar_url": avatar_url,
        "is_admin": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def _build_mock_httpx_client(email: str, name, avatar_url):
    """Build a mock httpx.AsyncClient that returns Google token + userinfo."""

    async def mock_post(url, **kwargs):
        """Mock the Google token exchange POST."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": "mock-google-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        resp.text = '{"access_token": "mock-google-access-token"}'
        return resp

    async def mock_get(url, **kwargs):
        """Mock the Google userinfo GET."""
        resp = MagicMock()
        resp.status_code = 200
        userinfo = {"email": email}
        if name is not None:
            userinfo["name"] = name
        if avatar_url is not None:
            userinfo["picture"] = avatar_url
        resp.json.return_value = userinfo
        resp.text = str(userinfo)
        return resp

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# Property 15: Google OAuth code exchange
# ---------------------------------------------------------------------------


class TestGoogleOAuthCodeExchange:
    """Property 15: Google OAuth code exchange.

    **Validates: Requirements 13.2**

    For any valid Google authorization code (mocked), the OAuth callback
    endpoint should create or update a web_users record and return a valid
    Access_Token and Refresh_Token pair with the correct user email from
    Google's response.
    """

    @given(
        email=google_emails,
        name=google_names,
        avatar_url=google_avatars,
        code=auth_codes,
    )
    @settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_oauth_callback_creates_user_and_returns_tokens(
        self, email, name, avatar_url, code
    ):
        # Feature: frontend-supabase-removal, Property 15: Google OAuth code exchange
        client = _create_test_client()
        user_id = uuid.uuid4()
        user_row = _make_user_row(user_id, email, name, avatar_url)

        stored_refresh_tokens = {}

        async def fake_create_or_update(pool, email=None, full_name=None, avatar_url=None):
            return _make_user_row(user_id, email, full_name, avatar_url)

        async def fake_store_refresh(pool, uid, token_hash, expires_at):
            stored_refresh_tokens[token_hash] = {
                "id": uuid.uuid4(),
                "user_id": uid,
                "token_hash": token_hash,
                "expires_at": expires_at,
                "created_at": datetime.now(timezone.utc),
            }

        mock_httpx = _build_mock_httpx_client(email, name, avatar_url)

        with (
            patch("auth_router.get_pool", new_callable=AsyncMock) as mock_pool,
            patch("auth_router.create_or_update_google_user", side_effect=fake_create_or_update),
            patch("auth_router.store_refresh_token", side_effect=fake_store_refresh),
            patch("auth_router.httpx.AsyncClient", return_value=mock_httpx),
        ):
            mock_pool.return_value = AsyncMock()

            resp = client.get(f"/api/auth/google/callback?code={code}")

            # The endpoint returns a redirect to the frontend with the access token
            assert resp.status_code == 307, f"Expected redirect, got {resp.status_code}"

            location = resp.headers["location"]
            parsed = urlparse(location)
            query_params = parse_qs(parsed.query)

            # Access token should be in the redirect URL
            assert "access_token" in query_params, (
                f"No access_token in redirect URL: {location}"
            )
            access_token = query_params["access_token"][0]

            # Decode and verify the access token has the correct email
            claims = decode_access_token(access_token)
            assert claims is not None, "Access token should be decodable"
            assert claims["email"] == email, (
                f"Token email {claims['email']} != Google email {email}"
            )
            assert claims["sub"] == str(user_id), (
                f"Token sub {claims['sub']} != user_id {user_id}"
            )

            # A refresh token should have been stored in the DB
            assert len(stored_refresh_tokens) == 1, (
                f"Expected 1 stored refresh token, got {len(stored_refresh_tokens)}"
            )

            # The refresh token cookie should be set on the response
            assert "refresh_token" in resp.cookies, (
                "Refresh token cookie should be set on the redirect response"
            )

            # Verify the stored hash matches the cookie value
            raw_cookie = resp.cookies["refresh_token"]
            expected_hash = hashlib.sha256(raw_cookie.encode()).hexdigest()
            assert expected_hash in stored_refresh_tokens, (
                "Stored refresh token hash should match the SHA-256 of the cookie value"
            )

    @given(code=auth_codes)
    @settings(max_examples=25, deadline=None)
    def test_oauth_callback_error_param_redirects_with_error(self, code):
        """When Google returns an error parameter, the endpoint should redirect
        to the frontend with an error message instead of tokens."""
        # Feature: frontend-supabase-removal, Property 15: Google OAuth code exchange
        client = _create_test_client()

        resp = client.get("/api/auth/google/callback?error=access_denied")

        assert resp.status_code == 307
        location = resp.headers["location"]
        assert "error=" in location, (
            f"Error redirect should contain error param: {location}"
        )
        assert "access_token" not in location, (
            "Error redirect should not contain access_token"
        )

    @given(
        email=google_emails,
        name=google_names,
        avatar_url=google_avatars,
        code=auth_codes,
    )
    @settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_oauth_callback_updates_existing_user(self, email, name, avatar_url, code):
        """For an existing user, the OAuth callback should update their profile
        and still return valid tokens with the correct email."""
        # Feature: frontend-supabase-removal, Property 15: Google OAuth code exchange
        client = _create_test_client()
        user_id = uuid.uuid4()

        # Track whether create_or_update was called
        upsert_called = {"count": 0, "args": None}

        async def fake_create_or_update(pool, email=None, full_name=None, avatar_url=None):
            upsert_called["count"] += 1
            upsert_called["args"] = (email, full_name, avatar_url)
            return _make_user_row(user_id, email, full_name, avatar_url)

        async def fake_store_refresh(pool, uid, token_hash, expires_at):
            pass

        mock_httpx = _build_mock_httpx_client(email, name, avatar_url)

        with (
            patch("auth_router.get_pool", new_callable=AsyncMock) as mock_pool,
            patch("auth_router.create_or_update_google_user", side_effect=fake_create_or_update),
            patch("auth_router.store_refresh_token", side_effect=fake_store_refresh),
            patch("auth_router.httpx.AsyncClient", return_value=mock_httpx),
        ):
            mock_pool.return_value = AsyncMock()

            resp = client.get(f"/api/auth/google/callback?code={code}")

            assert resp.status_code == 307
            assert upsert_called["count"] == 1, "create_or_update_google_user should be called once"

            # Verify the upsert received the correct Google profile data
            upsert_email, upsert_name, upsert_avatar = upsert_called["args"]
            assert upsert_email == email
            assert upsert_name == name
            assert upsert_avatar == avatar_url

            # Verify the redirect contains a valid access token
            location = resp.headers["location"]
            parsed = urlparse(location)
            query_params = parse_qs(parsed.query)
            assert "access_token" in query_params

            claims = decode_access_token(query_params["access_token"][0])
            assert claims is not None
            assert claims["email"] == email
