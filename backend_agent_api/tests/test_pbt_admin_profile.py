"""Property-based tests for admin status and profile update endpoints.

# Feature: frontend-supabase-removal, Property 12: Admin status correctness
# Feature: frontend-supabase-removal, Property 13: Profile update round-trip

Uses hypothesis to generate arbitrary user profiles and profile updates,
verifying correctness properties hold across all generated cases. DB
interactions are mocked via patching get_pool and DB query functions.
"""

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pbt-admin-profile-32bytes!")

from admin_router import router as admin_router
from auth_middleware import get_current_user
from auth_router import router as auth_router

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JWT_SECRET = "test-secret-key-for-pbt-admin-profile-32bytes!"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    """Ensure token_manager uses our test secret."""
    monkeypatch.setenv("JWT_SECRET_KEY", JWT_SECRET)
    import token_manager
    monkeypatch.setattr(token_manager, "JWT_SECRET", JWT_SECRET)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

is_admin_values = st.booleans()

# Printable strings for profile fields, avoiding control characters
profile_names = st.one_of(
    st.none(),
    st.text(
        min_size=1,
        max_size=80,
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    ),
)

avatar_urls = st.one_of(
    st.none(),
    st.from_regex(r"https://[a-z]{3,12}\.[a-z]{2,4}/[a-z0-9]{1,20}", fullmatch=True),
)

_email_local = st.from_regex(r"[a-z][a-z0-9]{0,14}", fullmatch=True)
_email_domain = st.from_regex(r"[a-z]{2,8}\.[a-z]{2,4}", fullmatch=True)
valid_emails = st.builds(lambda l, d: f"{l}@{d}", _email_local, _email_domain)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_admin_app(user_id: str, email: str = "test@example.com") -> TestClient:
    """Create a FastAPI app with admin router and overridden auth."""
    app = FastAPI()
    app.include_router(admin_router)

    async def _override_auth():
        return {"sub": user_id, "email": email}

    app.dependency_overrides[get_current_user] = _override_auth
    return TestClient(app)


def _build_profile_app(user_id: str, email: str = "test@example.com") -> TestClient:
    """Create a FastAPI app with auth router (for /me endpoints) and overridden auth."""
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/auth")

    async def _override_auth():
        return {"sub": user_id, "email": email}

    app.dependency_overrides[get_current_user] = _override_auth
    return TestClient(app)


def _make_user_row(user_id, email, is_admin, full_name=None, avatar_url=None):
    """Build a fake user dict matching the DB row shape."""
    uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    return {
        "id": uid,
        "email": email,
        "password_hash": "hashed",
        "full_name": full_name,
        "avatar_url": avatar_url,
        "is_admin": is_admin,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


# ---------------------------------------------------------------------------
# Property 12: Admin status correctness
# ---------------------------------------------------------------------------


class TestAdminStatusCorrectness:
    """Property 12: Admin status correctness.

    **Validates: Requirements 6.1**

    For any user, the admin status endpoint should return an is_admin
    value that matches the is_admin column in the web_users table for
    that user.
    """

    @given(is_admin=is_admin_values, email=valid_emails)
    @settings(max_examples=25, deadline=None)
    def test_admin_status_matches_db_column(self, is_admin, email):
        # Feature: frontend-supabase-removal, Property 12: Admin status correctness
        user_id = str(uuid.uuid4())
        client = _build_admin_app(user_id, email)

        user_row = _make_user_row(user_id, email, is_admin)
        mock_pool = AsyncMock()

        with (
            patch("admin_router.get_pool", return_value=mock_pool),
            patch(
                "admin_router.get_web_user_by_id",
                new_callable=AsyncMock,
                return_value=user_row,
            ) as mock_get_user,
        ):
            resp = client.get("/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_admin"] is is_admin, (
            f"Expected is_admin={is_admin}, got {data['is_admin']}"
        )

        # Verify the endpoint looked up the correct user
        mock_get_user.assert_called_once()
        call_args = mock_get_user.call_args
        assert call_args[0][1] == user_id


# ---------------------------------------------------------------------------
# Property 13: Profile update round-trip
# ---------------------------------------------------------------------------


class TestProfileUpdateRoundTrip:
    """Property 13: Profile update round-trip.

    **Validates: Requirements 7.1, 7.2**

    For any authenticated user and any valid profile update (full_name,
    avatar_url), updating the profile and then fetching it should return
    the updated values.
    """

    @given(
        email=valid_emails,
        new_full_name=profile_names,
        new_avatar_url=avatar_urls,
    )
    @settings(max_examples=25, deadline=None)
    def test_patch_then_get_returns_updated_values(
        self, email, new_full_name, new_avatar_url
    ):
        # Feature: frontend-supabase-removal, Property 13: Profile update round-trip
        user_id = str(uuid.uuid4())
        client = _build_profile_app(user_id, email)

        # The updated row returned by update_web_user_profile
        updated_row = _make_user_row(
            user_id, email, is_admin=False,
            full_name=new_full_name, avatar_url=new_avatar_url,
        )

        mock_pool = AsyncMock()

        with (
            patch("auth_router.get_pool", return_value=mock_pool),
            patch(
                "auth_router.update_web_user_profile",
                new_callable=AsyncMock,
                return_value=updated_row,
            ) as mock_update,
            patch(
                "auth_router.get_web_user_by_id",
                new_callable=AsyncMock,
                return_value=updated_row,
            ) as mock_get,
        ):
            # Step 1: PATCH /api/auth/me with the new profile values
            patch_body = {}
            if new_full_name is not None:
                patch_body["full_name"] = new_full_name
            if new_avatar_url is not None:
                patch_body["avatar_url"] = new_avatar_url

            patch_resp = client.patch("/api/auth/me", json=patch_body)
            assert patch_resp.status_code == 200, f"PATCH failed: {patch_resp.text}"

            patch_data = patch_resp.json()
            assert patch_data["full_name"] == new_full_name
            assert patch_data["avatar_url"] == new_avatar_url
            assert patch_data["email"] == email

            # Verify update was called with the correct arguments
            mock_update.assert_called_once()
            update_args = mock_update.call_args[0]
            assert update_args[1] == user_id  # user_id
            assert update_args[2] == new_full_name  # full_name
            assert update_args[3] == new_avatar_url  # avatar_url

            # Step 2: GET /api/auth/me should return the same updated values
            get_resp = client.get("/api/auth/me")
            assert get_resp.status_code == 200, f"GET failed: {get_resp.text}"

            get_data = get_resp.json()
            assert get_data["full_name"] == new_full_name
            assert get_data["avatar_url"] == new_avatar_url
            assert get_data["email"] == email
            assert get_data["id"] == user_id

            # The GET endpoint should look up the same user
            mock_get.assert_called_once()
            get_args = mock_get.call_args[0]
            assert get_args[1] == user_id
