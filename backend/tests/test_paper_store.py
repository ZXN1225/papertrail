from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.sources.arxiv import ArxivPage, ArxivWork
from app.sources.openalex import OpenAlexMeta, OpenAlexPage, OpenAlexWork
from app.storage.repository import PaperStore, UnsupportedSchemaVersion, _reconstruct_abstract


def _page(title: str = "Research on retrieval", *, with_abstract: bool = True) -> OpenAlexPage:
    return OpenAlexPage(
        meta=OpenAlexMeta(count=123, page=1, per_page=2),
        results=[
            OpenAlexWork(
                id="https://openalex.org/W100",
                title=title,
                doi="https://doi.org/10.1000/example",
                publication_year=2024,
                publication_date="2024-03-01",
                type="article",
                cited_by_count=4,
                authorships=[
                    {"author": {"id": "https://openalex.org/A1", "display_name": "A. Author"}}
                ],
                primary_location={"source": {"display_name": "Example Journal"}},
                open_access={"is_oa": True, "oa_url": "https://example.org/paper"},
                abstract_inverted_index={"Retrieval": [0], "works": [1], "well": [2]}
                if with_abstract
                else None,
                ignored_unknown_field="not retained",
            )
        ],
        fetched_at=datetime(2026, 9, 23, tzinfo=UTC),
    )


def _arxiv_page(title: str = "Research on retrieval", *, version: str = "v1") -> ArxivPage:
    return ArxivPage(
        total_results=1,
        start=0,
        items_per_page=1,
        works=[
            ArxivWork(
                arxiv_id=f"2401.12345{version}",
                title=title,
                abstract="An abstract for the arXiv work.",
                authors=["A. Author"],
                categories=["cs.AI"],
                primary_category="cs.AI",
                published_at=datetime(2024, 1, 2, tzinfo=UTC),
                updated_at=datetime(2024, 2, 3, tzinfo=UTC),
                doi="10.1000/example",
                journal_ref=None,
                source_url="https://arxiv.org/abs/2401.12345",
            )
        ],
        fetched_at=datetime(2026, 9, 23, tzinfo=UTC),
    )


def _store_in_tempdir() -> tuple[tempfile.TemporaryDirectory[str], PaperStore]:
    temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
    return temporary, PaperStore(Path(temporary.name) / "catalog.sqlite3")


def test_migrations_are_repeatable_and_record_schema_version() -> None:
    temporary, store = _store_in_tempdir()
    try:
        store.migrate()
        store.migrate()
        with closing(sqlite3.connect(store.database_path)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
            assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 5
    finally:
        temporary.cleanup()


def test_existing_v1_database_upgrades_without_losing_openalex_rows() -> None:
    temporary, store = _store_in_tempdir()
    try:
        initial_path = Path(__file__).parents[1] / "app/storage/migrations/0001_initial.sql"
        initial_sql = initial_path.read_text(encoding="utf-8")
        import hashlib

        with closing(sqlite3.connect(store.database_path)) as connection:
            connection.executescript(initial_sql)
            connection.execute(
                "INSERT INTO schema_migrations VALUES (1, '0001_initial', ?, ?)",
                (hashlib.sha256(initial_sql.encode()).hexdigest(), "2026-01-01T00:00:00+00:00"),
            )
            connection.execute("PRAGMA user_version = 1")
            connection.execute(
                """INSERT INTO works (
                    openalex_id, source_url, title, doi, publication_year, publication_date,
                    work_type, cited_by_count, abstract, abstract_status, authors_json,
                    venue_name, open_access_json, current_version_sha256,
                    first_seen_at, last_seen_at
                ) VALUES ('W44', 'https://openalex.org/W44', 'Legacy row', NULL, NULL, NULL,
                    NULL, NULL, NULL, 'missing', '[]', NULL, NULL, 'hash', 'now', 'now')"""
            )
            connection.commit()

        store.migrate()
        with closing(sqlite3.connect(store.database_path)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
            assert (
                connection.execute("SELECT title FROM works WHERE openalex_id='W44'").fetchone()[0]
                == "Legacy row"
            )
            assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 5
    finally:
        temporary.cleanup()


def test_upgrade_from_v4_allows_importing_one_hundred_openalex_works() -> None:
    temporary, store = _store_in_tempdir()
    try:
        with closing(sqlite3.connect(store.database_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            for version, migration_path in enumerate(
                sorted(
                    (Path(__file__).parents[1] / "app/storage/migrations").glob("000[1-4]_*.sql")
                ),
                start=1,
            ):
                migration_sql = migration_path.read_text(encoding="utf-8")
                connection.executescript("BEGIN IMMEDIATE;\n" + migration_sql)
                connection.execute(
                    "INSERT INTO schema_migrations (version, name, checksum_sha256, applied_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        version,
                        migration_path.stem,
                        hashlib.sha256(migration_sql.encode("utf-8")).hexdigest(),
                        "2026-09-24T00:00:00+00:00",
                    ),
                )
                connection.execute(f"PRAGMA user_version = {version}")
                connection.commit()

            connection.execute(
                """INSERT INTO import_snapshots VALUES (
                    'legacy-snapshot', 'openalex', 'https://api.openalex.org/works',
                    'retrieval', 1, 25, 1, 1, 'CC0-1.0',
                    'https://creativecommons.org/publicdomain/zero/1.0/',
                    '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 'snapshot-hash'
                )"""
            )
            connection.execute(
                """INSERT INTO works (
                    openalex_id, source_url, title, abstract_status, authors_json,
                    current_version_sha256, first_seen_at, last_seen_at
                ) VALUES ('W99', 'https://openalex.org/W99', 'Legacy', 'missing', '[]',
                    'work-hash', 'now', 'now')"""
            )
            connection.execute(
                """INSERT INTO work_versions (
                    openalex_id, payload_sha256, source_snapshot_id, source_url, fetched_at,
                    parser_version, record_json, abstract_status
                ) VALUES ('W99', 'work-hash', 'legacy-snapshot',
                    'https://openalex.org/W99', 'now', 'openalex-work-v1',
                    '{"id":"https://openalex.org/W99","title":"Legacy"}', 'missing')"""
            )
            connection.execute(
                """INSERT INTO snapshot_items
                    (snapshot_id, openalex_id, payload_sha256, result_position)
                    VALUES ('legacy-snapshot', 'W99', 'work-hash', 0)"""
            )
            connection.commit()

        store.migrate()
        assert store.get_snapshot("legacy-snapshot")["records_received"] == 1
        assert store.get_paper("W99", snapshot_id="legacy-snapshot")["title"] == "Legacy"
        page = OpenAlexPage(
            meta=OpenAlexMeta(count=100, page=1, per_page=100),
            results=[OpenAlexWork(id="https://openalex.org/W100", title="RAG paper")],
            fetched_at=datetime(2026, 9, 24, tzinfo=UTC),
        )
        imported = store.import_openalex_page(
            page, query="retrieval augmented generation", requested_page=1, per_page=100
        )

        assert store.get_snapshot(imported.snapshot_id)["per_page"] == 100
        assert store.get_paper("W100", snapshot_id=imported.snapshot_id)["title"] == "RAG paper"
    finally:
        temporary.cleanup()


def test_arxiv_import_versions_and_links_only_by_unique_exact_doi() -> None:
    temporary, store = _store_in_tempdir()
    try:
        store.import_openalex_page(_page(), query="retrieval", requested_page=1, per_page=2)
        first = store.import_arxiv_page(_arxiv_page(), query="retrieval", start=0)
        repeated = store.import_arxiv_page(_arxiv_page(), query="retrieval", start=0)
        changed = store.import_arxiv_page(
            _arxiv_page("Changed metadata", version="v2"), query="retrieval", start=0
        )

        paper = store.get_arxiv_paper("2401.12345v2")
        assert first.new_works == 1
        assert first.new_versions == 1
        assert first.linked_by_exact_doi == 1
        assert repeated.new_versions == 0
        assert repeated.unchanged_works == 1
        assert changed.new_versions == 1
        assert paper is not None
        assert paper["title"] == "Changed metadata"
        assert paper["crosswalk"]["openalex_id"] == "W100"
        assert paper["crosswalk"]["match_method"] == "exact_doi"
        assert paper["metadata_license"] == "CC0-1.0"
        assert store.list_arxiv_papers(query="changed", limit=10, offset=0)["total"] == 1
        with closing(sqlite3.connect(store.database_path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM arxiv_work_versions").fetchone()[0] == 2
    finally:
        temporary.cleanup()


def test_ambiguous_doi_does_not_create_crosswalk() -> None:
    temporary, store = _store_in_tempdir()
    try:
        original = _page()
        duplicate = OpenAlexWork(
            id="https://openalex.org/W101",
            title="Another work with ambiguous DOI",
            doi="10.1000/example",
            publication_year=2024,
        )
        page = OpenAlexPage(
            meta=OpenAlexMeta(count=2, page=1, per_page=2),
            results=[*original.results, duplicate],
            fetched_at=original.fetched_at,
        )
        store.import_openalex_page(page, query="doi", requested_page=1, per_page=2)
        summary = store.import_arxiv_page(_arxiv_page(), query="doi", start=0)
        stored = store.get_arxiv_paper("2401.12345")

        assert summary.linked_by_exact_doi == 0
        assert stored is not None
        assert stored["crosswalk"] is None
    finally:
        temporary.cleanup()


def test_import_is_idempotent_and_preserves_lineage_and_abstract() -> None:
    temporary, store = _store_in_tempdir()
    try:
        first = store.import_openalex_page(
            _page(), query="  retrieval   research ", requested_page=1, per_page=2
        )
        second = store.import_openalex_page(
            _page(), query="retrieval research", requested_page=1, per_page=2
        )

        assert first.new_works == 1
        assert first.new_versions == 1
        assert second.new_works == 0
        assert second.new_versions == 0
        assert second.unchanged_works == 1
        assert first.content_sha256 == second.content_sha256
        paper = store.get_paper("W100")
        assert paper is not None
        assert paper["title"] == "Research on retrieval"
        assert paper["abstract"] == "Retrieval works well"
        assert paper["abstract_status"] == "available"
        assert paper["authors"] == [{"id": "https://openalex.org/A1", "name": "A. Author"}]
        assert paper["venue"] == "Example Journal"
        assert paper["metadata_license"] == "CC0-1.0"
        assert paper["snapshot_id"] == second.snapshot_id
        assert len(store.list_snapshots()) == 2
        snapshot = store.get_snapshot(first.snapshot_id)
        assert snapshot is not None
        assert snapshot["source_license"] == "CC0-1.0"
        assert snapshot["items"][0]["openalex_id"] == "W100"
        with closing(sqlite3.connect(store.database_path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM work_versions").fetchone()[0] == 1
            record_json = connection.execute("SELECT record_json FROM work_versions").fetchone()[0]
            assert "ignored_unknown_field" not in record_json
    finally:
        temporary.cleanup()


def test_changed_source_record_appends_version_and_old_snapshot_is_readable() -> None:
    temporary, store = _store_in_tempdir()
    try:
        first = store.import_openalex_page(_page(), query="retrieval", requested_page=1, per_page=2)
        changed_page = _page("Updated title")
        second = store.import_openalex_page(
            changed_page, query="retrieval", requested_page=1, per_page=2
        )

        assert second.new_versions == 1
        assert second.unchanged_works == 0
        assert store.get_paper("W100")["title"] == "Updated title"
        assert (
            store.get_paper("W100", snapshot_id=first.snapshot_id)["title"]
            == "Research on retrieval"
        )
        with closing(sqlite3.connect(store.database_path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM work_versions").fetchone()[0] == 2
    finally:
        temporary.cleanup()


def test_failure_inside_transaction_rolls_back_snapshot_and_records() -> None:
    temporary, store = _store_in_tempdir()
    try:
        store.migrate()
        with closing(sqlite3.connect(store.database_path)) as connection:
            connection.execute(
                """CREATE TRIGGER reject_work BEFORE INSERT ON work_versions
                WHEN NEW.openalex_id = 'W100'
                BEGIN SELECT RAISE(ABORT, 'forced test rollback'); END"""
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.import_openalex_page(_page(), query="retrieval", requested_page=1, per_page=2)
        with closing(sqlite3.connect(store.database_path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM import_snapshots").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM work_versions").fetchone()[0] == 0
    finally:
        temporary.cleanup()


def test_snapshot_content_never_contains_authentication_secrets() -> None:
    temporary, store = _store_in_tempdir()
    try:
        store.import_openalex_page(_page(), query="retrieval", requested_page=1, per_page=2)
        database_bytes = store.database_path.read_bytes()
        assert b"private-test-key" not in database_bytes
        assert b"Authorization" not in database_bytes
    finally:
        temporary.cleanup()


def test_catalog_search_is_bounded_and_paginates() -> None:
    temporary, store = _store_in_tempdir()
    try:
        store.import_openalex_page(_page(), query="retrieval", requested_page=1, per_page=2)
        first_page = store.list_papers(query="retrieval", limit=1, offset=0)
        second_page = store.list_papers(query="retrieval", limit=1, offset=1)
        assert first_page["total"] == 1
        assert len(first_page["items"]) == 1
        assert second_page["items"] == []
        with pytest.raises(ValueError):
            store.list_papers(query=None, limit=51, offset=0)
    finally:
        temporary.cleanup()


def test_missing_paper_and_snapshot_return_none() -> None:
    temporary, store = _store_in_tempdir()
    try:
        assert store.get_paper("W999") is None
        assert store.get_snapshot("missing-snapshot") is None
        assert store.get_paper("https://not-openalex.example/W1") is None
    finally:
        temporary.cleanup()


def test_abstract_reconstruction_reports_missing_invalid_and_oversized() -> None:
    assert _reconstruct_abstract(None) == (None, "missing")
    assert _reconstruct_abstract({"term": [-1]}) == (None, "invalid")
    assert _reconstruct_abstract({"a": [0], "b": [0]}) == (None, "invalid")
    assert _reconstruct_abstract({"x" * 2_001: [0]}) == (None, "oversized")
    assert _reconstruct_abstract({"hello": [50_000]}) == (None, "invalid")


def test_unknown_future_schema_is_rejected() -> None:
    temporary, store = _store_in_tempdir()
    try:
        with closing(sqlite3.connect(store.database_path)) as connection:
            connection.execute("PRAGMA user_version = 99")
        with pytest.raises(UnsupportedSchemaVersion):
            store.migrate()
    finally:
        temporary.cleanup()
