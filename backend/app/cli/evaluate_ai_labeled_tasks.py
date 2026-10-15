"""Run the read-only AI-labeled evidence-grounding diagnostic over the licensed corpus."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import get_settings
from app.evaluation.ai_labeled_tasks import (
    AiLabeledTaskError,
    load_dataset,
    run_evaluation,
)
from app.storage.repository import PaperStore

DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "evaluation" / "ai-labeled-licensed-v1.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset, digest = load_dataset(args.dataset)
        store = PaperStore(get_settings().resolved_data_storage_path, readonly=True)
        report = run_evaluation(store, dataset, digest)
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError:
        print(
            "Refusing to overwrite an existing report; choose a new --output path.",
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        message = str(error) if isinstance(error, AiLabeledTaskError) else type(error).__name__
        print(f"AI-labeled task evaluation failed: {message}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(output),
                "dataset_sha256": digest,
                "provider_calls": 0,
                "quality_claim_allowed": report["quality_claim_allowed"],
                "label_source": report["label_source"],
                "summary": {
                    "task_count": report["dataset"]["task_count"],
                    "answerable_count": report["dataset"]["answerable_count"],
                    "unanswerable_count": report["dataset"]["unanswerable_count"],
                    "evidence_hit_at_1": report["summary"]["evidence_hit_at_1"],
                    f"evidence_hit_at_{report['retrieval']['top_k']}": report["summary"][
                        f"evidence_hit_at_{report['retrieval']['top_k']}"
                    ],
                    "top1_score_separability": report["summary"]["top1_score_separability"],
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
