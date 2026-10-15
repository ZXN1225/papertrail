from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.cli import import_licensed_fulltext
from app.cli.import_licensed_fulltext import FullTextManifest, validate_fulltext_manifest


def _manifest(**updates: str) -> FullTextManifest:
    values = {
        "source_type": "openalex",
        "source_id": "W123",
        "text_source_url": "https://example.org/paper.pdf",
        "license_id": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "license_evidence_url": "https://example.org/license",
        "reviewer": "manual-reviewer",
        "attribution": "Synthetic test attribution",
    }
    values.update(updates)
    return FullTextManifest.model_validate(values)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"license_id": "CC-BY-NC-4.0"}, "not on the full-text processing allowlist"),
        ({"license_url": "https://example.org/license"}, "canonical license identifier"),
        ({"license_evidence_url": "http://example.org/license"}, "HTTPS URL"),
        ({"source_id": "not-an-openalex-id"}, "OpenAlex work ID"),
    ],
)
def test_manifest_preflight_rejects_invalid_license_before_reading_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    updates: dict[str, str],
    message: str,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest(**updates).model_dump()), encoding="utf-8")
    parser_calls = 0

    def parse_pdf_spy(_pdf_bytes: bytes) -> dict[str, object]:
        nonlocal parser_calls
        parser_calls += 1
        raise AssertionError("PDF parser must not run before the license manifest is accepted")

    monkeypatch.setattr(import_licensed_fulltext, "parse_pdf_bytes", parse_pdf_spy)
    result = import_licensed_fulltext.main(
        [
            "--manifest",
            str(manifest_path),
            "--pdf",
            str(tmp_path / "does-not-exist.pdf"),
            "--confirm-license-reviewed",
        ]
    )

    assert result == 3
    assert message in capsys.readouterr().err
    assert parser_calls == 0


def test_manifest_preflight_returns_valid_approved_manifest() -> None:
    manifest = validate_fulltext_manifest(_manifest())
    assert manifest.license_id == "CC-BY-4.0"
    assert manifest.source_id == "W123"


def test_pdf_hash_and_parser_use_the_same_single_byte_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest().model_dump()), encoding="utf-8")
    pdf_path = tmp_path / "paper.pdf"
    source_bytes = b"TEST synthetic pdf bytes before mutation"
    pdf_path.write_bytes(source_bytes)
    observed: dict[str, object] = {}

    def parse_pdf_bytes_spy(pdf_bytes: bytes) -> dict[str, object]:
        observed["parser_bytes"] = pdf_bytes
        # Simulate a file changing after the CLI has taken its snapshot.
        pdf_path.write_bytes(b"different bytes after snapshot")
        return {
            "elements": [
                {
                    "element_id": "pdfel_TEST",
                    "order_index": 0,
                    "page_number": 1,
                    "page_width": 612,
                    "page_height": 792,
                    "bbox": [0, 0, 100, 20],
                    "element_type": "paragraph",
                    "section_path": ["TEST"],
                    "text": "Synthetic text",
                    "structured": {},
                    "warnings": [],
                }
            ],
            "page_count": 1,
            "table_regions": 0,
            "image_regions": 0,
            "figure_captions": 0,
            "warnings": [],
        }

    class FakePaperStore:
        def __init__(self, _path: Path) -> None:
            pass

        def ingest_licensed_fulltext(self, **kwargs: object) -> dict[str, str]:
            observed["ingest_kwargs"] = kwargs
            return {"status": "approved"}

    monkeypatch.setattr(import_licensed_fulltext, "parse_pdf_bytes", parse_pdf_bytes_spy)
    monkeypatch.setattr(
        import_licensed_fulltext,
        "get_settings",
        lambda: SimpleNamespace(resolved_data_storage_path=tmp_path / "catalog.sqlite3"),
    )
    monkeypatch.setattr(import_licensed_fulltext, "PaperStore", FakePaperStore)

    result = import_licensed_fulltext.main(
        [
            "--manifest",
            str(manifest_path),
            "--pdf",
            str(pdf_path),
            "--confirm-license-reviewed",
        ]
    )

    assert result == 0
    capsys.readouterr()
    assert observed["parser_bytes"] == source_bytes
    ingest_kwargs = observed["ingest_kwargs"]
    assert isinstance(ingest_kwargs, dict)
    assert ingest_kwargs["source_document_sha256"] == hashlib.sha256(source_bytes).hexdigest()
