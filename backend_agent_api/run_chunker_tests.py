#!/usr/bin/env python
"""Simple test runner for hierarchical_chunker tests."""

import sys
from unittest.mock import Mock, patch

# Import the module
import hierarchical_chunker as hc
from markdown_parser import ParsedMarkdown

def test_token_estimation():
    """Test token estimation functions."""
    print("Testing token estimation...")
    
    # Test estimate_tokens
    assert hc.estimate_tokens("a" * 400) == 100
    assert hc.estimate_tokens("") == 0
    
    # Test tokens_to_chars
    assert hc.tokens_to_chars(100) == 400
    
    # Test calculate_overlap
    assert hc.calculate_overlap(1000, 0.15) == 150
    
    print("✓ Token estimation tests passed")

def test_section_extraction():
    """Test section extraction."""
    print("Testing section extraction...")
    
    content = """# Title
Introduction

## Section 1
Content 1

## Section 2
Content 2"""
    
    sections = hc.extract_sections(content)
    assert len(sections) == 3
    assert sections[0].heading == "# Title"
    assert sections[1].heading == "## Section 1"
    
    print("✓ Section extraction tests passed")

def test_category_extraction():
    """Test category path extraction."""
    print("Testing category extraction...")
    
    assert hc.extract_category_path("development/api-design.md") == "development"
    assert hc.extract_category_path("infra/net/vpn.md") == "infra/net"
    assert hc.extract_category_path("readme.md") == ""
    
    print("✓ Category extraction tests passed")

def test_chunk_section():
    """Test section chunking."""
    print("Testing section chunking...")
    
    # Small content
    small = "Small content."
    chunks = hc.chunk_section(small, hc.LEAF_MIN_TOKENS, hc.LEAF_MAX_TOKENS, 0.15)
    assert len(chunks) == 1
    
    # Large content
    large = "Sentence. " * 200
    chunks = hc.chunk_section(large, hc.LEAF_MIN_TOKENS, hc.LEAF_MAX_TOKENS, 0.15)
    assert len(chunks) > 1
    
    print("✓ Section chunking tests passed")

@patch('hierarchical_chunker.generate_document_summary')
def test_hierarchical_chunking(mock_summary):
    """Test complete hierarchical chunking."""
    print("Testing hierarchical chunking...")
    
    mock_summary.return_value = "Document summary."
    
    # Test short document
    short_content = "# Short\n\nVery short."
    chunks = hc.chunk_document_hierarchical(short_content, "test.md", "file1")
    assert len(chunks) == 1
    assert chunks[0]['chunk_level'] == 'document'
    assert chunks[0]['metadata']['is_short_document'] is True
    
    # Test document with sections
    long_content = """# Title
Intro.

## Section 1
Content 1. """ * 30 + """

## Section 2
Content 2. """ * 30
    
    chunks = hc.chunk_document_hierarchical(long_content, "dev/test.md", "file2")
    assert len(chunks) > 3
    
    # Check levels exist
    levels = set(c['chunk_level'] for c in chunks)
    assert 'document' in levels
    assert 'section' in levels
    
    # Check category
    for chunk in chunks:
        assert chunk['category_path'] == "dev"
    
    # Check required fields
    for chunk in chunks:
        assert 'content' in chunk
        assert 'chunk_level' in chunk
        assert 'parent_chunk_id' in chunk
        assert 'category_path' in chunk
        assert 'sibling_count' in chunk
        assert 'sibling_position' in chunk
        assert 'metadata' in chunk
        assert 'file_id' in chunk['metadata']
        assert 'file_path' in chunk['metadata']
    
    print("✓ Hierarchical chunking tests passed")

def main():
    """Run all tests."""
    print("=" * 60)
    print("Running hierarchical_chunker tests")
    print("=" * 60)
    
    try:
        test_token_estimation()
        test_section_extraction()
        test_category_extraction()
        test_chunk_section()
        test_hierarchical_chunking()
        
        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
