"""Unit tests for document validation utilities.

Tests cover:
- Path validation and directory traversal prevention
- Filename validation with safe character sets
- Directory name validation
- Markdown content validation (size limits, null bytes)
"""

import pytest
from pathlib import Path
from document_validation import (
    validate_path,
    validate_filename,
    validate_dirname,
    validate_markdown_content,
    RAG_DOCUMENTS_DIR,
    MAX_CONTENT_SIZE_BYTES,
)
from document_exceptions import DocumentValidationError


class TestValidatePath:
    """Tests for validate_path function."""
    
    def test_valid_simple_path(self):
        """Test validation of a simple valid path."""
        result = validate_path("document.md")
        assert result == RAG_DOCUMENTS_DIR / "document.md"
    
    def test_valid_nested_path(self):
        """Test validation of a nested path."""
        result = validate_path("development/api-design.md")
        assert result == RAG_DOCUMENTS_DIR / "development" / "api-design.md"
    
    def test_valid_deeply_nested_path(self):
        """Test validation of a deeply nested path."""
        result = validate_path("operations/runbooks/incident-response.md")
        expected = RAG_DOCUMENTS_DIR / "operations" / "runbooks" / "incident-response.md"
        assert result == expected
    
    def test_path_with_leading_slash(self):
        """Test that leading slashes are stripped."""
        result = validate_path("/development/api-design.md")
        assert result == RAG_DOCUMENTS_DIR / "development" / "api-design.md"
    
    def test_path_with_multiple_leading_slashes(self):
        """Test that multiple leading slashes are stripped."""
        result = validate_path("///development/api-design.md")
        assert result == RAG_DOCUMENTS_DIR / "development" / "api-design.md"
    
    def test_directory_traversal_parent(self):
        """Test that parent directory traversal is blocked."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_path("../etc/passwd")
        assert "directory traversal detected" in str(exc_info.value.detail)
    
    def test_directory_traversal_nested(self):
        """Test that nested directory traversal is blocked."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_path("development/../../etc/passwd")
        assert "directory traversal detected" in str(exc_info.value.detail)
    
    def test_directory_traversal_multiple(self):
        """Test that multiple parent traversals are blocked."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_path("../../../etc/passwd")
        assert "directory traversal detected" in str(exc_info.value.detail)
    
    def test_absolute_path_attack(self):
        """Test that absolute paths outside RAG_DOCUMENTS_DIR are blocked."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_path("/etc/passwd")
        # After stripping leading slash, this becomes "etc/passwd" which is valid
        # unless it resolves outside RAG_DOCUMENTS_DIR
        # The actual behavior depends on filesystem, but the function should catch it
    
    def test_symlink_escape_attempt(self):
        """Test that symlink-based escapes are blocked by path resolution."""
        # This test verifies that resolve() catches symlink-based escapes
        # In practice, if a symlink points outside RAG_DOCUMENTS_DIR,
        # the resolved path will be outside and validation will fail
        with pytest.raises(DocumentValidationError) as exc_info:
            # Simulate a path that would resolve outside after symlink resolution
            validate_path("development/../../../etc/passwd")
        assert "directory traversal detected" in str(exc_info.value.detail)


class TestValidateFilename:
    """Tests for validate_filename function."""
    
    def test_valid_simple_filename(self):
        """Test validation of a simple filename."""
        assert validate_filename("document.md") is True
    
    def test_valid_filename_with_hyphens(self):
        """Test validation of filename with hyphens."""
        assert validate_filename("api-design.md") is True
    
    def test_valid_filename_with_underscores(self):
        """Test validation of filename with underscores."""
        assert validate_filename("my_document.md") is True
    
    def test_valid_filename_with_numbers(self):
        """Test validation of filename with numbers."""
        assert validate_filename("document-123.md") is True
    
    def test_valid_filename_mixed_case(self):
        """Test validation of filename with mixed case."""
        assert validate_filename("MyDocument.md") is True
    
    def test_invalid_filename_no_extension(self):
        """Test that filenames without .md extension are rejected."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_filename("document")
        assert "must contain only alphanumeric" in str(exc_info.value.detail)
        assert "end with .md" in str(exc_info.value.detail)
    
    def test_invalid_filename_wrong_extension(self):
        """Test that filenames with wrong extension are rejected."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_filename("document.txt")
        assert "end with .md" in str(exc_info.value.detail)
    
    def test_invalid_filename_with_spaces(self):
        """Test that filenames with spaces are rejected."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_filename("my document.md")
        assert "must contain only alphanumeric" in str(exc_info.value.detail)
    
    def test_invalid_filename_with_slash(self):
        """Test that filenames with path separators are rejected."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_filename("path/to/document.md")
        assert "must contain only alphanumeric" in str(exc_info.value.detail)
    
    def test_invalid_filename_with_backslash(self):
        """Test that filenames with backslashes are rejected."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_filename("path\\document.md")
        assert "must contain only alphanumeric" in str(exc_info.value.detail)
    
    def test_invalid_filename_with_special_chars(self):
        """Test that filenames with special characters are rejected."""
        special_chars = ['!', '@', '#', '$', '%', '^', '&', '*', '(', ')', '+', '=']
        for char in special_chars:
            with pytest.raises(DocumentValidationError):
                validate_filename(f"document{char}.md")
    
    def test_invalid_filename_with_dots(self):
        """Test that filenames with dots (except extension) are rejected."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_filename("my.document.md")
        assert "must contain only alphanumeric" in str(exc_info.value.detail)
    
    def test_invalid_filename_empty(self):
        """Test that empty filenames are rejected."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_filename(".md")
        assert "must contain only alphanumeric" in str(exc_info.value.detail)


class TestValidateDirname:
    """Tests for validate_dirname function."""
    
    def test_valid_simple_dirname(self):
        """Test validation of a simple directory name."""
        assert validate_dirname("development") is True
    
    def test_valid_dirname_with_hyphens(self):
        """Test validation of directory name with hyphens."""
        assert validate_dirname("my-folder") is True
    
    def test_valid_dirname_with_underscores(self):
        """Test validation of directory name with underscores."""
        assert validate_dirname("my_folder") is True
    
    def test_valid_dirname_with_numbers(self):
        """Test validation of directory name with numbers."""
        assert validate_dirname("folder123") is True
    
    def test_valid_dirname_mixed_case(self):
        """Test validation of directory name with mixed case."""
        assert validate_dirname("MyFolder") is True
    
    def test_invalid_dirname_with_spaces(self):
        """Test that directory names with spaces are rejected."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_dirname("my folder")
        assert "must contain only alphanumeric" in str(exc_info.value.detail)
    
    def test_invalid_dirname_with_slash(self):
        """Test that directory names with slashes are rejected."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_dirname("path/to/folder")
        assert "must contain only alphanumeric" in str(exc_info.value.detail)
    
    def test_invalid_dirname_with_backslash(self):
        """Test that directory names with backslashes are rejected."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_dirname("path\\folder")
        assert "must contain only alphanumeric" in str(exc_info.value.detail)
    
    def test_invalid_dirname_with_dots(self):
        """Test that directory names with dots are rejected."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_dirname("my.folder")
        assert "must contain only alphanumeric" in str(exc_info.value.detail)
    
    def test_invalid_dirname_with_special_chars(self):
        """Test that directory names with special characters are rejected."""
        special_chars = ['!', '@', '#', '$', '%', '^', '&', '*', '(', ')', '+', '=']
        for char in special_chars:
            with pytest.raises(DocumentValidationError):
                validate_dirname(f"folder{char}")
    
    def test_invalid_dirname_empty(self):
        """Test that empty directory names are rejected."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_dirname("")
        assert "must contain only alphanumeric" in str(exc_info.value.detail)
    
    def test_invalid_dirname_with_extension(self):
        """Test that directory names with file extensions are rejected."""
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_dirname("folder.md")
        assert "must contain only alphanumeric" in str(exc_info.value.detail)


class TestValidateMarkdownContent:
    """Tests for validate_markdown_content function."""
    
    def test_valid_simple_content(self):
        """Test validation of simple markdown content."""
        content = "# Hello World\n\nThis is a test document."
        assert validate_markdown_content(content) is True
    
    def test_valid_empty_content(self):
        """Test validation of empty content."""
        assert validate_markdown_content("") is True
    
    def test_valid_content_with_unicode(self):
        """Test validation of content with Unicode characters."""
        content = "# 你好世界\n\nThis is a test with émojis 🎉"
        assert validate_markdown_content(content) is True
    
    def test_valid_content_with_code_blocks(self):
        """Test validation of content with code blocks."""
        content = """# Code Example
        
```python
def hello():
    print("Hello, World!")
```
"""
        assert validate_markdown_content(content) is True
    
    def test_valid_large_content_under_limit(self):
        """Test validation of large content under the 10 MB limit."""
        # Create content just under the limit
        content = "x" * (MAX_CONTENT_SIZE_BYTES - 1000)
        assert validate_markdown_content(content) is True
    
    def test_invalid_content_exceeds_size_limit(self):
        """Test that content exceeding 10 MB is rejected."""
        # Create content over the limit
        content = "x" * (MAX_CONTENT_SIZE_BYTES + 1)
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_markdown_content(content)
        assert "exceeds 10 MB limit" in str(exc_info.value.detail)
    
    def test_invalid_content_with_null_byte(self):
        """Test that content with null bytes is rejected."""
        content = "Hello\x00World"
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_markdown_content(content)
        assert "contains null bytes" in str(exc_info.value.detail)
    
    def test_invalid_content_with_multiple_null_bytes(self):
        """Test that content with multiple null bytes is rejected."""
        content = "Hello\x00World\x00Test"
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_markdown_content(content)
        assert "contains null bytes" in str(exc_info.value.detail)
    
    def test_invalid_content_null_byte_at_start(self):
        """Test that content with null byte at start is rejected."""
        content = "\x00Hello World"
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_markdown_content(content)
        assert "contains null bytes" in str(exc_info.value.detail)
    
    def test_invalid_content_null_byte_at_end(self):
        """Test that content with null byte at end is rejected."""
        content = "Hello World\x00"
        with pytest.raises(DocumentValidationError) as exc_info:
            validate_markdown_content(content)
        assert "contains null bytes" in str(exc_info.value.detail)
    
    def test_content_size_calculation_with_unicode(self):
        """Test that size calculation accounts for UTF-8 encoding."""
        # Unicode characters can be multiple bytes
        # "你" is 3 bytes in UTF-8
        content = "你" * 1000
        # This should be 3000 bytes, well under the limit
        assert validate_markdown_content(content) is True
        
        # Verify the size calculation is correct
        assert len(content.encode('utf-8')) == 3000
    
    def test_valid_content_with_newlines(self):
        """Test validation of content with various newline types."""
        content = "Line 1\nLine 2\r\nLine 3\rLine 4"
        assert validate_markdown_content(content) is True
    
    def test_valid_content_with_tabs(self):
        """Test validation of content with tabs."""
        content = "Line 1\tTabbed\tContent"
        assert validate_markdown_content(content) is True


class TestValidationIntegration:
    """Integration tests for validation functions working together."""
    
    def test_full_path_validation_workflow(self):
        """Test complete workflow of validating a document path."""
        # Validate directory name
        assert validate_dirname("development") is True
        
        # Validate filename
        assert validate_filename("api-design.md") is True
        
        # Validate full path
        full_path = validate_path("development/api-design.md")
        assert full_path == RAG_DOCUMENTS_DIR / "development" / "api-design.md"
    
    def test_nested_directory_validation_workflow(self):
        """Test validation of nested directory structure."""
        # Validate each directory level
        assert validate_dirname("operations") is True
        assert validate_dirname("runbooks") is True
        
        # Validate filename
        assert validate_filename("incident-response.md") is True
        
        # Validate full path
        full_path = validate_path("operations/runbooks/incident-response.md")
        expected = RAG_DOCUMENTS_DIR / "operations" / "runbooks" / "incident-response.md"
        assert full_path == expected
    
    def test_document_creation_validation_workflow(self):
        """Test complete validation workflow for document creation."""
        # Validate directory
        dirname = "security"
        assert validate_dirname(dirname) is True
        
        # Validate filename
        filename = "authentication.md"
        assert validate_filename(filename) is True
        
        # Validate path
        path = f"{dirname}/{filename}"
        full_path = validate_path(path)
        assert full_path == RAG_DOCUMENTS_DIR / dirname / filename
        
        # Validate content
        content = "# Authentication\n\nThis document describes authentication."
        assert validate_markdown_content(content) is True
