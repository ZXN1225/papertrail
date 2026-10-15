from __future__ import annotations

import copy
from typing import Any

import pytest

from app.evaluation.fulltext_retrieval import (
    FullTextRetrievalEvaluationError,
    load_dataset,
    run_evaluation,
    validate_dataset,
)

PDF_SHA = "a" * 64
CONTENT_SHA = "b" * 64
CHUNK_ID = f"arxiv:2608.20519:{CONTENT_SHA[:16]}:1"


def _dataset() -> dict[str, Any]:
    return {
        "schema": "papertrail.fulltext-retrieval-diagnostic.v1",
        "dataset_id": "TEST-fulltext-retrieval-v1",
        "synthetic": False,
        "gold_standard": False,
        "quality_claim_allowed": False,
        "reference_status": "single_reviewer_selected_reference",
        "retrieval_method": "bm25",
        "top_k": 2,
        "sources": {
            "2608.20519": {
                "source_document_sha256": PDF_SHA,
                "content_sha256": CONTENT_SHA,
                "license_id": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "parser_version": "pdfplumber-layout-v17",
            }
        },
        "tasks": [
            {
                "task_id": "R1",
                "source_id": "2608.20519",
                "question": "Which table contains the IVIM parameters?",
                "reference_chunk_id": CHUNK_ID,
                "reference_page": 14,
                "reference_element_type": "table",
            }
        ],
    }


class _ReadOnlyStore:
    def __init__(self) -> None:
        self.readonly = True
        self.metadata = {
            "source_type": "arxiv",
            "source_id": "2608.20519",
            "status": "approved",
            "current_sha256": CONTENT_SHA,
            "content_sha256": CONTENT_SHA,
            "source_document_sha256": PDF_SHA,
            "license_id": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "parser_version": "pdfplumber-layout-v17",
            "chunker_version": "test-chunker",
            "chunk_count": 3,
        }
        self.metadata_by_source = {"2608.20519": self.metadata}
        self.search_calls: list[dict[str, Any]] = []
        self.search_response: dict[str, Any] | None = None

    def get_current_fulltext_metadata(self, *, source_type: str, source_id: str):
        assert source_type == "arxiv"
        return self.metadata_by_source.get(source_id)

    def list_current_fulltext_metadata(self, *, source_type: str | None = None):
        assert source_type == "arxiv"
        return [
            {"source_type": "arxiv", "source_id": source_id, **metadata}
            for source_id, metadata in self.metadata_by_source.items()
        ]

    def search_fulltext_evidence(self, query: str, **kwargs):
        self.search_calls.append({"query": query, **kwargs})
        if self.search_response is not None:
            return self.search_response
        return {
            "status": "ok",
            "retrieval_method": "bm25_fulltext_v3",
            "scanned_chunks": 3,
            "truncated": False,
            "items": [
                {
                    "chunk_id": "arxiv:2608.20519:otherhash00000000:0",
                    "source_type": "arxiv",
                    "source_id": "2608.20519",
                    "content_sha256": CONTENT_SHA,
                    "page_number": 13,
                    "element_type": "paragraph",
                },
                {
                    "chunk_id": CHUNK_ID,
                    "source_type": "arxiv",
                    "source_id": "2608.20519",
                    "content_sha256": CONTENT_SHA,
                    "page_number": 14,
                    "element_type": "table",
                },
            ],
        }


def test_current_v21_diagnostic_manifest_is_pinned_and_non_gold() -> None:
    dataset, digest = load_dataset()

    assert len(digest) == 64
    assert dataset["gold_standard"] is False
    assert dataset["quality_claim_allowed"] is False
    assert all(
        source["parser_version"] == "pdfplumber-layout-v21"
        for source in dataset["sources"].values()
    )
    assert [task["task_id"] for task in dataset["tasks"]] == [
        "R1",
        "R2",
        "R3",
        "R4",
        "R5",
        "R6",
    ]


def test_runner_pins_lineage_and_reports_selected_reference_rank_only() -> None:
    store = _ReadOnlyStore()
    dataset = _dataset()

    report = run_evaluation(store, dataset, "c" * 64)

    assert report["quality_claim_allowed"] is False
    assert report["summary"] == {
        "selected_reference_hits": 1,
        "task_count": 1,
        "selected_reference_hit_rate": 1.0,
    }
    assert report["tasks"][0]["reference_rank"] == 2
    assert report["tasks"][0]["reference_location_matches"] is True
    assert store.search_calls == [
        {
            "query": "Which table contains the IVIM parameters?",
            "limit": 2,
            "source_type": "arxiv",
            "source_id": "2608.20519",
            "retrieval_method": "bm25",
        }
    ]


def test_full_corpus_scope_checks_every_source_and_ranks_across_sources() -> None:
    store = _ReadOnlyStore()
    dataset = _dataset()
    dataset["source_scope"] = "all_approved_arxiv"
    other_id = "2401.12345"
    other_content_sha = "d" * 64
    other_pdf_sha = "e" * 64
    dataset["sources"][other_id] = {
        "source_document_sha256": other_pdf_sha,
        "content_sha256": other_content_sha,
        "license_id": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "parser_version": "pdfplumber-layout-v21",
    }
    store.metadata_by_source[other_id] = {
        "status": "approved",
        "content_sha256": other_content_sha,
        "source_document_sha256": other_pdf_sha,
        "license_id": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "parser_version": "pdfplumber-layout-v21",
        "chunk_count": 1,
    }
    store.search_response = {
        "status": "ok",
        "scanned_chunks": 4,
        "truncated": False,
        "items": [
            {
                "chunk_id": f"arxiv:{other_id}:{other_content_sha[:16]}:1",
                "source_type": "arxiv",
                "source_id": other_id,
                "content_sha256": other_content_sha,
                "page_number": 1,
                "element_type": "paragraph",
            },
            {
                "chunk_id": CHUNK_ID,
                "source_type": "arxiv",
                "source_id": "2608.20519",
                "content_sha256": CONTENT_SHA,
                "page_number": 14,
                "element_type": "table",
            },
        ],
    }

    report = run_evaluation(store, dataset, "c" * 64)

    assert report["retrieval"]["source_scope"] == "all_approved_arxiv"
    assert report["tasks"][0]["reference_rank"] == 2
    assert report["tasks"][0]["reference_location_matches"] is True
    assert store.search_calls[0]["source_id"] is None


def test_full_corpus_scope_rejects_unfrozen_active_source_before_search() -> None:
    store = _ReadOnlyStore()
    dataset = _dataset()
    dataset["source_scope"] = "all_approved_arxiv"
    store.metadata_by_source["2401.12345"] = {**store.metadata, "source_id": "2401.12345"}

    with pytest.raises(FullTextRetrievalEvaluationError, match="every current active source"):
        run_evaluation(store, dataset, "c" * 64)

    assert store.search_calls == []


@pytest.mark.parametrize("scope", ["exact_arxiv_id_per_task", "all_approved_arxiv"])
def test_diagnostic_rejects_results_from_an_unfrozen_source(scope: str) -> None:
    store = _ReadOnlyStore()
    dataset = _dataset()
    dataset["source_scope"] = scope
    store.search_response = {
        "status": "ok",
        "scanned_chunks": 3,
        "items": [
            {"source_type": "arxiv", "source_id": "2401.12345", "content_sha256": CONTENT_SHA}
        ],
    }

    with pytest.raises(FullTextRetrievalEvaluationError, match="retrieved evidence lineage"):
        run_evaluation(store, dataset, "c" * 64)


def test_full_corpus_diagnostic_rejects_partial_scan() -> None:
    store = _ReadOnlyStore()
    dataset = _dataset()
    dataset["source_scope"] = "all_approved_arxiv"
    store.search_response = {"status": "ok", "scanned_chunks": 2, "items": []}

    with pytest.raises(FullTextRetrievalEvaluationError, match="complete frozen scope"):
        run_evaluation(store, dataset, "c" * 64)


def test_runner_refuses_a_writable_store() -> None:
    store = _ReadOnlyStore()
    store.readonly = False

    with pytest.raises(FullTextRetrievalEvaluationError, match="read-only PaperStore"):
        run_evaluation(store, _dataset(), "c" * 64)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_document_sha256", "d" * 64),
        ("content_sha256", "e" * 64),
        ("license_id", "CC0-1.0"),
        ("parser_version", "pdfplumber-layout-v14"),
    ],
)
def test_runner_fails_closed_on_stale_source_lineage(field: str, value: str) -> None:
    store = _ReadOnlyStore()
    dataset = _dataset()
    store.metadata[field] = value

    with pytest.raises(FullTextRetrievalEvaluationError, match="lineage/license"):
        run_evaluation(store, dataset, "c" * 64)


def test_runner_rejects_changed_reference_page_or_element_type() -> None:
    store = _ReadOnlyStore()
    dataset = _dataset()
    dataset["tasks"][0]["reference_page"] = 15

    with pytest.raises(FullTextRetrievalEvaluationError, match="reference locator"):
        run_evaluation(store, dataset, "c" * 64)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda item: item.update(gold_standard=True), "provenance"),
        (lambda item: item.update(top_k=0), "top_k"),
        (lambda item: item["tasks"][0].update(task_id="task1"), "task identity"),
        (lambda item: item["tasks"][0].update(source_id=[]), "task identity"),
    ],
)
def test_manifest_validator_rejects_invalid_or_claim_inflating_input(
    mutation, message: str
) -> None:
    dataset = copy.deepcopy(_dataset())
    mutation(dataset)

    with pytest.raises(FullTextRetrievalEvaluationError, match=message):
        validate_dataset(dataset)
