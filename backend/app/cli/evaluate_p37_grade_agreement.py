"""Compare P36 human grades with the existing P13 assistant suggestions offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from app.evaluation.grade_agreement import evaluate_grade_agreement
from app.evaluation.p36_evaluation import parse_completed_review_csv
from app.evaluation.p36_pool import PoolReviewError, build_blind_review_pool
from app.evaluation.runner import load_dataset

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = BACKEND_ROOT / "data/evaluation/p13_ai_labeled_v1.json"
DEFAULT_METADATA = BACKEND_ROOT / "reports/p13-review-pack.json"
DEFAULT_ASSISTANT_QRELS = BACKEND_ROOT / "reports/p13-ai-labeled-pack.json"
DEFAULT_SMALL_REPORT = BACKEND_ROOT / "reports/p14-retrieval-comparison.json"
DEFAULT_LARGE_REPORT = BACKEND_ROOT / "reports/p17-large-retrieval-comparison.json"
DEFAULT_REVIEW_PACK = BACKEND_ROOT / "reports/p36-blind-review-pack.json"
DEFAULT_AUDIT = BACKEND_ROOT / "reports/p36-blind-review-audit.json"
DEFAULT_COMPLETED_CSV = BACKEND_ROOT / "reports/p36-blind-review-completed.csv"
DEFAULT_OUTPUT = BACKEND_ROOT / "reports/p37-assistant-human-grade-agreement.json"


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise PoolReviewError(f"{path} must contain a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _write_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--metadata-pack", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--assistant-qrels", type=Path, default=DEFAULT_ASSISTANT_QRELS)
    parser.add_argument("--small-report", type=Path, default=DEFAULT_SMALL_REPORT)
    parser.add_argument("--large-report", type=Path, default=DEFAULT_LARGE_REPORT)
    parser.add_argument("--review-pack", type=Path, default=DEFAULT_REVIEW_PACK)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--completed-csv", type=Path, default=DEFAULT_COMPLETED_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--confirm-human-review", action="store_true")
    args = parser.parse_args(argv)

    try:
        if not args.confirm_human_review:
            raise PoolReviewError("comparison requires explicit --confirm-human-review")
        dataset, dataset_sha256 = load_dataset(args.dataset)
        metadata, _ = _read_json(args.metadata_pack)
        small, small_sha256 = _read_json(args.small_report)
        large, large_sha256 = _read_json(args.large_report)
        ai_pack, ai_sha256 = _read_json(args.assistant_qrels)
        review_pack, _ = _read_json(args.review_pack)
        audit, _ = _read_json(args.audit)
        expected_pack, expected_audit = build_blind_review_pool(
            dataset, dataset_sha256, metadata, small, small_sha256, large, large_sha256
        )
        if review_pack != expected_pack or audit != expected_audit:
            raise PoolReviewError("P36 review pack or audit is stale or modified")
        if (
            ai_pack.get("review_status") != "assistant_labeled_not_human_reviewed"
            or ai_pack.get("source_dataset_sha256") != metadata.get("source_dataset_sha256")
            or not isinstance(ai_pack.get("rows"), list)
        ):
            raise PoolReviewError("P13 assistant qrels do not match the frozen review package")
        judgments, csv_sha256, csv_encoding = parse_completed_review_csv(
            args.completed_csv.read_bytes(), review_pack
        )
        human_grades = {
            (row["query_id"], row["openalex_id"]): row["reviewed_grade"]
            for row in judgments.values()
        }
        assistant_grades: dict[tuple[str, str], int] = {}
        for row in ai_pack["rows"]:
            key = (row.get("query_id"), row.get("openalex_id"))
            grade = row.get("suggested_grade")
            if key in assistant_grades or type(grade) is not int or not 0 <= grade <= 3:
                raise PoolReviewError(
                    "P13 assistant qrels contain duplicate pairs or invalid grades"
                )
            assistant_grades[key] = grade
        if not set(human_grades).issubset(assistant_grades):
            raise PoolReviewError("P13 assistant qrels are missing human-reviewed candidate pairs")
        paired_assistant_grades = {pair: assistant_grades[pair] for pair in human_grades}
        buckets = {row["query_id"]: row["query_bucket"] for row in review_pack["rows"]}
        metrics = evaluate_grade_agreement(
            paired_assistant_grades,
            human_grades,
            query_buckets=buckets,
        )
        report = {
            "report_schema": "papertrail-p37-assistant-human-grade-agreement-v1",
            "dataset": {
                "judgment_status": "paired_assistant_suggestions_and_human_review",
                "pair_count": metrics["pair_count"],
                "query_count": metrics["query_count"],
                "exploratory_only": True,
                "quality_claim_allowed": False,
                "limitations": [
                    "P36 queries were selected by disagreement under prior assistant qrels",
                    "P36 candidates are pooled from ranking top-fives, not randomly sampled",
                    "one human reviewer completed the grades",
                    "results do not establish a calibrated LLM judge or general retrieval quality",
                ],
            },
            "provenance": {
                "p13_assistant_qrels_sha256": ai_sha256,
                "p36_review_pack_sha256": audit["review_pack_sha256"],
                "human_review_csv_sha256": csv_sha256,
                "human_review_csv_encoding": csv_encoding,
            },
            "agreement": metrics,
        }
        output_path = args.output.resolve()
        inputs = {
            args.dataset.resolve(),
            args.metadata_pack.resolve(),
            args.assistant_qrels.resolve(),
            args.small_report.resolve(),
            args.large_report.resolve(),
            args.review_pack.resolve(),
            args.audit.resolve(),
            args.completed_csv.resolve(),
        }
        if output_path in inputs:
            raise PoolReviewError("output must not overwrite an input file")
        _write_new(args.output, report)
        print(
            json.dumps(
                {
                    "status": "completed",
                    "output": str(output_path),
                    "pair_count": metrics["pair_count"],
                    "exact_agreement": metrics["exact_agreement"],
                    "within_one_grade": metrics["within_one_grade"],
                    "mean_absolute_error": metrics["mean_absolute_error"],
                    "quadratic_weighted_kappa": metrics["quadratic_weighted_kappa"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (
        PoolReviewError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        print(f"P37 grade agreement failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
