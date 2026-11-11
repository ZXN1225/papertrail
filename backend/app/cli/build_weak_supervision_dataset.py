"""Build a read-only weak-supervision retrieval dataset from approved licensed full text."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import get_settings
from app.evaluation.weak_supervision import build_dataset_from_store
from app.storage.repository import PaperStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-type", choices=("arxiv", "openalex"))
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        store = PaperStore(get_settings().resolved_data_storage_path, readonly=True)
        dataset = build_dataset_from_store(store, source_type=args.source_type)
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(dataset, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError:
        print(
            "Refusing to overwrite an existing dataset; choose a new --output path.",
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Weak-supervision dataset build failed: {type(error).__name__}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(output),
                "dataset_sha256": dataset["dataset_sha256"],
                "candidate_count": sum(dataset["split_counts"]["query_count"].values()),
                "split_counts": dataset["split_counts"],
                "gold_standard": dataset["gold_standard"],
                "quality_claim_allowed": dataset["quality_claim_allowed"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
