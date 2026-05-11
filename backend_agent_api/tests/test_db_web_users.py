"""Unit tests for db_web_users.py — asyncpg web user, refresh token, and reset token operations."""

from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock

from db_web_users import (
    create_web_user,
    get_web_user_by_email,
    get_web_user_by_id,
    update_web_user_profile,
    update_web_user_password,
    store_refresh_token,
    get_refresh_token,
    delete_refresh_token,
    delete_all_refresh_tokens,
    store_reset_token,
    get_reset_token,
    mark_reset_token_used,
    create_or_update_google_user,
)


# ---------------------------------------------------------------------------
# create_web_user
# ---------------------------------------------------------------------------

class TestCreateWebUser:
    @pytest.mark.asyncio
    async def test_returns_dict_from_fetchrow(self):
        fake_row = {
            "id": "uuid-1",
            "email": "alice@example.com",
            "password_hash": "hashed",
            "full_name": None,
            "avatar_url": None,
            "is_admin": False,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
        pool = AsyncMock()
        pool.fetchrow.return_value = fake_row

        result = await create_web_user(pool, "alice@example.com", "hashed")

        assert result["email"] == "alice@example.com"
        assert result["password_hash"] == "hashed"
        assert result["is_admin"] is False

    @pytest.mark.asyncio
    async def test_uses_parameterized_insert(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = {"id": "uuid-1", "email": "a@b.com"}

        await create_web_user(pool, "a@b.com", "hash123")

        query = pool.fetchrow.call_args[0][0]
        assert "INSERT INTO web_users" in query
        assert "$1" in query and "$2" in query
        assert pool.fetchrow.call_args[0][1] == "a@b.com"
        assert pool.fetchrow.call_args[0][2] == "hash123"


# ---------------------------------------------------------------------------
# get_web_user_by_email
# ---------------------------------------------------------------------------

class TestGetWebUserByEmail:
    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self):
        fake_row = {"id": "uuid-1", "email": "alice@example.com"}
        pool = AsyncMock()
        pool.fetchrow.return_value = fake_row

        result = await get_web_user_by_email(pool, "alice@example.com")

        assert result["email"] == "alice@example.com"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = None

        result = await get_web_user_by_email(pool, "nobody@example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_parameterized_query(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = None

        await get_web_user_by_email(pool, "test@example.com")

        query = pool.fetchrow.call_args[0][0]
        assert "$1" in query
        assert pool.fetchrow.call_args[0][1] == "test@example.com"


# ---------------------------------------------------------------------------
# get_web_user_by_id
# ---------------------------------------------------------------------------

class TestGetWebUserById:
    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self):
        fake_row = {"id": "uuid-1", "email": "alice@example.com"}
        pool = AsyncMock()
        pool.fetchrow.return_value = fake_row

        result = await get_web_user_by_id(pool, "uuid-1")

        assert result["id"] == "uuid-1"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = None

        result = await get_web_user_by_id(pool, "nonexistent-uuid")

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_parameterized_query(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = None

        await get_web_user_by_id(pool, "uuid-abc")

        query = pool.fetchrow.call_args[0][0]
        assert "WHERE id = $1" in query
        assert pool.fetchrow.call_args[0][1] == "uuid-abc"


# ---------------------------------------------------------------------------
# update_web_user_profile
# ---------------------------------------------------------------------------

class TestUpdateWebUserProfile:
    @pytest.mark.asyncio
    async def test_returns_updated_row(self):
        fake_row = {
            "id": "uuid-1",
            "email": "alice@example.com",
            "full_name": "Alice Smith",
            "avatar_url": "https://img.example.com/alice.png",
        }
        pool = AsyncMock()
        pool.fetchrow.return_value = fake_row

        result = await update_web_user_profile(
            pool, "uuid-1", "Alice Smith", "https://img.example.com/alice.png"
        )

        assert result["full_name"] == "Alice Smith"
        assert result["avatar_url"] == "https://img.example.com/alice.png"

    @pytest.mark.asyncio
    async def test_uses_parameterized_update(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = {"id": "uuid-1"}

        await update_web_user_profile(pool, "uuid-1", "Bob", None)

        query = pool.fetchrow.call_args[0][0]
        assert "UPDATE web_users" in query
        assert "$1" in query and "$2" in query and "$3" in query
        assert pool.fetchrow.call_args[0][1] == "uuid-1"
        assert pool.fetchrow.call_args[0][2] == "Bob"
        assert pool.fetchrow.call_args[0][3] is None

    @pytest.mark.asyncio
    async def test_sets_updated_at(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = {"id": "uuid-1"}

        await update_web_user_profile(pool, "uuid-1", "Name", None)

        query = pool.fetchrow.call_args[0][0]
        assert "updated_at = NOW()" in query


# ---------------------------------------------------------------------------
# update_web_user_password
# ---------------------------------------------------------------------------

class TestUpdateWebUserPassword:
    @pytest.mark.asyncio
    async def test_executes_update(self):
        pool = AsyncMock()

        await update_web_user_password(pool, "uuid-1", "new-hash")

        pool.execute.assert_awaited_once()
        query = pool.execute.call_args[0][0]
        assert "UPDATE web_users" in query
        assert "password_hash" in query
        assert "$1" in query and "$2" in query

    @pytest.mark.asyncio
    async def test_passes_correct_params(self):
        pool = AsyncMock()

        await update_web_user_password(pool, "uuid-1", "bcrypt-hash-xyz")

        assert pool.execute.call_args[0][1] == "uuid-1"
        assert pool.execute.call_args[0][2] == "bcrypt-hash-xyz"

    @pytest.mark.asyncio
    async def test_sets_updated_at(self):
        pool = AsyncMock()

        await update_web_user_password(pool, "uuid-1", "hash")

        query = pool.execute.call_args[0][0]
        assert "updated_at = NOW()" in query


# ---------------------------------------------------------------------------
# store_refresh_token
# ---------------------------------------------------------------------------

class TestStoreRefreshToken:
    @pytest.mark.asyncio
    async def test_returns_created_row(self):
        expires = datetime(2025, 7, 1, tzinfo=timezone.utc)
        fake_row = {
            "id": "tok-uuid",
            "user_id": "uuid-1",
            "token_hash": "hash123",
            "expires_at": expires,
        }
        pool = AsyncMock()
        pool.fetchrow.return_value = fake_row

        result = await store_refresh_token(pool, "uuid-1", "hash123", expires)

        assert result["token_hash"] == "hash123"
        assert result["user_id"] == "uuid-1"

    @pytest.mark.asyncio
    async def test_uses_parameterized_insert(self):
        pool = AsyncMock()
        expires = datetime(2025, 7, 1, tzinfo=timezone.utc)
        pool.fetchrow.return_value = {"id": "tok-uuid"}

        await store_refresh_token(pool, "uuid-1", "hash", expires)

        query = pool.fetchrow.call_args[0][0]
        assert "INSERT INTO refresh_tokens" in query
        assert "$1" in query and "$2" in query and "$3" in query


# ---------------------------------------------------------------------------
# get_refresh_token
# ---------------------------------------------------------------------------

class TestGetRefreshToken:
    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self):
        fake_row = {"id": "tok-uuid", "token_hash": "hash123", "user_id": "uuid-1"}
        pool = AsyncMock()
        pool.fetchrow.return_value = fake_row

        result = await get_refresh_token(pool, "hash123")

        assert result["token_hash"] == "hash123"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = None

        result = await get_refresh_token(pool, "nonexistent-hash")

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_parameterized_query(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = None

        await get_refresh_token(pool, "hash-abc")

        query = pool.fetchrow.call_args[0][0]
        assert "WHERE token_hash = $1" in query
        assert pool.fetchrow.call_args[0][1] == "hash-abc"


# ---------------------------------------------------------------------------
# delete_refresh_token
# ---------------------------------------------------------------------------

class TestDeleteRefreshToken:
    @pytest.mark.asyncio
    async def test_executes_delete(self):
        pool = AsyncMock()

        await delete_refresh_token(pool, "hash-to-delete")

        pool.execute.assert_awaited_once()
        query = pool.execute.call_args[0][0]
        assert "DELETE FROM refresh_tokens" in query
        assert "WHERE token_hash = $1" in query
        assert pool.execute.call_args[0][1] == "hash-to-delete"


# ---------------------------------------------------------------------------
# delete_all_refresh_tokens
# ---------------------------------------------------------------------------

class TestDeleteAllRefreshTokens:
    @pytest.mark.asyncio
    async def test_executes_delete_by_user_id(self):
        pool = AsyncMock()

        await delete_all_refresh_tokens(pool, "uuid-1")

        pool.execute.assert_awaited_once()
        query = pool.execute.call_args[0][0]
        assert "DELETE FROM refresh_tokens" in query
        assert "WHERE user_id = $1" in query
        assert pool.execute.call_args[0][1] == "uuid-1"


# ---------------------------------------------------------------------------
# store_reset_token
# ---------------------------------------------------------------------------

class TestStoreResetToken:
    @pytest.mark.asyncio
    async def test_returns_created_row(self):
        expires = datetime(2025, 7, 1, 1, 0, 0, tzinfo=timezone.utc)
        fake_row = {
            "id": "reset-uuid",
            "user_id": "uuid-1",
            "token_hash": "reset-hash",
            "expires_at": expires,
            "used": False,
        }
        pool = AsyncMock()
        pool.fetchrow.return_value = fake_row

        result = await store_reset_token(pool, "uuid-1", "reset-hash", expires)

        assert result["token_hash"] == "reset-hash"
        assert result["used"] is False

    @pytest.mark.asyncio
    async def test_uses_parameterized_insert(self):
        pool = AsyncMock()
        expires = datetime(2025, 7, 1, tzinfo=timezone.utc)
        pool.fetchrow.return_value = {"id": "reset-uuid"}

        await store_reset_token(pool, "uuid-1", "hash", expires)

        query = pool.fetchrow.call_args[0][0]
        assert "INSERT INTO password_reset_tokens" in query
        assert "$1" in query and "$2" in query and "$3" in query


# ---------------------------------------------------------------------------
# get_reset_token
# ---------------------------------------------------------------------------

class TestGetResetToken:
    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self):
        fake_row = {"id": "reset-uuid", "token_hash": "reset-hash", "used": False}
        pool = AsyncMock()
        pool.fetchrow.return_value = fake_row

        result = await get_reset_token(pool, "reset-hash")

        assert result["token_hash"] == "reset-hash"
        assert result["used"] is False

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = None

        result = await get_reset_token(pool, "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_parameterized_query(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = None

        await get_reset_token(pool, "hash-xyz")

        query = pool.fetchrow.call_args[0][0]
        assert "WHERE token_hash = $1" in query
        assert pool.fetchrow.call_args[0][1] == "hash-xyz"


# ---------------------------------------------------------------------------
# mark_reset_token_used
# ---------------------------------------------------------------------------

class TestMarkResetTokenUsed:
    @pytest.mark.asyncio
    async def test_executes_update(self):
        pool = AsyncMock()

        await mark_reset_token_used(pool, "reset-uuid")

        pool.execute.assert_awaited_once()
        query = pool.execute.call_args[0][0]
        assert "UPDATE password_reset_tokens" in query
        assert "SET used = TRUE" in query
        assert "WHERE id = $1" in query
        assert pool.execute.call_args[0][1] == "reset-uuid"


# ---------------------------------------------------------------------------
# create_or_update_google_user
# ---------------------------------------------------------------------------

class TestCreateOrUpdateGoogleUser:
    @pytest.mark.asyncio
    async def test_returns_upserted_row(self):
        fake_row = {
            "id": "uuid-google",
            "email": "alice@gmail.com",
            "password_hash": None,
            "full_name": "Alice G",
            "avatar_url": "https://lh3.google.com/alice",
            "is_admin": False,
        }
        pool = AsyncMock()
        pool.fetchrow.return_value = fake_row

        result = await create_or_update_google_user(
            pool, "alice@gmail.com", "Alice G", "https://lh3.google.com/alice"
        )

        assert result["email"] == "alice@gmail.com"
        assert result["password_hash"] is None
        assert result["full_name"] == "Alice G"

    @pytest.mark.asyncio
    async def test_uses_on_conflict_upsert(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = {"id": "uuid-google"}

        await create_or_update_google_user(pool, "a@gmail.com", "A", None)

        query = pool.fetchrow.call_args[0][0]
        assert "ON CONFLICT (email) DO UPDATE" in query

    @pytest.mark.asyncio
    async def test_uses_parameterized_query(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = {"id": "uuid-google"}

        await create_or_update_google_user(
            pool, "bob@gmail.com", "Bob", "https://img.com/bob.png"
        )

        query = pool.fetchrow.call_args[0][0]
        assert "$1" in query and "$2" in query and "$3" in query
        assert pool.fetchrow.call_args[0][1] == "bob@gmail.com"
        assert pool.fetchrow.call_args[0][2] == "Bob"
        assert pool.fetchrow.call_args[0][3] == "https://img.com/bob.png"

    @pytest.mark.asyncio
    async def test_preserves_existing_values_with_coalesce(self):
        """COALESCE ensures NULL new values don't overwrite existing data."""
        pool = AsyncMock()
        pool.fetchrow.return_value = {"id": "uuid-google"}

        await create_or_update_google_user(pool, "a@gmail.com", None, None)

        query = pool.fetchrow.call_args[0][0]
        assert "COALESCE(EXCLUDED.full_name, web_users.full_name)" in query
        assert "COALESCE(EXCLUDED.avatar_url, web_users.avatar_url)" in query
