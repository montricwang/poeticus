-- Optional pgvector migration; run only after the PostgreSQL server provides the vector extension.
-- Does not alter any poem tables and does not create approximate indexes for this small corpus.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_corpus.chunk_embeddings (
    chunk_id UUID NOT NULL REFERENCES document_corpus.retrieval_chunks(id) ON DELETE RESTRICT,
    model_id TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    text_sha256 CHAR(64) NOT NULL,
    PRIMARY KEY (chunk_id, model_id)
);
