CREATE TABLE IF NOT EXISTS arxiv_import_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    source_endpoint TEXT NOT NULL CHECK (source_endpoint = 'https://export.arxiv.org/api/query'),
    query TEXT NOT NULL,
    start_index INTEGER NOT NULL CHECK (start_index >= 0),
    per_page INTEGER NOT NULL CHECK (per_page BETWEEN 1 AND 25),
    total_matching_count INTEGER NOT NULL CHECK (total_matching_count >= 0),
    records_received INTEGER NOT NULL CHECK (records_received >= 0),
    source_license TEXT NOT NULL CHECK (source_license = 'CC0-1.0'),
    fetched_at TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    content_sha256 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS arxiv_works (
    arxiv_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL,
    authors_json TEXT NOT NULL,
    categories_json TEXT NOT NULL,
    primary_category TEXT,
    published_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    doi TEXT,
    journal_ref TEXT,
    current_version_sha256 TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS arxiv_work_versions (
    arxiv_id TEXT NOT NULL REFERENCES arxiv_works(arxiv_id),
    payload_sha256 TEXT NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES arxiv_import_snapshots(snapshot_id),
    parser_version TEXT NOT NULL,
    record_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (arxiv_id, payload_sha256)
);

CREATE TABLE IF NOT EXISTS arxiv_snapshot_items (
    snapshot_id TEXT NOT NULL REFERENCES arxiv_import_snapshots(snapshot_id),
    arxiv_id TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    result_position INTEGER NOT NULL CHECK (result_position >= 0),
    PRIMARY KEY (snapshot_id, arxiv_id),
    FOREIGN KEY (arxiv_id, payload_sha256)
        REFERENCES arxiv_work_versions(arxiv_id, payload_sha256)
);

CREATE TABLE IF NOT EXISTS work_identifier_crosswalk (
    openalex_id TEXT PRIMARY KEY REFERENCES works(openalex_id),
    arxiv_id TEXT NOT NULL UNIQUE REFERENCES arxiv_works(arxiv_id),
    match_method TEXT NOT NULL CHECK (match_method = 'exact_doi'),
    normalized_doi TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    verified_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_arxiv_works_published
    ON arxiv_works(published_at DESC, arxiv_id);
CREATE INDEX IF NOT EXISTS idx_arxiv_snapshots_imported
    ON arxiv_import_snapshots(imported_at DESC);
