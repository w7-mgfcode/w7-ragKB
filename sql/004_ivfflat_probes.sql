-- Improve RAG retrieval reliability on IVFFlat by increasing probes.
-- This prevents zero-hit results on semantically valid queries.

CREATE OR REPLACE FUNCTION match_documents(
    query_embedding vector(768),
    match_count     INT  DEFAULT 4,
    filter          JSONB DEFAULT '{}'
)
RETURNS TABLE (
    id         BIGINT,
    content    TEXT,
    metadata   JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM set_config('ivfflat.probes', '20', true);

    RETURN QUERY
    SELECT
        d.id,
        d.content,
        d.metadata,
        1 - (d.embedding <=> query_embedding) AS similarity
    FROM documents d
    WHERE d.metadata @> filter
    ORDER BY d.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
