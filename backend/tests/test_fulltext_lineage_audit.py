from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from app.cli.audit_fulltext_lineage import (
    FullTextLineageAuditError,
    audit_sources,
    parse_source_pdf,
)

PDF_SHA = "a" * 64
CONTENT_SHA = "b" * 64


class _ReadOnlyStore:
    def __init__(self) -> None:
        self.readonly = True
        self.metadata: dict[str, Any] | None = {
            "status": "approved",
            "source_document_sha256": PDF_SHA,
            "content_sha256": CONTENT_SHA,
            "license_id": "CC-BY-4.0",
            "parser_version": "pdfplumber-layout-v15",
            "chunk_count": 2,
        }
        self.chunks = [
            {"content_sha256": CONTENT_SHA},
            {"content_sha256": CONTENT_SHA},
        ]
        self.metadata_calls: list[tuple[str, str]] = []

    def get_current_fulltext_metadata(self, *, source_type: str, source_id: str):
        self.metadata_calls.append((source_type, source_id))
        return self.metadata

    def list_current_fulltext_chunks(self, *, source_type: str, source_id: str):
        return self.chunks


def _write_pdf(tmp_path: Path, contents: bytes = b"local PDF bytes") -> Path:
    path = tmp_path / "paper.pdf"
    path.write_bytes(contents)
    return path


def test_audit_verifies_pdf_index_license_and_chunk_lineage(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path)
    store = _ReadOnlyStore()
    store.metadata["source_document_sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()

    report = audit_sources(store, [("2608.20519", pdf)])

    assert report["status"] == "verified"
    assert report["quality_claim_allowed"] is False
    assert report["sources"][0]["checks"] == {
        "approved": True,
        "license_allowed": True,
        "pdf_sha_matches": True,
        "chunk_count_matches": True,
        "chunk_content_hashes_match": True,
    }
    assert store.metadata_calls == [("arxiv", "2608.20519")]


def test_audit_reports_pdf_hash_mismatch_without_reading_pdf_text(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path)
    report = audit_sources(_ReadOnlyStore(), [("2608.20519", pdf)])

    assert report["status"] == "failed"
    assert report["sources"][0]["checks"]["pdf_sha_matches"] is False
    assert report["sources"][0]["status"] == "mismatch"


def test_audit_reports_missing_pdf_and_missing_index(tmp_path: Path) -> None:
    store = _ReadOnlyStore()
    missing_pdf = tmp_path / "missing.pdf"

    missing_pdf_report = audit_sources(store, [("2608.20519", missing_pdf)])
    assert missing_pdf_report["sources"][0]["status"] == "pdf_missing"
    assert store.metadata_calls == []

    pdf = _write_pdf(tmp_path)
    store.metadata = None
    missing_index_report = audit_sources(store, [("2608.20519", pdf)])
    assert missing_index_report["sources"][0]["status"] == "index_missing"


@pytest.mark.parametrize(
    ("mutation", "check"),
    [
        (lambda store: store.metadata.update(status="revoked"), "approved"),
        (lambda store: store.metadata.update(license_id="All-rights-reserved"), "license_allowed"),
        (lambda store: store.metadata.update(chunk_count=3), "chunk_count_matches"),
        (
            lambda store: store.chunks[0].update(content_sha256="c" * 64),
            "chunk_content_hashes_match",
        ),
    ],
)
def test_audit_fails_closed_for_invalid_index_lineage(tmp_path: Path, mutation, check: str) -> None:
    pdf = _write_pdf(tmp_path)
    store = _ReadOnlyStore()
    store.metadata["source_document_sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
    mutation(store)

    report = audit_sources(store, [("2608.20519", pdf)])

    assert report["status"] == "failed"
    assert report["sources"][0]["checks"][check] is False


def test_audit_requires_read_only_store_and_unique_sources(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path)
    store = _ReadOnlyStore()
    store.readonly = False
    with pytest.raises(FullTextLineageAuditError, match="read-only"):
        audit_sources(store, [("2608.20519", pdf)])

    store.readonly = True
    with pytest.raises(FullTextLineageAuditError, match="duplicate"):
        audit_sources(store, [("2608.20519", pdf), ("2608.20519", pdf)])


@pytest.mark.parametrize("value", ["", "no-equals", "2608.20519=", "not-an-id=paper.pdf"])
def test_parse_source_pdf_rejects_malformed_values(value: str) -> None:
    with pytest.raises(FullTextLineageAuditError):
        parse_source_pdf(value)


def test_parse_source_pdf_normalizes_arxiv_version_suffix() -> None:
    source_id, path = parse_source_pdf("2608.20519v2=paper.pdf")

    assert source_id == "2608.20519"
    assert path == Path("paper.pdf")
