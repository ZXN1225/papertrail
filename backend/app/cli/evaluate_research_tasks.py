"""Run the isolated synthetic research-task lexical regression benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.evaluation.research_tasks import (
    DEFAULT_DATASET_PATH,
    ResearchTaskEvaluationError,
    load_dataset,
    run_evaluation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument(
        "--output", type=Path, default=Path("reports/TEST-research-task-report.json")
    )
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--min-overlap-tokens", type=int, default=2)
    parser.add_argument("--split", choices=("all", "dev", "test"), default="all")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset, dataset_sha256 = load_dataset(args.dataset)
        report = run_evaluation(
            dataset,
            dataset_sha256,
            top_k=args.top_k,
            min_overlap_tokens=args.min_overlap_tokens,
            split=args.split,
        )
    except (OSError, ResearchTaskEvaluationError) as error:
        print(
            f"Synthetic research-task evaluation failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(args.output.resolve()),
                "dataset_sha256": report["dataset"]["sha256"],
                "synthetic": report["dataset"]["synthetic"],
                "quality_claim_allowed": report["dataset"]["quality_claim_allowed"],
                "documents": report["dataset"]["document_count"],
                "tasks": report["dataset"]["task_count"],
                "split": report["dataset"]["split"],
                "answerable": report["dataset"]["answerable_count"],
                "unanswerable": report["dataset"]["unanswerable_count"],
                "summary": report["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
