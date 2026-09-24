"""Exploratory BM25/dense/hybrid runner for explicitly synthetic fixtures."""

from __future__ import annotations

import math
import statistics
import time
from typing import Any

from app.evaluation.metrics import score_query
from app.retrieval.bm25 import BM25Index
from app.retrieval.vectors import dense_rank, reciprocal_rank_fusion

METRICS = (
    "hit@1",
    "hit@3",
    "hit@5",
    "hit@10",
    "mrr@10",
    "ndcg@1",
    "ndcg@3",
    "ndcg@5",
    "ndcg@10",
)


class HybridEvaluationError(ValueError):
    """Invalid or non-isolated synthetic retrieval fixture."""


def run_synthetic_hybrid_evaluation(dataset: dict[str, Any], dataset_sha256: str) -> dict[str, Any]:
    documents = dataset.get("documents")
    queries = dataset.get("queries")
    if dataset.get("synthetic") is not True or not isinstance(documents, list) or not documents:
        raise HybridEvaluationError("only a non-empty synthetic=true fixture is accepted")
    if not isinstance(queries, list) or not queries:
        raise HybridEvaluationError("synthetic fixture requires queries")
    ids: set[str] = set()
    dimensions: set[int] = set()
    for document in documents:
        if (
            not isinstance(document, dict)
            or document.get("synthetic") is not True
            or not isinstance(document.get("id"), str)
            or not document["id"].startswith("TEST-")
            or document["id"] in ids
            or not isinstance(document.get("text"), str)
            or not document["text"].strip()
            or not isinstance(document.get("title"), str)
        ):
            raise HybridEvaluationError(
                "every fixture document must be unique TEST-* synthetic data"
            )
        ids.add(document["id"])
        vector = document.get("fixture_vector")
        if not _valid_vector(vector):
            raise HybridEvaluationError("fixture vectors must be finite non-empty numeric arrays")
        dimensions.add(len(vector))
    if len(dimensions) != 1:
        raise HybridEvaluationError("all fixture vectors must have one dimension")

    index = BM25Index(
        [
            {
                "openalex_id": document["id"],
                "title": document["title"],
                "abstract": document["text"],
            }
            for document in documents
        ]
    )
    rankings: dict[str, list[list[str]]] = {"bm25": [], "dense": [], "hybrid_rrf_k60": []}
    qids: set[str] = set()
    latencies: dict[str, list[float]] = {key: [] for key in rankings}
    results: list[dict[str, Any]] = []
    for query in queries:
        if (
            not isinstance(query, dict)
            or not isinstance(query.get("id"), str)
            or query["id"] in qids
            or not isinstance(query.get("text"), str)
            or not query["text"].strip()
            or not _valid_vector(query.get("fixture_vector"))
            or len(query["fixture_vector"]) not in dimensions
            or not isinstance(query.get("relevance"), dict)
            or set(query["relevance"]) != ids
            or any(
                type(grade) is not int or not 0 <= grade <= 3
                for grade in query["relevance"].values()
            )
        ):
            raise HybridEvaluationError(
                "each query requires a unique ID, valid vector and TEST-* qrels"
            )
        qids.add(query["id"])
        vectors = {doc["id"]: doc["fixture_vector"] for doc in documents}
        started = time.perf_counter_ns()
        bm25 = index.search(query["text"], limit=len(documents))
        latencies["bm25"].append(_elapsed(started))
        started = time.perf_counter_ns()
        dense = dense_rank(query["fixture_vector"], vectors)
        latencies["dense"].append(_elapsed(started))
        started = time.perf_counter_ns()
        hybrid = reciprocal_rank_fusion(
            [[(hit.openalex_id, hit.score) for hit in bm25], dense], k=60
        )
        latencies["hybrid_rrf_k60"].append(_elapsed(started))
        per_query: dict[str, Any] = {"query_id": query["id"], "rankings": {}}
        for method, ranking in (
            ("bm25", [hit.openalex_id for hit in bm25]),
            ("dense", [item_id for item_id, _ in dense]),
            ("hybrid_rrf_k60", [item_id for item_id, _ in hybrid]),
        ):
            rankings[method].append(ranking)
            per_query["rankings"][method] = {
                "ids": ranking[:10],
                "metrics": score_query(ranking, query["relevance"]),
            }
        results.append(per_query)

    method_reports: dict[str, Any] = {}
    for method, per_query_rankings in rankings.items():
        metric_values = [
            score_query(ranking, query["relevance"])
            for ranking, query in zip(per_query_rankings, queries, strict=True)
        ]
        lat = latencies[method]
        method_reports[method] = {
            "metrics_macro_average": {
                key: round(statistics.mean(item[key] for item in metric_values), 6)
                for key in METRICS
            },
            "latency_mean_ms": round(statistics.mean(lat), 4),
            "latency_p50_ms": round(_percentile(lat, 0.50), 4),
            "latency_p95_ms": round(_percentile(lat, 0.95), 4),
        }
    return {
        "report_schema": "papertrail-hybrid-evaluation-v1",
        "dataset": {
            "id": dataset.get("dataset_id"),
            "version": dataset.get("dataset_version"),
            "sha256": dataset_sha256,
            "synthetic": True,
            "exploratory_only": True,
            "quality_claim_allowed": False,
            "document_count": len(documents),
            "query_count": len(queries),
            "embedding_source": "fixed_synthetic_fixture_vectors; no provider calls",
            "dimensions": dimensions.pop(),
            "embedding_calls": 0,
            "embedding_input_tokens": 0,
            "estimated_embedding_cost_usd": 0.0,
        },
        "retrieval": {
            "dense_metric": "cosine_similarity",
            "hybrid": "reciprocal_rank_fusion",
            "rrf_k": 60,
            "tie_break": "ascending_TEST_id",
        },
        "methods": method_reports,
        "queries": results,
    }


def _valid_vector(vector: Any) -> bool:
    return (
        isinstance(vector, list)
        and bool(vector)
        and all(type(value) in {int, float} and math.isfinite(value) for value in vector)
    )


def _elapsed(started_ns: int) -> float:
    return (time.perf_counter_ns() - started_ns) / 1_000_000


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]
