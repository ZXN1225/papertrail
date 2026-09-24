import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.sources.openalex import OpenAlexMeta, OpenAlexPage, OpenAlexWork
from app.storage.repository import PaperStore


def test_empty_and_populated_catalog_routes_have_source_lineage() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
        database_path = Path(directory) / "catalog.sqlite3"
        client = TestClient(create_app(Settings(_env_file=None, data_storage_path=database_path)))

        empty = client.get("/api/v1/catalog/papers")
        assert empty.status_code == 200
        assert empty.json() == {"total": 0, "limit": 20, "offset": 0, "items": []}
        assert client.get("/api/v1/catalog/papers/W999").status_code == 404

        page = OpenAlexPage(
            meta=OpenAlexMeta(count=1, page=1, per_page=1),
            results=[
                OpenAlexWork(
                    id="https://openalex.org/W777",
                    title="Local catalog paper",
                    publication_year=2026,
                )
            ],
            fetched_at=datetime(2026, 9, 23, tzinfo=UTC),
        )
        summary = PaperStore(database_path).import_openalex_page(
            page, query="local catalog", requested_page=1, per_page=1
        )

        listing = client.get("/api/v1/catalog/papers?q=local")
        detail = client.get(f"/api/v1/catalog/papers/W777?snapshot_id={summary.snapshot_id}")
        snapshot = client.get(f"/api/v1/catalog/snapshots/{summary.snapshot_id}")

        assert listing.status_code == 200
        assert listing.json()["total"] == 1
        assert listing.json()["items"][0]["source_url"] == "https://openalex.org/W777"
        assert detail.status_code == 200
        assert detail.json()["snapshot_id"] == summary.snapshot_id
        assert detail.json()["abstract"] is None
        assert detail.json()["abstract_status"] == "missing"
        assert snapshot.status_code == 200
        assert snapshot.json()["items"][0]["result_position"] == 0
        assert client.get("/api/v1/catalog/papers/not-an-openalex-id").status_code == 422
