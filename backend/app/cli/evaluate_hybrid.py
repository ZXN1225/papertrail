"""Run the isolated synthetic P10 retrieval-mechanics evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from app.evaluation.hybrid import HybridEvaluationError, run_synthetic_hybrid_evaluation

DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "data/evaluation/p10_synthetic_v1.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=Path("reports/p10-synthetic-report.json"))
    args = parser.parse_args(argv)
    try:
        raw = args.dataset.read_bytes()
        dataset = json.loads(raw)
        report = run_synthetic_hybrid_evaluation(dataset, hashlib.sha256(raw).hexdigest())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, HybridEvaluationError) as error:
        print(f"Synthetic hybrid evaluation failed: {type(error).__name__}", file=sys.stderr)
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
                "synthetic": report["dataset"]["synthetic"],
                "quality_claim_allowed": report["dataset"]["quality_claim_allowed"],
                "documents": report["dataset"]["document_count"],
                "queries": report["dataset"]["query_count"],
                "methods": report["methods"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
