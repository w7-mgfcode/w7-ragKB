"""Unit tests for category-related document browser endpoints.

Tests GET /categories, POST /route-query, GET /category-stats.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth_middleware import get_current_user
from db import get_pool
from documents_router import router


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


class TestGetCategories:
    """Tests for GET /categories endpoint."""

    def test_get_categories_success(self, test_client):
        """Should return category tree."""
        from query_router import CategoryNode as DC_CategoryNode

        mock_tree = [
            DC_CategoryNode(
                name="development",
                path="development",
                document_count=5,
                subcategories=[
                    DC_CategoryNode(
                        name="testing",
                        path="development/testing",
                        document_count=3,
                        subcategories=[],
                    )
                ],
            )
        ]

        with patch("documents_router._build_category_tree", return_value=mock_tree):
            response = test_client.get("/categories")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["name"] == "development"
            assert data[0]["document_count"] == 5
            assert data[0]["total_chunks"] == 0
            assert len(data[0]["subcategories"]) == 1
            assert data[0]["subcategories"][0]["name"] == "testing"

    def test_get_categories_empty(self, test_client):
        """Should return empty list for empty directory."""
        with patch("documents_router._build_category_tree", return_value=[]):
            response = test_client.get("/categories")

            assert response.status_code == 200
            assert response.json() == []

    def test_get_categories_error(self, test_client):
        """Should return 500 on internal error."""
        with patch("documents_router._build_category_tree", side_effect=OSError("disk error")):
            response = test_client.get("/categories")

            assert response.status_code == 500


class TestRouteQuery:
    """Tests for POST /route-query endpoint."""

    def test_route_query_success(self, test_client):
        """Should route query to categories."""
        from query_router import QueryRoutingResponse as QRR

        mock_result = QRR(
            query="how to test",
            selected_categories=["development", "testing"],
            reasoning="Query is about testing",
            confidence=0.9,
        )

        with patch("documents_router._build_category_tree", return_value=[]):
            with patch("documents_router.asyncio") as mock_asyncio:
                mock_asyncio.to_thread = AsyncMock(return_value=mock_result)

                response = test_client.post(
                    "/route-query",
                    json={"query": "how to test", "max_categories": 3},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["query"] == "how to test"
                assert "development" in data["selected_categories"]
                assert data["confidence"] == 0.9

    def test_route_query_empty_query(self, test_client):
        """Should return 422 for empty query."""
        response = test_client.post(
            "/route-query",
            json={"query": "", "max_categories": 3},
        )

        assert response.status_code == 422

    def test_route_query_max_categories_validation(self, test_client):
        """Should reject max_categories > 10."""
        response = test_client.post(
            "/route-query",
            json={"query": "test", "max_categories": 20},
        )

        assert response.status_code == 422


class TestGetCategoryStats:
    """Tests for GET /category-stats endpoint."""

    def test_get_category_stats_success(self, test_client, mock_pool):
        """Should return category statistics."""
        mock_rows = [
            {
                "category_path": "development",
                "document_count": 5,
                "total_chunks": 25,
                "doc_chunks": 5,
                "section_chunks": 10,
                "leaf_chunks": 10,
                "avg_chunk_size": 150.5,
                "total_words": 3762,
                "last_updated": datetime(2025, 1, 15, 12, 0, 0),
            }
        ]

        mock_pool.fetch = AsyncMock(return_value=mock_rows)

        response = test_client.get("/category-stats")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["category_path"] == "development"
        assert data[0]["document_count"] == 5
        assert data[0]["total_chunks"] == 25
        assert data[0]["chunk_level_distribution"]["document"] == 5
        assert data[0]["avg_chunk_size"] == 150.5

    def test_get_category_stats_empty(self, test_client, mock_pool):
        """Should return empty list when no categories."""
        mock_pool.fetch = AsyncMock(return_value=[])

        response = test_client.get("/category-stats")

        assert response.status_code == 200
        assert response.json() == []
