"""Import one bounded page of OpenAlex Works metadata into the local SQLite catalog."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from app.config import get_settings
from app.sources.openalex import OpenAlexClient, OpenAlexError
from app.storage.repository import PaperStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True, help="OpenAlex Works text search")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--per-page", type=int, default=10, choices=range(1, 101))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    client = OpenAlexClient(
        settings.openalex_api_key.get_secret_value() if settings.openalex_api_key else None
    )
    try:
        page = client.search_works(args.query, page=args.page, per_page=args.per_page)
    except (OpenAlexError, ValueError) as error:
        print(f"OpenAlex import failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    finally:
        client.close()

    try:
        summary = PaperStore(settings.resolved_data_storage_path).import_openalex_page(
            page, query=args.query, requested_page=args.page, per_page=args.per_page
        )
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as error:
        print(f"Local import failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 3

    print(
        json.dumps(
            {
                "status": "imported",
                "snapshot_id": summary.snapshot_id,
                "total_matching_count": summary.total_matching_count,
                "records_received": summary.records_received,
                "new_works": summary.new_works,
                "new_versions": summary.new_versions,
                "unchanged_works": summary.unchanged_works,
                "content_sha256": summary.content_sha256,
                "database_path": str(settings.resolved_data_storage_path),
                "source": "openalex",
                "source_license": "CC0-1.0",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
