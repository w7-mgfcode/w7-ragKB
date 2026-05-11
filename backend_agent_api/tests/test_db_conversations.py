"""Unit tests for db_conversations.py — asyncpg conversation/message operations."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend_agent_api.db_conversations import (
    create_conversation,
    ensure_slack_user,
    fetch_conversation_history,
    generate_session_id,
    store_message,
    update_conversation_title,
)


# ---------------------------------------------------------------------------
# generate_session_id (pure function — no mocks needed)
# ---------------------------------------------------------------------------

class TestGenerateSessionId:
    def test_deterministic_for_same_inputs(self):
        """Same channel + thread_ts always produces the same session ID."""
        sid1 = generate_session_id("C123", "1234567890.123456")
        sid2 = generate_session_id("C123", "1234567890.123456")
        assert sid1 == sid2

    def test_different_channels_produce_different_ids(self):
        ts = "1234567890.123456"
        assert generate_session_id("C111", ts) != generate_session_id("C222", ts)

    def test_different_threads_produce_different_ids(self):
        ch = "C123"
        assert generate_session_id(ch, "111.111") != generate_session_id(ch, "222.222")

    def test_returns_16_hex_chars(self):
        sid = generate_session_id("C123", "1234567890.123456")
        assert len(sid) == 16
        assert all(c in "0123456789abcdef" for c in sid)


# ---------------------------------------------------------------------------
# ensure_slack_user
# ---------------------------------------------------------------------------

class TestEnsureSlackUser:
    @pytest.mark.asyncio
    async def test_calls_execute_with_parameterized_query(self):
        pool = AsyncMock()
        await ensure_slack_user(pool, "U123", "Alice")

        pool.execute.assert_awaited_once()
        args = pool.execute.call_args
        query = args[0][0]
        assert "$1" in query and "$2" in query
        assert args[0][1] == "U123"
        assert args[0][2] == "Alice"

    @pytest.mark.asyncio
    async def test_upsert_query_contains_on_conflict(self):
        pool = AsyncMock()
        await ensure_slack_user(pool, "U999")

        query = pool.execute.call_args[0][0]
        assert "ON CONFLICT" in query

    @pytest.mark.asyncio
    async def test_display_name_defaults_to_none(self):
        pool = AsyncMock()
        await ensure_slack_user(pool, "U456")

        assert pool.execute.call_args[0][2] is None


# ---------------------------------------------------------------------------
# create_conversation
# ---------------------------------------------------------------------------

class TestCreateConversation:
    @pytest.mark.asyncio
    async def test_returns_dict_from_fetchrow(self):
        fake_row = {
            "session_id": "abc123",
            "slack_user_id": "U123",
            "slack_channel_id": "C456",
            "title": None,
            "created_at": "2025-01-01T00:00:00+00:00",
            "last_message_at": "2025-01-01T00:00:00+00:00",
            "is_archived": False,
        }
        pool = AsyncMock()
        pool.fetchrow.return_value = MagicMock(**{"__iter__": lambda s: iter(fake_row.items()), "keys": lambda s: fake_row.keys(), "__getitem__": fake_row.__getitem__})
        # asyncpg Record supports dict() conversion; simulate with a real dict
        pool.fetchrow.return_value = fake_row

        result = await create_conversation(pool, "U123", "abc123", "C456")

        assert result["session_id"] == "abc123"
        assert result["slack_user_id"] == "U123"
        assert result["slack_channel_id"] == "C456"

    @pytest.mark.asyncio
    async def test_uses_parameterized_insert(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = {"session_id": "s1", "slack_user_id": "U1", "slack_channel_id": "C1", "title": None, "created_at": None, "last_message_at": None, "is_archived": False}

        await create_conversation(pool, "U1", "s1", "C1")

        query = pool.fetchrow.call_args[0][0]
        assert "INSERT INTO conversations" in query
        assert "$1" in query and "$2" in query and "$3" in query


# ---------------------------------------------------------------------------
# fetch_conversation_history
# ---------------------------------------------------------------------------

class TestFetchConversationHistory:
    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        fake_rows = [
            {"id": 1, "session_id": "s1", "message": {"type": "human", "content": "hi"}, "message_data": None, "created_at": "2025-01-01T00:00:00+00:00"},
            {"id": 2, "session_id": "s1", "message": {"type": "ai", "content": "hello"}, "message_data": None, "created_at": "2025-01-01T00:01:00+00:00"},
        ]
        pool = AsyncMock()
        pool.fetch.return_value = fake_rows

        result = await fetch_conversation_history(pool, "s1")

        assert len(result) == 2
        assert result[0]["message"]["type"] == "human"
        assert result[1]["message"]["content"] == "hello"

    @pytest.mark.asyncio
    async def test_orders_by_created_at_asc(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        await fetch_conversation_history(pool, "s1")

        query = pool.fetch.call_args[0][0]
        assert "ORDER BY created_at ASC" in query

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_messages(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        result = await fetch_conversation_history(pool, "nonexistent")
        assert result == []

    @pytest.mark.asyncio
    async def test_handles_string_jsonb_message(self):
        """If message comes back as a JSON string, it gets parsed."""
        fake_rows = [
            {"id": 1, "session_id": "s1", "message": '{"type": "human", "content": "hi"}', "message_data": None, "created_at": "2025-01-01"},
        ]
        pool = AsyncMock()
        pool.fetch.return_value = fake_rows

        result = await fetch_conversation_history(pool, "s1")
        assert result[0]["message"]["type"] == "human"


# ---------------------------------------------------------------------------
# update_conversation_title
# ---------------------------------------------------------------------------

class TestUpdateConversationTitle:
    @pytest.mark.asyncio
    async def test_executes_update_with_params(self):
        pool = AsyncMock()
        await update_conversation_title(pool, "s1", "My Chat")

        pool.execute.assert_awaited_once()
        query = pool.execute.call_args[0][0]
        assert "UPDATE conversations" in query
        assert "$1" in query and "$2" in query
        assert pool.execute.call_args[0][1] == "My Chat"
        assert pool.execute.call_args[0][2] == "s1"


# ---------------------------------------------------------------------------
# store_message
# ---------------------------------------------------------------------------

class TestStoreMessage:
    def _make_pool_with_transaction(self):
        """Create a mock pool that supports `async with pool.acquire() as conn`."""
        conn = AsyncMock()
        # conn.transaction() returns an async context manager
        tx = AsyncMock()
        conn.transaction.return_value = tx
        tx.__aenter__ = AsyncMock(return_value=tx)
        tx.__aexit__ = AsyncMock(return_value=False)

        pool = AsyncMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__ = AsyncMock(return_value=False)
        pool.acquire.return_value = ctx

        return pool, conn

    @pytest.mark.asyncio
    async def test_inserts_message_and_updates_conversation(self):
        pool, conn = self._make_pool_with_transaction()

        await store_message(pool, "s1", "human", "hello")

        assert conn.execute.await_count == 2
        insert_query = conn.execute.call_args_list[0][0][0]
        update_query = conn.execute.call_args_list[1][0][0]
        assert "INSERT INTO messages" in insert_query
        assert "UPDATE conversations" in update_query

    @pytest.mark.asyncio
    async def test_message_obj_contains_type_and_content(self):
        pool, conn = self._make_pool_with_transaction()

        await store_message(pool, "s1", "ai", "world")

        insert_args = conn.execute.call_args_list[0][0]
        message_json = json.loads(insert_args[2])
        assert message_json["type"] == "ai"
        assert message_json["content"] == "world"

    @pytest.mark.asyncio
    async def test_includes_optional_fields_when_provided(self):
        pool, conn = self._make_pool_with_transaction()

        await store_message(
            pool, "s1", "human", "check this",
            data={"key": "val"},
            files=[{"name": "f.txt"}],
            trace_id="trace-abc",
        )

        insert_args = conn.execute.call_args_list[0][0]
        message_json = json.loads(insert_args[2])
        assert message_json["data"] == {"key": "val"}
        assert message_json["files"] == [{"name": "f.txt"}]
        assert message_json["trace_id"] == "trace-abc"

    @pytest.mark.asyncio
    async def test_omits_optional_fields_when_none(self):
        pool, conn = self._make_pool_with_transaction()

        await store_message(pool, "s1", "human", "plain msg")

        insert_args = conn.execute.call_args_list[0][0]
        message_json = json.loads(insert_args[2])
        assert "data" not in message_json
        assert "files" not in message_json
        assert "trace_id" not in message_json

    @pytest.mark.asyncio
    async def test_passes_message_data_as_third_param(self):
        pool, conn = self._make_pool_with_transaction()

        await store_message(pool, "s1", "ai", "resp", message_data="raw-pydantic-json")

        insert_args = conn.execute.call_args_list[0][0]
        assert insert_args[3] == "raw-pydantic-json"

    @pytest.mark.asyncio
    async def test_uses_parameterized_queries(self):
        pool, conn = self._make_pool_with_transaction()

        await store_message(pool, "s1", "human", "test")

        insert_query = conn.execute.call_args_list[0][0][0]
        assert "$1" in insert_query and "$2" in insert_query
