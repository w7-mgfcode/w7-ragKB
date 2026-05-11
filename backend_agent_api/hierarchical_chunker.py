"""Hierarchical document chunking for RAG Document Browser.

This module implements multi-level document chunking with three hierarchical levels:
1. Document-level summary (~2048 tokens)
2. Section-level chunks (~512-1024 tokens)
3. Leaf-level chunks (~128-256 tokens)

The chunking strategy includes:
- 10-20% overlap between adjacent chunks at the same level
- Parent-child relationships between levels
- Sibling metadata (count and position)
- Category path extraction from file paths
- LLM-based document summarization with extractive fallback

Token counting uses approximation: 1 token ≈ 4 characters
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

from google import genai

from markdown_parser import parse_markdown, ParsedMarkdown

logger = logging.getLogger(__name__)

# Token approximation: 1 token ≈ 4 characters
CHARS_PER_TOKEN = 4

# Chunk size targets (in tokens)
DOCUMENT_SUMMARY_TOKENS = 2048
SECTION_MIN_TOKENS = 512
SECTION_MAX_TOKENS = 1024
LEAF_MIN_TOKENS = 128
LEAF_MAX_TOKENS = 256

# Overlap percentages
LEAF_OVERLAP_PERCENT = 0.15  # 15% overlap for leaf chunks
SECTION_OVERLAP_PERCENT = 0.15  # 15% overlap for section chunks

# Short document threshold (tokens)
SHORT_DOCUMENT_THRESHOLD = 256

# Lazy-initialized Vertex AI client for summarization
_genai_client = None


def _get_genai_client() -> genai.Client:
    """Return a lazily-initialized Vertex AI genai client."""
    global _genai_client
    if _genai_client is None:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        _genai_client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )
    return _genai_client


def estimate_tokens(text: str) -> int:
    """Estimate token count using character approximation.
    
    Args:
        text: Input text
        
    Returns:
        Estimated token count (1 token ≈ 4 characters)
    """
    return len(text) // CHARS_PER_TOKEN


def tokens_to_chars(tokens: int) -> int:
    """Convert token count to approximate character count.
    
    Args:
        tokens: Number of tokens
        
    Returns:
        Approximate character count
    """
    return tokens * CHARS_PER_TOKEN


def calculate_overlap(chunk_size_chars: int, overlap_percent: float) -> int:
    """Calculate overlap size in characters.
    
    Args:
        chunk_size_chars: Size of chunk in characters
        overlap_percent: Overlap percentage (0.0 to 1.0)
        
    Returns:
        Overlap size in characters
    """
    return int(chunk_size_chars * overlap_percent)


@dataclass
class Section:
    """Represents a document section with heading and content.
    
    Attributes:
        heading: Section heading text (e.g., "## Introduction")
        level: Heading level (1-6)
        content: Section content (text after heading, before next heading)
        start_pos: Character position where section starts in document
    """
    heading: str
    level: int
    content: str
    start_pos: int


def extract_sections(content: str) -> List[Section]:
    """Extract sections from markdown content based on headings.
    
    Parses markdown headings (# through ######) and extracts content
    between headings as sections.
    
    Args:
        content: Markdown content (without frontmatter)
        
    Returns:
        List of Section objects
        
    Examples:
        >>> content = "# Title\\nIntro\\n## Section 1\\nContent 1\\n## Section 2\\nContent 2"
        >>> sections = extract_sections(content)
        >>> len(sections)
        3
        >>> sections[0].heading
        '# Title'
        >>> sections[1].heading
        '## Section 1'
    """
    sections = []
    
    # Pattern to match markdown headings: # through ######
    heading_pattern = r'^(#{1,6})\s+(.+)$'
    
    lines = content.split('\n')
    current_section = None
    current_content_lines = []
    
    for i, line in enumerate(lines):
        match = re.match(heading_pattern, line)
        
        if match:
            # Save previous section if exists
            if current_section is not None:
                current_section.content = '\n'.join(current_content_lines).strip()
                sections.append(current_section)
            
            # Start new section
            hashes = match.group(1)
            heading_text = match.group(2)
            level = len(hashes)
            
            # Calculate start position (approximate)
            start_pos = sum(len(l) + 1 for l in lines[:i])
            
            current_section = Section(
                heading=line,
                level=level,
                content="",
                start_pos=start_pos
            )
            current_content_lines = []
        else:
            # Accumulate content for current section
            if current_section is not None:
                current_content_lines.append(line)
            else:
                # Content before first heading - create implicit section
                if not sections and (line.strip() or current_content_lines):
                    current_content_lines.append(line)
    
    # Save last section
    if current_section is not None:
        current_section.content = '\n'.join(current_content_lines).strip()
        sections.append(current_section)
    elif current_content_lines:
        # Document has content but no headings
        sections.append(Section(
            heading="",
            level=0,
            content='\n'.join(current_content_lines).strip(),
            start_pos=0
        ))
    
    return sections


def chunk_section(
    section_content: str,
    target_min_tokens: int,
    target_max_tokens: int,
    overlap_percent: float
) -> List[str]:
    """Split section content into leaf chunks with overlap.
    
    Args:
        section_content: Text content to chunk
        target_min_tokens: Minimum chunk size in tokens
        target_max_tokens: Maximum chunk size in tokens
        overlap_percent: Overlap percentage (0.0 to 1.0)
        
    Returns:
        List of text chunks
    """
    if not section_content.strip():
        return []
    
    # Convert token targets to character counts
    target_min_chars = tokens_to_chars(target_min_tokens)
    target_max_chars = tokens_to_chars(target_max_tokens)
    
    # Calculate overlap in characters
    overlap_chars = calculate_overlap(target_max_chars, overlap_percent)
    
    # If content is smaller than target, return as single chunk
    if len(section_content) <= target_max_chars:
        return [section_content]
    
    chunks = []
    start = 0
    
    while start < len(section_content):
        # Extract chunk
        end = start + target_max_chars
        chunk = section_content[start:end]
        
        # Try to break at paragraph boundary (double newline)
        if end < len(section_content):
            # Look for paragraph break within last 20% of chunk
            search_start = int(len(chunk) * 0.8)
            para_break = chunk.rfind('\n\n', search_start)
            
            if para_break > 0:
                chunk = chunk[:para_break].strip()
                end = start + para_break
            else:
                # Try to break at sentence boundary
                sentence_break = max(
                    chunk.rfind('. ', search_start),
                    chunk.rfind('.\n', search_start),
                    chunk.rfind('! ', search_start),
                    chunk.rfind('? ', search_start)
                )
                
                if sentence_break > 0:
                    chunk = chunk[:sentence_break + 1].strip()
                    end = start + sentence_break + 1
        
        if chunk.strip():
            chunks.append(chunk.strip())
        
        # Move start position with overlap
        start = end - overlap_chars
        
        # Ensure we make progress
        if start <= chunks[-1] if chunks else 0:
            start = end
    
    return chunks


def generate_document_summary(
    content: str,
    file_path: str,
    parsed: ParsedMarkdown
) -> str:
    """Generate document-level summary using LLM with extractive fallback.
    
    Uses Vertex AI Gemini to generate a concise summary of the document.
    Falls back to extractive summary (first N tokens) if LLM fails.
    
    Args:
        content: Full document content
        file_path: Document file path
        parsed: Parsed markdown document
        
    Returns:
        Document summary (~2048 tokens)
    """
    # Try LLM-based summarization
    try:
        client = _get_genai_client()
        model_name = os.getenv("LLM_CHOICE", "gemini-2.0-flash")
        
        # Build context from frontmatter if available
        context_parts = []
        if parsed.frontmatter:
            if 'title' in parsed.frontmatter:
                context_parts.append(f"Title: {parsed.frontmatter['title']}")
            if 'tags' in parsed.frontmatter:
                tags = parsed.frontmatter['tags']
                if isinstance(tags, list):
                    context_parts.append(f"Tags: {', '.join(tags)}")
                else:
                    context_parts.append(f"Tags: {tags}")
        
        context = '\n'.join(context_parts) if context_parts else ""
        
        # Create summarization prompt
        prompt = f"""Summarize the following document in approximately 500 words. Focus on:
- Main topics and key concepts
- Document structure and organization
- Important information and takeaways

{context}

Document content:
{content[:tokens_to_chars(4000)]}  # Limit input to avoid token limits

Provide a concise, informative summary:"""
        
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "temperature": 0.3,
                "max_output_tokens": 1024,
            }
        )
        
        summary = response.text.strip()
        
        # Verify summary is reasonable length
        if estimate_tokens(summary) > DOCUMENT_SUMMARY_TOKENS * 1.2:
            # Truncate if too long
            summary = summary[:tokens_to_chars(DOCUMENT_SUMMARY_TOKENS)]
        
        logger.info(f"Generated LLM summary for {file_path}")
        return summary
        
    except Exception as e:
        logger.warning(f"LLM summarization failed for {file_path}: {e}. Using extractive fallback.")
        
        # Extractive fallback: first N tokens with metadata
        fallback_parts = []
        
        if parsed.frontmatter:
            if 'title' in parsed.frontmatter:
                fallback_parts.append(f"# {parsed.frontmatter['title']}\n")
        
        # Take first portion of content
        max_chars = tokens_to_chars(DOCUMENT_SUMMARY_TOKENS)
        content_preview = content[:max_chars]
        
        # Try to break at paragraph boundary
        last_para = content_preview.rfind('\n\n')
        if last_para > max_chars * 0.8:
            content_preview = content_preview[:last_para]
        
        fallback_parts.append(content_preview)
        
        return '\n'.join(fallback_parts)


def extract_category_path(file_path: str) -> str:
    """Extract category path from file path relative to rag-documents root.
    
    Args:
        file_path: File path (e.g., "development/testing/unit-tests.md")
        
    Returns:
        Category path (e.g., "development/testing")
        
    Examples:
        >>> extract_category_path("development/api-design.md")
        'development'
        >>> extract_category_path("infrastructure/networking/vpn.md")
        'infrastructure/networking'
        >>> extract_category_path("security.md")
        ''
    """
    # Remove filename to get directory path
    dir_path = os.path.dirname(file_path)
    
    # Normalize path separators
    category = dir_path.replace('\\', '/')
    
    return category


def auto_merge_sibling_chunks(
    chunks: List[Dict[str, Any]],
    merge_threshold: float = 0.5
) -> List[Dict[str, Any]]:
    """Auto-merge sibling chunks when >50% of siblings match a query.
    
    Groups chunks by parent_chunk_id and calculates match rate.
    If more than merge_threshold of siblings are present, returns
    the parent chunk instead of individual leaf chunks.
    
    This function is typically used during search/retrieval to reduce
    fragmentation when multiple adjacent chunks from the same section match.
    
    Args:
        chunks: List of chunk dictionaries (typically leaf-level search results)
        merge_threshold: Minimum match rate to trigger merge (default 0.5 = 50%)
        
    Returns:
        List of chunks with siblings merged into parents where appropriate.
        Merged chunks have 'merged_from_siblings' metadata added.
        
    Example:
        If 3 out of 4 sibling leaf chunks match (75% > 50% threshold),
        return the parent section chunk instead of the 3 individual leaves.
    """
    # Group chunks by parent_id
    parent_groups = defaultdict(list)
    for chunk in chunks:
        parent_id = chunk.get('parent_chunk_id')
        parent_groups[parent_id].append(chunk)
    
    merged_results = []
    
    for parent_id, sibling_chunks in parent_groups.items():
        if parent_id is None:
            # No parent (document-level chunks), return as-is
            merged_results.extend(sibling_chunks)
            continue
        
        # Calculate match rate
        sibling_count = sibling_chunks[0].get('sibling_count', 0)
        if sibling_count == 0:
            # No sibling info, return as-is
            merged_results.extend(sibling_chunks)
            continue
            
        match_count = len(sibling_chunks)
        match_rate = match_count / sibling_count
        
        if match_rate > merge_threshold:
            # Merge: create a parent chunk reference
            # In practice, this would fetch the parent from database
            # For now, we mark the first chunk as representing the merged group
            merged_chunk = sibling_chunks[0].copy()
            merged_chunk['metadata'] = merged_chunk.get('metadata', {}).copy()
            merged_chunk['metadata']['merged_from_siblings'] = True
            merged_chunk['metadata']['merged_leaf_count'] = match_count
            merged_chunk['metadata']['total_sibling_count'] = sibling_count
            merged_chunk['metadata']['match_rate'] = match_rate
            merged_results.append(merged_chunk)
            
            logger.info(
                f"Merged {match_count}/{sibling_count} sibling chunks "
                f"(match_rate={match_rate:.2f}) for parent_id={parent_id}"
            )
        else:
            # Don't merge: return individual chunks
            merged_results.extend(sibling_chunks)
    
    return merged_results


def chunk_document_hierarchical(
    content: str,
    file_path: str,
    file_id: str
) -> List[Dict[str, Any]]:
    """Chunk document into hierarchical levels with parent-child relationships.
    
    Creates three levels of chunks:
    1. Document-level summary (~2048 tokens)
    2. Section-level chunks (~512-1024 tokens)
    3. Leaf-level chunks (~128-256 tokens)
    
    Short documents (< 256 tokens) create only a document-level chunk.
    Documents without sections are split by paragraphs and grouped artificially.
    
    Args:
        content: Full document content (markdown)
        file_path: Document file path relative to rag-documents root
        file_id: Unique document identifier
        
    Returns:
        List of chunk dictionaries with fields:
        - content: Chunk text content
        - chunk_level: 'document', 'section', or 'leaf'
        - parent_chunk_id: Temporary ID of parent chunk (None for document level)
        - category_path: Category extracted from file path
        - sibling_count: Number of sibling chunks at same level
        - sibling_position: Position among siblings (0-indexed)
        - metadata: Additional metadata (file_id, file_path, heading, etc.)
    """
    # Parse markdown
    parsed = parse_markdown(content)
    
    # Extract category from file path
    category_path = extract_category_path(file_path)
    
    # Estimate document size
    doc_tokens = estimate_tokens(parsed.content)
    
    chunks = []
    temp_chunk_id = 0  # Temporary ID for parent-child relationships
    
    # Check if document is short
    if doc_tokens < SHORT_DOCUMENT_THRESHOLD:
        # Create single document-level chunk
        chunks.append({
            'content': content,
            'chunk_level': 'document',
            'parent_chunk_id': None,
            'category_path': category_path,
            'sibling_count': 0,
            'sibling_position': 0,
            'metadata': {
                'file_id': file_id,
                'file_path': file_path,
                'is_short_document': True,
                'token_count': doc_tokens,
            }
        })
        return chunks
    
    # Generate document-level summary
    doc_summary = generate_document_summary(parsed.content, file_path, parsed)
    doc_chunk_id = temp_chunk_id
    temp_chunk_id += 1
    
    chunks.append({
        'content': doc_summary,
        'chunk_level': 'document',
        'parent_chunk_id': None,
        'category_path': category_path,
        'sibling_count': 0,
        'sibling_position': 0,
        'metadata': {
            'file_id': file_id,
            'file_path': file_path,
            'is_summary': True,
            'token_count': estimate_tokens(doc_summary),
        }
    })
    
    # Extract sections
    sections = extract_sections(parsed.content)
    
    if not sections:
        # No sections found - treat entire content as one section
        sections = [Section(
            heading="",
            level=0,
            content=parsed.content,
            start_pos=0
        )]
    
    # Process each section
    section_chunks = []
    
    for section in sections:
        section_text = f"{section.heading}\n{section.content}" if section.heading else section.content
        section_tokens = estimate_tokens(section_text)
        
        # Create section-level chunk
        section_chunk_id = temp_chunk_id
        temp_chunk_id += 1
        
        section_chunks.append({
            'id': section_chunk_id,
            'content': section_text,
            'chunk_level': 'section',
            'parent_chunk_id': doc_chunk_id,
            'category_path': category_path,
            'sibling_count': 0,  # Will be updated after all sections processed
            'sibling_position': len(section_chunks),
            'metadata': {
                'file_id': file_id,
                'file_path': file_path,
                'heading': section.heading,
                'heading_level': section.level,
                'token_count': section_tokens,
            }
        })
        
        # Create leaf-level chunks for this section
        leaf_chunk_texts = chunk_section(
            section.content,
            LEAF_MIN_TOKENS,
            LEAF_MAX_TOKENS,
            LEAF_OVERLAP_PERCENT
        )
        
        for i, leaf_text in enumerate(leaf_chunk_texts):
            chunks.append({
                'content': leaf_text,
                'chunk_level': 'leaf',
                'parent_chunk_id': section_chunk_id,
                'category_path': category_path,
                'sibling_count': len(leaf_chunk_texts),
                'sibling_position': i,
                'metadata': {
                    'file_id': file_id,
                    'file_path': file_path,
                    'section_heading': section.heading,
                    'token_count': estimate_tokens(leaf_text),
                }
            })
    
    # Update sibling counts for section chunks
    for section_chunk in section_chunks:
        section_chunk['sibling_count'] = len(section_chunks)
        chunks.append(section_chunk)
    
    logger.info(
        f"Chunked {file_path}: {len(chunks)} total chunks "
        f"(1 document, {len(section_chunks)} sections, "
        f"{len(chunks) - len(section_chunks) - 1} leaves)"
    )
    
    return chunks
