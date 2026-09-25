"""Prepare a blinded, bounded human review pool from the P14/P17 rankers."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from app.evaluation.p36_pool import PoolReviewError, build_blind_review_pool
from app.evaluation.runner import load_dataset

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = BACKEND_ROOT / "data/evaluation/p13_ai_labeled_v1.json"
DEFAULT_METADATA_PACK = BACKEND_ROOT / "reports/p13-review-pack.json"
DEFAULT_SMALL_REPORT = BACKEND_ROOT / "reports/p14-retrieval-comparison.json"
DEFAULT_LARGE_REPORT = BACKEND_ROOT / "reports/p17-large-retrieval-comparison.json"
DEFAULT_OUTPUT = BACKEND_ROOT / "reports/p36-blind-review-pack.json"
DEFAULT_CSV_OUTPUT = BACKEND_ROOT / "reports/p36-blind-review.csv"
DEFAULT_AUDIT = BACKEND_ROOT / "reports/p36-blind-review-audit.json"


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
        raise PoolReviewError(f"{path} already exists; choose new output paths") from error


def _write_new_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
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
    try:
        with path.open("x", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    except FileExistsError as error:
        raise PoolReviewError(f"{path} already exists; choose new output paths") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--metadata-pack", type=Path, default=DEFAULT_METADATA_PACK)
    parser.add_argument("--small-report", type=Path, default=DEFAULT_SMALL_REPORT)
    parser.add_argument("--large-report", type=Path, default=DEFAULT_LARGE_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV_OUTPUT)
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--queries", type=int, default=8)
    parser.add_argument("--depth", type=int, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset, dataset_sha256 = load_dataset(args.dataset)
        metadata_pack, _ = _read_json(args.metadata_pack)
        small_report, small_sha256 = _read_json(args.small_report)
        large_report, large_sha256 = _read_json(args.large_report)
        pack, audit = build_blind_review_pool(
            dataset,
            dataset_sha256,
            metadata_pack,
            small_report,
            small_sha256,
            large_report,
            large_sha256,
            query_count=args.queries,
            depth=args.depth,
        )
        output_paths = {
            args.output.resolve(),
            args.csv_output.resolve(),
            args.audit_output.resolve(),
        }
        input_paths = {
            args.dataset.resolve(),
            args.metadata_pack.resolve(),
            args.small_report.resolve(),
            args.large_report.resolve(),
        }
        if len(output_paths) != 3:
            raise PoolReviewError("review pack, CSV and audit outputs must be different files")
        if output_paths & input_paths:
            raise PoolReviewError("output paths must not overwrite any source input")
        if any(path.exists() for path in output_paths):
            raise PoolReviewError("an output path already exists; choose three new paths")
        _write_new(args.output, pack)
        _write_new_csv(args.csv_output, pack["rows"])
        _write_new(args.audit_output, audit)
        print(
            json.dumps(
                {
                    "status": "review_pool_prepared",
                    "review_pack": str(args.output.resolve()),
                    "csv": str(args.csv_output.resolve()),
                    "audit": str(args.audit_output.resolve()),
                    "queries": pack["sampling"]["query_count"],
                    "candidate_pairs": pack["sampling"]["candidate_pair_count"],
                    "max_candidate_pairs": pack["sampling"]["max_candidate_pair_count"],
                    "review_status": pack["review_status"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (PoolReviewError, OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as error:
        print(f"P36 review preparation failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
