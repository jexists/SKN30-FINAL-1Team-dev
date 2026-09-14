-- Apply before deploying the document RAG code. Existing JSONB is retained for rollback.
BEGIN;
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE public.document_chunk
    ADD COLUMN embedding_vector vector,
    ADD COLUMN embedding_model text,
    ADD CONSTRAINT document_chunk_vector_model_check CHECK (
        (embedding_vector IS NULL AND embedding_model IS NULL)
        OR (embedding_vector IS NOT NULL AND embedding_model IS NOT NULL
            AND vector_dims(embedding_vector) IN (384, 1536))
    );
CREATE INDEX document_chunk_vector_384_idx ON public.document_chunk
    USING hnsw ((embedding_vector::vector(384)) vector_cosine_ops)
    WHERE vector_dims(embedding_vector) = 384;
CREATE INDEX document_chunk_vector_1536_idx ON public.document_chunk
    USING hnsw ((embedding_vector::vector(1536)) vector_cosine_ops)
    WHERE vector_dims(embedding_vector) = 1536;
-- Old arrays have no reliable model identity. Backfill from content, not from unknown vectors.
COMMIT;
