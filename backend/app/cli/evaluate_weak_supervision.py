"""Run the read-only weak-supervision BM25 diagnostic over a frozen licensed corpus."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import get_settings
from app.evaluation.weak_supervision import run_evaluation
from app.storage.repository import PaperStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "dev", "test", "all"), default="test")
    parser.add_argument("--k", type=int, default=5)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        store = PaperStore(get_settings().resolved_data_storage_path, readonly=True)
        report = run_evaluation(store, dataset, split=args.split, k=args.k)
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError:
        print(
            "Refusing to overwrite an existing report; choose a new --output path.", file=sys.stderr
        )
        return 2
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"Weak-supervision evaluation failed: {type(error).__name__}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(output),
                "dataset_sha256": report["dataset_sha256"],
                "split": report["split"],
                "summary": report["summary"],
                "gold_standard": report["gold_standard"],
                "quality_claim_allowed": report["quality_claim_allowed"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
