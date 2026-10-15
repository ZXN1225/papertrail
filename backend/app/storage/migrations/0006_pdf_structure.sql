ALTER TABLE fulltext_versions ADD COLUMN parser_version TEXT NOT NULL DEFAULT 'plain-text-v1';
ALTER TABLE fulltext_versions ADD COLUMN source_document_sha256 TEXT;
ALTER TABLE fulltext_chunks ADD COLUMN page_number INTEGER CHECK (page_number IS NULL OR page_number > 0);
ALTER TABLE fulltext_chunks ADD COLUMN element_type TEXT NOT NULL DEFAULT 'paragraph';
ALTER TABLE fulltext_chunks ADD COLUMN section_path TEXT NOT NULL DEFAULT '[]';
ALTER TABLE fulltext_chunks ADD COLUMN bbox_json TEXT;
