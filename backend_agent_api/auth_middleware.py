"""FastAPI dependency for JWT authentication.

Extracts and validates Bearer tokens from the Authorization header,
returning decoded user claims or raising HTTP 401.
"""

from fastapi import HTTPException, Request

from token_manager import decode_access_token


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency that validates the JWT Bearer token.

    Extracts the token from the Authorization header, decodes it,
    and returns the user claims dict containing sub, email, exp, iat.

    Args:
        request: The incoming FastAPI request.

    Returns:
        Decoded JWT claims dict with user_id (sub) and email.

    Raises:
        HTTPException: 401 if the token is missing, malformed,
            invalid, or expired.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = auth_header.split(" ", 1)[1]
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload
