-- Document Corpus uses an isolated schema; do not change the existing poem reader schema.
CREATE SCHEMA IF NOT EXISTS document_corpus;

CREATE TABLE document_corpus.documents (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL UNIQUE,
    author TEXT,
    dynasty TEXT,
    genre TEXT NOT NULL DEFAULT 'literary_criticism',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE TABLE document_corpus.document_versions (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES document_corpus.documents(id) ON DELETE RESTRICT,
    edition_label TEXT NOT NULL,
    source_uri TEXT,
    source_file TEXT NOT NULL,
    source_sha256 CHAR(64) NOT NULL,
    rights_status TEXT NOT NULL DEFAULT 'unreviewed',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, source_sha256),
    UNIQUE (id, document_id)
);

CREATE TABLE document_corpus.document_nodes (
    id UUID PRIMARY KEY,
    version_id UUID NOT NULL REFERENCES document_corpus.document_versions(id) ON DELETE RESTRICT,
    parent_id UUID,
    node_type TEXT NOT NULL CHECK (node_type IN ('volume', 'group', 'section', 'preface', 'postface', 'appendix')),
    source_key TEXT NOT NULL,
    sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
    title TEXT NOT NULL,
    body_text TEXT NOT NULL DEFAULT '',
    content_sha256 CHAR(64) NOT NULL,
    source_locator JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(source_locator) = 'object'),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    UNIQUE (version_id, source_key),
    UNIQUE (version_id, id),
    UNIQUE (version_id, sort_order),
    FOREIGN KEY (version_id, parent_id) REFERENCES document_corpus.document_nodes(version_id, id) ON DELETE RESTRICT,
    CHECK (node_type <> 'section' OR body_text <> '')
);
CREATE INDEX idx_document_nodes_parent_order ON document_corpus.document_nodes(version_id, parent_id, sort_order);

CREATE TABLE document_corpus.retrieval_chunks (
    id UUID PRIMARY KEY,
    node_id UUID NOT NULL REFERENCES document_corpus.document_nodes(id) ON DELETE RESTRICT,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL CHECK (end_offset > start_offset),
    text TEXT NOT NULL CHECK (text <> ''),
    text_sha256 CHAR(64) NOT NULL,
    UNIQUE (node_id, chunk_index)
);
CREATE INDEX idx_retrieval_chunks_node ON document_corpus.retrieval_chunks(node_id);

CREATE TABLE document_corpus.migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
