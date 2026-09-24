"""Import one bounded page of arXiv metadata into the local catalog."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from app.config import get_settings
from app.sources.arxiv import ArxivClient, ArxivError
from app.storage.repository import PaperStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True, help="arXiv metadata query")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--max-results", type=int, default=10, choices=range(1, 26))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    try:
        with ArxivClient(timeout_seconds=20) as client:
            page = client.search(args.query, start=args.start, max_results=args.max_results)
    except (ArxivError, ValueError) as error:
        print(f"arXiv import failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    try:
        summary = PaperStore(settings.resolved_data_storage_path).import_arxiv_page(
            page, query=args.query, start=args.start
        )
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as error:
        print(f"Local import failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 3
    print(
        json.dumps(
            {
                "status": "imported",
                "source": "arxiv",
                "source_license": "CC0-1.0",
                "snapshot_id": summary.snapshot_id,
                "total_matching_count": summary.total_matching_count,
                "records_received": summary.records_received,
                "new_works": summary.new_works,
                "new_versions": summary.new_versions,
                "unchanged_works": summary.unchanged_works,
                "linked_by_exact_doi": summary.linked_by_exact_doi,
                "content_sha256": summary.content_sha256,
                "database_path": str(settings.resolved_data_storage_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
