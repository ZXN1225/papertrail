CREATE TABLE IF NOT EXISTS fulltext_documents (
    source_type TEXT NOT NULL CHECK (source_type IN ('openalex', 'arxiv')),
    source_id TEXT NOT NULL,
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 500),
    source_url TEXT NOT NULL,
    current_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status = 'approved'),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (source_type, source_id)
);

CREATE TABLE IF NOT EXISTS fulltext_versions (
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    source_text_sha256 TEXT NOT NULL,
    text_content TEXT NOT NULL,
    license_id TEXT NOT NULL CHECK (license_id IN ('CC0-1.0', 'CC-BY-4.0')),
    license_url TEXT NOT NULL,
    license_evidence_url TEXT NOT NULL,
    text_source_url TEXT NOT NULL,
    license_reviewed_at TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    attribution TEXT NOT NULL CHECK (length(attribution) BETWEEN 1 AND 500),
    chunker_version TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    PRIMARY KEY (source_type, source_id, content_sha256),
    FOREIGN KEY (source_type, source_id)
        REFERENCES fulltext_documents(source_type, source_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fulltext_chunks (
    chunk_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    title TEXT NOT NULL,
    locator TEXT NOT NULL,
    char_start INTEGER NOT NULL CHECK (char_start >= 0),
    char_end INTEGER NOT NULL CHECK (char_end > char_start),
    text TEXT NOT NULL CHECK (length(text) BETWEEN 1 AND 2000),
    UNIQUE (source_type, source_id, content_sha256, ordinal),
    FOREIGN KEY (source_type, source_id, content_sha256)
        REFERENCES fulltext_versions(source_type, source_id, content_sha256) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fulltext_deletion_events (
    event_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('openalex', 'arxiv')),
    source_id TEXT NOT NULL,
    deleted_content_sha256 TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (length(reason) BETWEEN 3 AND 500),
    deleted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fulltext_active
    ON fulltext_documents(status, source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_fulltext_chunks_doc
    ON fulltext_chunks(source_type, source_id, content_sha256, ordinal);
