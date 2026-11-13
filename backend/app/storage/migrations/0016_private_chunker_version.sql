ALTER TABLE user_documents ADD COLUMN chunker_version TEXT;

UPDATE user_documents
SET state='failed', error_code='reindex_required', updated_at=datetime('now')
WHERE state='indexed';
