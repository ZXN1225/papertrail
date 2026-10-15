ALTER TABLE fulltext_chunks ADD COLUMN retrieval_text TEXT NOT NULL DEFAULT '';
ALTER TABLE fulltext_chunks ADD COLUMN evidence_text TEXT NOT NULL DEFAULT '';
ALTER TABLE fulltext_chunks ADD COLUMN parent_element_id TEXT;

UPDATE fulltext_chunks
SET retrieval_text = text,
    evidence_text = text,
    parent_element_id = element_id;

CREATE INDEX IF NOT EXISTS idx_fulltext_chunks_parent
    ON fulltext_chunks(source_type, source_id, content_sha256, parent_element_id);
