CREATE TABLE auth_attempts (
    client_key TEXT NOT NULL,
    username_key TEXT NOT NULL,
    attempted_at REAL NOT NULL
);

CREATE INDEX idx_auth_attempts_window
    ON auth_attempts(client_key, username_key, attempted_at);
