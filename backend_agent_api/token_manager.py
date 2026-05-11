"""JWT access token and refresh token management.

Handles creation and validation of short-lived JWT access tokens (15-min expiry)
and generation of opaque refresh tokens stored as SHA-256 hashes.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt

JWT_SECRET = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRY = timedelta(minutes=15)
REFRESH_TOKEN_EXPIRY = timedelta(days=7)


def create_access_token(user_id: str, email: str) -> str:
    """Create a signed JWT access token with 15-minute expiry.

    Args:
        user_id: The user's UUID as a string.
        email: The user's email address.

    Returns:
        An encoded JWT string containing sub, email, exp, and iat claims.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": now + ACCESS_TOKEN_EXPIRY,
        "iat": now,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT access token.

    Args:
        token: The encoded JWT string.

    Returns:
        The decoded claims dict if valid, or None if the token is
        expired, malformed, or otherwise invalid.
    """
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None


def generate_refresh_token() -> tuple[str, str]:
    """Generate a cryptographically secure refresh token.

    Returns:
        A (raw_token, token_hash) tuple where raw_token is the opaque
        string sent to the client and token_hash is the SHA-256 hex
        digest stored in the database.
    """
    raw = secrets.token_urlsafe(48)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed
