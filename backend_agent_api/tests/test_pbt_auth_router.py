"""Property-based tests for auth_router registration and login endpoints.

# Feature: frontend-supabase-removal, Property 1: Registration then login round-trip
# Feature: frontend-supabase-removal, Property 2: Invalid registration input rejection
# Feature: frontend-supabase-removal, Property 3: Login error response consistency

Uses hypothesis to generate arbitrary valid/invalid inputs and verifies
correctness properties hold across all generated cases. DB interactions
are mocked since we don't have testcontainers set up.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pbt-auth-router-32bytes!")

from auth_router import router, _hash_password
from token_manager import create_access_token, decode_access_token

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_email_local = st.from_regex(r"[a-z][a-z0-9]{0,19}", fullmatch=True)
_email_domain = st.from_regex(r"[a-z]{2,8}\.[a-z]{2,4}", fullmatch=True)
valid_emails = st.builds(lambda l, d: f"{l}@{d}", _email_local, _email_domain)

valid_passwords = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=8,
    max_size=50,
)

short_passwords = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=0,
    max_size=7,
)

invalid_emails = st.sampled_from([
    "",
    "plaintext",
    "missing@",
    "@nodomain.com",
    "spaces in@email.com",
    "noatsign",
    "double@@at.com",
    ".leading@dot.com",
    "trailing.@dot.com",
    "no-tld@domain",
])

any_passwords = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=1,
    max_size=50,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

JWT_SECRET = "test-secret-key-for-pbt-auth-router-32bytes!"


@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    """Set JWT_SECRET_KEY and patch the module-level constant."""
    monkeypatch.setenv("JWT_SECRET_KEY", JWT_SECRET)
    import token_manager
    monkeypatch.setattr(token_manager, "JWT_SECRET", JWT_SECRET)


def _create_test_client() -> TestClient:
    """Build a fresh FastAPI app + TestClient for each hypothesis example."""
    app = FastAPI()
    app.include_router(router, prefix="/api/auth")
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(user_id=None, email="test@example.com", password="securepass123"):
    """Build a fake user dict matching the DB row shape."""
    uid = uuid.UUID(user_id) if user_id else uuid.uuid4()
    return {
        "id": uid,
        "email": email,
        "password_hash": _hash_password(password),
        "full_name": None,
        "avatar_url": None,
        "is_admin": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


# ---------------------------------------------------------------------------
# Property 1: Registration then login round-trip
# ---------------------------------------------------------------------------


class TestRegistrationLoginRoundTrip:
    """Property 1: Registration then login round-trip.

    **Validates: Requirements 1.1, 2.1**

    For any valid email and password (>= 8 chars, valid email format),
    registering a new user and then logging in with the same credentials
    should return a valid Access_Token and Refresh_Token pair, and the
    decoded Access_Token should contain the correct user ID and email claims.
    """

    @given(email=valid_emails, password=valid_passwords)
    @settings(max_examples=5, deadline=None)
    def test_register_then_login_returns_valid_tokens(self, email, password):
        client = _create_test_client()
        user_id = uuid.uuid4()

        # Track the bcrypt hash created during registration so login
        # can verify against it. Bcrypt is intentionally slow, so the
        # real hashing happens inside the router — we just capture it.
        captured_hash = {}

        async def fake_create_web_user(pool, em, pw_hash):
            captured_hash["hash"] = pw_hash
            return {
                "id": user_id, "email": em, "password_hash": pw_hash,
                "full_name": None, "avatar_url": None, "is_admin": False,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }

        call_count = {"n": 0}

        async def fake_get_by_email(pool, em):
            """First call (register duplicate check) returns None,
            subsequent calls (login) return the created user."""
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None
            return {
                "id": user_id, "email": em,
                "password_hash": captured_hash["hash"],
                "full_name": None, "avatar_url": None, "is_admin": False,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }

        with (
            patch("auth_router.get_pool", new_callable=AsyncMock) as mock_pool,
            patch("auth_router.get_web_user_by_email", side_effect=fake_get_by_email),
            patch("auth_router.create_web_user", side_effect=fake_create_web_user),
            patch("auth_router.store_refresh_token", new_callable=AsyncMock) as mock_store_rt,
            patch("auth_router.check_rate_limit", return_value=False),
            patch("auth_router.reset_attempts"),
        ):
            mock_pool.return_value = AsyncMock()
            mock_store_rt.return_value = {"id": uuid.uuid4()}

            # --- Register ---
            reg_resp = client.post(
                "/api/auth/register",
                json={"email": email, "password": password},
            )
            assert reg_resp.status_code == 200, f"Register failed: {reg_resp.text}"
            reg_data = reg_resp.json()
            assert "access_token" in reg_data
            assert reg_data["user"]["email"] == email

            reg_claims = decode_access_token(reg_data["access_token"])
            assert reg_claims is not None
            assert reg_claims["email"] == email
            assert reg_claims["sub"] == str(user_id)
            assert "refresh_token" in reg_resp.cookies

            # --- Login ---
            login_resp = client.post(
                "/api/auth/login",
                json={"email": email, "password": password},
            )
            assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
            login_data = login_resp.json()
            assert "access_token" in login_data
            assert login_data["user"]["email"] == email

            login_claims = decode_access_token(login_data["access_token"])
            assert login_claims is not None
            assert login_claims["email"] == email
            assert login_claims["sub"] == str(user_id)
            assert "refresh_token" in login_resp.cookies



# ---------------------------------------------------------------------------
# Property 2: Invalid registration input rejection
# ---------------------------------------------------------------------------


class TestInvalidRegistrationRejection:
    """Property 2: Invalid registration input rejection.

    **Validates: Requirements 1.3, 1.4**

    For any registration request where the password is shorter than 8
    characters OR the email is not a valid email format, the Auth_Service
    should reject the request with a 422 status code and the web_users
    table should remain unchanged.
    """

    @given(password=short_passwords)
    @settings(max_examples=10, deadline=None)
    def test_short_password_rejected_with_422(self, password):
        """Any password < 8 chars should be rejected with 422."""
        client = _create_test_client()
        with patch("auth_router.create_web_user", new_callable=AsyncMock) as mock_create:
            resp = client.post(
                "/api/auth/register",
                json={"email": "valid@example.com", "password": password},
            )
            assert resp.status_code == 422
            mock_create.assert_not_called()

    @given(email=invalid_emails)
    @settings(max_examples=10, deadline=None)
    def test_invalid_email_rejected_with_422(self, email):
        """Any invalid email format should be rejected with 422."""
        client = _create_test_client()
        with patch("auth_router.create_web_user", new_callable=AsyncMock) as mock_create:
            resp = client.post(
                "/api/auth/register",
                json={"email": email, "password": "validpassword123"},
            )
            assert resp.status_code == 422
            mock_create.assert_not_called()

    @given(email=invalid_emails, password=short_passwords)
    @settings(max_examples=10, deadline=None)
    def test_both_invalid_rejected_with_422(self, email, password):
        """When both email and password are invalid, still 422."""
        client = _create_test_client()
        with patch("auth_router.create_web_user", new_callable=AsyncMock) as mock_create:
            resp = client.post(
                "/api/auth/register",
                json={"email": email, "password": password},
            )
            assert resp.status_code == 422
            mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# Property 3: Login error response consistency
# ---------------------------------------------------------------------------


class TestLoginErrorResponseConsistency:
    """Property 3: Login error response consistency.

    **Validates: Requirements 2.2, 2.3**

    For any email that does not exist in the database and any email that
    does exist but is paired with an incorrect password, the Auth_Service
    should return identical 401 response shapes (same status code, same
    response body structure) so that an attacker cannot distinguish
    between the two cases.
    """

    # Pre-compute bcrypt hash once to avoid per-example overhead.
    _REAL_PASSWORD = "correctpassword99"
    _PRECOMPUTED_HASH = _hash_password(_REAL_PASSWORD)

    @given(email=valid_emails, wrong_password=any_passwords)
    @settings(max_examples=5, deadline=None)
    def test_nonexistent_vs_wrong_password_identical_response(
        self, email, wrong_password
    ):
        assume(wrong_password != self._REAL_PASSWORD)

        client = _create_test_client()
        existing_user = {
            "id": uuid.uuid4(), "email": email,
            "password_hash": self._PRECOMPUTED_HASH,
            "full_name": None, "avatar_url": None, "is_admin": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        with (
            patch("auth_router.get_pool", new_callable=AsyncMock) as mock_pool,
            patch("auth_router.check_rate_limit", return_value=False),
            patch("auth_router.record_failed_attempt"),
        ):
            mock_pool.return_value = AsyncMock()

            # Case 1: Non-existent email
            with patch(
                "auth_router.get_web_user_by_email",
                new_callable=AsyncMock,
                return_value=None,
            ):
                resp_nonexistent = client.post(
                    "/api/auth/login",
                    json={"email": email, "password": wrong_password},
                )

            # Case 2: Existing email, wrong password
            with patch(
                "auth_router.get_web_user_by_email",
                new_callable=AsyncMock,
                return_value=existing_user,
            ):
                resp_wrong_pw = client.post(
                    "/api/auth/login",
                    json={"email": email, "password": wrong_password},
                )

            # Both must return 401
            assert resp_nonexistent.status_code == 401
            assert resp_wrong_pw.status_code == 401

            # Response bodies must have identical structure and content
            body_nonexistent = resp_nonexistent.json()
            body_wrong_pw = resp_wrong_pw.json()

            assert set(body_nonexistent.keys()) == set(body_wrong_pw.keys()), (
                f"Keys differ: {body_nonexistent.keys()} vs {body_wrong_pw.keys()}"
            )
            assert body_nonexistent["detail"] == body_wrong_pw["detail"], (
                f"Details differ: {body_nonexistent['detail']!r} vs {body_wrong_pw['detail']!r}"
            )


# ---------------------------------------------------------------------------
# Helpers for Properties 5 & 6 — avoid bcrypt per hypothesis example
# ---------------------------------------------------------------------------


def _make_user_row(user_id, email):
    """Build a fake user row without bcrypt (no password needed for refresh/logout)."""
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


def _seed_refresh_token(stored_tokens, user_id):
    """Create a raw refresh token, store its hash in the fake DB, return the raw value."""
    import hashlib as _hl
    import secrets as _sec
    from datetime import timedelta as _td

    raw = _sec.token_urlsafe(48)
    hashed = _hl.sha256(raw.encode()).hexdigest()
    stored_tokens[hashed] = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "token_hash": hashed,
        "expires_at": datetime.now(timezone.utc) + _td(days=7),
        "created_at": datetime.now(timezone.utc),
    }
    return raw


def _build_refresh_mocks(stored_tokens, user_id, user_row):
    """Return a dict of side_effect callables for refresh-token DB operations."""

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

    async def delete_all(pool, uid):
        to_remove = [
            h for h, row in stored_tokens.items()
            if str(row["user_id"]) == str(uid)
        ]
        for h in to_remove:
            del stored_tokens[h]

    async def get_user_by_id(pool, uid):
        return user_row if str(uid) == str(user_id) else None

    return {
        "store": store,
        "get": get,
        "delete_one": delete_one,
        "delete_all": delete_all,
        "get_user_by_id": get_user_by_id,
    }


# ---------------------------------------------------------------------------
# Property 5: Refresh token rotation
# ---------------------------------------------------------------------------


class TestRefreshTokenRotation:
    """Property 5: Refresh token rotation.

    **Validates: Requirements 3.3**

    For any valid Refresh_Token, presenting it to the refresh endpoint
    should return a new Access_Token and a new Refresh_Token, and the
    old Refresh_Token should no longer be accepted by the refresh endpoint.
    """

    @given(email=valid_emails)
    @settings(max_examples=10, deadline=None)
    def test_refresh_rotates_token_and_old_is_rejected(self, email):
        # Feature: frontend-supabase-removal, Property 5: Refresh token rotation
        client = _create_test_client()
        user_id = uuid.uuid4()
        user_row = _make_user_row(user_id, email)
        stored_tokens = {}
        mocks = _build_refresh_mocks(stored_tokens, user_id, user_row)

        # Seed an initial refresh token and set it as a cookie
        initial_raw = _seed_refresh_token(stored_tokens, user_id)

        with (
            patch("auth_router.get_pool", new_callable=AsyncMock) as mock_pool,
            patch("auth_router.store_refresh_token", side_effect=mocks["store"]),
            patch("auth_router.get_refresh_token", side_effect=mocks["get"]),
            patch("auth_router.delete_refresh_token", side_effect=mocks["delete_one"]),
            patch("auth_router.get_web_user_by_id", side_effect=mocks["get_user_by_id"]),
        ):
            mock_pool.return_value = AsyncMock()

            # Use direct assignment — TestClient.cookies.set() with domain
            # silently drops cookies, but direct dict-style assignment works.
            client.cookies["refresh_token"] = initial_raw
            old_raw = initial_raw

            # Step 1: Refresh — should succeed and rotate
            resp1 = client.post("/api/auth/refresh")
            assert resp1.status_code == 200, f"Refresh failed: {resp1.text}"
            claims1 = decode_access_token(resp1.json()["access_token"])
            assert claims1 is not None
            assert claims1["sub"] == str(user_id)
            assert claims1["email"] == email
            assert len(stored_tokens) == 1, "Rotation should keep exactly 1 token"

            # Step 2: Old raw token hash should no longer be in the store
            import hashlib as _hl
            old_hash = _hl.sha256(old_raw.encode()).hexdigest()
            assert old_hash not in stored_tokens, "Old token hash must be deleted"

            # Step 3: Replay the old cookie — should be rejected
            client.cookies["refresh_token"] = old_raw
            resp_old = client.post("/api/auth/refresh")
            assert resp_old.status_code == 401, "Old refresh token must be rejected"

            # Step 4: Use the new cookie from the rotation — should still work
            new_raw = resp1.cookies.get("refresh_token")
            assert new_raw is not None, "Refresh response must set a new cookie"
            client.cookies["refresh_token"] = new_raw
            resp2 = client.post("/api/auth/refresh")
            assert resp2.status_code == 200
            claims2 = decode_access_token(resp2.json()["access_token"])
            assert claims2 is not None
            assert claims2["sub"] == str(user_id)


# ---------------------------------------------------------------------------
# Property 6: Logout invalidates all refresh tokens
# ---------------------------------------------------------------------------


class TestLogoutInvalidatesAllRefreshTokens:
    """Property 6: Logout invalidates all refresh tokens.

    **Validates: Requirements 3.5**

    For any user with one or more active Refresh_Tokens, calling the
    logout endpoint should result in all of that user's Refresh_Tokens
    being rejected by the refresh endpoint.
    """

    @given(
        email=valid_emails,
        num_extra_tokens=st.integers(min_value=0, max_value=4),
    )
    @settings(max_examples=10, deadline=None)
    def test_logout_invalidates_all_tokens_for_user(
        self, email, num_extra_tokens
    ):
        # Feature: frontend-supabase-removal, Property 6: Logout invalidates all refresh tokens
        client = _create_test_client()
        user_id = uuid.uuid4()
        user_row = _make_user_row(user_id, email)
        stored_tokens = {}
        mocks = _build_refresh_mocks(stored_tokens, user_id, user_row)

        # Seed the primary refresh token (the one in the cookie)
        primary_raw = _seed_refresh_token(stored_tokens, user_id)

        # Seed extra tokens simulating other devices/sessions
        for _ in range(num_extra_tokens):
            _seed_refresh_token(stored_tokens, user_id)

        total_before = len(stored_tokens)
        assert total_before == 1 + num_extra_tokens

        # Create a valid access token for the Authorization header
        access_token = create_access_token(str(user_id), email)

        with (
            patch("auth_router.get_pool", new_callable=AsyncMock) as mock_pool,
            patch("auth_router.store_refresh_token", side_effect=mocks["store"]),
            patch("auth_router.get_refresh_token", side_effect=mocks["get"]),
            patch("auth_router.delete_refresh_token", side_effect=mocks["delete_one"]),
            patch("auth_router.delete_all_refresh_tokens", side_effect=mocks["delete_all"]),
            patch("auth_router.get_web_user_by_id", side_effect=mocks["get_user_by_id"]),
        ):
            mock_pool.return_value = AsyncMock()

            # Step 1: Logout with the access token
            logout_resp = client.post(
                "/api/auth/logout",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert logout_resp.status_code == 200

            # Step 2: ALL refresh tokens for this user should be gone
            assert len(stored_tokens) == 0, (
                f"Expected 0 tokens after logout, found {len(stored_tokens)}"
            )

            # Step 3: Attempting to refresh with the primary cookie should fail
            client.cookies["refresh_token"] = primary_raw
            refresh_resp = client.post("/api/auth/refresh")
            assert refresh_resp.status_code == 401
