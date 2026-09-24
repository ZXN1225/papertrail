CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    source TEXT NOT NULL CHECK (source = 'openalex'),
    source_endpoint TEXT NOT NULL CHECK (source_endpoint = 'https://api.openalex.org/works'),
    query TEXT NOT NULL,
    page INTEGER NOT NULL CHECK (page >= 1),
    per_page INTEGER NOT NULL CHECK (per_page BETWEEN 1 AND 25),
    total_matching_count INTEGER NOT NULL CHECK (total_matching_count >= 0),
    records_received INTEGER NOT NULL CHECK (records_received >= 0),
    source_license TEXT NOT NULL CHECK (source_license = 'CC0-1.0'),
    source_license_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    content_sha256 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS works (
    openalex_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    title TEXT,
    doi TEXT,
    publication_year INTEGER,
    publication_date TEXT,
    work_type TEXT,
    cited_by_count INTEGER,
    abstract TEXT,
    abstract_status TEXT NOT NULL CHECK (abstract_status IN ('available', 'missing', 'invalid', 'oversized')),
    authors_json TEXT NOT NULL,
    venue_name TEXT,
    open_access_json TEXT,
    current_version_sha256 TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_versions (
    openalex_id TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    source_snapshot_id TEXT NOT NULL REFERENCES import_snapshots(snapshot_id),
    source_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    record_json TEXT NOT NULL,
    abstract TEXT,
    abstract_status TEXT NOT NULL CHECK (abstract_status IN ('available', 'missing', 'invalid', 'oversized')),
    PRIMARY KEY (openalex_id, payload_sha256),
    FOREIGN KEY (openalex_id) REFERENCES works(openalex_id)
);

CREATE TABLE IF NOT EXISTS snapshot_items (
    snapshot_id TEXT NOT NULL REFERENCES import_snapshots(snapshot_id),
    openalex_id TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    result_position INTEGER NOT NULL CHECK (result_position >= 0),
    PRIMARY KEY (snapshot_id, openalex_id),
    FOREIGN KEY (openalex_id, payload_sha256)
        REFERENCES work_versions(openalex_id, payload_sha256)
);

CREATE INDEX IF NOT EXISTS idx_works_publication_year
    ON works(publication_year DESC, openalex_id);
CREATE INDEX IF NOT EXISTS idx_snapshot_items_work
    ON snapshot_items(openalex_id, snapshot_id);
