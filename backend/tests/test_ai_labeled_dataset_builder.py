from __future__ import annotations

import sqlite3
from typing import Any

from tools.build_ai_labeled_dataset import validate_evidence_anchors

CONTENT_SHA = "a" * 64


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE fulltext_chunks (chunk_id TEXT, source_id TEXT, page_number INTEGER, "
        "element_type TEXT, content_sha256 TEXT, text TEXT)"
    )
    connection.executemany(
        "INSERT INTO fulltext_chunks VALUES (?,?,?,?,?,?)",
        [
            ("TEST-CHUNK-1", "TEST-source", 1, "paragraph", CONTENT_SHA, "TEST fact alpha."),
            ("TEST-CHUNK-2", "TEST-source", 2, "table", CONTENT_SHA, "TEST fact beta."),
            ("TEST-OTHER", "OTHER-source", 3, "paragraph", CONTENT_SHA, "TEST foreign fact."),
        ],
    )
    return connection


def _anchor(chunk_id: str, page: int, element_type: str, quote: str) -> dict[str, Any]:
    return {
        "source_id": "TEST-source",
        "chunk_id": chunk_id,
        "page_number": page,
        "element_type": element_type,
        "quote": quote,
    }


def test_builder_validates_and_preserves_all_required_evidence_anchors() -> None:
    connection = _connection()
    task = {
        "evidence": _anchor("TEST-CHUNK-1", 1, "paragraph", "TEST fact alpha."),
        "required_evidence": [
            _anchor("TEST-CHUNK-1", 1, "paragraph", "TEST fact alpha."),
            _anchor("TEST-CHUNK-2", 2, "table", "TEST fact beta."),
        ],
    }

    anchors, reason = validate_evidence_anchors(
        connection, "TEST-source", {"content_sha256": CONTENT_SHA}, task
    )

    assert reason is None
    assert anchors == task["required_evidence"]


def test_builder_rejects_required_evidence_when_any_anchor_is_invalid() -> None:
    connection = _connection()
    task = {
        "evidence": _anchor("TEST-CHUNK-1", 1, "paragraph", "TEST fact alpha."),
        "required_evidence": [
            _anchor("TEST-CHUNK-1", 1, "paragraph", "TEST fact alpha."),
            _anchor("TEST-CHUNK-2", 2, "table", "TEST text that is not present."),
        ],
    }

    anchors, reason = validate_evidence_anchors(
        connection, "TEST-source", {"content_sha256": CONTENT_SHA}, task
    )

    assert anchors is None
    assert reason == "quote_not_verbatim"


def test_builder_rejects_duplicate_or_incomplete_required_evidence() -> None:
    connection = _connection()
    anchor = _anchor("TEST-CHUNK-1", 1, "paragraph", "TEST fact alpha.")
    task = {
        "evidence": anchor,
        "required_evidence": [anchor, anchor],
    }

    anchors, reason = validate_evidence_anchors(
        connection, "TEST-source", {"content_sha256": CONTENT_SHA}, task
    )

    assert anchors is None
    assert reason == "invalid_required_evidence"
