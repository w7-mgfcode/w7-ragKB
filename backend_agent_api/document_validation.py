"""Input validation utilities for document operations.

Provides validation functions for paths, filenames, and content to prevent
directory traversal, injection attacks, and malformed input.
"""

import os
import re
from pathlib import Path

from document_exceptions import DocumentValidationError

# RAG documents directory (absolute path)
RAG_DOCUMENTS_DIR = Path(os.getenv("RAG_DOCUMENTS_DIR", "/rag-documents")).resolve()

# Maximum content size: 10 MB
MAX_CONTENT_SIZE = 10 * 1024 * 1024
MAX_CONTENT_SIZE_BYTES = MAX_CONTENT_SIZE  # Alias for compatibility

# Valid filename pattern: alphanumeric, hyphens, underscores, dots
FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

# Valid directory name pattern: alphanumeric, hyphens, underscores
DIRNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")


def validate_path(path: str, base_dir: Path = None) -> Path:
    """Validate and normalize a file path to prevent directory traversal.
    
    Args:
        path: Relative path to validate
        base_dir: Base directory to restrict access to (defaults to RAG_DOCUMENTS_DIR)
        
    Returns:
        Normalized absolute Path within base_dir
        
    Raises:
        DocumentValidationError: If path is invalid or attempts traversal
    """
    if not path:
        raise DocumentValidationError("Path cannot be empty")
    
    # Use RAG_DOCUMENTS_DIR if no base_dir provided
    if base_dir is None:
        base_dir = RAG_DOCUMENTS_DIR
    
    # Remove leading/trailing slashes
    path = path.strip("/")
    
    # Check for null bytes
    if "\x00" in path:
        raise DocumentValidationError("Path contains null bytes")
    
    # Resolve to absolute path
    base_path = Path(base_dir).resolve()
    target_path = (base_path / path).resolve()
    
    # Ensure target is within base directory
    try:
        target_path.relative_to(base_path)
    except ValueError:
        raise DocumentValidationError(
            f"Path traversal detected: {path}"
        )
    
    return target_path


def validate_filename(filename: str) -> str:
    """Validate a filename for safety and correctness.
    
    Args:
        filename: Filename to validate (must end with .md)
        
    Returns:
        Validated filename
        
    Raises:
        DocumentValidationError: If filename is invalid
    """
    if not filename:
        raise DocumentValidationError("Filename cannot be empty")
    
    if not filename.endswith(".md"):
        raise DocumentValidationError("Filename must end with .md")
    
    if not FILENAME_PATTERN.match(filename):
        raise DocumentValidationError(
            "Filename contains invalid characters. "
            "Only alphanumeric, hyphens, underscores, and dots allowed."
        )
    
    if filename.startswith("."):
        raise DocumentValidationError("Filename cannot start with a dot")
    
    if len(filename) > 255:
        raise DocumentValidationError("Filename too long (max 255 characters)")
    
    return filename


def validate_dirname(dirname: str) -> str:
    """Validate a directory name for safety and correctness.
    
    Args:
        dirname: Directory name to validate
        
    Returns:
        Validated directory name
        
    Raises:
        DocumentValidationError: If directory name is invalid
    """
    if not dirname:
        raise DocumentValidationError("Directory name cannot be empty")
    
    if not DIRNAME_PATTERN.match(dirname):
        raise DocumentValidationError(
            "Directory name contains invalid characters. "
            "Only alphanumeric, hyphens, and underscores allowed."
        )
    
    if dirname.startswith("."):
        raise DocumentValidationError("Directory name cannot start with a dot")
    
    if len(dirname) > 255:
        raise DocumentValidationError(
            "Directory name too long (max 255 characters)"
        )
    
    return dirname


def validate_markdown_content(content: str) -> str:
    """Validate markdown content for safety and size limits.
    
    Args:
        content: Markdown content to validate
        
    Returns:
        Validated content
        
    Raises:
        DocumentValidationError: If content is invalid
    """
    if content is None:
        raise DocumentValidationError("Content cannot be None")
    
    # Check for null bytes
    if "\x00" in content:
        raise DocumentValidationError("Content contains null bytes")
    
    # Check size limit
    content_size = len(content.encode("utf-8"))
    if content_size > MAX_CONTENT_SIZE:
        raise DocumentValidationError(
            f"Content too large: {content_size} bytes "
            f"(max {MAX_CONTENT_SIZE} bytes)"
        )
    
    return content


def normalize_line_endings(content: str) -> str:
    """Normalize line endings to LF (Unix style).
    
    Args:
        content: Content with potentially mixed line endings
        
    Returns:
        Content with normalized LF line endings
    """
    # Replace CRLF with LF, then CR with LF
    return content.replace("\r\n", "\n").replace("\r", "\n")
