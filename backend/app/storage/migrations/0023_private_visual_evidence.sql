CREATE TABLE user_document_visual_evidence (
    visual_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    element_id TEXT NOT NULL,
    page_number INTEGER NOT NULL CHECK (page_number >= 1),
    bbox_json TEXT,
    caption TEXT NOT NULL,
    description TEXT NOT NULL CHECK (length(description) BETWEEN 1 AND 2000),
    parser_version TEXT NOT NULL,
    document_sha256 TEXT NOT NULL CHECK (length(document_sha256) = 64),
    created_at TEXT NOT NULL,
    UNIQUE (document_id, element_id),
    FOREIGN KEY (document_id, user_id)
        REFERENCES user_documents(id, user_id) ON DELETE CASCADE
);

CREATE INDEX idx_user_document_visual_evidence_owner
ON user_document_visual_evidence(user_id, document_id, page_number);
