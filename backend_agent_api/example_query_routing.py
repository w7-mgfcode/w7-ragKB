"""Example usage of query routing module.

This script demonstrates how to use the query routing system to route
queries to relevant document categories.
"""

import os
from query_router import build_category_tree, route_query_to_categories


def main():
    """Demonstrate query routing functionality."""
    # Path to rag-documents directory
    rag_docs_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "rag-documents"
    )
    
    # Build category tree from filesystem
    print("Building category tree...")
    category_tree = build_category_tree(rag_docs_path)
    
    if not category_tree:
        print("No categories found. Please ensure rag-documents directory exists.")
        return
    
    print(f"Found {len(category_tree)} top-level categories:")
    for node in category_tree:
        print(f"  - {node.path} ({node.document_count} documents)")
        for sub in node.subcategories:
            print(f"    - {sub.path} ({sub.document_count} documents)")
    
    # Example queries
    queries = [
        "How do we handle JWT token refresh?",
        "What's our deployment process?",
        "API rate limiting implementation",
        "Database backup procedures",
    ]
    
    print("\nRouting example queries:")
    print("=" * 60)
    
    for query in queries:
        print(f"\nQuery: {query}")
        
        try:
            response = route_query_to_categories(
                query=query,
                category_tree=category_tree,
                max_categories=3
            )
            
            print(f"Selected categories: {', '.join(response.selected_categories)}")
            print(f"Reasoning: {response.reasoning}")
            print(f"Confidence: {response.confidence:.2f}")
            
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
