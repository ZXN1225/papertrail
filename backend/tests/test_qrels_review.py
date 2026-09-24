from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from app.cli.review_qrels import _write_new_json
from app.evaluation.review import (
    QrelsReviewError,
    apply_review_pack,
    build_review_pack,
)


@pytest.fixture
def source_data() -> tuple[dict, str, str, list[dict]]:
    dataset = {
        "dataset_id": "p05-test",
        "dataset_version": 1,
        "judgment_status": "assistant_seed_pending_human_review",
        "corpus": {
            "work_ids": ["W100", "W200"],
            "content_sha256": {"W100": "a" * 64, "W200": "b" * 64},
        },
        "queries": [
            {
                "query_id": "Q01",
                "bucket": "evaluation",
                "text": "How is retrieval evaluated?",
                "relevance": [3, 0],
            },
            {
                "query_id": "Q02",
                "bucket": "method",
                "text": "Which retrieval method is used?",
                "relevance": [1, 2],
            },
        ],
    }
    papers = [
        {
            "openalex_id": "W100",
            "title": "Paper 100",
            "publication_year": 2024,
            "abstract": "Abstract 100",
            "content_sha256": "a" * 64,
            "metadata_license": "CC0-1.0",
            "source_url": "https://openalex.org/W100",
            "snapshot_id": "snapshot-1",
        },
        {
            "openalex_id": "W200",
            "title": "Paper 200",
            "publication_year": 2025,
            "abstract": None,
            "content_sha256": "b" * 64,
            "metadata_license": "CC0-1.0",
            "source_url": "https://openalex.org/W200",
            "snapshot_id": "snapshot-1",
        },
    ]
    return dataset, hashlib.sha256(b"source dataset").hexdigest(), "snapshot-1", papers


def _completed_pack(source_data):
    dataset, dataset_sha, snapshot_id, papers = source_data
    pack = build_review_pack(dataset, dataset_sha, snapshot_id, papers)
    for row in pack["rows"]:
        row["reviewed_grade"] = row["suggested_grade"]
        row["reviewed"] = True
        row["review_note"] = "checked against title and abstract"
    return pack


def test_qrels_review_round_trip_creates_a_separate_human_reviewed_copy(source_data) -> None:
    dataset, dataset_sha, _, papers = source_data
    pack = _completed_pack(source_data)

    reviewed = apply_review_pack(
        dataset,
        dataset_sha,
        pack,
        papers,
        reviewer="local-project-owner",
        reviewed_at="2026-09-24T12:00:00+00:00",
    )

    assert reviewed["judgment_status"] == "human_reviewed"
    assert reviewed["dataset_version"] == 2
    assert reviewed["queries"][0]["relevance"] == [3, 0]
    assert reviewed["queries"][1]["relevance"] == [1, 2]
    assert reviewed["review_audit"]["reviewed_pair_count"] == 4
    assert len(reviewed["review_audit"]["review_pack_sha256"]) == 64
    assert reviewed["review_audit"]["entries"][0]["review_note"] == (
        "checked against title and abstract"
    )
    assert dataset["judgment_status"] == "assistant_seed_pending_human_review"
    assert dataset["queries"][0]["relevance"] == [3, 0]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_pair",
        "duplicate_pair",
        "invalid_grade",
        "unreviewed_row",
        "stale_dataset_hash",
        "stale_paper_metadata",
        "stale_snapshot",
        "edited_query_context",
    ],
)
def test_qrels_review_rejects_incomplete_or_stale_packs(source_data, mutation: str) -> None:
    dataset, dataset_sha, _, papers = source_data
    pack = _completed_pack(source_data)
    if mutation == "missing_pair":
        pack["rows"].pop()
    elif mutation == "duplicate_pair":
        pack["rows"][-1] = copy.deepcopy(pack["rows"][0])
    elif mutation == "invalid_grade":
        pack["rows"][0]["reviewed_grade"] = 4
    elif mutation == "unreviewed_row":
        pack["rows"][0]["reviewed"] = False
    elif mutation == "stale_dataset_hash":
        pack["source_dataset_sha256"] = "0" * 64
    elif mutation == "stale_paper_metadata":
        pack["documents"][0]["title"] = "Edited paper title"
    elif mutation == "stale_snapshot":
        pack["corpus_snapshot_id"] = "old-snapshot"
    else:
        pack["rows"][0]["query_text"] = "a different question"

    with pytest.raises(QrelsReviewError):
        apply_review_pack(dataset, dataset_sha, pack, papers, reviewer="reviewer")


def test_qrels_review_export_requires_snapshot_content_hashes(source_data) -> None:
    dataset, dataset_sha, snapshot_id, papers = source_data
    papers[0]["content_sha256"] = "0" * 64

    with pytest.raises(QrelsReviewError, match="hash"):
        build_review_pack(dataset, dataset_sha, snapshot_id, papers)


def test_qrels_review_writer_refuses_to_overwrite_a_protected_input() -> None:
    protected = Path("candidate.json").resolve()

    with pytest.raises(QrelsReviewError, match="new file"):
        _write_new_json(
            Path("candidate.json"),
            {"judgment_status": "human_reviewed"},
            protected_paths={protected},
        )
