"""Hierarchical document chunking for RAG.

Implements multi-level chunking strategy:
- Document level: ~2048 tokens (full document summary)
- Section level: ~512-1024 tokens (major sections)
- Leaf level: ~128-256 tokens (paragraphs)

With 10-20% overlap between adjacent chunks at each level.
"""

import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path


# Token estimation: ~4 characters per token (rough approximation)
CHARS_PER_TOKEN = 4

# Target sizes in tokens
DOCUMENT_LEVEL_TOKENS = 2048
SECTION_LEVEL_TOKENS = 768  # Mid-range of 512-1024
LEAF_LEVEL_TOKENS = 192     # Mid-range of 128-256

# Overlap percentages
LEAF_OVERLAP_PERCENT = 0.15    # 15% overlap
SECTION_OVERLAP_PERCENT = 0.15  # 15% overlap

# Convert to character counts
DOCUMENT_LEVEL_CHARS = DOCUMENT_LEVEL_TOKENS * CHARS_PER_TOKEN
SECTION_LEVEL_CHARS = SECTION_LEVEL_TOKENS * CHARS_PER_TOKEN
LEAF_LEVEL_CHARS = LEAF_LEVEL_TOKENS * CHARS_PER_TOKEN

LEAF_OVERLAP_CHARS = int(LEAF_LEVEL_CHARS * LEAF_OVERLAP_PERCENT)
SECTION_OVERLAP_CHARS = int(SECTION_LEVEL_CHARS * SECTION_OVERLAP_PERCENT)


def extract_category_from_path(file_path: str) -> str:
    """Extract category path from file path.
    
    Args:
        file_path: File path relative to rag-documents root
        
    Returns:
        Category path (e.g., "development/testing")
    """
    path = Path(file_path)
    # Remove filename, keep directory path
    if len(path.parts) > 1:
        return "/".join(path.parts[:-1])
    return ""


def split_into_sections(content: str) -> List[str]:
    """Split markdown content into sections based on headings.
    
    Args:
        content: Markdown content
        
    Returns:
        List of section strings (including heading)
    """
    # Split on markdown headings (# through ######)
    heading_pattern = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)
    
    sections = []
    current_section = []
    
    for line in content.split("\n"):
        if heading_pattern.match(line):
            # Save previous section if exists
            if current_section:
                sections.append("\n".join(current_section))
            # Start new section with heading
            current_section = [line]
        else:
            current_section.append(line)
    
    # Add final section
    if current_section:
        sections.append("\n".join(current_section))
    
    return sections


def split_into_paragraphs(text: str) -> List[str]:
    """Split text into paragraphs (separated by blank lines).
    
    Args:
        text: Text content
        
    Returns:
        List of paragraph strings
    """
    # Split on double newlines (blank lines)
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


def chunk_with_overlap(
    items: List[str],
    target_size: int,
    overlap_size: int
) -> List[str]:
    """Combine items into chunks with overlap.
    
    Args:
        items: List of text items to chunk
        target_size: Target chunk size in characters
        overlap_size: Overlap size in characters
        
    Returns:
        List of chunk strings
    """
    chunks = []
    current_chunk = []
    current_size = 0
    
    for item in items:
        item_size = len(item)
        
        # If adding this item exceeds target, save current chunk
        if current_size + item_size > target_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            
            # Start new chunk with overlap from previous chunk
            overlap_text = "\n\n".join(current_chunk)
            if len(overlap_text) > overlap_size:
                # Take last overlap_size characters
                overlap_text = overlap_text[-overlap_size:]
                # Find paragraph boundary
                boundary = overlap_text.find("\n\n")
                if boundary > 0:
                    overlap_text = overlap_text[boundary+2:]
            
            current_chunk = [overlap_text] if overlap_text else []
            current_size = len(overlap_text)
        
        current_chunk.append(item)
        current_size += item_size
    
    # Add final chunk
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    
    return chunks


def generate_document_summary(content: str, max_chars: int) -> str:
    """Generate document-level summary.
    
    For now, just takes the first max_chars. In production, this could
    use an LLM to generate a proper summary.
    
    Args:
        content: Full document content
        max_chars: Maximum summary length
        
    Returns:
        Document summary
    """
    if len(content) <= max_chars:
        return content
    
    # Take first max_chars and try to end at paragraph boundary
    summary = content[:max_chars]
    last_para = summary.rfind("\n\n")
    if last_para > max_chars * 0.8:  # If we're close to target
        summary = summary[:last_para]
    
    return summary + "\n\n[Document continues...]"


def chunk_document_hierarchical(
    content: str,
    file_path: str,
    file_id: str,
    file_title: str
) -> List[Dict]:
    """Chunk document into hierarchical levels.
    
    Args:
        content: Document content
        file_path: File path relative to rag-documents
        file_id: Unique file identifier
        file_title: Document title
        
    Returns:
        List of chunk dicts with metadata for database insertion
    """
    chunks = []
    category_path = extract_category_from_path(file_path)
    
    # Level 1: Document summary
    doc_summary = generate_document_summary(content, DOCUMENT_LEVEL_CHARS)
    doc_chunk = {
        "content": doc_summary,
        "chunk_level": "document",
        "parent_chunk_id": None,
        "category_path": category_path,
        "sibling_count": 0,
        "sibling_position": 0,
        "metadata": {
            "file_id": file_id,
            "file_path": file_path,
            "file_title": file_title,
            "chunk_type": "document_summary"
        }
    }
    chunks.append(doc_chunk)
    
    # Level 2: Sections
    sections = split_into_sections(content)
    section_chunks = []
    
    for section in sections:
        if len(section) > SECTION_LEVEL_CHARS:
            # Split large sections
            paragraphs = split_into_paragraphs(section)
            section_parts = chunk_with_overlap(
                paragraphs,
                SECTION_LEVEL_CHARS,
                SECTION_OVERLAP_CHARS
            )
            section_chunks.extend(section_parts)
        else:
            section_chunks.append(section)
    
    # Add section chunks with sibling metadata
    section_chunk_dicts = []
    for i, section_content in enumerate(section_chunks):
        section_chunk = {
            "content": section_content,
            "chunk_level": "section",
            "parent_chunk_id": None,  # Will be set after doc chunk inserted
            "category_path": category_path,
            "sibling_count": len(section_chunks),
            "sibling_position": i,
            "metadata": {
                "file_id": file_id,
                "file_path": file_path,
                "file_title": f"{file_title} - Section {i+1}",
                "chunk_type": "section"
            }
        }
        section_chunk_dicts.append(section_chunk)
        chunks.append(section_chunk)
    
    # Level 3: Leaf chunks (paragraphs within sections)
    for section_idx, section_content in enumerate(section_chunks):
        paragraphs = split_into_paragraphs(section_content)
        leaf_chunks_for_section = chunk_with_overlap(
            paragraphs,
            LEAF_LEVEL_CHARS,
            LEAF_OVERLAP_CHARS
        )
        
        for i, leaf_content in enumerate(leaf_chunks_for_section):
            leaf_chunk = {
                "content": leaf_content,
                "chunk_level": "leaf",
                "parent_chunk_id": None,  # Will be set after section inserted
                "parent_section_idx": section_idx,  # Temp field for linking
                "category_path": category_path,
                "sibling_count": len(leaf_chunks_for_section),
                "sibling_position": i,
                "metadata": {
                    "file_id": file_id,
                    "file_path": file_path,
                    "file_title": f"{file_title} - Chunk {i+1}",
                    "chunk_type": "leaf"
                }
            }
            chunks.append(leaf_chunk)
    
    return chunks
