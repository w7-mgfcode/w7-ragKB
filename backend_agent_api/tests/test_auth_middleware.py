"""Unit tests for auth_middleware module."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.datastructures import Headers


def _make_request(headers: dict | None = None) -> Request:
    """Build a minimal Starlette Request with the given headers."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (k.lower().encode(), v.encode())
            for k, v in (headers or {}).items()
        ],
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    """Ensure token_manager has a deterministic secret for all tests."""
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")
    import token_manager
    monkeypatch.setattr(token_manager, "JWT_SECRET", "test-secret-key-for-unit-tests")


class TestGetCurrentUserValidToken:
    @pytest.mark.asyncio
    async def test_returns_claims_for_valid_token(self):
        from token_manager import create_access_token
        from auth_middleware import get_current_user

        token = create_access_token("user-abc", "alice@example.com")
        request = _make_request({"Authorization": f"Bearer {token}"})

        claims = await get_current_user(request)

        assert claims["sub"] == "user-abc"
        assert claims["email"] == "alice@example.com"


class TestGetCurrentUserMissingHeader:
    @pytest.mark.asyncio
    async def test_raises_401_when_no_authorization_header(self):
        from auth_middleware import get_current_user

        request = _make_request()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Missing or invalid token"

    @pytest.mark.asyncio
    async def test_raises_401_when_header_is_empty(self):
        from auth_middleware import get_current_user

        request = _make_request({"Authorization": ""})

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Missing or invalid token"


class TestGetCurrentUserMalformedHeader:
    @pytest.mark.asyncio
    async def test_raises_401_when_no_bearer_prefix(self):
        from auth_middleware import get_current_user

        request = _make_request({"Authorization": "Token some-value"})

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Missing or invalid token"

    @pytest.mark.asyncio
    async def test_raises_401_when_bearer_lowercase(self):
        from auth_middleware import get_current_user

        token = "some-token"
        request = _make_request({"Authorization": f"bearer {token}"})

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Missing or invalid token"


class TestGetCurrentUserInvalidToken:
    @pytest.mark.asyncio
    async def test_raises_401_for_garbage_token(self):
        from auth_middleware import get_current_user

        request = _make_request({"Authorization": "Bearer not-a-real-jwt"})

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid or expired token"

    @pytest.mark.asyncio
    async def test_raises_401_for_expired_token(self):
        from auth_middleware import get_current_user

        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone

        expired_payload = {
            "sub": "user-expired",
            "email": "expired@example.com",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            "iat": datetime.now(timezone.utc) - timedelta(minutes=16),
        }
        expired_token = pyjwt.encode(
            expired_payload, "test-secret-key-for-unit-tests", algorithm="HS256"
        )
        request = _make_request({"Authorization": f"Bearer {expired_token}"})

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid or expired token"

    @pytest.mark.asyncio
    async def test_raises_401_for_wrong_secret(self):
        from auth_middleware import get_current_user

        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone

        payload = {
            "sub": "user-wrong",
            "email": "wrong@example.com",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
            "iat": datetime.now(timezone.utc),
        }
        token = pyjwt.encode(payload, "different-secret", algorithm="HS256")
        request = _make_request({"Authorization": f"Bearer {token}"})

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid or expired token"
