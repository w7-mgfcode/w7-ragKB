"""Property-based tests for token_manager module.

# Feature: frontend-supabase-removal, Property 4: Token issuance correctness

**Validates: Requirements 3.1, 3.2**

Property 4: For any user ID and email, the issued Access_Token should decode
to a JWT containing `sub` equal to the user ID, `email` equal to the email,
and an `exp` claim 15 minutes in the future. The associated Refresh_Token hash
should be the SHA-256 of the raw token, and REFRESH_TOKEN_EXPIRY should be 7
days (used when storing in the refresh_tokens table).
"""

import hashlib
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies: user IDs and email addresses
# ---------------------------------------------------------------------------

# User IDs are UUID-like strings
user_ids = st.uuids().map(str)

# Email local parts: alphanumeric + dots/underscores, 1-30 chars
email_local = st.from_regex(r"[a-z][a-z0-9._]{0,29}", fullmatch=True)
email_domain = st.from_regex(r"[a-z]{2,10}\.[a-z]{2,5}", fullmatch=True)
emails = st.builds(lambda local, domain: f"{local}@{domain}", email_local, email_domain)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def set_jwt_secret(monkeypatch):
    """Set JWT_SECRET_KEY and patch the module-level constant."""
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-pbt")
    import token_manager
    monkeypatch.setattr(token_manager, "JWT_SECRET", "test-secret-key-for-pbt")


# ---------------------------------------------------------------------------
# Property 4: Token issuance correctness
# ---------------------------------------------------------------------------

class TestTokenIssuanceCorrectness:
    """Property 4: Token issuance correctness.

    **Validates: Requirements 3.1, 3.2**
    """

    @given(user_id=user_ids, email=emails)
    @settings(max_examples=25, deadline=None)
    def test_access_token_contains_correct_claims(self, user_id: str, email: str):
        """For any user_id and email, the access token decodes to a JWT
        with sub == user_id, email == email, and exp ~15 minutes from now."""
        from token_manager import create_access_token, JWT_ALGORITHM

        before = datetime.now(timezone.utc)
        token = create_access_token(user_id, email)
        after = datetime.now(timezone.utc)

        payload = jwt.decode(
            token, "test-secret-key-for-pbt", algorithms=[JWT_ALGORITHM]
        )

        # sub and email claims match inputs
        assert payload["sub"] == user_id
        assert payload["email"] == email

        # exp is ~15 minutes in the future
        exp_dt = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        expected_min = before + timedelta(minutes=15)
        expected_max = after + timedelta(minutes=15)
        assert expected_min - timedelta(seconds=1) <= exp_dt <= expected_max + timedelta(seconds=1)

        # iat is present and reasonable
        iat_dt = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        assert before - timedelta(seconds=1) <= iat_dt <= after + timedelta(seconds=1)

    @given(user_id=user_ids, email=emails)
    @settings(max_examples=25, deadline=None)
    def test_access_token_round_trips_through_decode(self, user_id: str, email: str):
        """For any user_id and email, create_access_token followed by
        decode_access_token returns the original claims."""
        from token_manager import create_access_token, decode_access_token

        token = create_access_token(user_id, email)
        claims = decode_access_token(token)

        assert claims is not None
        assert claims["sub"] == user_id
        assert claims["email"] == email

    @given(data=st.data())
    @settings(max_examples=25, deadline=None)
    def test_refresh_token_hash_matches_raw(self, data):
        """For any generated refresh token, the hash is the SHA-256
        hex digest of the raw token string."""
        from token_manager import generate_refresh_token

        raw, hashed = generate_refresh_token()
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert hashed == expected

    def test_refresh_token_expiry_is_7_days(self):
        """REFRESH_TOKEN_EXPIRY is 7 days, matching Requirement 3.2."""
        from token_manager import REFRESH_TOKEN_EXPIRY

        assert REFRESH_TOKEN_EXPIRY == timedelta(days=7)

    def test_access_token_expiry_is_15_minutes(self):
        """ACCESS_TOKEN_EXPIRY is 15 minutes, matching Requirement 3.1."""
        from token_manager import ACCESS_TOKEN_EXPIRY

        assert ACCESS_TOKEN_EXPIRY == timedelta(minutes=15)
