"""Remove one paper's full-text content from the local searchable index."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from app.config import get_settings
from app.storage.repository import PaperStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-type", choices=("openalex", "arxiv"), required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--reason", required=True, help="3-500 character audit reason")
    args = parser.parse_args(argv)
    try:
        deleted = PaperStore(get_settings().resolved_data_storage_path).delete_fulltext(
            args.source_type, args.source_id, reason=args.reason
        )
    except (ValueError, sqlite3.Error) as error:
        print(f"Full-text deletion failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"status": "deleted" if deleted else "not_found"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
