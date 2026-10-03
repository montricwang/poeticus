-- Migration 0003: rename He Zhu's author-coined tune heading field.
-- Existing rows, UUIDs and source provenance remain intact.
ALTER TABLE poems RENAME COLUMN yusheng TO yusheng_title;
