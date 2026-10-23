-- Private Poeticus data is keyed by internal users.id, never client-reported Clerk IDs.
ALTER TABLE app_users
    ADD COLUMN memory_opt_in BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE app_conversations (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    poem_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_app_conversations_user_recent
    ON app_conversations(user_id, updated_at DESC);

CREATE TABLE app_messages (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES app_conversations(id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL CHECK (turn_number > 0),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL CHECK (char_length(content) BETWEEN 1 AND 12000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, turn_number, role)
);
CREATE INDEX idx_app_messages_conversation_turn
    ON app_messages(conversation_id, turn_number, role);
