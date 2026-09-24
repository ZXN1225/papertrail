"""Load, validate and execute a frozen-paper retrieval evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.evaluation.metrics import score_query
from app.retrieval.bm25 import BM25_VERSION, DEFAULT_B, DEFAULT_K1, BM25Index
from app.retrieval.tokenizer import TOKENIZER_VERSION
from app.storage.repository import PaperStore

DEFAULT_DATASET_PATH = Path(__file__).resolve().parents[2] / "data/evaluation/p05_gold_v1.json"
REPORT_SCHEMA = "papertrail-retrieval-evaluation-v1"


@dataclass(frozen=True)
class RetrievalDocument:
    openalex_id: str
    title: str
    abstract: str | None
    content_sha256: str


class EvaluationDataError(ValueError):
    """The frozen benchmark cannot be safely or reproducibly evaluated."""


def load_dataset(dataset_path: Path) -> tuple[dict[str, Any], str]:
    raw = dataset_path.read_bytes()
    try:
        dataset = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvaluationDataError("evaluation dataset is not valid UTF-8 JSON") from error
    if not isinstance(dataset, dict):
        raise EvaluationDataError("evaluation dataset root must be an object")
    return dataset, hashlib.sha256(raw).hexdigest()


def run_evaluation(
    store: PaperStore, dataset: dict[str, Any], dataset_sha256: str
) -> dict[str, Any]:
    corpus_config = dataset.get("corpus")
    queries = dataset.get("queries")
    if not isinstance(corpus_config, dict) or not isinstance(queries, list) or not queries:
        raise EvaluationDataError("dataset requires a corpus and at least one query")

    expected_hashes = corpus_config.get("content_sha256")
    work_ids = corpus_config.get("work_ids")
    if (
        not isinstance(expected_hashes, dict)
        or not isinstance(work_ids, list)
        or not work_ids
        or set(expected_hashes) != set(work_ids)
        or len(set(work_ids)) != len(work_ids)
    ):
        raise EvaluationDataError("corpus work IDs and expected content hashes must match")

    snapshot_id, papers = _load_frozen_corpus(store, work_ids, expected_hashes)
    documents = [
        RetrievalDocument(
            openalex_id=paper["openalex_id"],
            title=paper["title"] or "",
            abstract=paper["abstract"],
            content_sha256=paper["content_sha256"],
        )
        for paper in papers
    ]
    index = BM25Index(documents)

    seen_query_ids: set[str] = set()
    query_results: list[dict[str, Any]] = []
    latencies: list[float] = []
    metric_names = [
        "hit@1",
        "hit@3",
        "hit@5",
        "hit@10",
        "mrr@10",
        "ndcg@1",
        "ndcg@3",
        "ndcg@5",
        "ndcg@10",
    ]
    for query in queries:
        query_id = query.get("query_id") if isinstance(query, dict) else None
        query_text = query.get("text") if isinstance(query, dict) else None
        bucket = query.get("bucket") if isinstance(query, dict) else None
        relevance_values = query.get("relevance") if isinstance(query, dict) else None
        if (
            not isinstance(query_id, str)
            or not query_id
            or query_id in seen_query_ids
            or not isinstance(query_text, str)
            or not query_text.strip()
            or not isinstance(bucket, str)
            or not bucket
            or not isinstance(relevance_values, list)
            or len(relevance_values) != len(work_ids)
            or any(type(grade) is not int or not 0 <= grade <= 3 for grade in relevance_values)
        ):
            raise EvaluationDataError(
                "each query needs a unique ID, bucket, text and full 0-3 judgments"
            )
        seen_query_ids.add(query_id)
        relevance = dict(zip(work_ids, relevance_values, strict=True))
        started = time.perf_counter_ns()
        ranking = index.search(query_text, limit=10)
        latency_ms = (time.perf_counter_ns() - started) / 1_000_000
        latencies.append(latency_ms)
        metrics = score_query(
            [hit.openalex_id for hit in ranking], relevance, cutoffs=(1, 3, 5, 10)
        )
        query_results.append(
            {
                "query_id": query_id,
                "bucket": bucket,
                "result_count": len(ranking),
                "latency_ms": round(latency_ms, 4),
                "metrics": metrics,
                "ranking": [
                    {"openalex_id": hit.openalex_id, "score": round(hit.score, 8)}
                    for hit in ranking
                ],
            }
        )

    all_metrics = _mean_metrics(query_results, metric_names)
    bucket_metrics: dict[str, Any] = {}
    buckets = sorted({item["bucket"] for item in query_results})
    for bucket in buckets:
        bucket_metrics[bucket] = _mean_metrics(
            [item for item in query_results if item["bucket"] == bucket], metric_names
        )
    elapsed_ms = sum(latencies)
    limitations = []
    judgment_status = dataset.get("judgment_status")
    if judgment_status == "assistant_labeled":
        limitations.append("qrels were generated by an assistant and were not human-verified")
    elif judgment_status != "human_reviewed":
        limitations.append("qrels are provisional until reviewed by a human annotator")
    if len(queries) < 30 or len(documents) < 100:
        limitations.append("the benchmark has fewer than 30 queries and 100 documents")
    if len(documents) <= 10:
        limitations.append("the @10 cutoff covers the entire benchmark corpus")

    return {
        "report_schema": REPORT_SCHEMA,
        "dataset": {
            "id": dataset.get("dataset_id"),
            "version": dataset.get("dataset_version"),
            "sha256": dataset_sha256,
            "judgment_status": judgment_status or "unspecified",
            "judgment_protocol": dataset.get("judgment_protocol"),
            "exploratory_only": (
                judgment_status != "human_reviewed" or len(queries) < 30 or len(documents) < 100
            ),
            "limitations": limitations,
        },
        "corpus": {
            "source": corpus_config.get("source"),
            "snapshot_id": snapshot_id,
            "document_count": len(documents),
            "sha256": _corpus_hash(documents),
        },
        "retriever": {
            "name": BM25_VERSION,
            "k1": DEFAULT_K1,
            "b": DEFAULT_B,
            "title_weight": 2,
            "query_term_frequency_weight": "min(term_frequency, 2)",
            "document_fields": ["title", "abstract"],
            "tokenizer": TOKENIZER_VERSION,
            "latency_scope": "in-memory ranker search only; excludes database and process startup",
            "cutoffs": [1, 3, 5, 10],
        },
        "summary": {
            "query_count": len(query_results),
            "empty_result_rate": sum(item["result_count"] == 0 for item in query_results)
            / len(query_results),
            "query_latency_mean_ms": round(sum(latencies) / len(latencies), 4),
            "query_latency_p95_ms": round(_p95(latencies), 4),
            "retrieval_cpu_elapsed_ms": round(elapsed_ms, 4),
            "metrics_macro_average": all_metrics,
            "metrics_by_bucket": bucket_metrics,
        },
        "queries": query_results,
    }


def _load_frozen_corpus(
    store: PaperStore, work_ids: list[str], expected_hashes: dict[str, str]
) -> tuple[str, list[dict[str, Any]]]:
    wanted = set(work_ids)
    for summary in store.list_snapshots(limit=100):
        snapshot_id = summary["snapshot_id"]
        snapshot = store.get_snapshot(snapshot_id)
        if not snapshot:
            continue
        items = snapshot["items"]
        if {item["openalex_id"] for item in items} != wanted:
            continue
        if any(
            expected_hashes.get(item["openalex_id"]) != item["payload_sha256"] for item in items
        ):
            continue
        papers = [store.get_paper(work_id, snapshot_id=snapshot_id) for work_id in work_ids]
        if any(paper is None for paper in papers):
            continue
        return snapshot_id, [paper for paper in papers if paper is not None]
    raise EvaluationDataError(
        "no imported OpenAlex snapshot exactly matches the frozen benchmark work IDs and hashes"
    )


def _corpus_hash(documents: list[RetrievalDocument]) -> str:
    entries = [
        {"openalex_id": document.openalex_id, "content_sha256": document.content_sha256}
        for document in sorted(documents, key=lambda item: item.openalex_id)
    ]
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _mean_metrics(items: list[dict[str, Any]], names: list[str]) -> dict[str, float]:
    return {
        name: round(sum(item["metrics"][name] for item in items) / len(items), 6) for name in names
    }


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]
