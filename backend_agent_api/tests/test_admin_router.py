"""Unit tests for admin_router module.

Uses FastAPI TestClient with mocked DB and auth dependency.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth_middleware import get_current_user
from admin_router import router


USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _build_app(user_claims: dict) -> FastAPI:
    """Create a FastAPI app with the admin router and overridden auth."""
    app = FastAPI()
    app.include_router(router)

    async def _override_auth():
        return user_claims

    app.dependency_overrides[get_current_user] = _override_auth
    return app


class TestGetAdminStatus:
    """Tests for GET /status."""

    @pytest.mark.asyncio
    async def test_returns_true_for_admin_user(self):
        app = _build_app({"sub": USER_ID, "email": "admin@test.com"})
        client = TestClient(app)

        mock_pool = AsyncMock()

        with patch("admin_router.get_web_user_by_id", new_callable=AsyncMock) as mock_get_user, \
             patch("admin_router.get_pool", return_value=mock_pool):
            mock_get_user.return_value = {
                "id": USER_ID,
                "email": "admin@test.com",
                "is_admin": True,
            }
            resp = client.get("/status")

        assert resp.status_code == 200
        assert resp.json() == {"is_admin": True}

    @pytest.mark.asyncio
    async def test_returns_false_for_non_admin_user(self):
        app = _build_app({"sub": USER_ID, "email": "user@test.com"})
        client = TestClient(app)

        mock_pool = AsyncMock()

        with patch("admin_router.get_web_user_by_id", new_callable=AsyncMock) as mock_get_user, \
             patch("admin_router.get_pool", return_value=mock_pool):
            mock_get_user.return_value = {
                "id": USER_ID,
                "email": "user@test.com",
                "is_admin": False,
            }
            resp = client.get("/status")

        assert resp.status_code == 200
        assert resp.json() == {"is_admin": False}

    @pytest.mark.asyncio
    async def test_returns_403_when_user_not_found(self):
        app = _build_app({"sub": USER_ID, "email": "ghost@test.com"})
        client = TestClient(app)

        mock_pool = AsyncMock()

        with patch("admin_router.get_web_user_by_id", new_callable=AsyncMock) as mock_get_user, \
             patch("admin_router.get_pool", return_value=mock_pool):
            mock_get_user.return_value = None
            resp = client.get("/status")

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Forbidden"
