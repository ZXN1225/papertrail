"""Evaluate the frozen local PaperTrail corpus using the versioned BM25 baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.evaluation.runner import (
    DEFAULT_DATASET_PATH,
    EvaluationDataError,
    load_dataset,
    run_evaluation,
)
from app.storage.repository import PaperStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", type=Path, default=Path("reports/p05-bm25-report.json"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset, dataset_sha256 = load_dataset(args.dataset)
        report = run_evaluation(
            PaperStore(get_settings().resolved_data_storage_path), dataset, dataset_sha256
        )
    except (EvaluationDataError, OSError, ValueError, RuntimeError) as error:
        print(f"BM25 evaluation failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(args.output.resolve()),
                "dataset_sha256": report["dataset"]["sha256"],
                "corpus_snapshot_id": report["corpus"]["snapshot_id"],
                "document_count": report["corpus"]["document_count"],
                "query_count": report["summary"]["query_count"],
                "exploratory_only": report["dataset"]["exploratory_only"],
                "metrics_macro_average": report["summary"]["metrics_macro_average"],
                "empty_result_rate": report["summary"]["empty_result_rate"],
                "query_latency_mean_ms": report["summary"]["query_latency_mean_ms"],
                "query_latency_p95_ms": report["summary"]["query_latency_p95_ms"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
