CREATE TABLE user_chunk_embeddings (
    chunk_id TEXT NOT NULL REFERENCES user_document_chunks(chunk_id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions > 0),
    vector_json TEXT NOT NULL,
    PRIMARY KEY (chunk_id, model)
);
