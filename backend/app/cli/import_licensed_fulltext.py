"""Import a local UTF-8 paper text after its owner manually confirms the license."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.storage.repository import PaperStore

MAX_MANIFEST_BYTES = 32_768
MAX_TEXT_BYTES = 8_000_000


class FullTextManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_type: str
    source_id: str = Field(min_length=4, max_length=64)
    text_source_url: str = Field(min_length=9, max_length=2_048)
    license_id: str
    license_url: str = Field(min_length=9, max_length=2_048)
    license_evidence_url: str = Field(min_length=9, max_length=2_048)
    reviewer: str = Field(min_length=1, max_length=128)
    attribution: str = Field(min_length=1, max_length=500)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--text", type=Path, required=True, help="local UTF-8 .txt file")
    parser.add_argument(
        "--confirm-license-reviewed",
        action="store_true",
        help="confirm you checked the source license permits the intended local processing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.confirm_license_reviewed:
        print(
            "Refusing import: inspect the source license and pass --confirm-license-reviewed.",
            file=sys.stderr,
        )
        return 2
    try:
        if args.manifest.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("manifest exceeds the 32 KiB limit")
        if args.text.suffix.lower() != ".txt" or args.text.stat().st_size > MAX_TEXT_BYTES:
            raise ValueError("text input must be a .txt file no larger than 8 MB")
        manifest = FullTextManifest.model_validate_json(args.manifest.read_bytes())
        text = args.text.read_bytes().decode("utf-8", errors="strict")
        result = PaperStore(get_settings().resolved_data_storage_path).ingest_licensed_fulltext(
            **manifest.model_dump(),
            text=text,
            confirm_license_reviewed=True,
        )
    except (OSError, UnicodeDecodeError, ValueError, sqlite3.Error) as error:
        print(f"Licensed text import failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 3
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
