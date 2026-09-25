"""Build a small blinded pooled relevance-review package from P14/P17 rankings."""

from __future__ import annotations

import hashlib
from typing import Any

REVIEW_SCHEMA = "papertrail-p36-blind-review-v1"
AUDIT_SCHEMA = "papertrail-p36-pool-audit-v1"
RANKERS = (
    ("bm25", "p14", "bm25"),
    ("small_dense", "p14", "dense"),
    ("small_hybrid_rrf_k60", "p14", "hybrid_rrf_k60"),
    ("large_dense", "p17", "dense"),
    ("large_hybrid_rrf_k60", "p17", "hybrid_rrf_k60"),
)
DEFAULT_QUERY_COUNT = 8
DEFAULT_DEPTH = 5
MAX_REVIEW_PAIRS = 200


class PoolReviewError(ValueError):
    """The ranking reports, metadata pack, or generated review pool is invalid."""


def build_blind_review_pool(
    dataset: dict[str, Any],
    dataset_sha256: str,
    metadata_pack: dict[str, Any],
    small_report: dict[str, Any],
    small_report_sha256: str,
    large_report: dict[str, Any],
    large_report_sha256: str,
    *,
    query_count: int = DEFAULT_QUERY_COUNT,
    depth: int = DEFAULT_DEPTH,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pool the top-ranked candidates, withholding method attribution from reviewers.

    Query selection intentionally favors high disagreement under the old AI qrels;
    this creates a challenge set and must not be treated as a representative sample.
    """
    if type(query_count) is not int or not 1 <= query_count <= DEFAULT_QUERY_COUNT:
        raise PoolReviewError(f"query_count must be between 1 and {DEFAULT_QUERY_COUNT}")
    if type(depth) is not int or not 1 <= depth <= DEFAULT_DEPTH:
        raise PoolReviewError(f"depth must be between 1 and {DEFAULT_DEPTH}")
    if query_count * depth * len(RANKERS) > MAX_REVIEW_PAIRS:
        raise PoolReviewError("requested pool can exceed the 200-pair review limit")

    _validate_inputs(dataset, dataset_sha256, metadata_pack, small_report, large_report)
    small_rows = _index_report(small_report)
    large_rows = _index_report(large_report)
    dataset_queries = {query["query_id"]: query for query in dataset["queries"]}
    if set(small_rows) != set(large_rows) or set(small_rows) != set(dataset_queries):
        raise PoolReviewError("P14, P17 and dataset must contain the same query IDs")
    ranked_queries = []
    for query_id, query in dataset_queries.items():
        small_row = small_rows[query_id]
        large_row = large_rows[query_id]
        if any(
            small_row.get(field) != query.get(field) or large_row.get(field) != query.get(field)
            for field in ("text", "bucket")
        ):
            raise PoolReviewError("query text or bucket differs between dataset and reports")
        ranked_queries.append(
            {
                "query_id": query_id,
                "text": query["text"],
                "bucket": query["bucket"],
                "spread": small_row.get("ndcg@10_spread"),
            }
        )
    ranked_queries.sort(key=lambda row: (-_finite_number(row["spread"]), row["query_id"]))

    selected: list[dict[str, Any]] = []
    buckets: set[str] = set()
    for query in ranked_queries:
        if query["bucket"] not in buckets:
            selected.append(query)
            buckets.add(query["bucket"])
            if len(selected) == query_count:
                break
    if len(selected) < query_count:
        raise PoolReviewError("not enough distinct query buckets for the requested sample")

    document_by_id = {
        document.get("openalex_id"): document for document in metadata_pack.get("documents", [])
    }
    pooled: dict[tuple[str, str], dict[str, Any]] = {}
    origins: dict[str, dict[str, list[int]]] = {}
    reports = {"p14": small_rows, "p17": large_rows}
    for query in selected:
        query_id = query["query_id"]
        for ranker, report_key, method in RANKERS:
            ranked = reports[report_key][query_id]["methods"].get(method, {}).get("top_10")
            if not isinstance(ranked, list) or not ranked:
                raise PoolReviewError(f"ranking {ranker} is missing for query {query_id}")
            for rank, work_id in enumerate(ranked[:depth], start=1):
                document = document_by_id.get(work_id)
                if not isinstance(document, dict):
                    raise PoolReviewError(f"ranking references unknown work {work_id}")
                pair = (query_id, work_id)
                pooled[pair] = document
                row_id = _row_id(dataset_sha256, query_id, work_id)
                origins.setdefault(row_id, {}).setdefault(ranker, []).append(rank)

    if len(pooled) > MAX_REVIEW_PAIRS:
        raise PoolReviewError("generated pool exceeds the 200-pair review limit")

    selected_by_id = {row["query_id"]: row for row in selected}
    review_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for (query_id, work_id), document in pooled.items():
        query = selected_by_id[query_id]
        row_id = _row_id(dataset_sha256, query_id, work_id)
        review_rows.append(
            {
                "row_id": row_id,
                "query_id": query_id,
                "query_text": query["text"],
                "query_bucket": query["bucket"],
                "openalex_id": work_id,
                "title": document.get("title") or "",
                "publication_year": document.get("publication_year"),
                "abstract": document.get("abstract"),
                "source_url": document.get("source_url"),
                "reviewed_grade": None,
                "reviewed": False,
                "review_note": "",
            }
        )
        audit_rows.append(
            {
                "row_id": row_id,
                "query_id": query_id,
                "openalex_id": work_id,
                "origins": origins[row_id],
            }
        )
    review_rows.sort(key=lambda row: _stable_order(dataset_sha256, row["row_id"]))
    audit_rows.sort(key=lambda row: row["row_id"])

    review_pack = {
        "review_schema": REVIEW_SCHEMA,
        "review_status": "awaiting_human_review",
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["dataset_version"],
        "dataset_sha256": dataset_sha256,
        "corpus_snapshot_id": metadata_pack["corpus_snapshot_id"],
        "corpus_content_sha256": dataset["corpus"]["content_sha256"],
        "sampling": {
            "kind": "disagreement_enriched_challenge_pool",
            "query_count": len(selected),
            "candidate_pair_count": len(review_rows),
            "max_candidate_pair_count": MAX_REVIEW_PAIRS,
            "per_ranker_depth": depth,
            "instructions": (
                "Judge each query-paper pair independently using the query and metadata. "
                "Do not infer relevance from the paper source or ordering. "
                "Unreviewed rows are unknown, not grade 0."
            ),
        },
        "score_guide": {
            "0": "not relevant to the research question",
            "1": "useful background or partial relevance",
            "2": "directly relevant to the question",
            "3": "highly relevant / directly addresses the question",
        },
        "rows": review_rows,
    }
    audit = {
        "audit_schema": AUDIT_SCHEMA,
        "review_pack_sha256": _sha256_json(review_pack),
        "dataset_sha256": dataset_sha256,
        "p14_report_sha256": small_report_sha256,
        "p17_report_sha256": large_report_sha256,
        "selection_rule": (
            "Select one query per bucket in descending P14 NDCG@10 method spread; "
            "ties use query ID. Spread is based on unreviewed assistant qrels, so this "
            "is a challenge sample and not representative."
        ),
        "ranker_definitions": {
            "bm25": "shared BM25 baseline from P14/P17",
            "small_dense": "P14 text-embedding-3-small Dense cosine",
            "small_hybrid_rrf_k60": "P14 Small Dense + BM25 RRF@60",
            "large_dense": "P17 text-embedding-3-large Dense cosine",
            "large_hybrid_rrf_k60": "P17 Large Dense + BM25 RRF@60",
        },
        "selected_queries": [
            {key: query[key] for key in ("query_id", "bucket", "spread")} for query in selected
        ],
        "origins": audit_rows,
    }
    return review_pack, audit


def _validate_inputs(
    dataset: dict[str, Any],
    dataset_sha256: str,
    metadata_pack: dict[str, Any],
    small_report: dict[str, Any],
    large_report: dict[str, Any],
) -> None:
    if dataset.get("judgment_status") != "assistant_labeled":
        raise PoolReviewError("challenge pool source must be explicitly assistant_labeled")
    if dataset.get("dataset_id") != "papertrail-p13-rag-retrieval-ai-labeled-v1":
        raise PoolReviewError("challenge pool source dataset is not the frozen P13 AI dataset")
    corpus = dataset.get("corpus")
    work_ids = corpus.get("work_ids") if isinstance(corpus, dict) else None
    hashes = corpus.get("content_sha256") if isinstance(corpus, dict) else None
    queries = dataset.get("queries")
    if (
        not isinstance(work_ids, list)
        or len(work_ids) != 100
        or len(set(work_ids)) != 100
        or not isinstance(hashes, dict)
        or set(hashes) != set(work_ids)
        or not isinstance(queries, list)
        or len(queries) != 30
    ):
        raise PoolReviewError("challenge pool requires the frozen 100-work/30-query P13 data")
    query_ids = [query.get("query_id") for query in queries if isinstance(query, dict)]
    if (
        len(query_ids) != 30
        or len(set(query_ids)) != 30
        or any(
            not isinstance(query.get("text"), str)
            or not query["text"].strip()
            or not isinstance(query.get("bucket"), str)
            or not query["bucket"].strip()
            for query in queries
        )
    ):
        raise PoolReviewError("P13 queries require unique IDs, text and intent buckets")
    expected_doc_hashes = {
        item.get("openalex_id"): item.get("content_sha256")
        for item in metadata_pack.get("documents", [])
    }
    if (
        metadata_pack.get("review_status") != "awaiting_human_review"
        or len(expected_doc_hashes) != len(work_ids)
        or metadata_pack.get("corpus_snapshot_id") != corpus.get("snapshot_id")
        or metadata_pack.get("corpus_work_ids") != work_ids
        or metadata_pack.get("corpus_content_sha256") != hashes
        or expected_doc_hashes != hashes
    ):
        raise PoolReviewError("metadata review pack does not match the frozen P13 corpus")
    for report in (small_report, large_report):
        report_dataset = report.get("dataset")
        report_corpus = report.get("corpus")
        if (
            report.get("report_schema") != "papertrail-p14-retrieval-comparison-v1"
            or not isinstance(report_dataset, dict)
            or report_dataset.get("judgment_status") != "assistant_labeled"
            or report_dataset.get("sha256") != dataset_sha256
            or not isinstance(report_corpus, dict)
            or report_corpus.get("snapshot_id") != corpus.get("snapshot_id")
            or report_corpus.get("document_count") != 100
            or report_corpus.get("query_count") != 30
        ):
            raise PoolReviewError("P14/P17 report does not match the frozen P13 evaluation")


def _index_report(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = report.get("queries_ranked_by_method_disagreement")
    if not isinstance(rows, list) or len(rows) != 30:
        raise PoolReviewError("ranking report must include all 30 P13 queries")
    indexed = {row.get("query_id"): row for row in rows if isinstance(row, dict)}
    if len(indexed) != 30 or None in indexed:
        raise PoolReviewError("ranking report query IDs must be unique")
    return indexed


def _row_id(dataset_sha256: str, query_id: str, work_id: str) -> str:
    value = f"{dataset_sha256}:{query_id}:{work_id}".encode()
    return hashlib.sha256(value).hexdigest()[:16]


def _stable_order(seed: str, value: str) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def _sha256_json(value: dict[str, Any]) -> str:
    import json

    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return float("-inf")
    return float(value)
