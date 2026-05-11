"""Unit tests for db_documents.py — asyncpg document query operations."""

import json
import pytest
from unittest.mock import AsyncMock

from backend_agent_api.db_documents import (
    execute_custom_sql,
    get_document_content,
    list_documents,
    match_documents,
)


# ---------------------------------------------------------------------------
# match_documents
# ---------------------------------------------------------------------------

class TestMatchDocuments:
    @pytest.mark.asyncio
    async def test_calls_match_documents_sql_function(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        await match_documents(pool, [0.1] * 768)

        query = pool.fetch.call_args[0][0]
        assert "match_documents" in query
        assert "$1::vector" in query
        assert "$2" in query
        assert "$3::jsonb" in query

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        fake_rows = [
            {"id": 1, "content": "hello", "metadata": {"file_id": "f1"}, "similarity": 0.95},
            {"id": 2, "content": "world", "metadata": {"file_id": "f2"}, "similarity": 0.80},
        ]
        pool = AsyncMock()
        pool.fetch.return_value = fake_rows

        result = await match_documents(pool, [0.1] * 768)

        assert len(result) == 2
        assert result[0]["content"] == "hello"
        assert result[1]["similarity"] == 0.80

    @pytest.mark.asyncio
    async def test_passes_match_count(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        await match_documents(pool, [0.1] * 768, match_count=10)

        assert pool.fetch.call_args[0][2] == 10

    @pytest.mark.asyncio
    async def test_passes_filter_metadata_as_json(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        await match_documents(pool, [0.1] * 768, filter_metadata={"file_id": "abc"})

        filter_arg = pool.fetch.call_args[0][3]
        assert json.loads(filter_arg) == {"file_id": "abc"}

    @pytest.mark.asyncio
    async def test_defaults_filter_to_empty_json_object(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        await match_documents(pool, [0.1] * 768)

        filter_arg = pool.fetch.call_args[0][3]
        assert json.loads(filter_arg) == {}

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_matches(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        result = await match_documents(pool, [0.0] * 768)
        assert result == []


# ---------------------------------------------------------------------------
# list_documents
# ---------------------------------------------------------------------------

class TestListDocuments:
    @pytest.mark.asyncio
    async def test_queries_document_metadata_table(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        await list_documents(pool)

        query = pool.fetch.call_args[0][0]
        assert "document_metadata" in query
        assert "id" in query
        assert "title" in query

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        fake_rows = [
            {"id": "doc1", "title": "Report", "url": "http://example.com", "schema": None, "created_at": "2025-01-01"},
        ]
        pool = AsyncMock()
        pool.fetch.return_value = fake_rows

        result = await list_documents(pool)

        assert len(result) == 1
        assert result[0]["id"] == "doc1"
        assert result[0]["title"] == "Report"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_documents(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        result = await list_documents(pool)
        assert result == []


# ---------------------------------------------------------------------------
# get_document_content
# ---------------------------------------------------------------------------

class TestGetDocumentContent:
    @pytest.mark.asyncio
    async def test_queries_by_file_id_with_parameterized_query(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        await get_document_content(pool, "doc123")

        query = pool.fetch.call_args[0][0]
        assert "$1" in query
        assert "metadata->>'file_id'" in query
        assert pool.fetch.call_args[0][1] == "doc123"

    @pytest.mark.asyncio
    async def test_returns_not_found_message_when_empty(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        result = await get_document_content(pool, "missing")

        assert "No content found for document: missing" in result

    @pytest.mark.asyncio
    async def test_combines_chunks_into_single_string(self):
        fake_rows = [
            {"id": 1, "content": "First chunk.", "metadata": {"file_title": "My Doc", "file_id": "d1"}},
            {"id": 2, "content": "Second chunk.", "metadata": {"file_title": "My Doc - Chunk 2", "file_id": "d1"}},
        ]
        pool = AsyncMock()
        pool.fetch.return_value = fake_rows

        result = await get_document_content(pool, "d1")

        assert "# My Doc" in result
        assert "First chunk." in result
        assert "Second chunk." in result

    @pytest.mark.asyncio
    async def test_strips_chunk_suffix_from_title(self):
        fake_rows = [
            {"id": 1, "content": "text", "metadata": {"file_title": "Report - Chunk 1", "file_id": "r1"}},
        ]
        pool = AsyncMock()
        pool.fetch.return_value = fake_rows

        result = await get_document_content(pool, "r1")

        assert "# Report" in result
        assert "Chunk 1" not in result

    @pytest.mark.asyncio
    async def test_handles_string_metadata(self):
        """If metadata comes back as a JSON string, it gets parsed."""
        fake_rows = [
            {"id": 1, "content": "text", "metadata": '{"file_title": "Doc", "file_id": "d1"}'},
        ]
        pool = AsyncMock()
        pool.fetch.return_value = fake_rows

        result = await get_document_content(pool, "d1")

        assert "# Doc" in result

    @pytest.mark.asyncio
    async def test_skips_none_content_chunks(self):
        fake_rows = [
            {"id": 1, "content": "Good chunk.", "metadata": {"file_title": "Doc", "file_id": "d1"}},
            {"id": 2, "content": None, "metadata": {"file_title": "Doc", "file_id": "d1"}},
            {"id": 3, "content": "Another chunk.", "metadata": {"file_title": "Doc", "file_id": "d1"}},
        ]
        pool = AsyncMock()
        pool.fetch.return_value = fake_rows

        result = await get_document_content(pool, "d1")

        assert "Good chunk." in result
        assert "Another chunk." in result

    @pytest.mark.asyncio
    async def test_truncates_at_20000_characters(self):
        long_content = "x" * 25000
        fake_rows = [
            {"id": 1, "content": long_content, "metadata": {"file_title": "Big", "file_id": "b1"}},
        ]
        pool = AsyncMock()
        pool.fetch.return_value = fake_rows

        result = await get_document_content(pool, "b1")

        assert len(result) <= 20000

    @pytest.mark.asyncio
    async def test_orders_by_id(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        await get_document_content(pool, "d1")

        query = pool.fetch.call_args[0][0]
        assert "ORDER BY id" in query


# ---------------------------------------------------------------------------
# execute_custom_sql
# ---------------------------------------------------------------------------

class TestExecuteCustomSql:
    @pytest.mark.asyncio
    async def test_executes_select_query(self):
        fake_rows = [{"category": "A", "total": 100}]
        pool = AsyncMock()
        pool.fetch.return_value = fake_rows

        result = await execute_custom_sql(pool, "SELECT * FROM document_rows")

        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["category"] == "A"

    @pytest.mark.asyncio
    async def test_rejects_insert(self):
        pool = AsyncMock()
        result = await execute_custom_sql(pool, "INSERT INTO documents VALUES (1)")

        assert "Error" in result
        assert "INSERT" in result
        pool.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_update(self):
        pool = AsyncMock()
        result = await execute_custom_sql(pool, "UPDATE documents SET content = 'x'")

        assert "Error" in result
        assert "UPDATE" in result
        pool.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_delete(self):
        pool = AsyncMock()
        result = await execute_custom_sql(pool, "DELETE FROM documents")

        assert "Error" in result
        assert "DELETE" in result
        pool.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_drop(self):
        pool = AsyncMock()
        result = await execute_custom_sql(pool, "DROP TABLE documents")

        assert "Error" in result
        assert "DROP" in result
        pool.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_create(self):
        pool = AsyncMock()
        result = await execute_custom_sql(pool, "CREATE TABLE evil (id int)")

        assert "Error" in result
        assert "CREATE" in result
        pool.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_alter(self):
        pool = AsyncMock()
        result = await execute_custom_sql(pool, "ALTER TABLE documents ADD COLUMN x TEXT")

        assert "Error" in result
        assert "ALTER" in result
        pool.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_truncate(self):
        pool = AsyncMock()
        result = await execute_custom_sql(pool, "TRUNCATE documents")

        assert "Error" in result
        assert "TRUNCATE" in result
        pool.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_case_insensitive_write_ops(self):
        pool = AsyncMock()
        result = await execute_custom_sql(pool, "insert into documents values (1)")

        assert "Error" in result
        assert "INSERT" in result
        pool.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_strips_whitespace_before_validation(self):
        pool = AsyncMock()
        pool.fetch.return_value = [{"count": 5}]

        result = await execute_custom_sql(pool, "  SELECT COUNT(*) FROM documents  ")

        parsed = json.loads(result)
        assert parsed[0]["count"] == 5

    @pytest.mark.asyncio
    async def test_returns_error_message_on_exception(self):
        pool = AsyncMock()
        pool.fetch.side_effect = Exception("relation does not exist")

        result = await execute_custom_sql(pool, "SELECT * FROM nonexistent")

        assert "Error executing SQL query" in result
        assert "relation does not exist" in result

    @pytest.mark.asyncio
    async def test_returns_empty_list_json_for_no_results(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        result = await execute_custom_sql(pool, "SELECT * FROM document_rows WHERE 1=0")

        assert json.loads(result) == []
