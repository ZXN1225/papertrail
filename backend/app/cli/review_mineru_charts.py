"""Export, import, and score offline MinerU chart-fact review packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from app.evaluation.mineru_chart_review import (
    MineruChartReviewError,
    apply_review_pack,
    build_review_pack,
    evaluate_reviewed_dataset,
    load_dataset,
)


def _write_new(path: Path, value: dict, *, protected: set[Path]) -> None:
    if path.resolve() in {item.resolve() for item in protected}:
        raise MineruChartReviewError("output must not overwrite an input file")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError as error:
        raise MineruChartReviewError("output already exists; choose a new path") from error


def _verify_page_images(dataset: dict, root: Path) -> None:
    checked: dict[str, str] = {}
    rows = [*dataset["tasks"], *dataset["page_audits"]]
    for row in rows:
        relative = row["page_image_ref"]
        expected_sha256 = row["page_image_sha256"]
        if relative in checked:
            if checked[relative] != expected_sha256:
                raise MineruChartReviewError("one page image reference has conflicting hashes")
            continue
        checked[relative] = expected_sha256
        image_path = (root / Path(*relative.split("/"))).resolve()
        try:
            image_path.relative_to(root.resolve())
        except ValueError as error:
            raise MineruChartReviewError(
                "page image reference escapes the dataset directory"
            ) from error
        try:
            actual = hashlib.sha256(image_path.read_bytes()).hexdigest()
        except OSError as error:
            raise MineruChartReviewError("referenced local page image is unavailable") from error
        if actual != expected_sha256:
            raise MineruChartReviewError("referenced page image hash differs from the frozen task")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="create a frozen, unscored human-review pack")
    export.add_argument("--dataset", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    apply = commands.add_parser("import", help="validate completed labels into a new dataset")
    apply.add_argument("--dataset", type=Path, required=True)
    apply.add_argument("--pack", type=Path, required=True)
    apply.add_argument("--output", type=Path, required=True)
    apply.add_argument("--reviewer", required=True)
    apply.add_argument("--confirm-human-review", action="store_true")
    evaluate = commands.add_parser("evaluate", help="score held-out reviewed chart facts")
    evaluate.add_argument("--dataset", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset, dataset_sha256 = load_dataset(args.dataset)
        if args.command == "export":
            _verify_page_images(dataset, args.dataset.resolve().parent)
            pack = build_review_pack(dataset, dataset_sha256)
            _write_new(args.output, pack, protected={args.dataset})
            result = {
                "status": "exported",
                "output": str(args.output.resolve()),
                "dataset_sha256": dataset_sha256,
                "task_count": len(pack["rows"]),
                "source_count": len(dataset["sources"]),
                "review_status": pack["review_status"],
            }
        elif args.command == "import":
            if not args.confirm_human_review:
                raise MineruChartReviewError("import requires explicit --confirm-human-review")
            _verify_page_images(dataset, args.dataset.resolve().parent)
            try:
                pack = json.loads(args.pack.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise MineruChartReviewError("review pack must be readable UTF-8 JSON") from error
            reviewed = apply_review_pack(
                dataset,
                dataset_sha256,
                pack,
                reviewer=args.reviewer,
            )
            _write_new(args.output, reviewed, protected={args.dataset, args.pack})
            result = {
                "status": "imported_human_review",
                "output": str(args.output.resolve()),
                "reviewer": reviewed["review_audit"]["reviewer"],
                "reviewed_task_count": reviewed["review_audit"]["reviewed_task_count"],
                "judgment_status": reviewed["judgment_status"],
                "gold_standard": reviewed["gold_standard"],
            }
        else:
            report = evaluate_reviewed_dataset(dataset, dataset_sha256)
            _write_new(args.output, report, protected={args.dataset})
            result = {
                "status": "evaluated",
                "output": str(args.output.resolve()),
                "test_task_count": report["test_task_count"],
                "quality_claim_allowed": False,
            }
    except (OSError, MineruChartReviewError, ValueError, TypeError, KeyError) as error:
        print(f"MinerU chart review failed: {type(error).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
