"""Unit tests for query_router module.

Tests category tree building, query routing, and error handling.
"""

import os
import json
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
import pytest

from query_router import (
    build_category_tree,
    flatten_category_paths,
    route_query_to_categories,
    CategoryNode,
    QueryRoutingResponse,
)


class TestBuildCategoryTree:
    """Tests for build_category_tree function."""
    
    def test_build_tree_with_nested_categories(self, tmp_path):
        """Test building tree from nested directory structure."""
        # Create test directory structure
        (tmp_path / "development").mkdir()
        (tmp_path / "development" / "api-design.md").write_text("# API Design")
        (tmp_path / "development" / "testing").mkdir()
        (tmp_path / "development" / "testing" / "unit-tests.md").write_text("# Unit Tests")
        
        (tmp_path / "security").mkdir()
        (tmp_path / "security" / "auth.md").write_text("# Auth")
        
        tree = build_category_tree(str(tmp_path))
        
        assert len(tree) == 2
        
        # Find development node
        dev_node = next(n for n in tree if n.name == "development")
        assert dev_node.path == "development"
        assert dev_node.document_count == 1
        assert len(dev_node.subcategories) == 1
        
        # Check nested testing category
        testing_node = dev_node.subcategories[0]
        assert testing_node.name == "testing"
        assert testing_node.path == "development/testing"
        assert testing_node.document_count == 1
        
        # Find security node
        sec_node = next(n for n in tree if n.name == "security")
        assert sec_node.path == "security"
        assert sec_node.document_count == 1
        assert len(sec_node.subcategories) == 0
    
    def test_build_tree_empty_directory(self, tmp_path):
        """Test building tree from empty directory."""
        tree = build_category_tree(str(tmp_path))
        assert tree == []
    
    def test_build_tree_nonexistent_path(self):
        """Test building tree from nonexistent path."""
        tree = build_category_tree("/nonexistent/path")
        assert tree == []
    
    def test_build_tree_ignores_hidden_directories(self, tmp_path):
        """Test that hidden directories are ignored."""
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "file.md").write_text("content")
        (tmp_path / "visible").mkdir()
        (tmp_path / "visible" / "file.md").write_text("content")
        
        tree = build_category_tree(str(tmp_path))
        
        assert len(tree) == 1
        assert tree[0].name == "visible"
    
    def test_build_tree_counts_only_markdown_files(self, tmp_path):
        """Test that only .md files are counted."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "file1.md").write_text("content")
        (tmp_path / "docs" / "file2.md").write_text("content")
        (tmp_path / "docs" / "file3.txt").write_text("content")
        (tmp_path / "docs" / "image.png").write_bytes(b"image")
        
        tree = build_category_tree(str(tmp_path))
        
        assert len(tree) == 1
        assert tree[0].document_count == 2


class TestFlattenCategoryPaths:
    """Tests for flatten_category_paths function."""
    
    def test_flatten_single_level(self):
        """Test flattening single-level tree."""
        tree = [
            CategoryNode("dev", "development", 5, []),
            CategoryNode("sec", "security", 3, []),
        ]
        
        paths = flatten_category_paths(tree)
        
        assert paths == ["development", "security"]
    
    def test_flatten_nested_tree(self):
        """Test flattening nested tree."""
        tree = [
            CategoryNode(
                "dev",
                "development",
                5,
                [
                    CategoryNode("test", "development/testing", 2, []),
                    CategoryNode("api", "development/api", 3, []),
                ]
            ),
            CategoryNode("sec", "security", 3, []),
        ]
        
        paths = flatten_category_paths(tree)
        
        assert "development" in paths
        assert "development/testing" in paths
        assert "development/api" in paths
        assert "security" in paths
        assert len(paths) == 4
    
    def test_flatten_empty_tree(self):
        """Test flattening empty tree."""
        paths = flatten_category_paths([])
        assert paths == []


class TestRouteQueryToCategories:
    """Tests for route_query_to_categories function."""
    
    @pytest.fixture
    def sample_tree(self):
        """Create sample category tree for testing."""
        return [
            CategoryNode("dev", "development", 5, []),
            CategoryNode("sec", "security", 3, []),
            CategoryNode("infra", "infrastructure", 4, []),
        ]
    
    def test_route_query_with_valid_response(self, sample_tree):
        """Test routing with valid LLM response."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "selected_categories": ["security", "development"],
            "reasoning": "JWT tokens are security-related and involve development practices",
            "confidence": 0.95
        })
        
        with patch('query_router._get_genai_client') as mock_client:
            mock_client.return_value.models.generate_content.return_value = mock_response
            
            result = route_query_to_categories(
                "How do we handle JWT token refresh?",
                sample_tree,
                max_categories=3
            )
        
        assert result.query == "How do we handle JWT token refresh?"
        assert result.selected_categories == ["security", "development"]
        assert "JWT tokens" in result.reasoning
        assert result.confidence == 0.95
    
    def test_route_query_filters_invalid_categories(self, sample_tree):
        """Test that invalid categories are filtered out."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "selected_categories": ["security", "invalid_category", "development"],
            "reasoning": "Test reasoning",
            "confidence": 0.8
        })
        
        with patch('query_router._get_genai_client') as mock_client:
            mock_client.return_value.models.generate_content.return_value = mock_response
            
            result = route_query_to_categories(
                "test query",
                sample_tree,
                max_categories=3
            )
        
        assert "invalid_category" not in result.selected_categories
        assert "security" in result.selected_categories
        assert "development" in result.selected_categories
    
    def test_route_query_respects_max_categories(self, sample_tree):
        """Test that max_categories limit is enforced."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "selected_categories": ["security", "development", "infrastructure"],
            "reasoning": "All categories relevant",
            "confidence": 0.7
        })
        
        with patch('query_router._get_genai_client') as mock_client:
            mock_client.return_value.models.generate_content.return_value = mock_response
            
            result = route_query_to_categories(
                "test query",
                sample_tree,
                max_categories=2
            )
        
        assert len(result.selected_categories) <= 2
    
    def test_route_query_handles_json_parse_error(self, sample_tree):
        """Test fallback when LLM returns invalid JSON."""
        mock_response = Mock()
        mock_response.text = "This is not valid JSON"
        
        with patch('query_router._get_genai_client') as mock_client:
            mock_client.return_value.models.generate_content.return_value = mock_response
            
            result = route_query_to_categories(
                "test query",
                sample_tree,
                max_categories=3
            )
        
        # Should fallback to all categories
        assert len(result.selected_categories) > 0
        assert "Failed to parse" in result.reasoning
        assert result.confidence < 0.5
    
    def test_route_query_handles_llm_exception(self, sample_tree):
        """Test fallback when LLM call fails."""
        with patch('query_router._get_genai_client') as mock_client:
            mock_client.return_value.models.generate_content.side_effect = Exception("API error")
            
            result = route_query_to_categories(
                "test query",
                sample_tree,
                max_categories=3
            )
        
        # Should fallback to all categories
        assert len(result.selected_categories) > 0
        assert "error" in result.reasoning.lower()
        assert result.confidence < 0.5
    
    def test_route_query_empty_query_raises_error(self, sample_tree):
        """Test that empty query raises ValueError."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            route_query_to_categories("", sample_tree)
        
        with pytest.raises(ValueError, match="Query cannot be empty"):
            route_query_to_categories("   ", sample_tree)
    
    def test_route_query_empty_tree_raises_error(self):
        """Test that empty category tree raises ValueError."""
        with pytest.raises(ValueError, match="Category tree cannot be empty"):
            route_query_to_categories("test query", [])
    
    def test_route_query_no_valid_categories_fallback(self, sample_tree):
        """Test fallback when LLM returns no valid categories."""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "selected_categories": ["invalid1", "invalid2"],
            "reasoning": "Test reasoning",
            "confidence": 0.8
        })
        
        with patch('query_router._get_genai_client') as mock_client:
            mock_client.return_value.models.generate_content.return_value = mock_response
            
            result = route_query_to_categories(
                "test query",
                sample_tree,
                max_categories=3
            )
        
        # Should fallback to all available categories
        assert len(result.selected_categories) > 0
        assert all(cat in ["development", "security", "infrastructure"] 
                   for cat in result.selected_categories)
        assert result.confidence < 0.5


class TestQueryRoutingResponse:
    """Tests for QueryRoutingResponse model."""
    
    def test_valid_response_creation(self):
        """Test creating valid response."""
        response = QueryRoutingResponse(
            query="test query",
            selected_categories=["security", "development"],
            reasoning="Test reasoning",
            confidence=0.85
        )
        
        assert response.query == "test query"
        assert response.selected_categories == ["security", "development"]
        assert response.reasoning == "Test reasoning"
        assert response.confidence == 0.85
    
    def test_confidence_validation(self):
        """Test confidence score validation."""
        # Valid confidence
        response = QueryRoutingResponse(
            query="test",
            selected_categories=["security"],
            reasoning="test",
            confidence=0.5
        )
        assert response.confidence == 0.5
        
        # Test boundary values
        response = QueryRoutingResponse(
            query="test",
            selected_categories=["security"],
            reasoning="test",
            confidence=0.0
        )
        assert response.confidence == 0.0
        
        response = QueryRoutingResponse(
            query="test",
            selected_categories=["security"],
            reasoning="test",
            confidence=1.0
        )
        assert response.confidence == 1.0


class TestCategoryNode:
    """Tests for CategoryNode dataclass."""
    
    def test_category_node_creation(self):
        """Test creating CategoryNode."""
        node = CategoryNode(
            name="development",
            path="development",
            document_count=5,
            subcategories=[]
        )
        
        assert node.name == "development"
        assert node.path == "development"
        assert node.document_count == 5
        assert node.subcategories == []
    
    def test_category_node_with_subcategories(self):
        """Test CategoryNode with nested subcategories."""
        sub_node = CategoryNode(
            name="testing",
            path="development/testing",
            document_count=2,
            subcategories=[]
        )
        
        parent_node = CategoryNode(
            name="development",
            path="development",
            document_count=5,
            subcategories=[sub_node]
        )
        
        assert len(parent_node.subcategories) == 1
        assert parent_node.subcategories[0].name == "testing"
        assert parent_node.subcategories[0].path == "development/testing"


class TestIntegration:
    """Integration tests for complete workflow."""
    
    def test_end_to_end_query_routing(self, tmp_path):
        """Test complete workflow from filesystem to routing."""
        # Create test directory structure
        (tmp_path / "security").mkdir()
        (tmp_path / "security" / "auth.md").write_text("# Authentication")
        (tmp_path / "development").mkdir()
        (tmp_path / "development" / "api.md").write_text("# API Design")
        
        # Build tree
        tree = build_category_tree(str(tmp_path))
        assert len(tree) == 2
        
        # Mock LLM response
        mock_response = Mock()
        mock_response.text = json.dumps({
            "selected_categories": ["security"],
            "reasoning": "Query is about authentication",
            "confidence": 0.9
        })
        
        with patch('query_router._get_genai_client') as mock_client:
            mock_client.return_value.models.generate_content.return_value = mock_response
            
            # Route query
            result = route_query_to_categories(
                "How does authentication work?",
                tree,
                max_categories=2
            )
        
        assert "security" in result.selected_categories
        assert result.confidence == 0.9
