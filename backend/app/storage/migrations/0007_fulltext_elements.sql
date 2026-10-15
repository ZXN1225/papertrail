ALTER TABLE fulltext_versions ADD COLUMN parser_warnings_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE fulltext_chunks ADD COLUMN element_id TEXT;
ALTER TABLE fulltext_chunks ADD COLUMN char_offset_scope TEXT NOT NULL DEFAULT 'unknown_legacy';

CREATE TABLE IF NOT EXISTS fulltext_elements (
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    element_id TEXT NOT NULL,
    order_index INTEGER NOT NULL CHECK (order_index >= 0),
    page_number INTEGER NOT NULL CHECK (page_number > 0),
    element_type TEXT NOT NULL,
    element_json TEXT NOT NULL,
    PRIMARY KEY (source_type, source_id, content_sha256, element_id),
    UNIQUE (source_type, source_id, content_sha256, order_index),
    FOREIGN KEY (source_type, source_id, content_sha256)
        REFERENCES fulltext_versions(source_type, source_id, content_sha256) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fulltext_elements_page
    ON fulltext_elements(source_type, source_id, content_sha256, page_number, order_index);
CREATE INDEX IF NOT EXISTS idx_fulltext_chunks_element
    ON fulltext_chunks(source_type, source_id, content_sha256, element_id);
