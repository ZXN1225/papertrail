"""Human review pack creation and validation for the frozen P05 judgments."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

REVIEW_SCHEMA = "papertrail-qrels-review-v1"


class QrelsReviewError(ValueError):
    """A review pack is stale, incomplete, or malformed."""


def build_review_pack(
    dataset: dict[str, Any],
    dataset_sha256: str,
    snapshot_id: str,
    papers: list[dict[str, Any]],
) -> dict[str, Any]:
    work_ids = dataset.get("corpus", {}).get("work_ids")
    queries = dataset.get("queries")
    if not isinstance(work_ids, list) or not isinstance(queries, list) or not queries:
        raise QrelsReviewError("dataset must contain frozen work IDs and queries")
    if [paper.get("openalex_id") for paper in papers] != work_ids:
        raise QrelsReviewError("snapshot papers do not match the frozen dataset order")
    if any(
        paper.get("content_sha256") != dataset["corpus"]["content_sha256"].get(work_id)
        for work_id, paper in zip(work_ids, papers, strict=True)
    ):
        raise QrelsReviewError("snapshot paper hash differs from the frozen dataset")

    docs = {
        paper["openalex_id"]: {
            "openalex_id": paper["openalex_id"],
            "title": paper.get("title") or "",
            "publication_year": paper.get("publication_year"),
            "abstract": paper.get("abstract"),
            "content_sha256": paper["content_sha256"],
            "metadata_license": paper.get("metadata_license"),
            "source_url": paper.get("source_url"),
        }
        for paper in papers
    }
    rows: list[dict[str, Any]] = []
    seen_queries: set[str] = set()
    for query in queries:
        query_id = query.get("query_id")
        grades = query.get("relevance")
        if (
            not isinstance(query_id, str)
            or query_id in seen_queries
            or not isinstance(grades, list)
            or len(grades) != len(work_ids)
            or any(type(grade) is not int or not 0 <= grade <= 3 for grade in grades)
        ):
            raise QrelsReviewError("query IDs and suggested grades must be complete and valid")
        seen_queries.add(query_id)
        for work_id, suggested_grade in zip(work_ids, grades, strict=True):
            rows.append(
                {
                    "query_id": query_id,
                    "query_text": query.get("text"),
                    "query_bucket": query.get("bucket"),
                    "openalex_id": work_id,
                    "suggested_grade": suggested_grade,
                    "reviewed_grade": None,
                    "reviewed": False,
                    "review_note": "",
                }
            )
    return {
        "review_schema": REVIEW_SCHEMA,
        "review_status": "awaiting_human_review",
        "dataset_id": dataset.get("dataset_id"),
        "dataset_version": dataset.get("dataset_version"),
        "source_dataset_sha256": dataset_sha256,
        "corpus_snapshot_id": snapshot_id,
        "corpus_work_ids": work_ids.copy(),
        "corpus_content_sha256": dataset["corpus"]["content_sha256"].copy(),
        "score_guide": {
            "0": "not relevant",
            "1": "background relevance",
            "2": "direct relevance",
            "3": "high relevance",
        },
        "documents": list(docs.values()),
        "rows": rows,
    }


def apply_review_pack(
    dataset: dict[str, Any],
    dataset_sha256: str,
    pack: dict[str, Any],
    current_papers: list[dict[str, Any]],
    *,
    reviewer: str,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    if not reviewer.strip() or len(reviewer.strip()) > 120:
        raise QrelsReviewError("reviewer must be a non-empty name of at most 120 characters")
    if pack.get("review_schema") != REVIEW_SCHEMA:
        raise QrelsReviewError("unsupported review pack schema")
    if pack.get("review_status") != "awaiting_human_review":
        raise QrelsReviewError("review pack is not awaiting review")
    if pack.get("source_dataset_sha256") != dataset_sha256:
        raise QrelsReviewError("review pack belongs to a different dataset version")
    if pack.get("dataset_id") != dataset.get("dataset_id"):
        raise QrelsReviewError("review pack dataset ID does not match")

    expected_hashes = dataset.get("corpus", {}).get("content_sha256")
    work_ids = dataset.get("corpus", {}).get("work_ids")
    if (
        not isinstance(expected_hashes, dict)
        or not isinstance(work_ids, list)
        or pack.get("corpus_work_ids") != work_ids
        or pack.get("corpus_content_sha256") != expected_hashes
    ):
        raise QrelsReviewError("review pack corpus identity does not match the dataset")
    if [paper.get("openalex_id") for paper in current_papers] != work_ids:
        raise QrelsReviewError("current frozen snapshot does not match the dataset order")
    actual_documents = [
        {
            "openalex_id": paper["openalex_id"],
            "title": paper.get("title") or "",
            "publication_year": paper.get("publication_year"),
            "abstract": paper.get("abstract"),
            "content_sha256": paper["content_sha256"],
            "metadata_license": paper.get("metadata_license"),
            "source_url": paper.get("source_url"),
        }
        for paper in current_papers
    ]
    if pack.get("documents") != actual_documents:
        raise QrelsReviewError("review pack paper metadata changed since export")
    if pack.get("corpus_snapshot_id") != current_papers[0].get("snapshot_id"):
        raise QrelsReviewError("review pack snapshot is stale")

    queries = dataset.get("queries")
    if not isinstance(queries, list) or not queries:
        raise QrelsReviewError("dataset queries must be a non-empty list")
    query_by_id = {query.get("query_id"): query for query in queries}
    if None in query_by_id or len(query_by_id) != len(queries):
        raise QrelsReviewError("dataset query IDs must be valid and unique")
    expected_pairs = {(query_id, work_id) for query_id in query_by_id for work_id in work_ids}
    rows = pack.get("rows")
    if not isinstance(rows, list) or len(rows) != len(expected_pairs):
        raise QrelsReviewError("review pack must contain every query-document pair exactly once")
    row_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise QrelsReviewError("review pack row must be an object")
        pair = (row.get("query_id"), row.get("openalex_id"))
        if pair not in expected_pairs or pair in row_by_pair:
            raise QrelsReviewError("review pack contains unknown or duplicate query-document pairs")
        query = query_by_id[pair[0]]
        work_index = work_ids.index(pair[1])
        if (
            row.get("query_text") != query.get("text")
            or row.get("query_bucket") != query.get("bucket")
            or row.get("suggested_grade") != query["relevance"][work_index]
        ):
            raise QrelsReviewError("query text, bucket or suggested grade changed since export")
        grade = row.get("reviewed_grade")
        if type(grade) is not int or not 0 <= grade <= 3 or row.get("reviewed") is not True:
            raise QrelsReviewError(
                "every pair needs a reviewed grade from 0 to 3 and reviewed=true"
            )
        if (
            not isinstance(row.get("review_note", ""), str)
            or len(row.get("review_note", "")) > 1000
        ):
            raise QrelsReviewError("review notes must be text of at most 1000 characters")
        row_by_pair[pair] = row
    if set(row_by_pair) != expected_pairs:
        raise QrelsReviewError("review pack is missing query-document pairs")

    reviewed_dataset = {**dataset}
    reviewed_queries: list[dict[str, Any]] = []
    for query in queries:
        grades = [
            row_by_pair[(query["query_id"], work_id)]["reviewed_grade"] for work_id in work_ids
        ]
        reviewed_queries.append({**query, "relevance": grades})
    reviewed_dataset["queries"] = reviewed_queries
    dataset_version = dataset.get("dataset_version")
    if type(dataset_version) is int:
        reviewed_dataset["dataset_version"] = dataset_version + 1
    reviewed_dataset["judgment_status"] = "human_reviewed"
    reviewed_dataset["review_audit"] = {
        "reviewer": reviewer.strip(),
        "reviewed_at": reviewed_at or datetime.now(UTC).isoformat(),
        "review_pack_sha256": hashlib.sha256(
            json.dumps(pack, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "reviewed_pair_count": len(expected_pairs),
        "entries": [
            {
                "query_id": row["query_id"],
                "openalex_id": row["openalex_id"],
                "suggested_grade": row["suggested_grade"],
                "reviewed_grade": row["reviewed_grade"],
                "review_note": row.get("review_note", ""),
            }
            for row in rows
        ],
    }
    return reviewed_dataset
