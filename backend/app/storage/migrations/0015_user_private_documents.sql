CREATE UNIQUE INDEX idx_user_library_entry_owner
ON user_library_entries(id, user_id);

CREATE TABLE user_documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    library_entry_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('openalex', 'arxiv')),
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    document_sha256 TEXT NOT NULL CHECK (length(document_sha256) = 64),
    size_bytes INTEGER NOT NULL CHECK (size_bytes BETWEEN 1 AND 41943040),
    state TEXT NOT NULL CHECK (state IN ('queued', 'processing', 'indexed', 'failed')),
    rights_attested_at TEXT NOT NULL,
    parser_version TEXT,
    error_code TEXT,
    chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    indexed_at TEXT,
    UNIQUE (user_id, source_type, source_id, document_sha256),
    UNIQUE (id, user_id),
    FOREIGN KEY (library_entry_id, user_id)
        REFERENCES user_library_entries(id, user_id) ON DELETE RESTRICT
);

CREATE INDEX idx_user_documents_owner ON user_documents(user_id, created_at DESC);
CREATE INDEX idx_user_documents_state ON user_documents(state, updated_at);

CREATE TABLE user_document_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    retrieval_text TEXT NOT NULL,
    evidence_text TEXT NOT NULL,
    locator TEXT NOT NULL,
    char_start INTEGER NOT NULL CHECK (char_start >= 0),
    char_end INTEGER NOT NULL CHECK (char_end >= char_start),
    page_number INTEGER NOT NULL CHECK (page_number >= 1),
    element_type TEXT NOT NULL,
    section_path TEXT NOT NULL,
    bbox_json TEXT,
    element_id TEXT,
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    UNIQUE (document_id, ordinal),
    FOREIGN KEY (document_id, user_id)
        REFERENCES user_documents(id, user_id) ON DELETE CASCADE
);

CREATE INDEX idx_user_document_chunks_owner
ON user_document_chunks(user_id, document_id, ordinal);
