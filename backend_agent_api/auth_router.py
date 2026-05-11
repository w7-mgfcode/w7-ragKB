"""Authentication router for the web frontend.

Provides endpoints for registration, login, token refresh, logout,
password reset, Google OAuth, and user profile management.
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from auth_middleware import get_current_user
from db import get_pool
from db_web_users import (
    create_or_update_google_user,
    create_web_user,
    delete_all_refresh_tokens,
    delete_refresh_token,
    get_refresh_token,
    get_reset_token,
    get_web_user_by_email,
    get_web_user_by_id,
    mark_reset_token_used,
    store_refresh_token,
    store_reset_token,
    update_web_user_password,
    update_web_user_profile,
)
from rate_limiter import check_rate_limit, record_failed_attempt, reset_attempts
from token_manager import (
    REFRESH_TOKEN_EXPIRY,
    create_access_token,
    generate_refresh_token,
)

logger = logging.getLogger(__name__)

router = APIRouter()

RESET_TOKEN_EXPIRY = timedelta(hours=1)


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable with a safe default."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Cookie settings
COOKIE_NAME = "refresh_token"
COOKIE_PATH = "/api/auth"
COOKIE_HTTPONLY = True
COOKIE_SECURE = _env_bool("COOKIE_SECURE", True)
COOKIE_SAMESITE = "lax"

# Google OAuth settings
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"



# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    user: "UserResponse"


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    avatar_url: str | None
    is_admin: bool


class ResetPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    avatar_url: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _build_user_response(user: dict) -> UserResponse:
    """Convert a db user row dict to a UserResponse."""
    return UserResponse(
        id=str(user["id"]),
        email=user["email"],
        full_name=user.get("full_name"),
        avatar_url=user.get("avatar_url"),
        is_admin=user.get("is_admin", False),
    )


async def _issue_tokens_and_set_cookie(
    response: Response,
    user: dict,
) -> AuthResponse:
    """Create access + refresh tokens, store refresh in DB, set cookie."""
    pool = await get_pool()
    user_id = str(user["id"])

    access_token = create_access_token(user_id, user["email"])
    raw_refresh, refresh_hash = generate_refresh_token()
    expires_at = datetime.now(timezone.utc) + REFRESH_TOKEN_EXPIRY

    await store_refresh_token(pool, user_id, refresh_hash, expires_at)

    response.set_cookie(
        key=COOKIE_NAME,
        value=raw_refresh,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=int(REFRESH_TOKEN_EXPIRY.total_seconds()),
    )

    return AuthResponse(
        access_token=access_token,
        user=_build_user_response(user),
    )


def _hash_token(raw_token: str) -> str:
    """SHA-256 hash a raw token string for DB lookup."""
    return hashlib.sha256(raw_token.encode()).hexdigest()



# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=AuthResponse)
async def register(body: RegisterRequest, response: Response):
    """Create a new user account and issue tokens."""
    pool = await get_pool()

    existing = await get_web_user_by_email(pool, body.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = _hash_password(body.password)
    user = await create_web_user(pool, body.email, password_hash)

    return await _issue_tokens_and_set_cookie(response, user)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, response: Response):
    """Authenticate with email/password and issue tokens."""
    if check_rate_limit(body.email):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again later.",
        )

    pool = await get_pool()
    user = await get_web_user_by_email(pool, body.email)

    if not user or not user.get("password_hash"):
        record_failed_attempt(body.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not _verify_password(body.password, user["password_hash"]):
        record_failed_attempt(body.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    reset_attempts(body.email)
    return await _issue_tokens_and_set_cookie(response, user)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(request: Request, response: Response):
    """Rotate refresh token and issue a new access token."""
    raw_token = request.cookies.get(COOKIE_NAME)
    if not raw_token:
        raise HTTPException(
            status_code=401, detail="Invalid or expired refresh token"
        )

    token_hash = _hash_token(raw_token)
    pool = await get_pool()
    stored = await get_refresh_token(pool, token_hash)

    if not stored:
        raise HTTPException(
            status_code=401, detail="Invalid or expired refresh token"
        )

    if stored["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        await delete_refresh_token(pool, token_hash)
        raise HTTPException(
            status_code=401, detail="Invalid or expired refresh token"
        )

    # Invalidate old token before issuing new one (rotation)
    await delete_refresh_token(pool, token_hash)

    user = await get_web_user_by_id(pool, str(stored["user_id"]))
    if not user:
        raise HTTPException(
            status_code=401, detail="Invalid or expired refresh token"
        )

    return await _issue_tokens_and_set_cookie(response, user)


@router.post("/logout")
async def logout(
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    """Invalidate all refresh tokens for the user and clear the cookie."""
    pool = await get_pool()
    await delete_all_refresh_tokens(pool, current_user["sub"])

    response.delete_cookie(
        key=COOKIE_NAME,
        path=COOKIE_PATH,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
    )
    return {"detail": "Logged out"}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest):
    """Request a password reset token.

    Returns the same response whether the email is registered or not
    to prevent email enumeration.
    """
    pool = await get_pool()
    user = await get_web_user_by_email(pool, body.email)

    if user:
        raw_token = secrets.token_urlsafe(48)
        token_hash = _hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + RESET_TOKEN_EXPIRY
        await store_reset_token(pool, str(user["id"]), token_hash, expires_at)
        # In production, send raw_token via email.
        # For now, log it (never expose in response).
        logger.info("Password reset token generated for user %s", user["id"])

    return {"detail": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password/confirm")
async def reset_password_confirm(body: ResetPasswordConfirm):
    """Validate reset token, update password, invalidate refresh tokens."""
    token_hash = _hash_token(body.token)
    pool = await get_pool()
    stored = await get_reset_token(pool, token_hash)

    if not stored or stored.get("used"):
        raise HTTPException(
            status_code=400, detail="Invalid or expired reset token"
        )

    if stored["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400, detail="Invalid or expired reset token"
        )

    user_id = str(stored["user_id"])
    new_hash = _hash_password(body.new_password)

    await update_web_user_password(pool, user_id, new_hash)
    await mark_reset_token_used(pool, str(stored["id"]))
    await delete_all_refresh_tokens(pool, user_id)

    return {"detail": "Password has been reset."}



@router.get("/google")
async def google_oauth_redirect(request: Request):
    """Redirect to Google OAuth consent screen."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    # Build callback URL from the incoming request
    callback_url = str(request.url_for("google_oauth_callback"))

    state = secrets.token_urlsafe(32)

    params = {
        "client_id": client_id,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{query}")


@router.get("/google/callback")
async def google_oauth_callback(
    request: Request,
    response: Response,
    code: str | None = None,
    error: str | None = None,
):
    """Exchange Google auth code for user info, issue tokens, redirect."""
    frontend_url = os.getenv("FRONTEND_URL", "")

    if error or not code:
        logger.warning("Google OAuth error: %s", error)
        return RedirectResponse(
            url=f"{frontend_url}/auth/callback?error=OAuth+authentication+failed"
        )

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    callback_url = str(request.url_for("google_oauth_callback"))

    try:
        async with httpx.AsyncClient() as client:
            # Exchange code for tokens
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": callback_url,
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                logger.error("Google token exchange failed: %s", token_resp.text)
                return RedirectResponse(
                    url=f"{frontend_url}/auth/callback?error=OAuth+authentication+failed"
                )

            google_tokens = token_resp.json()
            google_access_token = google_tokens["access_token"]

            # Fetch user info
            userinfo_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {google_access_token}"},
            )
            if userinfo_resp.status_code != 200:
                logger.error("Google userinfo fetch failed: %s", userinfo_resp.text)
                return RedirectResponse(
                    url=f"{frontend_url}/auth/callback?error=OAuth+authentication+failed"
                )

            userinfo = userinfo_resp.json()

    except Exception:
        logger.exception("Google OAuth exchange failed")
        return RedirectResponse(
            url=f"{frontend_url}/auth/callback?error=OAuth+authentication+failed"
        )

    email = userinfo.get("email")
    if not email:
        return RedirectResponse(
            url=f"{frontend_url}/auth/callback?error=OAuth+authentication+failed"
        )

    pool = await get_pool()
    user = await create_or_update_google_user(
        pool,
        email=email,
        full_name=userinfo.get("name"),
        avatar_url=userinfo.get("picture"),
    )

    # Issue our own tokens
    user_id = str(user["id"])
    access_token = create_access_token(user_id, email)
    raw_refresh, refresh_hash = generate_refresh_token()
    expires_at = datetime.now(timezone.utc) + REFRESH_TOKEN_EXPIRY
    await store_refresh_token(pool, user_id, refresh_hash, expires_at)

    redirect = RedirectResponse(
        url=f"{frontend_url}/auth/callback?access_token={access_token}"
    )
    redirect.set_cookie(
        key=COOKIE_NAME,
        value=raw_refresh,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
        max_age=int(REFRESH_TOKEN_EXPIRY.total_seconds()),
    )
    return redirect


@router.get("/me", response_model=UserResponse)
async def get_profile(current_user: dict = Depends(get_current_user)):
    """Return the current user's profile."""
    pool = await get_pool()
    user = await get_web_user_by_id(pool, current_user["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return _build_user_response(user)


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    body: ProfileUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update the current user's profile fields."""
    pool = await get_pool()
    user = await update_web_user_profile(
        pool,
        current_user["sub"],
        body.full_name,
        body.avatar_url,
    )
    return _build_user_response(user)
