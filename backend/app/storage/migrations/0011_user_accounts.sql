CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE user_sessions (
    token_sha256 TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE INDEX idx_user_sessions_user ON user_sessions(user_id, expires_at);

CREATE TABLE user_library_entries (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (source IN ('openalex', 'arxiv')),
    source_id TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE(user_id, source, source_id)
);

CREATE INDEX idx_user_library_owner ON user_library_entries(user_id, added_at DESC);
