"""Run the offline-only PaperTrail P12 benchmark and write a local JSON report."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.evaluation.hybrid import HybridEvaluationError
from app.evaluation.p12 import run_p12_benchmark

DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "data/evaluation/p10_synthetic_v1.json"
RUNNER_PATH = Path(__file__).resolve().parents[1] / "evaluation/p12.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=Path("reports/p12-offline-report.json"))
    args = parser.parse_args(argv)
    try:
        raw = args.dataset.read_bytes()
        dataset = json.loads(raw)
        report = run_p12_benchmark(dataset, hashlib.sha256(raw).hexdigest())
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        HybridEvaluationError,
        ValueError,
    ) as error:
        print(f"P12 offline evaluation failed: {type(error).__name__}", file=sys.stderr)
        return 2
    report["reproducibility"] = {
        "command_args": [
            sys.executable,
            "-m",
            "app.cli.evaluate_p12",
            "--dataset",
            str(args.dataset),
            "--output",
            str(args.output),
        ],
        "dataset_path": args.dataset.as_posix(),
        "output_path": args.output.resolve().as_posix(),
        "runner_sha256": hashlib.sha256(RUNNER_PATH.read_bytes()).hexdigest(),
        "python_version": platform.python_version(),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(args.output.resolve()),
                "dataset_sha256": report["retrieval"]["dataset"]["sha256"],
                "synthetic": report["benchmark"]["synthetic"],
                "quality_claim_allowed": report["benchmark"]["quality_claim_allowed"],
                "agent_pass_rate": report["agent"]["pass_rate"],
                "blocked_unauthorized_attempts": report["agent"]["blocked_unauthorized_attempts"],
                "unauthorized_tool_executions": report["agent"]["unauthorized_tool_executions"],
                "estimated_cost_usd": report["benchmark"]["estimated_cost_usd"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["agent"]["passed_cases"] == report["agent"]["case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
