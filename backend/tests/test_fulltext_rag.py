from __future__ import annotations

import json
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent.tools import PaperToolRegistry
from app.cli import index_fulltext_embeddings
from app.config import Settings
from app.embeddings.client import EmbeddingBatch
from app.main import create_app
from app.retrieval.fulltext import MAX_CHUNK_CHARS, chunk_plain_text
from app.sources.arxiv import ArxivPage, ArxivWork
from app.sources.openalex import OpenAlexMeta, OpenAlexPage, OpenAlexWork
from app.storage.repository import PaperStore

CC0_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
CCBY_URL = "https://creativecommons.org/licenses/by/4.0/"


def _seed_store() -> tuple[tempfile.TemporaryDirectory[str], PaperStore]:
    temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
    store = PaperStore(Path(temporary.name) / "papers.sqlite3")
    store.import_openalex_page(
        OpenAlexPage(
            meta=OpenAlexMeta(count=1, page=1, per_page=1),
            results=[
                OpenAlexWork(
                    id="https://openalex.org/W900",
                    title="Retrieval augmented generation evaluation",
                    publication_year=2025,
                )
            ],
            fetched_at=datetime(2026, 9, 23, tzinfo=UTC),
        ),
        query="retrieval",
        requested_page=1,
        per_page=1,
    )
    return temporary, store


def _ingest(store: PaperStore, text: str, **overrides):
    values = {
        "source_type": "openalex",
        "source_id": "W900",
        "text": text,
        "text_source_url": "https://repository.example.org/paper.txt",
        "license_id": "CC-BY-4.0",
        "license_url": CCBY_URL,
        "license_evidence_url": "https://repository.example.org/license",
        "reviewer": "local-project-owner",
        "attribution": "A. Author, Retrieval augmented generation evaluation, CC BY 4.0",
        "confirm_license_reviewed": True,
    }
    values.update(overrides)
    return store.ingest_licensed_fulltext(**values)


def test_license_gate_rejects_unknown_restricted_and_unconfirmed_content() -> None:
    temporary, store = _seed_store()
    try:
        with pytest.raises(ValueError, match="allowlist"):
            _ingest(store, "licensed evidence", license_id="CC-BY-NC-ND-4.0")
        with pytest.raises(ValueError, match="explicit human"):
            _ingest(store, "licensed evidence", confirm_license_reviewed=False)
        with pytest.raises(ValueError, match="canonical"):
            _ingest(store, "licensed evidence", license_url="https://example.org/license")
        with pytest.raises(ValueError, match="HTTPS"):
            _ingest(
                store, "licensed evidence", text_source_url="http://repository.example.org/paper"
            )
        assert store.search_fulltext_evidence("licensed") == {
            "status": "no_results",
            "items": [],
            "scanned_chunks": 0,
            "truncated": False,
            "retrieval_method": "bm25_fulltext_v1",
        }
    finally:
        temporary.cleanup()


def test_ingest_is_idempotent_and_returns_license_and_exact_evidence_locator() -> None:
    temporary, store = _seed_store()
    try:
        text = (
            "# Abstract\n\nRetrieval augmented generation combines document retrieval "
            "with a language model.\n\n# Findings\n\nEvidence passages support "
            "answers and make research claims auditable."
        )
        first = _ingest(store, text)
        repeat = _ingest(store, text)
        result = store.search_fulltext_evidence("evidence passages support answers")
        evaluation_top_10 = store.search_fulltext_evidence(
            "evidence passages support answers", limit=10
        )

        assert first["status"] == "approved"
        assert repeat["status"] == "unchanged"
        assert first["content_sha256"] == repeat["content_sha256"]
        assert first["chunk_count"] == 2
        assert result["status"] == "ok"
        assert evaluation_top_10["status"] == "ok"
        assert 1 <= len(evaluation_top_10["items"]) <= 2
        hit = result["items"][0]
        assert hit["source_type"] == "openalex"
        assert hit["openalex_id"] == "W900"
        assert hit["license_id"] == "CC-BY-4.0"
        assert hit["attribution"].startswith("A. Author")
        assert hit["locator"].startswith("Findings · 字符")
        assert text.strip()[hit["char_start"] : hit["char_end"]].strip() == hit["excerpt"]
        with pytest.raises(ValueError, match="limit must be 1-10"):
            store.search_fulltext_evidence("evidence passages support answers", limit=11)
        with closing(sqlite3.connect(store.database_path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM fulltext_chunks").fetchone()[0] == 2
            row = connection.execute(
                "SELECT text_source_url, license_evidence_url, reviewer FROM fulltext_versions"
            ).fetchone()
            assert row == (
                "https://repository.example.org/paper.txt",
                "https://repository.example.org/license",
                "local-project-owner",
            )
    finally:
        temporary.cleanup()


def test_changed_content_replaces_active_version_without_exposing_old_text() -> None:
    temporary, store = _seed_store()
    try:
        _ingest(store, "The former unique phrase is withdrawn from current content.")
        changed = _ingest(store, "The updated evidence supports reproducible retrieval.")
        old_result = store.search_fulltext_evidence("former unique phrase")
        new_result = store.search_fulltext_evidence("updated evidence reproducible retrieval")
        with closing(sqlite3.connect(store.database_path)) as connection:
            versions = connection.execute("SELECT COUNT(*) FROM fulltext_versions").fetchone()[0]
            active_hash = connection.execute(
                "SELECT current_sha256 FROM fulltext_documents WHERE source_id='W900'"
            ).fetchone()[0]

        assert changed["status"] == "approved"
        assert old_result["status"] == "no_results"
        assert new_result["items"][0]["content_sha256"] == active_hash
        assert versions == 2
    finally:
        temporary.cleanup()


def test_arxiv_content_can_be_separately_approved_and_deleted_with_tombstone() -> None:
    temporary, store = _seed_store()
    try:
        store.import_arxiv_page(
            ArxivPage(
                total_results=1,
                start=0,
                items_per_page=1,
                works=[
                    ArxivWork(
                        arxiv_id="2401.12345v2",
                        title="Papertrail evidence retrieval",
                        abstract="arxiv metadata abstract",
                        authors=["A. Author"],
                        categories=["cs.IR"],
                        primary_category="cs.IR",
                        published_at=datetime(2024, 1, 1, tzinfo=UTC),
                        updated_at=datetime(2024, 2, 1, tzinfo=UTC),
                        source_url="https://arxiv.org/abs/2401.12345",
                    )
                ],
                fetched_at=datetime(2026, 9, 23, tzinfo=UTC),
            ),
            query="evidence retrieval",
            start=0,
        )
        approved = _ingest(
            store,
            "Open source evidence enables auditable research retrieval.",
            source_type="arxiv",
            source_id="2401.12345v2",
            license_id="CC0-1.0",
            license_url=CC0_URL,
        )
        result = store.search_fulltext_evidence("auditable research retrieval")
        assert approved["source_id"] == "2401.12345"
        assert result["items"][0]["arxiv_id"] == "2401.12345"
        assert store.delete_fulltext("arxiv", "2401.12345", reason="license corrected")
        assert (
            store.search_fulltext_evidence("auditable research retrieval")["status"] == "no_results"
        )
        with closing(sqlite3.connect(store.database_path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM fulltext_versions").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fulltext_chunks").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fulltext_embeddings").fetchone()[0] == 0
            assert (
                connection.execute("SELECT COUNT(*) FROM fulltext_deletion_events").fetchone()[0]
                == 1
            )
    finally:
        temporary.cleanup()


def test_chunker_bounds_chunks_and_preserves_offsets() -> None:
    source = "# Methods\n\n" + (
        ("A reproducible chunk keeps an evidence locator. " * 80) + "\n\nConclusion."
    )
    chunks = chunk_plain_text(source)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= MAX_CHUNK_CHARS for chunk in chunks)
    assert all(
        source.strip()[chunk.char_start : chunk.char_end].strip() == chunk.text for chunk in chunks
    )
    with pytest.raises(ValueError, match="2,000,000"):
        chunk_plain_text("x" * 2_000_001)


def test_evidence_api_only_returns_approved_fulltext_and_rejects_partial_filter() -> None:
    temporary, store = _seed_store()
    try:
        _ingest(store, "A verified passage about retrieval quality and evidence citations.")
        client = TestClient(
            create_app(Settings(_env_file=None, data_storage_path=store.database_path))
        )
        found = client.get("/api/v1/evidence/search?q=verified%20evidence%20citations")
        partial_filter = client.get("/api/v1/evidence/search?q=evidence&source_type=openalex")
        assert found.status_code == 200
        assert found.json()["items"][0]["license_id"] == "CC-BY-4.0"
        assert partial_filter.status_code == 422
        dense_disabled = client.get(
            "/api/v1/evidence/search",
            params={"q": "verified evidence", "retrieval_method": "dense"},
        )
        assert dense_disabled.status_code == 503
        assert dense_disabled.json()["detail"]["code"] == "embedding_disabled"
    finally:
        temporary.cleanup()


def test_dense_and_hybrid_use_only_current_approved_chunks_and_keep_citations() -> None:
    temporary, store = _seed_store()
    try:
        _ingest(
            store,
            "# Lexical\n\nExact lexical phrase matches this passage.\n\n"
            "# Semantic\n\nMeaning based retrieval can find this second passage.",
        )
        chunks = store.list_current_fulltext_chunks(source_type="openalex", source_id="W900")
        assert len(chunks) == 2
        store.store_fulltext_embeddings(
            model="fake-test-encoder-v1",
            dimensions=2,
            items=[
                {
                    "chunk_id": chunks[0]["chunk_id"],
                    "content_sha256": chunks[0]["content_sha256"],
                    "vector": [1.0, 0.0],
                },
                {
                    "chunk_id": chunks[1]["chunk_id"],
                    "content_sha256": chunks[1]["content_sha256"],
                    "vector": [0.0, 1.0],
                },
            ],
        )
        dense = store.search_fulltext_evidence(
            "semantic neighbor query",
            source_type="openalex",
            source_id="W900",
            retrieval_method="dense",
            query_embedding=[0.0, 1.0],
            embedding_model="fake-test-encoder-v1",
        )
        hybrid = store.search_fulltext_evidence(
            "exact lexical phrase",
            source_type="openalex",
            source_id="W900",
            retrieval_method="hybrid",
            query_embedding=[0.0, 1.0],
            embedding_model="fake-test-encoder-v1",
        )
        assert dense["retrieval_method"] == "dense_cosine_v1"
        assert dense["items"][0]["chunk_id"] == chunks[1]["chunk_id"]
        assert dense["items"][0]["license_id"] == "CC-BY-4.0"
        assert hybrid["retrieval_method"] == "hybrid_rrf_v1"
        assert hybrid["items"]
        assert all(
            item["content_sha256"] == chunks[0]["content_sha256"] for item in hybrid["items"]
        )
        store.delete_fulltext("openalex", "W900", reason="acceptance deletion test")
        after_delete = store.search_fulltext_evidence(
            "semantic neighbor query",
            retrieval_method="dense",
            query_embedding=[0.0, 1.0],
            embedding_model="fake-test-encoder-v1",
        )
        assert after_delete["status"] == "no_results"
        assert after_delete["scanned_chunks"] == 0
    finally:
        temporary.cleanup()


def test_dense_retrieval_reports_incomplete_index_and_refuses_stale_embedding_write() -> None:
    temporary, store = _seed_store()
    try:
        _ingest(store, "A current approved chunk for dense retrieval.")
        chunks = store.list_current_fulltext_chunks()
        store.store_fulltext_embeddings(
            model="fake-test-encoder-v1",
            dimensions=2,
            items=[
                {
                    "chunk_id": chunks[0]["chunk_id"],
                    "content_sha256": chunks[0]["content_sha256"],
                    "vector": [1.0, 0.0],
                }
            ],
        )
        result = store.search_fulltext_evidence(
            "current chunk",
            retrieval_method="dense",
            query_embedding=[1.0, 0.0],
            embedding_model="fake-test-encoder-v1",
        )
        assert result["status"] == "ok"
        changed = _ingest(store, "Replacement current chunk.")
        assert changed["status"] == "approved"
        assert (
            store.store_fulltext_embeddings(
                model="fake-test-encoder-v1",
                dimensions=2,
                items=[
                    {
                        "chunk_id": store.list_current_fulltext_chunks()[0]["chunk_id"],
                        "content_sha256": store.list_current_fulltext_chunks()[0]["content_sha256"],
                        "vector": [1.0, 0.0],
                    }
                ],
            )
            == 1
        )
        missing = store.search_fulltext_evidence(
            "replacement",
            retrieval_method="dense",
            query_embedding=[1.0, 0.0],
            embedding_model="new-model-v1",
        )
        assert missing["status"] == "embeddings_missing"
        with pytest.raises(ValueError, match="current approved"):
            store.store_fulltext_embeddings(
                model="fake-test-encoder-v1",
                dimensions=2,
                items=[
                    {
                        "chunk_id": chunks[0]["chunk_id"],
                        "content_sha256": chunks[0]["content_sha256"],
                        "vector": [1.0, 0.0],
                    }
                ],
            )
    finally:
        temporary.cleanup()


def test_evidence_api_dense_query_uses_fixed_embedding_provider(monkeypatch) -> None:
    temporary, store = _seed_store()
    try:
        _ingest(store, "A semantic passage for vector retrieval.")
        chunk = store.list_current_fulltext_chunks()[0]
        store.store_fulltext_embeddings(
            model="fake-test-encoder-v1",
            dimensions=2,
            items=[
                {
                    "chunk_id": chunk["chunk_id"],
                    "content_sha256": chunk["content_sha256"],
                    "vector": [0.0, 1.0],
                }
            ],
        )

        class FakeEmbeddingClient:
            def __init__(self, settings) -> None:
                self.settings = settings

            def embed(self, texts: list[str]) -> EmbeddingBatch:
                assert texts == ["unrelated semantic request"]
                return EmbeddingBatch("fake-test-encoder-v1", [[0.0, 1.0]], 3)

            def close(self) -> None:
                pass

        monkeypatch.setattr("app.main.OpenAIEmbeddingClient", FakeEmbeddingClient)
        settings = Settings(
            _env_file=None,
            data_storage_path=store.database_path,
            embedding_provider="openai",
            embedding_api_key="test-only",
            embedding_model="fake-test-encoder-v1",
            embedding_dimensions=2,
        )
        response = TestClient(create_app(settings)).get(
            "/api/v1/evidence/search",
            params={"q": "unrelated semantic request", "retrieval_method": "dense"},
        )
        assert response.status_code == 200
        assert response.json()["retrieval_method"] == "dense_cosine_v1"
        assert response.json()["items"][0]["chunk_id"] == chunk["chunk_id"]
    finally:
        temporary.cleanup()


def test_agent_evidence_tool_uses_hybrid_provider_and_fails_closed_when_disabled() -> None:
    temporary, store = _seed_store()
    try:
        _ingest(store, "A paper passage about evidence and citations.")
        chunk = store.list_current_fulltext_chunks()[0]
        store.store_fulltext_embeddings(
            model="fake-test-encoder-v1",
            dimensions=2,
            items=[
                {
                    "chunk_id": chunk["chunk_id"],
                    "content_sha256": chunk["content_sha256"],
                    "vector": [0.0, 1.0],
                }
            ],
        )

        class FakeProvider:
            model = "fake-test-encoder-v1"

            def embed(self, texts: list[str]) -> EmbeddingBatch:
                return EmbeddingBatch(self.model, [[0.0, 1.0]], 4)

        request = (
            '{"query":"semantic citation question","limit":5,"source_type":"openalex",'
            '"source_id":"W900","retrieval_method":"hybrid"}'
        )
        result = PaperToolRegistry(store, embeddings=FakeProvider()).execute(
            "retrieve_paper_evidence", request
        )
        disabled = PaperToolRegistry(store).execute("retrieve_paper_evidence", request)
        assert result["status"] == "ok"
        assert result["retrieval_method"] == "hybrid_rrf_v1"
        assert result["items"][0]["chunk_id"] == chunk["chunk_id"]
        assert disabled == {"status": "embedding_unavailable"}
    finally:
        temporary.cleanup()


def test_embedding_index_cli_batches_and_reports_safe_usage(monkeypatch, capsys) -> None:
    temporary, store = _seed_store()
    try:
        _ingest(store, "An approved text chunk to build an embedding index.")
        settings = Settings(
            _env_file=None,
            data_storage_path=store.database_path,
            embedding_provider="openai",
            embedding_api_key="test-only",
            embedding_model="fake-test-encoder-v1",
            embedding_dimensions=2,
            embedding_price_per_million_usd=0.02,
        )

        class FakeEmbeddingClient:
            def __init__(self, client_settings) -> None:
                assert client_settings.embedding_api_key is not None

            def embed(self, texts: list[str]) -> EmbeddingBatch:
                assert texts == ["An approved text chunk to build an embedding index."]
                return EmbeddingBatch("fake-test-encoder-v1", [[1.0, 0.0]], 12)

            def close(self) -> None:
                pass

        monkeypatch.setattr(index_fulltext_embeddings, "get_settings", lambda: settings)
        monkeypatch.setattr(index_fulltext_embeddings, "OpenAIEmbeddingClient", FakeEmbeddingClient)
        exit_code = index_fulltext_embeddings.main(
            ["--source-type", "openalex", "--source-id", "W900"]
        )
        output = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert output["indexed_chunks"] == 1
        assert output["input_tokens"] == 12
        assert output["estimated_cost_usd"] == 2.4e-07
        assert (
            store.search_fulltext_evidence(
                "meaning unrelated",
                retrieval_method="dense",
                query_embedding=[1.0, 0.0],
                embedding_model="fake-test-encoder-v1",
            )["status"]
            == "ok"
        )
    finally:
        temporary.cleanup()
