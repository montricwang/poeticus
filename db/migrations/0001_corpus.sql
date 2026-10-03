-- Migration 0001: reader records + immutable private source evidence.
CREATE TABLE poems (
 id UUID PRIMARY KEY,
 source_record_id TEXT NOT NULL UNIQUE,
 source_order INTEGER NOT NULL UNIQUE CHECK (source_order > 0),
 collection TEXT NOT NULL,
 author TEXT,
 tune TEXT,
 title TEXT,
 yusheng TEXT,
 body_segments JSONB NOT NULL CHECK (jsonb_typeof(body_segments) = 'array'),
 prefaces JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(prefaces) = 'array'),
 inline_notes JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(inline_notes) = 'array'),
 lacunae JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(lacunae) = 'array'),
 review_status TEXT NOT NULL DEFAULT 'imported_unreviewed',
 text_version INTEGER NOT NULL DEFAULT 1 CHECK (text_version > 0)
);
CREATE TABLE poem_source_texts (
 poem_id UUID PRIMARY KEY REFERENCES poems(id) ON DELETE RESTRICT,
 source_record_id TEXT NOT NULL UNIQUE,
 source_title TEXT NOT NULL,
 source_edition TEXT,
 source_locator JSONB,
 original_segments JSONB NOT NULL CHECK (jsonb_typeof(original_segments) = 'array'),
 original_inline_notes JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(original_inline_notes) = 'array'),
 source_sha256 CHAR(64) NOT NULL,
 imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_poems_author_order ON poems(author, source_order);
CREATE INDEX idx_poems_tune_order ON poems(tune, source_order);
