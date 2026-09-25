"""Validate the completed P36 blind-review CSV and evaluate pooled rankings."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from app.evaluation.p36_evaluation import evaluate_reviewed_pool, parse_completed_review_csv
from app.evaluation.p36_pool import PoolReviewError, build_blind_review_pool
from app.evaluation.runner import load_dataset

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = BACKEND_ROOT / "data/evaluation/p13_ai_labeled_v1.json"
DEFAULT_METADATA_PACK = BACKEND_ROOT / "reports/p13-review-pack.json"
DEFAULT_SMALL_REPORT = BACKEND_ROOT / "reports/p14-retrieval-comparison.json"
DEFAULT_LARGE_REPORT = BACKEND_ROOT / "reports/p17-large-retrieval-comparison.json"
DEFAULT_REVIEW_PACK = BACKEND_ROOT / "reports/p36-blind-review-pack.json"
DEFAULT_AUDIT = BACKEND_ROOT / "reports/p36-blind-review-audit.json"
DEFAULT_COMPLETED_CSV = BACKEND_ROOT / "reports/p36-blind-review-completed.csv"
DEFAULT_OUTPUT = BACKEND_ROOT / "reports/p36-human-reviewed-pool-report.json"


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise PoolReviewError(f"{path} must contain a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _write_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
    except FileExistsError as error:
        raise PoolReviewError(f"{path} already exists; choose a new output path") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--metadata-pack", type=Path, default=DEFAULT_METADATA_PACK)
    parser.add_argument("--small-report", type=Path, default=DEFAULT_SMALL_REPORT)
    parser.add_argument("--large-report", type=Path, default=DEFAULT_LARGE_REPORT)
    parser.add_argument("--review-pack", type=Path, default=DEFAULT_REVIEW_PACK)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--completed-csv", type=Path, default=DEFAULT_COMPLETED_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reviewer", default="me")
    parser.add_argument("--confirm-human-review", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.confirm_human_review:
            raise PoolReviewError("evaluation requires explicit --confirm-human-review")
        dataset, dataset_sha256 = load_dataset(args.dataset)
        metadata_pack, _ = _read_json(args.metadata_pack)
        small_report, small_report_sha256 = _read_json(args.small_report)
        large_report, large_report_sha256 = _read_json(args.large_report)
        stored_pack, _ = _read_json(args.review_pack)
        stored_audit, _ = _read_json(args.audit)
        expected_pack, expected_audit = build_blind_review_pool(
            dataset,
            dataset_sha256,
            metadata_pack,
            small_report,
            small_report_sha256,
            large_report,
            large_report_sha256,
        )
        if stored_pack != expected_pack or stored_audit != expected_audit:
            raise PoolReviewError("stored review pack or audit is stale or was modified")
        judgments, csv_sha256, csv_encoding = parse_completed_review_csv(
            args.completed_csv.read_bytes(), stored_pack
        )
        report = evaluate_reviewed_pool(
            stored_pack,
            stored_audit,
            judgments,
            reviewer=args.reviewer,
            csv_sha256=csv_sha256,
            csv_encoding=csv_encoding,
        )
        output_path = args.output.resolve()
        input_paths = {
            args.dataset.resolve(),
            args.metadata_pack.resolve(),
            args.small_report.resolve(),
            args.large_report.resolve(),
            args.review_pack.resolve(),
            args.audit.resolve(),
            args.completed_csv.resolve(),
        }
        if output_path in input_paths:
            raise PoolReviewError("output must not overwrite an input file")
        _write_new(args.output, report)
        print(
            json.dumps(
                {
                    "status": "human_reviewed_pool_evaluated",
                    "output": str(output_path),
                    "reviewer": report["dataset"]["reviewer"],
                    "reviewed_pairs": report["dataset"]["reviewed_pair_count"],
                    "queries": report["dataset"]["challenge_query_count"],
                    "exploratory_only": report["dataset"]["exploratory_only"],
                    "quality_claim_allowed": report["dataset"]["quality_claim_allowed"],
                },
                sort_keys=True,
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
        print(f"P36 review evaluation failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
