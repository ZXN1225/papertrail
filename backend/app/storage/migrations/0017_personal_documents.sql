CREATE TABLE user_documents_new (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    library_entry_id TEXT,
    source_type TEXT NOT NULL CHECK (source_type IN ('openalex', 'arxiv', 'personal')),
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
    chunker_version TEXT,
    UNIQUE (user_id, source_type, source_id, document_sha256),
    UNIQUE (id, user_id),
    CHECK ((source_type = 'personal' AND library_entry_id IS NULL AND source_id = id AND source_url = '') OR
           (source_type != 'personal' AND library_entry_id IS NOT NULL)),
    FOREIGN KEY (library_entry_id, user_id)
        REFERENCES user_library_entries(id, user_id) ON DELETE RESTRICT
);

INSERT INTO user_documents_new
SELECT id,user_id,library_entry_id,source_type,source_id,title,source_url,
       original_filename,storage_key,document_sha256,size_bytes,state,
       rights_attested_at,parser_version,error_code,chunk_count,created_at,
       updated_at,indexed_at,chunker_version FROM user_documents;

DROP TABLE user_documents;
ALTER TABLE user_documents_new RENAME TO user_documents;
CREATE INDEX idx_user_documents_owner ON user_documents(user_id, created_at DESC);
CREATE INDEX idx_user_documents_state ON user_documents(state, updated_at);
