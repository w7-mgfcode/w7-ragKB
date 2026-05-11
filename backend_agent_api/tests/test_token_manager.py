"""Unit tests for token_manager module."""

import hashlib
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest


# Set JWT_SECRET_KEY before importing token_manager
@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")
    # Reload the module-level constant after setting env
    import token_manager

    monkeypatch.setattr(token_manager, "JWT_SECRET", "test-secret-key-for-unit-tests")


class TestCreateAccessToken:
    def test_returns_string(self):
        from token_manager import create_access_token

        token = create_access_token("user-123", "user@example.com")
        assert isinstance(token, str)

    def test_contains_correct_claims(self):
        from token_manager import create_access_token

        token = create_access_token("user-123", "user@example.com")
        payload = jwt.decode(
            token, "test-secret-key-for-unit-tests", algorithms=["HS256"]
        )
        assert payload["sub"] == "user-123"
        assert payload["email"] == "user@example.com"
        assert "exp" in payload
        assert "iat" in payload

    def test_expiry_is_15_minutes(self):
        from token_manager import create_access_token

        before = datetime.now(timezone.utc)
        token = create_access_token("user-123", "user@example.com")
        after = datetime.now(timezone.utc)

        payload = jwt.decode(
            token, "test-secret-key-for-unit-tests", algorithms=["HS256"]
        )
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)

        # exp should be ~15 minutes after iat
        delta = exp - iat
        assert timedelta(minutes=14, seconds=59) <= delta <= timedelta(
            minutes=15, seconds=1
        )


class TestDecodeAccessToken:
    def test_decodes_valid_token(self):
        from token_manager import create_access_token, decode_access_token

        token = create_access_token("user-456", "test@example.com")
        claims = decode_access_token(token)
        assert claims is not None
        assert claims["sub"] == "user-456"
        assert claims["email"] == "test@example.com"

    def test_returns_none_for_expired_token(self):
        from token_manager import JWT_ALGORITHM, decode_access_token

        payload = {
            "sub": "user-789",
            "email": "expired@example.com",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            "iat": datetime.now(timezone.utc) - timedelta(minutes=16),
        }
        token = jwt.encode(
            payload, "test-secret-key-for-unit-tests", algorithm=JWT_ALGORITHM
        )
        assert decode_access_token(token) is None

    def test_returns_none_for_malformed_token(self):
        from token_manager import decode_access_token

        assert decode_access_token("not-a-valid-jwt") is None

    def test_returns_none_for_wrong_secret(self):
        from token_manager import decode_access_token

        payload = {
            "sub": "user-000",
            "email": "wrong@example.com",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
            "iat": datetime.now(timezone.utc),
        }
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        assert decode_access_token(token) is None

    def test_returns_none_for_empty_string(self):
        from token_manager import decode_access_token

        assert decode_access_token("") is None


class TestGenerateRefreshToken:
    def test_returns_tuple_of_two_strings(self):
        from token_manager import generate_refresh_token

        raw, hashed = generate_refresh_token()
        assert isinstance(raw, str)
        assert isinstance(hashed, str)

    def test_hash_matches_raw_token(self):
        from token_manager import generate_refresh_token

        raw, hashed = generate_refresh_token()
        expected_hash = hashlib.sha256(raw.encode()).hexdigest()
        assert hashed == expected_hash

    def test_generates_unique_tokens(self):
        from token_manager import generate_refresh_token

        tokens = {generate_refresh_token()[0] for _ in range(50)}
        assert len(tokens) == 50

    def test_raw_token_has_sufficient_length(self):
        from token_manager import generate_refresh_token

        raw, _ = generate_refresh_token()
        # token_urlsafe(48) produces a 64-char base64url string
        assert len(raw) >= 48

    def test_hash_is_valid_sha256_hex(self):
        from token_manager import generate_refresh_token

        _, hashed = generate_refresh_token()
        assert len(hashed) == 64
        int(hashed, 16)  # raises ValueError if not valid hex
