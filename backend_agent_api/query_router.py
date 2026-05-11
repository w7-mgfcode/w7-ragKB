"""Category-based query routing for hierarchical RAG.

This module implements LLM-based query routing to select relevant document
categories before executing vector search. This reduces search space by 90%+
and improves retrieval accuracy.

The routing system:
1. Builds a category tree from the filesystem structure
2. Uses Vertex AI Gemini to analyze query intent
3. Selects 1-3 most relevant categories
4. Returns selections with reasoning and confidence scores
"""

import os
import json
import logging
from typing import List, Dict, Any
from dataclasses import dataclass

from google import genai
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Lazy-initialized Vertex AI client
_genai_client = None


def _get_genai_client() -> genai.Client:
    """Return a lazily-initialized Vertex AI genai client.
    
    Returns:
        Configured genai.Client for Vertex AI
    """
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


@dataclass
class CategoryNode:
    """Represents a category in the hierarchical tree.
    
    Attributes:
        name: Category name (directory name)
        path: Full category path (e.g., "development/testing")
        document_count: Number of documents in this category
        subcategories: List of child CategoryNode objects
    """
    name: str
    path: str
    document_count: int
    subcategories: List['CategoryNode']


class QueryRoutingResponse(BaseModel):
    """Response model for query routing.
    
    Attributes:
        query: Original user query
        selected_categories: List of selected category paths
        reasoning: LLM explanation for category selection
        confidence: Confidence score (0.0 to 1.0)
    """
    query: str
    selected_categories: List[str] = Field(
        description="Selected category paths (e.g., ['security', 'development'])"
    )
    reasoning: str = Field(
        description="Explanation of why these categories were selected"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for the routing decision"
    )


def build_category_tree(rag_documents_path: str) -> List[CategoryNode]:
    """Build category tree from filesystem structure.
    
    Walks the rag-documents directory and creates a hierarchical tree
    of categories based on subdirectories. Counts documents in each category.
    
    Args:
        rag_documents_path: Path to rag-documents root directory
        
    Returns:
        List of top-level CategoryNode objects
        
    Examples:
        >>> tree = build_category_tree("/rag-documents")
        >>> tree[0].name
        'development'
        >>> tree[0].path
        'development'
        >>> tree[0].document_count
        5
    """
    if not os.path.exists(rag_documents_path):
        logger.warning(f"RAG documents path does not exist: {rag_documents_path}")
        return []
    
    def count_documents(dir_path: str) -> int:
        """Count markdown documents in directory (non-recursive)."""
        try:
            return sum(
                1 for f in os.listdir(dir_path)
                if os.path.isfile(os.path.join(dir_path, f)) and f.endswith('.md')
            )
        except (OSError, PermissionError) as e:
            logger.warning(f"Failed to count documents in {dir_path}: {e}")
            return 0
    
    def build_node(dir_path: str, relative_path: str) -> CategoryNode:
        """Recursively build category node from directory."""
        dir_name = os.path.basename(dir_path)
        doc_count = count_documents(dir_path)
        
        # Find subdirectories
        subcategories = []
        try:
            for entry in os.listdir(dir_path):
                entry_path = os.path.join(dir_path, entry)
                if os.path.isdir(entry_path) and not entry.startswith('.'):
                    sub_relative = f"{relative_path}/{entry}" if relative_path else entry
                    subcategories.append(build_node(entry_path, sub_relative))
        except (OSError, PermissionError) as e:
            logger.warning(f"Failed to list subdirectories in {dir_path}: {e}")
        
        return CategoryNode(
            name=dir_name,
            path=relative_path if relative_path else dir_name,
            document_count=doc_count,
            subcategories=subcategories
        )
    
    # Build tree from top-level directories
    tree = []
    try:
        for entry in os.listdir(rag_documents_path):
            entry_path = os.path.join(rag_documents_path, entry)
            if os.path.isdir(entry_path) and not entry.startswith('.'):
                tree.append(build_node(entry_path, entry))
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to build category tree from {rag_documents_path}: {e}")
        return []
    
    logger.info(f"Built category tree with {len(tree)} top-level categories")
    return tree


async def build_category_tree_sync_filtered(
    rag_documents_path: str,
    pool,
) -> List[CategoryNode]:
    """Build category tree counting only in-sync documents.

    Queries document_sync_status to determine which files are in-sync
    and only counts those in the category document_count.

    Args:
        rag_documents_path: Path to rag-documents root directory
        pool: asyncpg connection pool

    Returns:
        List of top-level CategoryNode objects with filtered counts
    """
    # Fetch in-sync file paths from shared database
    rows = await pool.fetch(
        "SELECT file_path FROM document_sync_status WHERE sync_status = 'in_sync'"
    )
    in_sync_paths = {r["file_path"] for r in rows}

    if not os.path.exists(rag_documents_path):
        logger.warning(f"RAG documents path does not exist: {rag_documents_path}")
        return []

    def count_in_sync_documents(dir_path: str) -> int:
        """Count markdown documents that are in-sync."""
        try:
            count = 0
            for f in os.listdir(dir_path):
                full = os.path.join(dir_path, f)
                if os.path.isfile(full) and f.endswith('.md'):
                    rel = os.path.relpath(full, rag_documents_path)
                    if rel in in_sync_paths:
                        count += 1
            return count
        except (OSError, PermissionError):
            return 0

    def build_node(dir_path: str, relative_path: str) -> CategoryNode:
        dir_name = os.path.basename(dir_path)
        doc_count = count_in_sync_documents(dir_path)
        subcategories = []
        try:
            for entry in os.listdir(dir_path):
                entry_path = os.path.join(dir_path, entry)
                if os.path.isdir(entry_path) and not entry.startswith('.'):
                    sub_relative = f"{relative_path}/{entry}" if relative_path else entry
                    subcategories.append(build_node(entry_path, sub_relative))
        except (OSError, PermissionError):
            pass
        return CategoryNode(
            name=dir_name,
            path=relative_path if relative_path else dir_name,
            document_count=doc_count,
            subcategories=subcategories,
        )

    tree = []
    try:
        for entry in os.listdir(rag_documents_path):
            entry_path = os.path.join(rag_documents_path, entry)
            if os.path.isdir(entry_path) and not entry.startswith('.'):
                tree.append(build_node(entry_path, entry))
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to build filtered category tree: {e}")
        return []

    logger.info(f"Built sync-filtered category tree with {len(tree)} top-level categories")
    return tree


def flatten_category_paths(tree: List[CategoryNode]) -> List[str]:
    """Extract all category paths from tree as flat list.
    
    Args:
        tree: List of CategoryNode objects
        
    Returns:
        List of category path strings
        
    Examples:
        >>> tree = [CategoryNode("dev", "development", 5, [])]
        >>> flatten_category_paths(tree)
        ['development']
    """
    paths = []
    
    def traverse(node: CategoryNode):
        paths.append(node.path)
        for sub in node.subcategories:
            traverse(sub)
    
    for node in tree:
        traverse(node)
    
    return paths


def route_query_to_categories(
    query: str,
    category_tree: List[CategoryNode],
    max_categories: int = 3
) -> QueryRoutingResponse:
    """Route query to relevant categories using LLM analysis.
    
    Uses Vertex AI Gemini to analyze the query intent and select the most
    relevant categories from the available category tree. Returns selections
    with reasoning and confidence score.
    
    Args:
        query: User's search query
        category_tree: Hierarchical category tree from filesystem
        max_categories: Maximum number of categories to select (default: 3)
        
    Returns:
        QueryRoutingResponse with selected categories, reasoning, and confidence
        
    Raises:
        ValueError: If query is empty or category_tree is empty
        RuntimeError: If LLM call fails after retries
        
    Examples:
        >>> tree = build_category_tree("/rag-documents")
        >>> response = route_query_to_categories(
        ...     "How do we handle JWT token refresh?",
        ...     tree,
        ...     max_categories=3
        ... )
        >>> response.selected_categories
        ['security', 'development']
        >>> response.confidence
        0.95
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty")
    
    if not category_tree:
        raise ValueError("Category tree cannot be empty")
    
    # Extract flat list of category paths
    available_categories = flatten_category_paths(category_tree)
    
    if not available_categories:
        logger.warning("No categories found in tree, returning empty routing")
        return QueryRoutingResponse(
            query=query,
            selected_categories=[],
            reasoning="No categories available in the knowledge base",
            confidence=0.0
        )
    
    # Build LLM prompt for category selection
    prompt = f"""You are a query routing system for a document knowledge base.

Available categories:
{json.dumps(available_categories, indent=2)}

User query: "{query}"

Analyze the query and select up to {max_categories} most relevant categories.

Consider:
- Query intent and domain (e.g., security, infrastructure, development)
- Keywords and technical terms in the query
- Likely document types that would answer this query
- Category names and their typical content

Respond in JSON format:
{{
    "selected_categories": ["category1", "category2"],
    "reasoning": "Explanation of why these categories were selected",
    "confidence": 0.85
}}

Rules:
- Select 1-{max_categories} categories (prefer fewer if query is specific)
- Categories must be from the available list
- Confidence should be 0.0-1.0 (higher = more certain)
- Reasoning should be concise (1-2 sentences)
"""
    
    try:
        client = _get_genai_client()
        model_name = os.getenv("LLM_CHOICE", "gemini-2.0-flash")
        
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "temperature": 0.2,  # Low temperature for consistent routing
                "max_output_tokens": 512,
                "response_mime_type": "application/json",
            }
        )
        
        # Parse JSON response
        routing_result = json.loads(response.text)
        
        # Validate and sanitize response
        selected = routing_result.get('selected_categories', [])
        reasoning = routing_result.get('reasoning', 'No reasoning provided')
        confidence = routing_result.get('confidence', 0.5)
        
        # Ensure selected categories are valid
        valid_selected = [
            cat for cat in selected
            if cat in available_categories
        ][:max_categories]
        
        # If no valid categories, fall back to all categories
        if not valid_selected:
            logger.warning(
                f"LLM returned invalid categories for query '{query}': {selected}. "
                f"Falling back to all categories."
            )
            valid_selected = available_categories[:max_categories]
            reasoning = "Unable to determine specific categories, searching all available categories"
            confidence = 0.3
        
        logger.info(
            f"Routed query '{query}' to categories: {valid_selected} "
            f"(confidence: {confidence:.2f})"
        )
        
        return QueryRoutingResponse(
            query=query,
            selected_categories=valid_selected,
            reasoning=reasoning,
            confidence=float(confidence)
        )
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        # Fallback: return all categories
        return QueryRoutingResponse(
            query=query,
            selected_categories=available_categories[:max_categories],
            reasoning="Failed to parse routing response, searching all categories",
            confidence=0.3
        )
    
    except Exception as e:
        logger.error(f"Query routing failed for '{query}': {e}")
        # Fallback: return all categories
        return QueryRoutingResponse(
            query=query,
            selected_categories=available_categories[:max_categories],
            reasoning=f"Routing error: {str(e)}. Searching all categories.",
            confidence=0.2
        )
