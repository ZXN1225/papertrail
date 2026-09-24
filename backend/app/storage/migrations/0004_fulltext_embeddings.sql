CREATE TABLE IF NOT EXISTS fulltext_embeddings (
    chunk_id TEXT NOT NULL,
    model TEXT NOT NULL CHECK (length(model) BETWEEN 1 AND 160),
    dimensions INTEGER NOT NULL CHECK (dimensions BETWEEN 1 AND 8192),
    normalization TEXT NOT NULL DEFAULT 'none' CHECK (normalization = 'none'),
    vector_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (chunk_id, model, dimensions),
    FOREIGN KEY (chunk_id) REFERENCES fulltext_chunks(chunk_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fulltext_embeddings_model
    ON fulltext_embeddings(model, dimensions, chunk_id);
