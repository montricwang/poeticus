-- Prevent delayed Mem0 extraction from resurrecting memories after consent changes
-- or explicit user edits/deletions. User message timestamps remain immutable.
ALTER TABLE app_users ADD COLUMN memory_reset_at TIMESTAMPTZ;
