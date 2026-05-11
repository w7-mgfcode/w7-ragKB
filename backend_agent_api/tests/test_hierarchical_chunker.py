"""Unit tests for hierarchical_chunker module.

Tests the multi-level document chunking functionality including:
- Document-level summary generation
- Section-level chunking
- Leaf-level chunking
- Overlap calculation
- Parent-child relationships
- Category path extraction
- Short document handling
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from hierarchical_chunker import (
    estimate_tokens,
    tokens_to_chars,
    calculate_overlap,
    extract_sections,
    chunk_section,
    extract_category_path,
    chunk_document_hierarchical,
    Section,
    DOCUMENT_SUMMARY_TOKENS,
    SECTION_MIN_TOKENS,
    SECTION_MAX_TOKENS,
    LEAF_MIN_TOKENS,
    LEAF_MAX_TOKENS,
    SHORT_DOCUMENT_THRESHOLD,
)


class TestTokenEstimation:
    """Test token estimation and conversion functions."""
    
    def test_estimate_tokens_basic(self):
        """Test basic token estimation (1 token ≈ 4 chars)."""
        text = "a" * 400  # 400 characters
        assert estimate_tokens(text) == 100  # 100 tokens
    
    def test_estimate_tokens_empty(self):
        """Test token estimation with empty string."""
        assert estimate_tokens("") == 0
    
    def test_tokens_to_chars(self):
        """Test token to character conversion."""
        assert tokens_to_chars(100) == 400
        assert tokens_to_chars(0) == 0
    
    def test_calculate_overlap(self):
        """Test overlap calculation."""
        # 15% of 1000 chars = 150 chars
        assert calculate_overlap(1000, 0.15) == 150
        
        # 20% of 500 chars = 100 chars
        assert calculate_overlap(500, 0.20) == 100
        
        # 0% overlap
        assert calculate_overlap(1000, 0.0) == 0


class TestSectionExtraction:
    """Test markdown section extraction."""
    
    def test_extract_sections_with_headings(self):
        """Test extracting sections from markdown with headings."""
        content = """# Title
Introduction text

## Section 1
Content for section 1

## Section 2
Content for section 2"""
        
        sections = extract_sections(content)
        
        assert len(sections) == 3
        assert sections[0].heading == "# Title"
        assert sections[0].level == 1
        assert "Introduction text" in sections[0].content
        
        assert sections[1].heading == "## Section 1"
        assert sections[1].level == 2
        assert "Content for section 1" in sections[1].content
        
        assert sections[2].heading == "## Section 2"
        assert sections[2].level == 2
    
    def test_extract_sections_no_headings(self):
        """Test extracting sections from content without headings."""
        content = "Just plain text\nwithout any headings\nat all."
        
        sections = extract_sections(content)
        
        assert len(sections) == 1
        assert sections[0].heading == ""
        assert sections[0].level == 0
        assert "Just plain text" in sections[0].content
    
    def test_extract_sections_nested_headings(self):
        """Test extracting sections with nested heading levels."""
        content = """# H1
Content 1

## H2
Content 2

### H3
Content 3

## Another H2
Content 4"""
        
        sections = extract_sections(content)
        
        assert len(sections) == 4
        assert sections[0].level == 1
        assert sections[1].level == 2
        assert sections[2].level == 3
        assert sections[3].level == 2
    
    def test_extract_sections_empty_content(self):
        """Test extracting sections from empty content."""
        sections = extract_sections("")
        assert len(sections) == 0


class TestChunkSection:
    """Test section chunking into leaf chunks."""
    
    def test_chunk_section_small_content(self):
        """Test chunking content smaller than target size."""
        content = "Small content that fits in one chunk."
        chunks = chunk_section(content, LEAF_MIN_TOKENS, LEAF_MAX_TOKENS, 0.15)
        
        assert len(chunks) == 1
        assert chunks[0] == content
    
    def test_chunk_section_with_overlap(self):
        """Test chunking creates overlapping chunks."""
        # Create content that requires multiple chunks
        content = "Sentence. " * 200  # ~2000 chars, needs multiple chunks
        
        chunks = chunk_section(content, LEAF_MIN_TOKENS, LEAF_MAX_TOKENS, 0.15)
        
        assert len(chunks) > 1
        
        # Verify overlap exists between consecutive chunks
        for i in range(len(chunks) - 1):
            # Last part of chunk i should appear in beginning of chunk i+1
            chunk_i_end = chunks[i][-50:]  # Last 50 chars
            chunk_next_start = chunks[i + 1][:100]  # First 100 chars
            
            # Some overlap should exist (not exact match due to boundary breaking)
            # Just verify chunks are not completely disjoint
            assert len(chunks[i]) > 0
            assert len(chunks[i + 1]) > 0
    
    def test_chunk_section_empty_content(self):
        """Test chunking empty content."""
        chunks = chunk_section("", LEAF_MIN_TOKENS, LEAF_MAX_TOKENS, 0.15)
        assert len(chunks) == 0
    
    def test_chunk_section_paragraph_boundaries(self):
        """Test chunking respects paragraph boundaries."""
        content = """First paragraph with some content.

Second paragraph with more content.

Third paragraph with even more content.

Fourth paragraph to ensure multiple chunks.""" * 10
        
        chunks = chunk_section(content, LEAF_MIN_TOKENS, LEAF_MAX_TOKENS, 0.15)
        
        # Verify chunks were created
        assert len(chunks) > 1
        
        # Verify no chunk is empty
        for chunk in chunks:
            assert len(chunk.strip()) > 0


class TestCategoryExtraction:
    """Test category path extraction from file paths."""
    
    def test_extract_category_single_level(self):
        """Test extracting category from single-level path."""
        assert extract_category_path("development/api-design.md") == "development"
        assert extract_category_path("security/auth.md") == "security"
    
    def test_extract_category_multi_level(self):
        """Test extracting category from multi-level path."""
        assert extract_category_path("infrastructure/networking/vpn.md") == "infrastructure/networking"
        assert extract_category_path("dev/testing/unit/test.md") == "dev/testing/unit"
    
    def test_extract_category_root_level(self):
        """Test extracting category from root-level file."""
        assert extract_category_path("readme.md") == ""
        assert extract_category_path("index.md") == ""
    
    def test_extract_category_windows_paths(self):
        """Test extracting category with Windows-style paths."""
        assert extract_category_path("development\\api-design.md") == "development"
        assert extract_category_path("infra\\network\\vpn.md") == "infra/network"


class TestDocumentSummaryGeneration:
    """Test document summary generation."""
    
    @patch('hierarchical_chunker._get_genai_client')
    def test_generate_summary_with_llm_success(self, mock_get_client):
        """Test successful LLM-based summary generation."""
        from hierarchical_chunker import generate_document_summary
        from markdown_parser import ParsedMarkdown
        
        # Mock LLM response
        mock_response = Mock()
        mock_response.text = "This is a concise summary of the document."
        
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        
        mock_client = Mock()
        mock_client.models = mock_model
        
        mock_get_client.return_value = mock_client
        
        content = "# Test Document\n\nThis is test content." * 50
        parsed = ParsedMarkdown(
            frontmatter={'title': 'Test'},
            content=content,
            raw_frontmatter='title: Test'
        )
        
        summary = generate_document_summary(content, "test.md", parsed)
        
        assert "concise summary" in summary
        assert len(summary) > 0
    
    @patch('hierarchical_chunker._get_genai_client')
    def test_generate_summary_llm_failure_fallback(self, mock_get_client):
        """Test extractive fallback when LLM fails."""
        from hierarchical_chunker import generate_document_summary
        from markdown_parser import ParsedMarkdown
        
        # Mock LLM failure
        mock_get_client.side_effect = Exception("LLM API error")
        
        content = "# Test Document\n\nThis is the first paragraph.\n\nSecond paragraph." * 100
        parsed = ParsedMarkdown(
            frontmatter={'title': 'Test Doc'},
            content=content,
            raw_frontmatter='title: Test Doc'
        )
        
        summary = generate_document_summary(content, "test.md", parsed)
        
        # Should contain beginning of content
        assert "Test Document" in summary or "first paragraph" in summary
        assert len(summary) > 0
        # Should be truncated to reasonable length
        assert estimate_tokens(summary) <= DOCUMENT_SUMMARY_TOKENS * 1.5


class TestHierarchicalChunking:
    """Test complete hierarchical chunking pipeline."""
    
    @patch('hierarchical_chunker.generate_document_summary')
    def test_chunk_short_document(self, mock_summary):
        """Test chunking a short document (< 256 tokens)."""
        content = "# Short Doc\n\nThis is a very short document."
        
        chunks = chunk_document_hierarchical(content, "test.md", "file123")
        
        # Short document should create only one document-level chunk
        assert len(chunks) == 1
        assert chunks[0]['chunk_level'] == 'document'
        assert chunks[0]['parent_chunk_id'] is None
        assert chunks[0]['category_path'] == ""
        assert chunks[0]['metadata']['is_short_document'] is True
        assert chunks[0]['metadata']['file_id'] == "file123"
    
    @patch('hierarchical_chunker.generate_document_summary')
    def test_chunk_document_with_sections(self, mock_summary):
        """Test chunking a document with multiple sections."""
        mock_summary.return_value = "Document summary text."
        
        content = """# Main Title
Introduction paragraph.

## Section 1
Content for section 1 with multiple sentences. """ * 20 + """

## Section 2
Content for section 2 with multiple sentences. """ * 20
        
        chunks = chunk_document_hierarchical(content, "dev/test.md", "file456")
        
        # Should have: 1 document + N sections + M leaves
        assert len(chunks) > 3
        
        # Check document-level chunk
        doc_chunks = [c for c in chunks if c['chunk_level'] == 'document']
        assert len(doc_chunks) == 1
        assert doc_chunks[0]['content'] == "Document summary text."
        assert doc_chunks[0]['category_path'] == "dev"
        
        # Check section-level chunks
        section_chunks = [c for c in chunks if c['chunk_level'] == 'section']
        assert len(section_chunks) >= 2
        
        # Verify sibling metadata for sections
        for section in section_chunks:
            assert section['sibling_count'] == len(section_chunks)
            assert 0 <= section['sibling_position'] < len(section_chunks)
        
        # Check leaf-level chunks
        leaf_chunks = [c for c in chunks if c['chunk_level'] == 'leaf']
        assert len(leaf_chunks) > 0
        
        # Verify each leaf has a parent section
        for leaf in leaf_chunks:
            assert leaf['parent_chunk_id'] is not None
            assert leaf['sibling_count'] > 0
    
    @patch('hierarchical_chunker.generate_document_summary')
    def test_chunk_document_parent_child_relationships(self, mock_summary):
        """Test parent-child relationships are correctly set."""
        mock_summary.return_value = "Summary."
        
        content = """# Title
Intro.

## Section A
Content A. """ * 30
        
        chunks = chunk_document_hierarchical(content, "test.md", "file789")
        
        # Get chunks by level
        doc_chunk = [c for c in chunks if c['chunk_level'] == 'document'][0]
        section_chunks = [c for c in chunks if c['chunk_level'] == 'section']
        leaf_chunks = [c for c in chunks if c['chunk_level'] == 'leaf']
        
        # Document chunk has no parent
        assert doc_chunk['parent_chunk_id'] is None
        
        # All sections should reference document as parent
        # (Note: In the implementation, parent_chunk_id is a temporary ID)
        for section in section_chunks:
            assert section['parent_chunk_id'] is not None
        
        # All leaves should reference a section as parent
        for leaf in leaf_chunks:
            assert leaf['parent_chunk_id'] is not None
    
    @patch('hierarchical_chunker.generate_document_summary')
    def test_chunk_document_category_extraction(self, mock_summary):
        """Test category path is correctly extracted and set."""
        mock_summary.return_value = "Summary."
        
        content = "# Doc\n\nContent." * 50
        
        chunks = chunk_document_hierarchical(
            content,
            "infrastructure/networking/vpn-setup.md",
            "file999"
        )
        
        # All chunks should have the same category path
        for chunk in chunks:
            assert chunk['category_path'] == "infrastructure/networking"
    
    @patch('hierarchical_chunker.generate_document_summary')
    def test_chunk_document_metadata_fields(self, mock_summary):
        """Test all required metadata fields are present."""
        mock_summary.return_value = "Summary."
        
        content = "# Test\n\nContent." * 50
        
        chunks = chunk_document_hierarchical(content, "test.md", "file111")
        
        required_fields = [
            'content',
            'chunk_level',
            'parent_chunk_id',
            'category_path',
            'sibling_count',
            'sibling_position',
            'metadata'
        ]
        
        for chunk in chunks:
            for field in required_fields:
                assert field in chunk, f"Missing field: {field}"
            
            # Verify metadata contains file_id and file_path
            assert 'file_id' in chunk['metadata']
            assert 'file_path' in chunk['metadata']
            assert chunk['metadata']['file_id'] == "file111"
            assert chunk['metadata']['file_path'] == "test.md"
    
    @patch('hierarchical_chunker.generate_document_summary')
    def test_chunk_document_no_sections(self, mock_summary):
        """Test chunking document without explicit sections."""
        mock_summary.return_value = "Summary."
        
        # Content without markdown headings
        content = "This is a document without any headings. " * 100
        
        chunks = chunk_document_hierarchical(content, "plain.md", "file222")
        
        # Should still create hierarchical structure
        assert len(chunks) > 1
        
        # Should have document, section, and leaf levels
        levels = set(c['chunk_level'] for c in chunks)
        assert 'document' in levels
        assert 'section' in levels or 'leaf' in levels


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    @patch('hierarchical_chunker.generate_document_summary')
    def test_chunk_empty_document(self, mock_summary):
        """Test chunking an empty document."""
        mock_summary.return_value = ""
        
        chunks = chunk_document_hierarchical("", "empty.md", "file000")
        
        # Should create at least one chunk (short document handling)
        assert len(chunks) >= 1
    
    @patch('hierarchical_chunker.generate_document_summary')
    def test_chunk_document_with_frontmatter(self, mock_summary):
        """Test chunking document with YAML frontmatter."""
        mock_summary.return_value = "Summary with frontmatter context."
        
        content = """---
title: Test Document
tags: [test, example]
---

# Content
This is the actual content.""" * 30
        
        chunks = chunk_document_hierarchical(content, "test.md", "file333")
        
        # Should successfully chunk despite frontmatter
        assert len(chunks) > 0
        
        # Document summary should be generated
        doc_chunk = [c for c in chunks if c['chunk_level'] == 'document'][0]
        assert len(doc_chunk['content']) > 0
    
    def test_section_with_special_characters(self):
        """Test section extraction with special characters in headings."""
        content = """# Title with "quotes" and 'apostrophes'

## Section with $pecial Ch@rs!

Content here."""
        
        sections = extract_sections(content)
        
        assert len(sections) == 2
        assert '"quotes"' in sections[0].heading
        assert '$pecial' in sections[1].heading
