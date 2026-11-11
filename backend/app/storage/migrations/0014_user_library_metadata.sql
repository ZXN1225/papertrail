ALTER TABLE user_library_entries ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE user_library_entries ADD COLUMN metadata_sha256 TEXT NOT NULL DEFAULT '';
