CREATE TABLE import_snapshots_new (
    snapshot_id TEXT PRIMARY KEY,
    source TEXT NOT NULL CHECK (source = 'openalex'),
    source_endpoint TEXT NOT NULL CHECK (source_endpoint = 'https://api.openalex.org/works'),
    query TEXT NOT NULL,
    page INTEGER NOT NULL CHECK (page >= 1),
    per_page INTEGER NOT NULL CHECK (per_page BETWEEN 1 AND 100),
    total_matching_count INTEGER NOT NULL CHECK (total_matching_count >= 0),
    records_received INTEGER NOT NULL CHECK (records_received >= 0),
    source_license TEXT NOT NULL CHECK (source_license = 'CC0-1.0'),
    source_license_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    content_sha256 TEXT NOT NULL
);

INSERT INTO import_snapshots_new (
    snapshot_id, source, source_endpoint, query, page, per_page,
    total_matching_count, records_received, source_license, source_license_url,
    fetched_at, imported_at, content_sha256
)
SELECT
    snapshot_id, source, source_endpoint, query, page, per_page,
    total_matching_count, records_received, source_license, source_license_url,
    fetched_at, imported_at, content_sha256
FROM import_snapshots;

DROP TABLE import_snapshots;
ALTER TABLE import_snapshots_new RENAME TO import_snapshots;
