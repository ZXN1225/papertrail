"""Three-way metadata retrieval comparison for the exploratory P13 benchmark."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Any, Protocol

from app.evaluation.metrics import score_query
from app.evaluation.runner import _load_frozen_corpus
from app.retrieval.bm25 import BM25Index
from app.retrieval.vectors import dense_rank, reciprocal_rank_fusion
from app.storage.repository import PaperStore

METHODS = ("bm25", "dense", "hybrid_rrf_k60")
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


class BatchEmbedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> Any: ...


class P14EvaluationError(ValueError):
    """Invalid P14 dataset, corpus or embedding response."""


def run_p14_comparison(
    store: PaperStore,
    dataset: dict[str, Any],
    dataset_sha256: str,
    embedder: BatchEmbedder,
    *,
    price_per_million_usd: float | None,
) -> dict[str, Any]:
    if dataset.get("judgment_status") != "assistant_labeled":
        raise P14EvaluationError("P14 requires an explicitly assistant_labeled dataset")
    corpus_config = dataset.get("corpus")
    queries = dataset.get("queries")
    if not isinstance(corpus_config, dict) or not isinstance(queries, list):
        raise P14EvaluationError("dataset requires corpus and queries")
    work_ids = corpus_config.get("work_ids")
    hashes = corpus_config.get("content_sha256")
    if (
        not isinstance(work_ids, list)
        or len(work_ids) != 100
        or len(set(work_ids)) != 100
        or not isinstance(hashes, dict)
        or set(hashes) != set(work_ids)
        or len(queries) != 30
    ):
        raise P14EvaluationError("P14 requires exactly 100 frozen works and 30 queries")
    snapshot_id, papers = _load_frozen_corpus(store, work_ids, hashes)
    if snapshot_id != corpus_config.get("snapshot_id"):
        raise P14EvaluationError("frozen snapshot ID does not match dataset")
    papers_by_id = {paper["openalex_id"]: paper for paper in papers}
    docs = [papers_by_id[work_id] for work_id in work_ids]
    doc_texts = [_document_text(paper) for paper in docs]
    query_rows = _validate_queries(queries, work_ids)
    all_texts = [*doc_texts, *(row["text"] for row in query_rows)]

    vectors: list[list[float]] = []
    embedding_tokens = 0
    embedding_calls = 0
    for offset in range(0, len(all_texts), 64):
        batch = embedder.embed(all_texts[offset : offset + 64])
        if not isinstance(batch.vectors, list) or len(batch.vectors) != len(
            all_texts[offset : offset + 64]
        ):
            raise P14EvaluationError("embedding provider returned an invalid batch")
        vectors.extend(batch.vectors)
        embedding_tokens += batch.input_tokens
        embedding_calls += 1
    if (
        len(vectors) != len(all_texts)
        or not vectors
        or any(len(vector) != len(vectors[0]) for vector in vectors)
    ):
        raise P14EvaluationError("embedding dimensions or count are inconsistent")

    doc_vectors = {work_id: vector for work_id, vector in zip(work_ids, vectors[:100], strict=True)}
    query_vectors = vectors[100:]
    bm25_index = BM25Index(docs)
    per_method: dict[str, list[dict[str, Any]]] = {method: [] for method in METHODS}
    query_diagnostics: list[dict[str, Any]] = []
    for query, query_vector in zip(query_rows, query_vectors, strict=True):
        bm25_hits = bm25_index.search(query["text"], limit=100)
        dense_hits = dense_rank(query_vector, doc_vectors)
        hybrid_hits = reciprocal_rank_fusion([bm25_hits, dense_hits], k=60)
        rankings = {
            "bm25": [hit.openalex_id for hit in bm25_hits],
            "dense": [work_id for work_id, _ in dense_hits],
            "hybrid_rrf_k60": [work_id for work_id, _ in hybrid_hits],
        }
        query_metrics = {
            method: score_query(ranking[:10], query["relevance"])
            for method, ranking in rankings.items()
        }
        for method, metrics in query_metrics.items():
            per_method[method].append(
                {"query_id": query["query_id"], "bucket": query["bucket"], "metrics": metrics}
            )
        ndcg_values = [query_metrics[method]["ndcg@10"] for method in METHODS]
        query_diagnostics.append(
            {
                "query_id": query["query_id"],
                "bucket": query["bucket"],
                "text": query["text"],
                "best_method_ndcg@10": METHODS[ndcg_values.index(max(ndcg_values))],
                "ndcg@10_spread": round(max(ndcg_values) - min(ndcg_values), 6),
                "methods": {
                    method: {
                        "metrics": query_metrics[method],
                        "top_3": rankings[method][:3],
                        "top_10": rankings[method][:10],
                    }
                    for method in METHODS
                },
            }
        )

    by_method: dict[str, Any] = {}
    bucket_names = sorted({row["bucket"] for row in query_rows})
    for method, rows in per_method.items():
        by_method[method] = {
            "metrics_macro_average": _mean_metrics(rows),
            "metrics_by_bucket": {
                bucket: _mean_metrics([row for row in rows if row["bucket"] == bucket])
                for bucket in bucket_names
            },
        }
    query_diagnostics.sort(key=lambda row: (-row["ndcg@10_spread"], row["query_id"]))
    return {
        "report_schema": "papertrail-p14-retrieval-comparison-v1",
        "dataset": {
            "id": dataset.get("dataset_id"),
            "version": dataset.get("dataset_version"),
            "sha256": dataset_sha256,
            "judgment_status": "assistant_labeled",
            "human_reviewed": False,
            "exploratory_only": True,
            "quality_claim_allowed": False,
            "limitations": [
                "qrels were copied from assistant suggestions and were not human-verified",
                "dense embeddings were generated for this run; repeated runs may incur API cost",
                "only one frozen 100-work corpus and 30 queries were evaluated",
            ],
        },
        "corpus": {
            "source": "openalex",
            "snapshot_id": snapshot_id,
            "document_count": len(docs),
            "query_count": len(query_rows),
        },
        "embedding": {
            "provider": "openai",
            "model": embedder.model,
            "input_count": len(all_texts),
            "api_calls": embedding_calls,
            "input_tokens": embedding_tokens,
            "dimensions": len(vectors[0]),
            "estimated_cost_usd": (
                round(price_per_million_usd * embedding_tokens / 1_000_000, 10)
                if price_per_million_usd is not None
                else None
            ),
            "vectors_persisted": False,
        },
        "retrieval": {
            "methods": list(METHODS),
            "dense_metric": "cosine_similarity",
            "hybrid": "reciprocal_rank_fusion",
            "rrf_k": 60,
            "cutoffs": [1, 3, 5, 10],
        },
        "methods": by_method,
        "queries_ranked_by_method_disagreement": query_diagnostics,
    }


def _document_text(paper: dict[str, Any]) -> str:
    title = (paper.get("title") or "").strip()
    abstract = (paper.get("abstract") or "").strip()
    text = f"Title: {title}\nAbstract: {abstract}".strip()
    if not text or len(text) > 8_000:
        raise P14EvaluationError(
            "paper title/abstract is empty or exceeds the provider input limit"
        )
    return text


def _validate_queries(queries: list[Any], work_ids: list[str]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for query in queries:
        if (
            not isinstance(query, dict)
            or not isinstance(query.get("query_id"), str)
            or query["query_id"] in seen
            or not isinstance(query.get("text"), str)
            or not query["text"].strip()
            or not isinstance(query.get("bucket"), str)
            or not isinstance(query.get("relevance"), list)
            or len(query["relevance"]) != len(work_ids)
            or any(type(grade) is not int or not 0 <= grade <= 3 for grade in query["relevance"])
        ):
            raise P14EvaluationError("each query requires unique ID, bucket, text and full qrels")
        seen.add(query["query_id"])
        validated.append(
            {
                "query_id": query["query_id"],
                "text": query["text"],
                "bucket": query["bucket"],
                "relevance": dict(zip(work_ids, query["relevance"], strict=True)),
            }
        )
    return validated


def _mean_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    return {
        metric: round(statistics.mean(row["metrics"][metric] for row in rows), 6)
        for metric in METRICS
    }
