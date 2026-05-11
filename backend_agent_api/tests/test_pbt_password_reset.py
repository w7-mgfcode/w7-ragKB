"""Property-based tests for password reset endpoints.

# Feature: frontend-supabase-removal, Property 7: Password reset round-trip
# Feature: frontend-supabase-removal, Property 8: Reset request anti-enumeration

Uses hypothesis to generate arbitrary valid inputs and verifies
correctness properties hold across all generated cases. DB interactions
are mocked. bcrypt is replaced with a fast fake hasher to keep
hypothesis examples within a reasonable time budget.
"""

import hashlib
import secrets as stdlib_secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pbt-password-reset-32bytes!")

from auth_router import router
from token_manager import decode_access_token

# ---------------------------------------------------------------------------
# Fast password hashing (replaces bcrypt for PBT speed)
# ---------------------------------------------------------------------------

_FAKE_PREFIX = "fakehash:"


def _fast_hash_password(password: str) -> str:
    """Deterministic fast hash for testing — NOT for production."""
    return _FAKE_PREFIX + hashlib.sha256(password.encode()).hexdigest()


def _fast_verify_password(password: str, password_hash: str) -> bool:
    return password_hash == _fast_hash_password(password)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_email_local = st.from_regex(r"[a-z][a-z0-9]{0,19}", fullmatch=True)
_email_domain = st.from_regex(r"[a-z]{2,8}\.[a-z]{2,4}", fullmatch=True)
valid_emails = st.builds(lambda l, d: f"{l}@{d}", _email_local, _email_domain)

valid_passwords = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=8,
    max_size=30,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

JWT_SECRET = "test-secret-key-for-pbt-password-reset-32bytes!"


@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", JWT_SECRET)
    import token_manager
    monkeypatch.setattr(token_manager, "JWT_SECRET", JWT_SECRET)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/auth")
    return TestClient(app)


def _make_user_row(user_id, email, password_hash="not-used"):
    return {
        "id": user_id,
        "email": email,
        "password_hash": password_hash,
        "full_name": None,
        "avatar_url": None,
        "is_admin": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def _build_reset_mocks(user_id, email, user_state, stored_reset_tokens, stored_refresh_tokens):
    """Build all DB mock side-effects for the password reset flow."""

    async def get_user_by_email(_pool, em):
        if em == email:
            return _make_user_row(user_id, email, user_state["password_hash"])
        return None

    async def store_reset_token(_pool, uid, token_hash, expires_at):
        stored_reset_tokens[token_hash] = {
            "id": uuid.uuid4(),
            "user_id": uuid.UUID(uid) if isinstance(uid, str) else uid,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "used": False,
            "created_at": datetime.now(timezone.utc),
        }

    async def get_reset_token(_pool, token_hash):
        return stored_reset_tokens.get(token_hash)

    async def mark_reset_token_used(_pool, token_id):
        for t in stored_reset_tokens.values():
            if str(t["id"]) == str(token_id):
                t["used"] = True

    async def update_password(_pool, _uid, pw_hash):
        user_state["password_hash"] = pw_hash

    async def store_refresh_token(_pool, uid, token_hash, expires_at):
        stored_refresh_tokens[token_hash] = {
            "id": uuid.uuid4(),
            "user_id": uuid.UUID(uid) if isinstance(uid, str) else uid,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc),
        }

    async def delete_all_refresh_tokens(_pool, uid):
        to_remove = [
            h for h, row in stored_refresh_tokens.items()
            if str(row["user_id"]) == str(uid)
        ]
        for h in to_remove:
            del stored_refresh_tokens[h]

    return {
        "get_user_by_email": get_user_by_email,
        "store_reset_token": store_reset_token,
        "get_reset_token": get_reset_token,
        "mark_reset_token_used": mark_reset_token_used,
        "update_password": update_password,
        "store_refresh_token": store_refresh_token,
        "delete_all_refresh_tokens": delete_all_refresh_tokens,
    }



# ---------------------------------------------------------------------------
# Property 7: Password reset round-trip
# ---------------------------------------------------------------------------


class TestPasswordResetRoundTrip:
    """Property 7: Password reset round-trip.

    **Validates: Requirements 4.1, 4.3**

    For any registered user, requesting a password reset, then confirming
    with the reset token and a new password, should allow the user to
    login with the new password and should invalidate all previously
    issued Refresh_Tokens.

    bcrypt is patched with a fast deterministic hasher so hypothesis
    can run many examples without timing out. The round-trip logic
    (reset → confirm → login succeeds with new pw, fails with old pw,
    refresh tokens invalidated) is fully exercised.
    """

    @given(
        email=valid_emails,
        original_password=valid_passwords,
        new_password=valid_passwords,
    )
    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_reset_then_login_with_new_password(
        self, email, original_password, new_password
    ):
        # Feature: frontend-supabase-removal, Property 7: Password reset round-trip
        client = _create_test_client()
        user_id = uuid.uuid4()
        original_hash = _fast_hash_password(original_password)

        user_state = {"password_hash": original_hash}
        stored_reset_tokens = {}
        stored_refresh_tokens = {}

        mocks = _build_reset_mocks(
            user_id, email, user_state, stored_reset_tokens, stored_refresh_tokens
        )

        # Capture the raw reset token generated inside the endpoint
        captured_raw = {"value": None}
        _real_token_urlsafe = stdlib_secrets.token_urlsafe

        def capturing_token_urlsafe(nbytes=32):
            raw = _real_token_urlsafe(nbytes)
            captured_raw["value"] = raw
            return raw

        with (
            patch("auth_router.get_pool", new_callable=AsyncMock) as mock_pool,
            patch("auth_router.get_web_user_by_email", side_effect=mocks["get_user_by_email"]),
            patch("auth_router.store_reset_token", side_effect=mocks["store_reset_token"]),
            patch("auth_router.get_reset_token", side_effect=mocks["get_reset_token"]),
            patch("auth_router.mark_reset_token_used", side_effect=mocks["mark_reset_token_used"]),
            patch("auth_router.update_web_user_password", side_effect=mocks["update_password"]),
            patch("auth_router.store_refresh_token", side_effect=mocks["store_refresh_token"]),
            patch("auth_router.delete_all_refresh_tokens", side_effect=mocks["delete_all_refresh_tokens"]),
            patch("auth_router.check_rate_limit", return_value=False),
            patch("auth_router.reset_attempts"),
            patch("auth_router.secrets.token_urlsafe", side_effect=capturing_token_urlsafe),
            patch("auth_router._hash_password", side_effect=_fast_hash_password),
            patch("auth_router._verify_password", side_effect=_fast_verify_password),
        ):
            mock_pool.return_value = AsyncMock()

            # Step 1: Request password reset — captures the raw token
            reset_resp = client.post(
                "/api/auth/reset-password",
                json={"email": email},
            )
            assert reset_resp.status_code == 200
            assert "detail" in reset_resp.json()

            raw_token = captured_raw["value"]
            assert raw_token is not None, "Should have captured the raw reset token"

            expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            assert expected_hash in stored_reset_tokens, "Reset token hash should be stored"

            # Seed a pre-existing refresh token to verify invalidation
            pre_raw = _real_token_urlsafe(48)
            pre_hash = hashlib.sha256(pre_raw.encode()).hexdigest()
            stored_refresh_tokens[pre_hash] = {
                "id": uuid.uuid4(),
                "user_id": user_id,
                "token_hash": pre_hash,
                "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
                "created_at": datetime.now(timezone.utc),
            }
            assert len(stored_refresh_tokens) == 1

            # Step 2: Confirm password reset
            confirm_resp = client.post(
                "/api/auth/reset-password/confirm",
                json={"token": raw_token, "new_password": new_password},
            )
            assert confirm_resp.status_code == 200, f"Confirm failed: {confirm_resp.text}"

            # Step 3: All refresh tokens should be invalidated
            assert len(stored_refresh_tokens) == 0, (
                "All refresh tokens should be invalidated after password reset"
            )

            # Step 4: Reset token should be marked as used
            assert stored_reset_tokens[expected_hash]["used"] is True

            # Step 5: Login with the new password should succeed
            login_resp = client.post(
                "/api/auth/login",
                json={"email": email, "password": new_password},
            )
            assert login_resp.status_code == 200, f"Login with new pw failed: {login_resp.text}"
            login_data = login_resp.json()
            assert "access_token" in login_data
            claims = decode_access_token(login_data["access_token"])
            assert claims is not None
            assert claims["sub"] == str(user_id)
            assert claims["email"] == email

            # Step 6: Old password should no longer work (unless identical)
            if original_password != new_password:
                login_old_resp = client.post(
                    "/api/auth/login",
                    json={"email": email, "password": original_password},
                )
                assert login_old_resp.status_code == 401, (
                    "Login with old password should fail after reset"
                )


# ---------------------------------------------------------------------------
# Property 8: Reset request anti-enumeration
# ---------------------------------------------------------------------------


class TestResetRequestAntiEnumeration:
    """Property 8: Reset request anti-enumeration.

    **Validates: Requirements 4.2**

    For any email address (registered or not), the password reset request
    endpoint should return the same HTTP status code and response body
    structure, so that an attacker cannot determine whether an email is
    registered.
    """

    @given(registered_email=valid_emails, unregistered_email=valid_emails)
    @settings(max_examples=25, deadline=None)
    def test_registered_vs_unregistered_identical_response(
        self, registered_email, unregistered_email
    ):
        # Feature: frontend-supabase-removal, Property 8: Reset request anti-enumeration
        client = _create_test_client()
        user_id = uuid.uuid4()
        user_row = _make_user_row(user_id, registered_email)

        async def fake_get_user_by_email(_pool, em):
            if em == registered_email:
                return user_row
            return None

        with (
            patch("auth_router.get_pool", new_callable=AsyncMock) as mock_pool,
            patch("auth_router.get_web_user_by_email", side_effect=fake_get_user_by_email),
            patch("auth_router.store_reset_token", new_callable=AsyncMock),
        ):
            mock_pool.return_value = AsyncMock()

            resp_registered = client.post(
                "/api/auth/reset-password",
                json={"email": registered_email},
            )

            resp_unregistered = client.post(
                "/api/auth/reset-password",
                json={"email": unregistered_email},
            )

            # Both must return the same status code
            assert resp_registered.status_code == resp_unregistered.status_code, (
                f"Status codes differ: {resp_registered.status_code} vs "
                f"{resp_unregistered.status_code}"
            )

            body_registered = resp_registered.json()
            body_unregistered = resp_unregistered.json()

            # Both must have identical response body keys
            assert set(body_registered.keys()) == set(body_unregistered.keys()), (
                f"Keys differ: {body_registered.keys()} vs {body_unregistered.keys()}"
            )

            # Both must have identical response body values
            assert body_registered == body_unregistered, (
                f"Bodies differ: {body_registered} vs {body_unregistered}"
            )
