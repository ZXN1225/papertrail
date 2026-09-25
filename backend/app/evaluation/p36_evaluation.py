"""Validate completed P36 human judgments and score pooled ranking candidates."""

from __future__ import annotations

import csv
import hashlib
import io
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from app.evaluation.metrics import score_query
from app.evaluation.p36_pool import RANKERS, PoolReviewError, _sha256_json

CSV_COLUMNS = [
    "row_id",
    "query_id",
    "query_text",
    "query_bucket",
    "openalex_id",
    "title",
    "publication_year",
    "abstract",
    "source_url",
    "reviewed_grade",
    "reviewed",
    "review_note",
]
METRICS = ("hit@1", "hit@3", "hit@5", "mrr@5", "ndcg@1", "ndcg@3", "ndcg@5")
EXCEL_SUPERSCRIPT_DIGITS = str.maketrans({"¹": "1", "²": "2", "³": "3"})


def parse_completed_review_csv(
    raw: bytes, expected_pack: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], str, dict[str, Any]]:
    """Parse UTF-8 or Excel's Windows-936 CSV; reject changed or incomplete rows."""
    try:
        text = raw.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        try:
            text = raw.decode("cp936")
            encoding = "cp936"
        except UnicodeDecodeError as error:
            raise PoolReviewError("review CSV must be UTF-8 or Windows-936 encoded") from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != CSV_COLUMNS:
        raise PoolReviewError("review CSV columns or their order have changed")
    expected_rows = {row.get("row_id"): row for row in expected_pack.get("rows", [])}
    if None in expected_rows or len(expected_rows) != len(expected_pack.get("rows", [])):
        raise PoolReviewError("frozen review package has invalid row IDs")

    reviewed: dict[str, dict[str, Any]] = {}
    lossy_fields = 0
    replaced_characters = 0
    superscript_normalizations = 0
    immutable = [
        column
        for column in CSV_COLUMNS
        if column not in {"reviewed_grade", "reviewed", "review_note"}
    ]
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise PoolReviewError("review CSV contains malformed or extra columns")
        row_id = row["row_id"]
        expected = expected_rows.get(row_id)
        if expected is None or row_id in reviewed:
            raise PoolReviewError("review CSV contains an unknown or duplicate row ID")
        for column in immutable:
            expected_value = expected.get(column)
            expected_text = "" if expected_value is None else str(expected_value)
            if row[column] != expected_text:
                if encoding != "cp936":
                    raise PoolReviewError(f"review CSV changed protected field {column}")
                try:
                    excel_text = expected_text.translate(EXCEL_SUPERSCRIPT_DIGITS)
                    legacy_text = excel_text.encode("cp936", errors="replace").decode("cp936")
                except UnicodeError as error:
                    raise PoolReviewError(
                        "review CSV contains invalid Windows-936 metadata"
                    ) from error
                if row[column] != legacy_text:
                    raise PoolReviewError(f"review CSV changed protected field {column}")
                lossy_fields += 1
                superscript_normalizations += sum(
                    original != normalized
                    for original, normalized in zip(expected_text, excel_text, strict=True)
                )
                replaced_characters += sum(
                    original != converted
                    for original, converted in zip(excel_text, legacy_text, strict=True)
                )
        grade_text = row["reviewed_grade"].strip()
        if grade_text not in {"0", "1", "2", "3"}:
            raise PoolReviewError("each reviewed grade must be an integer from 0 through 3")
        if row["reviewed"].strip().casefold() != "true":
            raise PoolReviewError("every candidate pair must have reviewed=true")
        note = row["review_note"]
        if len(note) > 1000:
            raise PoolReviewError("review notes must be at most 1000 characters")
        reviewed[row_id] = {**row, "reviewed_grade": int(grade_text), "reviewed": True}

    if set(reviewed) != set(expected_rows):
        raise PoolReviewError("review CSV is incomplete; every pooled candidate must be judged")
    return (
        reviewed,
        hashlib.sha256(raw).hexdigest(),
        {
            "encoding": encoding,
            "lossy_metadata_fields": lossy_fields,
            "replacement_characters": replaced_characters,
            "superscript_digit_normalizations": superscript_normalizations,
        },
    )


def evaluate_reviewed_pool(
    pack: dict[str, Any],
    audit: dict[str, Any],
    judgments: dict[str, dict[str, Any]],
    *,
    reviewer: str,
    csv_sha256: str,
    csv_encoding: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate only judged members of the pooled top-five candidate set."""
    if not reviewer.strip() or len(reviewer.strip()) > 120:
        raise PoolReviewError("reviewer must be a non-empty name of at most 120 characters")
    if pack.get("review_status") != "awaiting_human_review" or pack.get("review_schema") != (
        "papertrail-p36-blind-review-v1"
    ):
        raise PoolReviewError("review pack is not a valid pending P36 package")
    if audit.get("audit_schema") != "papertrail-p36-pool-audit-v1":
        raise PoolReviewError("P36 audit sidecar is invalid")
    if audit.get("review_pack_sha256") != _sha256_json(pack):
        raise PoolReviewError("audit sidecar does not match the frozen review package")

    rows_by_id = {row["row_id"]: row for row in pack["rows"]}
    if set(rows_by_id) != set(judgments):
        raise PoolReviewError("human judgments do not cover the complete pooled candidate set")
    relevance_by_query: dict[str, dict[str, int]] = defaultdict(dict)
    bucket_by_query: dict[str, str] = {}
    for row_id, row in rows_by_id.items():
        judgment = judgments[row_id]
        if (
            type(judgment.get("reviewed_grade")) is not int
            or not 0 <= judgment["reviewed_grade"] <= 3
            or judgment.get("reviewed") is not True
        ):
            raise PoolReviewError("human judgments contain an invalid grade or review state")
        query_id = row["query_id"]
        work_id = row["openalex_id"]
        if work_id in relevance_by_query[query_id]:
            raise PoolReviewError("review package contains duplicate query-paper pairs")
        relevance_by_query[query_id][work_id] = judgment["reviewed_grade"]
        bucket_by_query[query_id] = row["query_bucket"]

    origin_by_pair: dict[tuple[str, str], dict[str, list[int]]] = {}
    for entry in audit.get("origins", []):
        pair = (entry.get("query_id"), entry.get("openalex_id"))
        if pair in origin_by_pair or entry.get("row_id") not in rows_by_id:
            raise PoolReviewError("audit candidate origins contain invalid or duplicate rows")
        if (
            rows_by_id[entry["row_id"]]["query_id"] != pair[0]
            or rows_by_id[entry["row_id"]]["openalex_id"] != pair[1]
        ):
            raise PoolReviewError("audit origins do not match the blinded review package")
        origin_by_pair[pair] = entry.get("origins", {})
    if len(origin_by_pair) != len(rows_by_id):
        raise PoolReviewError("audit sidecar is missing pooled candidate origins")

    query_ids = sorted(relevance_by_query)
    per_method: dict[str, list[dict[str, Any]]] = {method: [] for method, _, _ in RANKERS}
    query_results: list[dict[str, Any]] = []
    for query_id in query_ids:
        qrels = relevance_by_query[query_id]
        method_metrics: dict[str, dict[str, float]] = {}
        method_rankings: dict[str, list[str]] = {}
        for method, _, _ in RANKERS:
            ranked: list[tuple[int, str]] = []
            for work_id in qrels:
                ranks = origin_by_pair[(query_id, work_id)].get(method)
                if ranks is not None:
                    if (
                        not isinstance(ranks, list)
                        or len(ranks) != 1
                        or type(ranks[0]) is not int
                        or not 1 <= ranks[0] <= pack["sampling"]["per_ranker_depth"]
                    ):
                        raise PoolReviewError("audit contains an invalid rank position")
                    ranked.append((ranks[0], work_id))
            ranked.sort()
            ranking = [work_id for _, work_id in ranked]
            if not ranking or len({rank for rank, _ in ranked}) != len(ranked):
                raise PoolReviewError(f"{method} ranking is missing or has duplicate ranks")
            metrics = score_query(ranking, qrels, cutoffs=(1, 3, 5))
            method_rankings[method] = ranking
            method_metrics[method] = metrics
            per_method[method].append({"query_id": query_id, "metrics": metrics})
        query_results.append(
            {
                "query_id": query_id,
                "bucket": bucket_by_query[query_id],
                "judged_candidate_count": len(qrels),
                "methods": method_metrics,
                "ranked_work_ids": method_rankings,
            }
        )

    summary = {
        method: {
            "macro_average": {
                metric: round(statistics.mean(row["metrics"][metric] for row in rows), 6)
                for metric in METRICS
            },
            "delta_vs_bm25": None,
        }
        for method, rows in per_method.items()
    }
    baseline = summary["bm25"]["macro_average"]
    for method in summary:
        if method != "bm25":
            summary[method]["delta_vs_bm25"] = {
                metric: round(summary[method]["macro_average"][metric] - baseline[metric], 6)
                for metric in METRICS
            }
    return {
        "report_schema": "papertrail-p36-blind-pool-evaluation-v1",
        "dataset": {
            "id": pack["dataset_id"],
            "version": pack["dataset_version"],
            "sha256": pack["dataset_sha256"],
            "judgment_status": "human_reviewed_candidate_pool",
            "reviewer": reviewer.strip(),
            "reviewed_pair_count": len(judgments),
            "challenge_query_count": len(query_ids),
            "challenge_buckets": sorted(set(bucket_by_query.values())),
            "exploratory_only": True,
            "quality_claim_allowed": False,
            "limitations": [
                "queries were selected by disagreement under prior unreviewed AI judgments",
                "only the pooled top-five candidates per ranker were judged",
                "documents outside the pool are unjudged, not irrelevant",
                "the sample is small and must not be generalized to user-query performance",
            ],
        },
        "human_review": {
            "csv_sha256": csv_sha256,
            "csv_encoding": csv_encoding,
            "reviewed_at": datetime.now(UTC).isoformat(),
            "score_guide": pack["score_guide"],
        },
        "provenance": {
            "review_pack_sha256": audit["review_pack_sha256"],
            "p14_report_sha256": audit["p14_report_sha256"],
            "p17_report_sha256": audit["p17_report_sha256"],
            "selection_rule": audit["selection_rule"],
            "ranker_definitions": audit["ranker_definitions"],
        },
        "pool": {
            "candidate_count": len(rows_by_id),
            "query_count": len(query_ids),
            "per_ranker_depth": pack["sampling"]["per_ranker_depth"],
            "evaluation_cutoffs": [1, 3, 5],
            "unjudged_handling": "exclude all papers outside the union pool; report is pool-only",
        },
        "methods": summary,
        "queries": query_results,
    }
