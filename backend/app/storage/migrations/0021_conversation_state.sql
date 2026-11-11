CREATE TABLE conversation_state (
    conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL DEFAULT 0,
    state_json TEXT NOT NULL DEFAULT '{}'
);
