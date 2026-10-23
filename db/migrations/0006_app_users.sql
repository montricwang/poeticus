-- User identity is owned by Poeticus; Clerk IDs are external login credentials.
-- Never store an email address, password, or JWT in this table.
CREATE TABLE app_users (
    id UUID PRIMARY KEY,
    clerk_user_id TEXT NOT NULL UNIQUE CHECK (
        char_length(clerk_user_id) BETWEEN 6 AND 255
        AND left(clerk_user_id, 5) = 'user_'
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
