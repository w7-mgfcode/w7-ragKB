-- ==============================================================================
-- Hierarchical RAG Schema Extensions
-- ==============================================================================
-- Adds multi-level chunking support (document/section/leaf) with parent-child
-- relationships, category-based routing, and sibling tracking for auto-merge.
-- ==============================================================================

-- Add hierarchical fields to documents table
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS chunk_level TEXT
        CHECK (chunk_level IN ('document', 'section', 'leaf')),
    ADD COLUMN IF NOT EXISTS parent_chunk_id BIGINT
        REFERENCES documents(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS category_path TEXT,
    ADD COLUMN IF NOT EXISTS sibling_count INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS sibling_position INT DEFAULT 0;

-- Create indexes for hierarchical queries
CREATE INDEX IF NOT EXISTS idx_documents_chunk_level
    ON documents(chunk_level);

CREATE INDEX IF NOT EXISTS idx_documents_parent_chunk_id
    ON documents(parent_chunk_id)
    WHERE parent_chunk_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_category_path
    ON documents(category_path)
    WHERE category_path IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_file_id
    ON documents ((metadata->>'file_id'));

CREATE INDEX IF NOT EXISTS idx_documents_file_path
    ON documents ((metadata->>'file_path'));

-- Composite index for sibling queries
CREATE INDEX IF NOT EXISTS idx_documents_siblings
    ON documents(parent_chunk_id, sibling_position)
    WHERE parent_chunk_id IS NOT NULL;

-- ==============================================================================
-- HELPER FUNCTIONS
-- ==============================================================================

-- List all documents with metadata
CREATE OR REPLACE FUNCTION list_all_documents()
RETURNS TABLE (
    file_id TEXT,
    file_title TEXT,
    file_path TEXT,
    chunk_count BIGINT,
    total_words BIGINT,
    last_modified TIMESTAMP
)
LANGUAGE plpgsql
AS $
BEGIN
    RETURN QUERY
    SELECT 
        metadata->>'file_id' as file_id,
        SPLIT_PART(metadata->>'file_title', ' - ', 1) as file_title,
        metadata->>'file_path' as file_path,
        COUNT(*) as chunk_count,
        SUM(array_length(string_to_array(content, ' '), 1)) as total_words,
        MAX((metadata->>'last_modified')::timestamp) as last_modified
    FROM documents
    WHERE metadata->>'file_id' IS NOT NULL
    GROUP BY metadata->>'file_id', file_title, file_path;
END;
$;

-- Delete all chunks for a document
CREATE OR REPLACE FUNCTION delete_document_chunks(doc_file_id TEXT)
RETURNS VOID
LANGUAGE plpgsql
AS $
BEGIN
    DELETE FROM documents WHERE metadata->>'file_id' = doc_file_id;
END;
$;

-- Search documents by content
CREATE OR REPLACE FUNCTION search_documents_by_content(search_query TEXT)
RETURNS TABLE (
    file_id TEXT,
    file_title TEXT,
    file_path TEXT,
    match_snippet TEXT,
    match_position INT
)
LANGUAGE plpgsql
AS $
BEGIN
    RETURN QUERY
    SELECT 
        metadata->>'file_id' as file_id,
        SPLIT_PART(metadata->>'file_title', ' - ', 1) as file_title,
        metadata->>'file_path' as file_path,
        substring(
            content FROM 
            greatest(1, position(lower(search_query) in lower(content)) - 50)
            FOR 200
        ) as match_snippet,
        position(lower(search_query) in lower(content)) as match_position
    FROM documents
    WHERE lower(content) LIKE '%' || lower(search_query) || '%'
        AND metadata->>'file_id' IS NOT NULL
    GROUP BY metadata->>'file_id', file_title, file_path, content
    LIMIT 100;
END;
$;

-- ==============================================================================
-- SETUP COMPLETE
-- ==============================================================================
-- Added:
--   Columns: chunk_level, parent_chunk_id, category_path, sibling_count,
--            sibling_position
--   Indexes: chunk_level, parent_chunk_id, category_path, file_id, file_path,
--            siblings composite
--   Functions: list_all_documents, delete_document_chunks,
--              search_documents_by_content
-- ==============================================================================
