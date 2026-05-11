"""Unit tests for auth_router module.

Uses FastAPI TestClient with mocked DB dependencies to test all auth endpoints.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Patch env before importing modules that read it at import time
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from auth_router import router, _hash_password, _verify_password, _hash_token
from token_manager import create_access_token


@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    """Ensure token_manager has a deterministic secret for all tests."""
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")
    import token_manager
    monkeypatch.setattr(token_manager, "JWT_SECRET", "test-secret-key-for-unit-tests")


@pytest.fixture
def app():
    """Create a FastAPI app with the auth router mounted."""
    app = FastAPI()
    app.include_router(router, prefix="/api/auth")
    return app


@pytest.fixture
def client(app):
    """Create a TestClient for the app."""
    return TestClient(app)


def _make_user(
    user_id=None,
    email="alice@example.com",
    password="securepass123",
    is_admin=False,
):
    """Build a fake user dict matching DB row shape."""
    return {
        "id": uuid.UUID(user_id) if user_id else uuid.uuid4(),
        "email": email,
        "password_hash": _hash_password(password),
        "full_name": None,
        "avatar_url": None,
        "is_admin": is_admin,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }



# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegister:
    @patch("auth_router.get_pool")
    @patch("auth_router.get_web_user_by_email", new_callable=AsyncMock)
    @patch("auth_router.create_web_user", new_callable=AsyncMock)
    @patch("auth_router.store_refresh_token", new_callable=AsyncMock)
    def test_register_success(
        self, mock_store_rt, mock_create, mock_get_email, mock_pool, client
    ):
        mock_pool.return_value = AsyncMock()
        mock_get_email.return_value = None
        user = _make_user()
        mock_create.return_value = user
        mock_store_rt.return_value = {"id": uuid.uuid4()}

        resp = client.post(
            "/api/auth/register",
            json={"email": "alice@example.com", "password": "securepass123"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["email"] == "alice@example.com"
        assert "refresh_token" in resp.cookies

    @patch("auth_router.get_pool")
    @patch("auth_router.get_web_user_by_email", new_callable=AsyncMock)
    def test_register_duplicate_email(self, mock_get_email, mock_pool, client):
        mock_pool.return_value = AsyncMock()
        mock_get_email.return_value = _make_user()

        resp = client.post(
            "/api/auth/register",
            json={"email": "alice@example.com", "password": "securepass123"},
        )

        assert resp.status_code == 409
        assert resp.json()["detail"] == "Email already registered"

    def test_register_short_password(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"email": "alice@example.com", "password": "short"},
        )
        assert resp.status_code == 422

    def test_register_invalid_email(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "password": "securepass123"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


class TestLogin:
    @patch("auth_router.get_pool")
    @patch("auth_router.get_web_user_by_email", new_callable=AsyncMock)
    @patch("auth_router.store_refresh_token", new_callable=AsyncMock)
    @patch("auth_router.reset_attempts")
    @patch("auth_router.check_rate_limit", return_value=False)
    def test_login_success(
        self,
        mock_rate,
        mock_reset,
        mock_store_rt,
        mock_get_email,
        mock_pool,
        client,
    ):
        mock_pool.return_value = AsyncMock()
        user = _make_user(password="correctpassword")
        mock_get_email.return_value = user
        mock_store_rt.return_value = {"id": uuid.uuid4()}

        resp = client.post(
            "/api/auth/login",
            json={"email": "alice@example.com", "password": "correctpassword"},
        )

        assert resp.status_code == 200
        assert "access_token" in resp.json()
        mock_reset.assert_called_once_with("alice@example.com")

    @patch("auth_router.get_pool")
    @patch("auth_router.get_web_user_by_email", new_callable=AsyncMock)
    @patch("auth_router.record_failed_attempt")
    @patch("auth_router.check_rate_limit", return_value=False)
    def test_login_wrong_password(
        self, mock_rate, mock_record, mock_get_email, mock_pool, client
    ):
        mock_pool.return_value = AsyncMock()
        user = _make_user(password="correctpassword")
        mock_get_email.return_value = user

        resp = client.post(
            "/api/auth/login",
            json={"email": "alice@example.com", "password": "wrongpassword"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"
        mock_record.assert_called_once()

    @patch("auth_router.get_pool")
    @patch("auth_router.get_web_user_by_email", new_callable=AsyncMock)
    @patch("auth_router.record_failed_attempt")
    @patch("auth_router.check_rate_limit", return_value=False)
    def test_login_nonexistent_email(
        self, mock_rate, mock_record, mock_get_email, mock_pool, client
    ):
        mock_pool.return_value = AsyncMock()
        mock_get_email.return_value = None

        resp = client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "anypassword"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    @patch("auth_router.check_rate_limit", return_value=True)
    def test_login_rate_limited(self, mock_rate, client):
        resp = client.post(
            "/api/auth/login",
            json={"email": "alice@example.com", "password": "anypassword"},
        )

        assert resp.status_code == 429
        assert "Too many login attempts" in resp.json()["detail"]



# ---------------------------------------------------------------------------
# Refresh token tests
# ---------------------------------------------------------------------------


class TestRefresh:
    @patch("auth_router.get_pool")
    @patch("auth_router.get_refresh_token", new_callable=AsyncMock)
    @patch("auth_router.delete_refresh_token", new_callable=AsyncMock)
    @patch("auth_router.get_web_user_by_id", new_callable=AsyncMock)
    @patch("auth_router.store_refresh_token", new_callable=AsyncMock)
    def test_refresh_success(
        self,
        mock_store_rt,
        mock_get_user,
        mock_delete_rt,
        mock_get_rt,
        mock_pool,
        client,
    ):
        mock_pool.return_value = AsyncMock()
        raw_token = "test-refresh-token"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        user = _make_user()

        mock_get_rt.return_value = {
            "id": uuid.uuid4(),
            "user_id": user["id"],
            "token_hash": token_hash,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
            "created_at": datetime.now(timezone.utc),
        }
        mock_get_user.return_value = user
        mock_store_rt.return_value = {"id": uuid.uuid4()}

        client.cookies.set("refresh_token", raw_token, domain="testserver.local")
        resp = client.post("/api/auth/refresh")

        assert resp.status_code == 200
        assert "access_token" in resp.json()
        mock_delete_rt.assert_called_once()

    def test_refresh_no_cookie(self, client):
        resp = client.post("/api/auth/refresh")
        assert resp.status_code == 401

    @patch("auth_router.get_pool")
    @patch("auth_router.get_refresh_token", new_callable=AsyncMock)
    def test_refresh_invalid_token(self, mock_get_rt, mock_pool, client):
        mock_pool.return_value = AsyncMock()
        mock_get_rt.return_value = None

        client.cookies.set("refresh_token", "bad-token", domain="testserver.local")
        resp = client.post("/api/auth/refresh")

        assert resp.status_code == 401

    @patch("auth_router.get_pool")
    @patch("auth_router.get_refresh_token", new_callable=AsyncMock)
    @patch("auth_router.delete_refresh_token", new_callable=AsyncMock)
    def test_refresh_expired_token(
        self, mock_delete_rt, mock_get_rt, mock_pool, client
    ):
        mock_pool.return_value = AsyncMock()
        mock_get_rt.return_value = {
            "id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "token_hash": "somehash",
            "expires_at": datetime.now(timezone.utc) - timedelta(hours=1),
            "created_at": datetime.now(timezone.utc) - timedelta(days=8),
        }

        client.cookies.set("refresh_token", "expired-token", domain="testserver.local")
        resp = client.post("/api/auth/refresh")

        assert resp.status_code == 401
        mock_delete_rt.assert_called_once()


# ---------------------------------------------------------------------------
# Logout tests
# ---------------------------------------------------------------------------


class TestLogout:
    @patch("auth_router.get_pool")
    @patch("auth_router.delete_all_refresh_tokens", new_callable=AsyncMock)
    def test_logout_success(self, mock_delete_all, mock_pool, client):
        mock_pool.return_value = AsyncMock()
        token = create_access_token("user-123", "alice@example.com")

        resp = client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        mock_delete_all.assert_called_once_with(mock_pool.return_value, "user-123")

    def test_logout_no_token(self, client):
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 401



# ---------------------------------------------------------------------------
# Password reset tests
# ---------------------------------------------------------------------------


class TestResetPassword:
    @patch("auth_router.get_pool")
    @patch("auth_router.get_web_user_by_email", new_callable=AsyncMock)
    @patch("auth_router.store_reset_token", new_callable=AsyncMock)
    def test_reset_registered_email(
        self, mock_store, mock_get_email, mock_pool, client
    ):
        mock_pool.return_value = AsyncMock()
        mock_get_email.return_value = _make_user()
        mock_store.return_value = {"id": uuid.uuid4()}

        resp = client.post(
            "/api/auth/reset-password",
            json={"email": "alice@example.com"},
        )

        assert resp.status_code == 200
        mock_store.assert_called_once()

    @patch("auth_router.get_pool")
    @patch("auth_router.get_web_user_by_email", new_callable=AsyncMock)
    def test_reset_unregistered_email_same_response(
        self, mock_get_email, mock_pool, client
    ):
        mock_pool.return_value = AsyncMock()
        mock_get_email.return_value = None

        resp = client.post(
            "/api/auth/reset-password",
            json={"email": "nobody@example.com"},
        )

        # Same status and response shape as registered email
        assert resp.status_code == 200
        assert "detail" in resp.json()


class TestResetPasswordConfirm:
    @patch("auth_router.get_pool")
    @patch("auth_router.get_reset_token", new_callable=AsyncMock)
    @patch("auth_router.update_web_user_password", new_callable=AsyncMock)
    @patch("auth_router.mark_reset_token_used", new_callable=AsyncMock)
    @patch("auth_router.delete_all_refresh_tokens", new_callable=AsyncMock)
    def test_confirm_success(
        self,
        mock_delete_all,
        mock_mark_used,
        mock_update_pw,
        mock_get_reset,
        mock_pool,
        client,
    ):
        mock_pool.return_value = AsyncMock()
        user_id = uuid.uuid4()
        token_id = uuid.uuid4()
        mock_get_reset.return_value = {
            "id": token_id,
            "user_id": user_id,
            "token_hash": "somehash",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=30),
            "used": False,
            "created_at": datetime.now(timezone.utc),
        }

        resp = client.post(
            "/api/auth/reset-password/confirm",
            json={"token": "raw-reset-token", "new_password": "newpassword123"},
        )

        assert resp.status_code == 200
        mock_update_pw.assert_called_once()
        mock_mark_used.assert_called_once()
        mock_delete_all.assert_called_once()

    @patch("auth_router.get_pool")
    @patch("auth_router.get_reset_token", new_callable=AsyncMock)
    def test_confirm_invalid_token(self, mock_get_reset, mock_pool, client):
        mock_pool.return_value = AsyncMock()
        mock_get_reset.return_value = None

        resp = client.post(
            "/api/auth/reset-password/confirm",
            json={"token": "bad-token", "new_password": "newpassword123"},
        )

        assert resp.status_code == 400
        assert "Invalid or expired reset token" in resp.json()["detail"]

    @patch("auth_router.get_pool")
    @patch("auth_router.get_reset_token", new_callable=AsyncMock)
    def test_confirm_expired_token(self, mock_get_reset, mock_pool, client):
        mock_pool.return_value = AsyncMock()
        mock_get_reset.return_value = {
            "id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "token_hash": "somehash",
            "expires_at": datetime.now(timezone.utc) - timedelta(hours=2),
            "used": False,
            "created_at": datetime.now(timezone.utc) - timedelta(hours=3),
        }

        resp = client.post(
            "/api/auth/reset-password/confirm",
            json={"token": "expired-token", "new_password": "newpassword123"},
        )

        assert resp.status_code == 400

    @patch("auth_router.get_pool")
    @patch("auth_router.get_reset_token", new_callable=AsyncMock)
    def test_confirm_already_used_token(self, mock_get_reset, mock_pool, client):
        mock_pool.return_value = AsyncMock()
        mock_get_reset.return_value = {
            "id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "token_hash": "somehash",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=30),
            "used": True,
            "created_at": datetime.now(timezone.utc),
        }

        resp = client.post(
            "/api/auth/reset-password/confirm",
            json={"token": "used-token", "new_password": "newpassword123"},
        )

        assert resp.status_code == 400



# ---------------------------------------------------------------------------
# Profile tests
# ---------------------------------------------------------------------------


class TestGetProfile:
    @patch("auth_router.get_pool")
    @patch("auth_router.get_web_user_by_id", new_callable=AsyncMock)
    def test_get_profile_success(self, mock_get_user, mock_pool, client):
        mock_pool.return_value = AsyncMock()
        user = _make_user()
        mock_get_user.return_value = user
        token = create_access_token(str(user["id"]), user["email"])

        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["email"] == "alice@example.com"

    def test_get_profile_no_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401


class TestUpdateProfile:
    @patch("auth_router.get_pool")
    @patch("auth_router.update_web_user_profile", new_callable=AsyncMock)
    def test_update_profile_success(self, mock_update, mock_pool, client):
        mock_pool.return_value = AsyncMock()
        user = _make_user()
        updated_user = {**user, "full_name": "Alice Smith", "avatar_url": "https://example.com/avatar.png"}
        mock_update.return_value = updated_user
        token = create_access_token(str(user["id"]), user["email"])

        resp = client.patch(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            json={"full_name": "Alice Smith", "avatar_url": "https://example.com/avatar.png"},
        )

        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Alice Smith"
        assert resp.json()["avatar_url"] == "https://example.com/avatar.png"


# ---------------------------------------------------------------------------
# Google OAuth tests
# ---------------------------------------------------------------------------


class TestGoogleOAuth:
    @patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "test-client-id"})
    def test_google_redirect(self, client):
        resp = client.get("/api/auth/google", follow_redirects=False)

        assert resp.status_code == 307
        assert "accounts.google.com" in resp.headers["location"]
        assert "test-client-id" in resp.headers["location"]

    @patch.dict(os.environ, {}, clear=False)
    def test_google_redirect_not_configured(self, client, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)

        resp = client.get("/api/auth/google")
        assert resp.status_code == 500

    def test_google_callback_error_param(self, client):
        resp = client.get(
            "/api/auth/google/callback?error=access_denied",
            follow_redirects=False,
        )

        assert resp.status_code == 307
        assert "error=" in resp.headers["location"]

    @patch("auth_router.get_pool")
    @patch("auth_router.create_or_update_google_user", new_callable=AsyncMock)
    @patch("auth_router.store_refresh_token", new_callable=AsyncMock)
    @patch("httpx.AsyncClient.post", new_callable=AsyncMock)
    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    @patch.dict(
        os.environ,
        {
            "GOOGLE_CLIENT_ID": "test-client-id",
            "GOOGLE_CLIENT_SECRET": "test-client-secret",
            "FRONTEND_URL": "http://localhost:3000",
        },
    )
    def test_google_callback_success(
        self,
        mock_httpx_get,
        mock_httpx_post,
        mock_store_rt,
        mock_create_google,
        mock_pool,
        client,
    ):
        mock_pool.return_value = AsyncMock()

        # Mock Google token exchange
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {"access_token": "google-access-token"}
        mock_httpx_post.return_value = token_response

        # Mock Google userinfo
        userinfo_response = MagicMock()
        userinfo_response.status_code = 200
        userinfo_response.json.return_value = {
            "email": "alice@gmail.com",
            "name": "Alice",
            "picture": "https://example.com/photo.jpg",
        }
        mock_httpx_get.return_value = userinfo_response

        user = _make_user(email="alice@gmail.com")
        mock_create_google.return_value = user
        mock_store_rt.return_value = {"id": uuid.uuid4()}

        resp = client.get(
            "/api/auth/google/callback?code=test-auth-code",
            follow_redirects=False,
        )

        assert resp.status_code == 307
        assert "access_token=" in resp.headers["location"]
        mock_create_google.assert_called_once()


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_hash_and_verify_password(self):
        hashed = _hash_password("mypassword")
        assert _verify_password("mypassword", hashed)
        assert not _verify_password("wrongpassword", hashed)

    def test_hash_token(self):
        raw = "test-token-value"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert _hash_token(raw) == expected
