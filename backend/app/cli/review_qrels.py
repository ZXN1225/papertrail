"""Export and import the frozen P05 qrels human-review package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.evaluation.review import QrelsReviewError, apply_review_pack, build_review_pack
from app.evaluation.runner import (
    DEFAULT_DATASET_PATH,
    EvaluationDataError,
    _load_frozen_corpus,
    load_dataset,
)
from app.storage.repository import PaperStore

DEFAULT_PACK_PATH = Path("reports/p05-review-pack.json")
DEFAULT_REVIEWED_DATASET = Path("data/evaluation/p05_human_reviewed_v2.json")


def _load_snapshot_papers(
    store: PaperStore, dataset: dict[str, Any], snapshot_id: str | None = None
) -> tuple[str, list[dict[str, Any]]]:
    work_ids = dataset["corpus"]["work_ids"]
    hashes = dataset["corpus"]["content_sha256"]
    if snapshot_id is None:
        return _load_frozen_corpus(store, work_ids, hashes)
    snapshot = store.get_snapshot(snapshot_id)
    if snapshot is None:
        raise QrelsReviewError("the review pack snapshot is not present in the local catalog")
    entries = snapshot["items"]
    if {item["openalex_id"] for item in entries} != set(work_ids) or any(
        hashes.get(item["openalex_id"]) != item["payload_sha256"] for item in entries
    ):
        raise QrelsReviewError("the review pack snapshot no longer matches the frozen corpus")
    papers = [store.get_paper(work_id, snapshot_id=snapshot_id) for work_id in work_ids]
    if any(paper is None for paper in papers):
        raise QrelsReviewError("the review pack snapshot is incomplete")
    return snapshot_id, [paper for paper in papers if paper is not None]


def _write_new_json(path: Path, value: dict[str, Any], *, protected_paths: set[Path]) -> None:
    destination = path.resolve()
    if destination in protected_paths:
        raise QrelsReviewError("output must be a new file, not the input dataset or review pack")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
    except FileExistsError as error:
        raise QrelsReviewError("output file already exists; choose a new path") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser(
        "export", help="create a review pack from the local snapshot"
    )
    export_parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    export_parser.add_argument("--output", type=Path, default=DEFAULT_PACK_PATH)
    import_parser = subparsers.add_parser(
        "import", help="validate a completed pack into a new dataset"
    )
    import_parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    import_parser.add_argument("--pack", type=Path, required=True)
    import_parser.add_argument("--output", type=Path, default=DEFAULT_REVIEWED_DATASET)
    import_parser.add_argument("--reviewer", required=True)
    import_parser.add_argument("--confirm-human-review", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset, dataset_sha256 = load_dataset(args.dataset)
        store = PaperStore(get_settings().resolved_data_storage_path)
        if args.command == "export":
            snapshot_id, papers = _load_snapshot_papers(store, dataset)
            pack = build_review_pack(dataset, dataset_sha256, snapshot_id, papers)
            _write_new_json(
                args.output,
                pack,
                protected_paths={args.dataset.resolve()},
            )
            print(
                json.dumps(
                    {
                        "status": "exported",
                        "output": str(args.output.resolve()),
                        "dataset_sha256": dataset_sha256,
                        "snapshot_id": snapshot_id,
                        "documents": len(papers),
                        "queries": len(dataset["queries"]),
                        "judgment_pairs": len(pack["rows"]),
                        "review_status": pack["review_status"],
                    },
                    sort_keys=True,
                )
            )
            return 0

        if not args.confirm_human_review:
            raise QrelsReviewError("import requires explicit --confirm-human-review")
        pack = json.loads(args.pack.read_text(encoding="utf-8"))
        snapshot_id = pack.get("corpus_snapshot_id") if isinstance(pack, dict) else None
        if not isinstance(snapshot_id, str):
            raise QrelsReviewError("review package has no valid snapshot ID")
        _, papers = _load_snapshot_papers(store, dataset, snapshot_id)
        reviewed = apply_review_pack(
            dataset,
            dataset_sha256,
            pack,
            papers,
            reviewer=args.reviewer,
        )
        _write_new_json(
            args.output,
            reviewed,
            protected_paths={args.dataset.resolve(), args.pack.resolve()},
        )
        print(
            json.dumps(
                {
                    "status": "imported_human_review",
                    "output": str(args.output.resolve()),
                    "judgment_status": reviewed["judgment_status"],
                    "reviewer": reviewed["review_audit"]["reviewer"],
                    "reviewed_pair_count": reviewed["review_audit"]["reviewed_pair_count"],
                    "review_pack_sha256": reviewed["review_audit"]["review_pack_sha256"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (
        EvaluationDataError,
        QrelsReviewError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
    ) as error:
        print(f"Qrels review workflow failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
