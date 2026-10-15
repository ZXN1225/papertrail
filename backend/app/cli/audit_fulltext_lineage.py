"""Audit local licensed PDFs against the current read-only full-text index."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.sources.arxiv import normalize_arxiv_id
from app.storage.repository import ALLOWED_FULLTEXT_LICENSES, PaperStore

REPORT_SCHEMA = "papertrail.fulltext-lineage-audit.v1"
HASH_READ_SIZE = 1024 * 1024


class FullTextLineageAuditError(ValueError):
    """The audit request is malformed or the database is not read-only."""


def parse_source_pdf(value: str) -> tuple[str, Path]:
    source_id, separator, path_text = value.partition("=")
    if not separator or not path_text.strip():
        raise FullTextLineageAuditError("each --pdf value must be SOURCE_ID=PATH")
    try:
        canonical_id = normalize_arxiv_id(source_id.strip())
    except ValueError as error:
        raise FullTextLineageAuditError("--pdf contains an invalid arXiv ID") from error
    return canonical_id, Path(path_text.strip())


def audit_sources(store: PaperStore, sources: Sequence[tuple[str, Path]]) -> dict[str, Any]:
    if getattr(store, "readonly", False) is not True:
        raise FullTextLineageAuditError("lineage audit requires a read-only PaperStore")
    if not sources:
        raise FullTextLineageAuditError("at least one PDF source is required")
    source_ids = [source_id for source_id, _ in sources]
    if len(source_ids) != len(set(source_ids)):
        raise FullTextLineageAuditError("duplicate arXiv source IDs are not allowed")

    rows: list[dict[str, Any]] = []
    for source_id, pdf_path in sources:
        path = pdf_path.expanduser()
        base = {"source_id": source_id, "pdf_file": path.name}
        if not path.is_file():
            rows.append({**base, "status": "pdf_missing"})
            continue
        pdf_sha256 = _sha256_file(path)
        metadata = store.get_current_fulltext_metadata(source_type="arxiv", source_id=source_id)
        if metadata is None:
            rows.append({**base, "pdf_sha256": pdf_sha256, "status": "index_missing"})
            continue
        chunks = store.list_current_fulltext_chunks(source_type="arxiv", source_id=source_id)
        expected_pdf_sha256 = metadata.get("source_document_sha256")
        content_sha256 = metadata.get("content_sha256")
        count_matches = len(chunks) == metadata.get("chunk_count") and bool(chunks)
        chunks_match = count_matches and all(
            chunk.get("content_sha256") == content_sha256 for chunk in chunks
        )
        checks = {
            "approved": metadata.get("status") == "approved",
            "license_allowed": metadata.get("license_id") in ALLOWED_FULLTEXT_LICENSES,
            "pdf_sha_matches": pdf_sha256 == expected_pdf_sha256,
            "chunk_count_matches": count_matches,
            "chunk_content_hashes_match": chunks_match,
        }
        rows.append(
            {
                **base,
                "status": "verified" if all(checks.values()) else "mismatch",
                "license_id": metadata.get("license_id"),
                "parser_version": metadata.get("parser_version"),
                "pdf_sha256": pdf_sha256,
                "indexed_pdf_sha256": expected_pdf_sha256,
                "content_sha256": content_sha256,
                "metadata_chunk_count": metadata.get("chunk_count"),
                "active_chunk_count": len(chunks),
                "checks": checks,
            }
        )
    verified_count = sum(row["status"] == "verified" for row in rows)
    return {
        "report_schema": REPORT_SCHEMA,
        "read_only": True,
        "quality_claim_allowed": False,
        "status": "verified" if verified_count == len(rows) else "failed",
        "source_count": len(rows),
        "verified_count": verified_count,
        "sources": rows,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(HASH_READ_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        action="append",
        required=True,
        metavar="ARXIV_ID=PATH",
        help="local PDF and its canonical arXiv ID; repeat once per source",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sources = [parse_source_pdf(value) for value in args.pdf]
        store = PaperStore(get_settings().resolved_data_storage_path, readonly=True)
        report = audit_sources(store, sources)
    except (OSError, ValueError, KeyError, TypeError) as error:
        message = (
            str(error) if isinstance(error, FullTextLineageAuditError) else type(error).__name__
        )
        print(f"Full-text lineage audit failed: {message}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "verified" else 3


if __name__ == "__main__":
    raise SystemExit(main())
