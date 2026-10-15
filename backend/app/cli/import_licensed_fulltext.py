"""Import a local UTF-8 paper text after its owner manually confirms the license."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.retrieval.pdf_parser import PARSER_VERSION, parse_pdf_bytes, read_pdf_bytes
from app.sources.arxiv import normalize_arxiv_id
from app.storage.repository import ALLOWED_FULLTEXT_LICENSES, PaperStore

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


def validate_fulltext_manifest(manifest: FullTextManifest) -> FullTextManifest:
    """Validate source identity and license before opening or parsing full-text input."""
    from urllib.parse import urlparse

    if manifest.source_type not in {"openalex", "arxiv"}:
        raise ValueError("source_type must be openalex or arxiv")
    if manifest.source_type == "openalex" and not re.fullmatch(r"W\d+", manifest.source_id):
        raise ValueError("invalid OpenAlex work ID")
    if manifest.source_type == "arxiv":
        normalized_id = normalize_arxiv_id(manifest.source_id)
        if normalized_id != manifest.source_id:
            manifest = manifest.model_copy(update={"source_id": normalized_id})
    canonical_license_url = ALLOWED_FULLTEXT_LICENSES.get(manifest.license_id)
    if canonical_license_url is None:
        raise ValueError("license is not on the full-text processing allowlist")
    if manifest.license_url.rstrip("/") != canonical_license_url.rstrip("/"):
        raise ValueError("license URL does not match the canonical license identifier")
    for label, value in (
        ("text_source_url", manifest.text_source_url),
        ("license_url", manifest.license_url),
        ("license_evidence_url", manifest.license_evidence_url),
    ):
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or len(value) > 2_048:
            raise ValueError(f"{label} must be a bounded HTTPS URL")
    if not manifest.reviewer.strip() or len(manifest.reviewer.strip()) > 128:
        raise ValueError("reviewer must contain 1 to 128 characters")
    if not manifest.attribution.strip() or len(manifest.attribution.strip()) > 500:
        raise ValueError("attribution must contain 1 to 500 characters")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", type=Path, help="local UTF-8 .txt file")
    source.add_argument("--pdf", type=Path, help="local PDF; parsed locally after license review")
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
        manifest = validate_fulltext_manifest(
            FullTextManifest.model_validate_json(args.manifest.read_bytes())
        )
        elements = None
        parser_version = "plain-text-v1"
        document_sha256 = None
        parser_details = None
        if args.pdf:
            if args.pdf.suffix.lower() != ".pdf":
                raise ValueError("PDF input must use the .pdf extension")
            pdf_bytes = read_pdf_bytes(args.pdf)
            document_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            parsed = parse_pdf_bytes(pdf_bytes)
            elements = parsed["elements"]
            parser_details = {
                key: parsed[key]
                for key in (
                    "page_count",
                    "table_regions",
                    "image_regions",
                    "figure_captions",
                    "warnings",
                )
            }
            text = "\n\n".join(str(item["text"]) for item in elements)
            parser_version = PARSER_VERSION
        else:
            if args.text.suffix.lower() != ".txt" or args.text.stat().st_size > MAX_TEXT_BYTES:
                raise ValueError("text input must be a .txt file no larger than 8 MB")
            text = args.text.read_bytes().decode("utf-8", errors="strict")
        result = PaperStore(get_settings().resolved_data_storage_path).ingest_licensed_fulltext(
            **manifest.model_dump(),
            text=text,
            confirm_license_reviewed=True,
            parsed_elements=elements,
            parser_warnings=parsed["warnings"] if args.pdf else None,
            parser_version=parser_version,
            source_document_sha256=document_sha256,
        )
        if parser_details is not None:
            result["parser_details"] = parser_details
    except (OSError, UnicodeDecodeError, ValueError, sqlite3.Error) as error:
        print(f"Licensed text import failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 3
    except Exception as error:
        print(f"Licensed document parsing failed: {type(error).__name__}", file=sys.stderr)
        return 3
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
