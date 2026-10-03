-- Migration 0002: clarify that the field contains ci-pai, not gong-diao.
-- Renaming preserves the 3491 rows, stored UUIDs and foreign key references.
ALTER TABLE poems RENAME COLUMN tune TO cipai;
ALTER INDEX idx_poems_tune_order RENAME TO idx_poems_cipai_order;
