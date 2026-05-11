"""Unit tests for documents router endpoints.

Tests all CRUD operations, search, bulk operations, and error handling.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth_middleware import get_current_user
from db import get_pool
from documents_router import router
from document_exceptions import (
    DocumentNotFoundError,
    DocumentConflictError,
    DocumentValidationError,
    DirectoryNotEmptyError,
)


MOCK_USER = {"user_id": "test_user", "email": "test@example.com"}


@pytest.fixture
def mock_pool():
    """Mock asyncpg connection pool."""
    pool = AsyncMock()
    return pool


@pytest.fixture
def test_app(mock_pool):
    """FastAPI app with dependency overrides."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    app.dependency_overrides[get_pool] = lambda: mock_pool
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def test_client(test_app):
    """FastAPI test client."""
    return TestClient(test_app)


class TestGetDocumentTree:
    """Tests for GET /tree endpoint."""

    def test_get_tree_success(self, test_client):
        """Should return document tree structure."""
        with patch("documents_router.build_tree") as mock_build:
            mock_build.return_value = [
                {
                    "type": "directory",
                    "name": "development",
                    "path": "development",
                    "children": []
                }
            ]
            with patch("documents_router.Path") as mock_path:
                mock_base = MagicMock()
                mock_base.exists.return_value = True
                mock_path.return_value = mock_base

                response = test_client.get("/tree")

                assert response.status_code == 200
                data = response.json()
                assert len(data) == 1
                assert data[0]["type"] == "directory"

    def test_get_tree_creates_base_dir(self, test_client):
        """Should create base directory if it doesn't exist."""
        with patch("documents_router.Path") as mock_path:
            mock_base = MagicMock()
            mock_base.exists.return_value = False
            mock_path.return_value = mock_base

            response = test_client.get("/tree")

            mock_base.mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestGetDocumentStats:
    """Tests for GET /stats endpoint."""

    def test_get_stats_success(self, test_client):
        """Should return document statistics."""
        with patch("documents_router.calculate_stats") as mock_calc:
            mock_calc.return_value = {
                "total_directories": 5,
                "total_documents": 20,
                "total_subdirectories": 10,
                "total_words": 50000
            }
            with patch("documents_router.Path") as mock_path:
                mock_base = MagicMock()
                mock_base.exists.return_value = True
                mock_path.return_value = mock_base

                response = test_client.get("/stats")

                assert response.status_code == 200
                data = response.json()
                assert data["total_documents"] == 20
                assert data["total_words"] == 50000


class TestGetDocument:
    """Tests for GET /{path} endpoint."""

    def test_get_document_success(self, test_client):
        """Should return document content and metadata."""
        with patch("documents_router.validate_path"):
            with patch("documents_router.Path") as mock_path:
                mock_file = MagicMock()
                mock_file.exists.return_value = True
                mock_file.is_file.return_value = True
                mock_file.read_text.return_value = "# Test Document\n\nContent here."
                mock_file.stat.return_value = MagicMock(st_size=100, st_mtime=1700000000)
                mock_path.return_value = mock_file

                response = test_client.get("/development/test.md")

                assert response.status_code == 200
                data = response.json()
                assert "content" in data
                assert "metadata" in data

    def test_get_document_not_found(self, test_client):
        """Should return 404 if document doesn't exist."""
        with patch("documents_router.validate_path"):
            with patch("documents_router.Path") as mock_path:
                mock_file = MagicMock()
                mock_file.exists.return_value = False
                mock_path.return_value = mock_file

                response = test_client.get("/nonexistent.md")

                assert response.status_code == 404


class TestCreateDocument:
    """Tests for POST / endpoint."""

    def test_create_document_success(self, test_client):
        """Should create document and return it."""
        with patch("documents_router.validate_path"):
            with patch("documents_router.Path") as mock_path:
                mock_file = MagicMock()
                mock_file.exists.return_value = False
                mock_file.name = "test.md"
                mock_file.stem = "test"
                mock_file.stat.return_value = MagicMock(st_size=10, st_mtime=1700000000)
                mock_file.read_text.return_value = "# Test\n"
                mock_file.parent = MagicMock()
                mock_path.return_value = mock_file

                with patch("documents_router.validate_filename"):
                    with patch("documents_router.validate_markdown_content", side_effect=lambda x: x):
                        with patch("documents_router.normalize_line_endings", side_effect=lambda x: x):
                            with patch("documents_router.markdown_round_trip", side_effect=lambda x: x):
                                with patch("documents_router.chunk_document_hierarchical", return_value=[]):
                                    response = test_client.post(
                                        "/",
                                        json={"path": "test.md", "content": "# Test"}
                                    )

                                    assert response.status_code == 201

    def test_create_document_conflict(self, test_client):
        """Should return 409 if document already exists."""
        with patch("documents_router.validate_path"):
            with patch("documents_router.Path") as mock_path:
                mock_file = MagicMock()
                mock_file.exists.return_value = True
                mock_path.return_value = mock_file

                response = test_client.post(
                    "/",
                    json={"path": "existing.md", "content": "# Test"}
                )

                assert response.status_code == 409

    def test_create_document_invalid_extension(self, test_client):
        """Should return 422 if path doesn't end with .md."""
        response = test_client.post(
            "/",
            json={"path": "test.txt", "content": "# Test"}
        )

        assert response.status_code == 422  # Pydantic validation error


class TestUpdateDocument:
    """Tests for PUT /{path} endpoint."""

    def test_update_document_success(self, test_client):
        """Should update document content."""
        with patch("documents_router.validate_path"):
            with patch("documents_router.Path") as mock_path:
                mock_file = MagicMock()
                mock_file.exists.return_value = True
                mock_file.stem = "test"
                mock_file.stat.return_value = MagicMock(st_size=20, st_mtime=1700000000)
                mock_file.read_text.return_value = "# Updated\n"
                mock_backup = MagicMock()
                mock_file.with_suffix.return_value = mock_backup
                mock_path.return_value = mock_file

                with patch("documents_router.validate_markdown_content", side_effect=lambda x: x):
                    with patch("documents_router.normalize_line_endings", side_effect=lambda x: x):
                        with patch("documents_router.markdown_round_trip", side_effect=lambda x: x):
                            with patch("documents_router.chunk_document_hierarchical", return_value=[]):
                                with patch("documents_router.db_documents.delete_document_by_path", new_callable=AsyncMock):
                                    response = test_client.put(
                                        "/test.md",
                                        json={"content": "# Updated Content"}
                                    )

                                    assert response.status_code == 200

    def test_update_document_not_found(self, test_client):
        """Should return 404 if document doesn't exist."""
        with patch("documents_router.validate_path"):
            with patch("documents_router.Path") as mock_path:
                mock_file = MagicMock()
                mock_file.exists.return_value = False
                mock_path.return_value = mock_file

                response = test_client.put(
                    "/nonexistent.md",
                    json={"content": "# Updated"}
                )

                assert response.status_code == 404


class TestDeleteDocument:
    """Tests for DELETE /{path} endpoint."""

    def test_delete_document_success(self, test_client):
        """Should delete document."""
        with patch("documents_router.validate_path"):
            with patch("documents_router.Path") as mock_path:
                mock_file = MagicMock()
                mock_file.exists.return_value = True
                mock_file.is_file.return_value = True
                mock_path.return_value = mock_file

                with patch("documents_router.db_documents.delete_document_by_path", new_callable=AsyncMock):
                    response = test_client.delete("/test.md")

                    assert response.status_code == 200
                    mock_file.unlink.assert_called_once()


class TestSearchDocuments:
    """Tests for POST /search endpoint."""

    def test_search_content_success(self, test_client, mock_pool):
        """Should search document content."""
        mock_pool.fetch = AsyncMock(return_value=[])
        with patch("documents_router.db_documents.search_documents_by_content") as mock_search:
            mock_search.return_value = [
                {
                    "file_path": "test.md",
                    "content_snippet": "matching content",
                    "match_position": 10
                }
            ]
            with patch("documents_router.Path") as mock_path:
                mock_base = MagicMock()
                mock_file = MagicMock()
                mock_file.exists.return_value = True
                mock_file.name = "test.md"
                mock_file.stat.return_value = MagicMock(st_size=100, st_mtime=1700000000)
                mock_file.read_text.return_value = "content"
                mock_base.__truediv__ = MagicMock(return_value=mock_file)
                mock_path.return_value = mock_base

                response = test_client.post(
                    "/search",
                    json={"query": "test", "search_content": True}
                )

                assert response.status_code == 200


class TestDirectoryOperations:
    """Tests for directory creation and deletion."""

    def test_create_directory_success(self, test_client):
        """Should create directory."""
        with patch("documents_router.validate_path"):
            with patch("documents_router.Path") as mock_path:
                mock_dir = MagicMock()
                mock_dir.exists.return_value = False
                mock_dir.name = "new_dir"
                mock_path.return_value = mock_dir

                with patch("documents_router.validate_dirname"):
                    response = test_client.post(
                        "/directories",
                        json={"path": "new_dir"}
                    )

                    assert response.status_code == 201
                    mock_dir.mkdir.assert_called_once()

    def test_delete_empty_directory_success(self, test_client):
        """Should delete empty directory."""
        with patch("documents_router.validate_path"):
            with patch("documents_router.Path") as mock_path:
                mock_dir = MagicMock()
                mock_dir.exists.return_value = True
                mock_dir.is_dir.return_value = True
                mock_dir.iterdir.return_value = []
                mock_path.return_value = mock_dir

                response = test_client.delete("/directories/empty_dir")

                assert response.status_code == 200
                mock_dir.rmdir.assert_called_once()

    def test_delete_non_empty_directory_fails(self, test_client):
        """Should return 400 if directory is not empty."""
        with patch("documents_router.validate_path"):
            with patch("documents_router.Path") as mock_path:
                mock_dir = MagicMock()
                mock_dir.exists.return_value = True
                mock_dir.is_dir.return_value = True
                mock_dir.iterdir.return_value = [MagicMock()]
                mock_path.return_value = mock_dir

                response = test_client.delete("/directories/full_dir")

                assert response.status_code == 400


class TestBulkOperations:
    """Tests for bulk delete and move operations."""

    def test_bulk_delete_success(self, test_client):
        """Should delete multiple documents."""
        with patch("documents_router.validate_path"):
            with patch("documents_router.Path") as mock_path:
                mock_file = MagicMock()
                mock_file.exists.return_value = True
                mock_path.return_value = mock_file

                with patch("documents_router.db_documents"):
                    response = test_client.post(
                        "/bulk-delete",
                        json={"paths": ["file1.md", "file2.md"]}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert "successful" in data
                    assert "failed" in data
