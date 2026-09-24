from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.evaluation.p14 import P14EvaluationError, run_p14_comparison
from app.sources.openalex import OpenAlexMeta, OpenAlexPage, OpenAlexWork
from app.storage.repository import PaperStore


class FakeEmbedder:
    model = "fake-embedding-model"

    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def embed(self, texts: list[str]):
        self.batch_sizes.append(len(texts))
        return type(
            "Batch",
            (),
            {"vectors": [[1.0, 0.0] for _ in texts], "input_tokens": len(texts) * 3},
        )()


def _dataset(store_path: Path) -> tuple[PaperStore, dict, str]:
    store = PaperStore(store_path)
    page = OpenAlexPage(
        meta=OpenAlexMeta(count=100, page=1, per_page=100),
        results=[
            OpenAlexWork(
                id=f"https://openalex.org/W{index}",
                title=f"Title for work {index}",
                abstract_inverted_index={"abstract": [0], str(index): [1]},
            )
            for index in range(100, 200)
        ],
        fetched_at=datetime(2026, 9, 24, tzinfo=UTC),
    )
    imported = store.import_openalex_page(page, query="test", requested_page=1, per_page=100)
    snapshot = store.get_snapshot(imported.snapshot_id)
    work_ids = [item["openalex_id"] for item in snapshot["items"]]
    hashes = {item["openalex_id"]: item["payload_sha256"] for item in snapshot["items"]}
    queries = []
    for query_index in range(30):
        grades = [0] * 100
        grades[99 if query_index == 0 else 0] = 3
        queries.append(
            {
                "query_id": f"Q{query_index:02}",
                "text": f"research question {query_index}",
                "bucket": f"bucket-{query_index % 3}",
                "relevance": grades,
            }
        )
    dataset = {
        "dataset_id": "P13-ai-test",
        "dataset_version": 1,
        "judgment_status": "assistant_labeled",
        "corpus": {
            "snapshot_id": imported.snapshot_id,
            "work_ids": work_ids,
            "content_sha256": hashes,
        },
        "queries": queries,
    }
    return store, dataset, imported.snapshot_id


def test_p14_compares_methods_and_bounds_embedding_batches(tmp_path: Path) -> None:
    store, dataset, _ = _dataset(tmp_path / "p14.sqlite3")
    embedder = FakeEmbedder()

    report = run_p14_comparison(
        store, dataset, "dataset-hash", embedder, price_per_million_usd=0.02
    )

    assert embedder.batch_sizes == [64, 64, 2]
    assert report["dataset"]["exploratory_only"] is True
    assert report["dataset"]["quality_claim_allowed"] is False
    assert report["dataset"]["human_reviewed"] is False
    assert set(report["methods"]) == {"bm25", "dense", "hybrid_rrf_k60"}
    assert len(report["queries_ranked_by_method_disagreement"]) == 30
    assert (
        len(report["queries_ranked_by_method_disagreement"][0]["methods"]["bm25"]["top_10"]) <= 10
    )
    assert set(report["methods"]["bm25"]["metrics_by_bucket"]) == {
        "bucket-0",
        "bucket-1",
        "bucket-2",
    }
    assert report["embedding"]["input_count"] == 130
    assert report["embedding"]["input_tokens"] == 390
    assert report["embedding"]["vectors_persisted"] is False
    first_query = next(
        row for row in report["queries_ranked_by_method_disagreement"] if row["query_id"] == "Q00"
    )
    assert first_query["methods"]["dense"]["metrics"]["mrr@10"] == 0.0


def test_p14_rejects_non_assistant_labels_before_provider_call(tmp_path: Path) -> None:
    store, dataset, _ = _dataset(tmp_path / "p14.sqlite3")
    dataset["judgment_status"] = "human_reviewed"
    embedder = FakeEmbedder()

    with pytest.raises(P14EvaluationError, match="assistant_labeled"):
        run_p14_comparison(store, dataset, "hash", embedder, price_per_million_usd=None)
    assert embedder.batch_sizes == []


def test_p14_rejects_snapshot_mismatch_before_provider_call(tmp_path: Path) -> None:
    store, dataset, _ = _dataset(tmp_path / "p14.sqlite3")
    dataset["corpus"]["snapshot_id"] = "wrong-snapshot"
    embedder = FakeEmbedder()

    with pytest.raises(P14EvaluationError, match="snapshot ID"):
        run_p14_comparison(store, dataset, "hash", embedder, price_per_million_usd=None)
    assert embedder.batch_sizes == []
