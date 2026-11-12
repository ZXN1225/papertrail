from __future__ import annotations

import copy
from typing import Any

import pytest

from app.evaluation.ai_labeled_tasks import (
    TEST_LABEL_SOURCE,
    AiLabeledTaskError,
    run_evaluation,
    validate_dataset,
)

PDF_SHA = "a" * 64
CONTENT_SHA = "b" * 64
REFERENCE_CHUNK_ID = f"arxiv:2608.20519:{CONTENT_SHA[:16]}:1"
OTHER_CHUNK_ID = f"arxiv:2608.20519:{CONTENT_SHA[:16]}:0"
DATASET_SHA = "c" * 64


def _dataset() -> dict[str, Any]:
    """Synthetic fixture: TEST-* ids, synthetic=true, and the test label source."""
    return {
        "schema": "papertrail.ai-labeled-tasks.v1",
        "dataset_id": "TEST-ai-labeled-v1",
        "synthetic": True,
        "gold_standard": False,
        "quality_claim_allowed": False,
        "human_reviewed": False,
        "label_source": TEST_LABEL_SOURCE,
        "retrieval_method": "bm25",
        "top_k": 2,
        "source_scope": "all_approved_arxiv",
        "sources": {
            "2608.20519": {
                "source_document_sha256": PDF_SHA,
                "content_sha256": CONTENT_SHA,
                "license_id": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "parser_version": "pdfplumber-layout-v27",
            }
        },
        "tasks": [
            {
                "task_id": "TEST-AI-1",
                "source_id": "2608.20519",
                "challenge_type": "table_lookup",
                "question": "TEST which table lists the diffusion parameters?",
                "answer": "TEST Table 2",
                "expected_answerable": True,
                "evidence": {
                    "source_id": "2608.20519",
                    "chunk_id": REFERENCE_CHUNK_ID,
                    "page_number": 14,
                    "element_type": "table",
                    "quote": "TEST IVIM parameters",
                },
            },
            {
                "task_id": "TEST-AI-2",
                "source_id": "2608.20519",
                "challenge_type": "unanswerable",
                "question": "TEST what is the melting point of tungsten?",
                "expected_answerable": False,
                "absent_fact": "TEST tungsten melts at 3422 degrees",
                "related_source_id": "2608.20519",
            },
        ],
    }


class _ReadOnlyStore:
    def __init__(self) -> None:
        self.readonly = True
        self.metadata = {
            "source_type": "arxiv",
            "source_id": "2608.20519",
            "status": "approved",
            "content_sha256": CONTENT_SHA,
            "source_document_sha256": PDF_SHA,
            "license_id": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "parser_version": "pdfplumber-layout-v27",
            "chunk_count": 3,
        }
        self.search_calls: list[dict[str, Any]] = []

    def get_current_fulltext_metadata(self, *, source_type: str, source_id: str):
        assert source_type == "arxiv"
        return self.metadata if source_id == "2608.20519" else None

    def search_fulltext_evidence(self, query: str, **kwargs):
        self.search_calls.append({"query": query, **kwargs})
        items = [
            {
                "chunk_id": OTHER_CHUNK_ID,
                "source_id": "2608.20519",
                "content_sha256": CONTENT_SHA,
                "page_number": 13,
                "element_type": "paragraph",
                "score": 9.5,
            }
        ]
        if "table" in query:
            items.append(
                {
                    "chunk_id": REFERENCE_CHUNK_ID,
                    "source_id": "2608.20519",
                    "content_sha256": CONTENT_SHA,
                    "page_number": 14,
                    "element_type": "table",
                    "score": 4.0,
                }
            )
        return {
            "status": "ok" if items else "no_results",
            "retrieval_method": {
                "bm25": "bm25_fulltext_v3",
                "dense": "dense_cosine_v1",
                "hybrid": "hybrid_rrf_v3",
                "bm25_dense_rerank": "bm25_dense_rerank_v1",
            }[kwargs["retrieval_method"]],
            "scanned_chunks": 3,
            "truncated": False,
            "items": items,
        }


def test_synthetic_fixture_scores_and_keeps_ai_labeling_visible() -> None:
    report = run_evaluation(_ReadOnlyStore(), _dataset(), DATASET_SHA)

    assert report["synthetic"] is True
    assert report["label_source"] == TEST_LABEL_SOURCE
    assert report["quality_claim_allowed"] is False
    assert report["gold_standard"] is False
    assert report["human_reviewed"] is False
    assert report["dataset"]["answerable_count"] == 1
    assert report["dataset"]["unanswerable_count"] == 1
    # The reference sits at rank 2, so hit@1 misses and hit@2 hits.
    assert report["summary"]["evidence_hit_at_1"]["count"] == 0
    assert report["summary"]["evidence_hit_at_2"]["count"] == 1
    negative = next(row for row in report["tasks"] if not row["expected_answerable"])
    assert negative["retrieval_candidate_returned"] is True
    assert negative["top1_score"] == 9.5
    assert report["summary"]["top1_score_separability"]["answerable_mean"] == 9.5


def test_multihop_measures_all_required_evidence_coverage() -> None:
    dataset = _dataset()
    task = dataset["tasks"][0]
    task["challenge_type"] = "multi_hop"
    task["question"] = "TEST which results list the study parameters?"
    task["required_evidence"] = [
        task["evidence"],
        {
            "source_id": "2608.20519",
            "chunk_id": OTHER_CHUNK_ID,
            "page_number": 13,
            "element_type": "paragraph",
            "quote": "TEST additional evidence anchor",
        },
    ]

    report = run_evaluation(_ReadOnlyStore(), dataset, DATASET_SHA)

    answerable = report["tasks"][0]
    assert answerable["required_evidence_count"] == 2
    assert answerable["required_evidence_retrieved_count"] == 1
    assert answerable["complete_evidence_coverage"] is False
    assert answerable["evidence_metrics"]["recall_at_k"] == 0.5
    assert report["dataset"]["multi_hop_without_required_evidence"] == 0
    assert report["summary"]["answerable_retrieval_metrics"]["complete_evidence_coverage"] == 0.0


def test_multihop_without_required_evidence_is_reported_as_unmeasured() -> None:
    dataset = _dataset()
    dataset["tasks"][0]["challenge_type"] = "multi_hop"

    report = run_evaluation(_ReadOnlyStore(), dataset, DATASET_SHA)

    assert report["tasks"][0]["complete_evidence_coverage"] is None
    assert report["dataset"]["multi_hop_without_required_evidence"] == 1
    assert report["summary"]["answerable_retrieval_metrics"]["complete_evidence_denominator"] == 0


def test_dataset_claiming_human_review_or_gold_status_is_rejected() -> None:
    for key in ("human_reviewed", "gold_standard", "quality_claim_allowed"):
        dataset = _dataset()
        dataset[key] = True
        with pytest.raises(AiLabeledTaskError):
            validate_dataset(dataset)


def test_real_corpus_label_source_cannot_be_used_by_a_synthetic_fixture() -> None:
    dataset = _dataset()
    dataset["label_source"] = "ai_agent_review"

    with pytest.raises(AiLabeledTaskError):
        validate_dataset(dataset)


def test_unanswerable_task_with_evidence_or_without_absent_fact_is_rejected() -> None:
    dataset = _dataset()
    dataset["tasks"][1]["evidence"] = {"source_id": "2608.20519"}
    with pytest.raises(AiLabeledTaskError):
        validate_dataset(dataset)

    dataset = _dataset()
    dataset["tasks"][1]["required_evidence"] = [dataset["tasks"][0]["evidence"]]
    with pytest.raises(AiLabeledTaskError, match="must not carry evidence"):
        validate_dataset(dataset)

    dataset = _dataset()
    dataset["tasks"][1]["absent_fact"] = "   "
    with pytest.raises(AiLabeledTaskError):
        validate_dataset(dataset)


def test_evidence_anchor_from_a_foreign_source_is_rejected() -> None:
    dataset = _dataset()
    dataset["tasks"][0]["evidence"]["source_id"] = "9999.99999"

    with pytest.raises(AiLabeledTaskError):
        validate_dataset(dataset)


def test_required_evidence_must_be_unique_and_include_primary_anchor() -> None:
    dataset = _dataset()
    task = dataset["tasks"][0]
    task["required_evidence"] = [task["evidence"], task["evidence"]]
    with pytest.raises(AiLabeledTaskError, match="unique"):
        validate_dataset(dataset)

    dataset = _dataset()
    task = dataset["tasks"][0]
    task["required_evidence"] = [
        {
            "source_id": "2608.20519",
            "chunk_id": OTHER_CHUNK_ID,
            "page_number": 13,
            "element_type": "paragraph",
            "quote": "TEST different anchor only",
        },
        {
            "source_id": "2608.20519",
            "chunk_id": f"arxiv:2608.20519:{CONTENT_SHA[:16]}:2",
            "page_number": 15,
            "element_type": "paragraph",
            "quote": "TEST another anchor",
        },
    ]
    with pytest.raises(AiLabeledTaskError, match="include the primary"):
        validate_dataset(dataset)


def test_active_lineage_must_match_the_dataset() -> None:
    store = _ReadOnlyStore()
    store.metadata = {**store.metadata, "parser_version": "pdfplumber-layout-v26"}

    with pytest.raises(AiLabeledTaskError, match="lineage"):
        run_evaluation(store, _dataset(), DATASET_SHA)


def test_ai_labeled_evaluation_accepts_pinned_mineru_lineage() -> None:
    store = _ReadOnlyStore()
    dataset = _dataset()
    mineru_version = "mineru-4.1.7-papertrail-v11"
    dataset["sources"]["2608.20519"]["parser_version"] = mineru_version
    store.metadata = {**store.metadata, "parser_version": mineru_version}

    report = run_evaluation(store, dataset, DATASET_SHA)

    assert report["sources"]["2608.20519"]["parser_version"] == mineru_version


def test_ai_labeled_evaluation_rejects_unrecognized_parser_lineage() -> None:
    dataset = _dataset()
    dataset["sources"]["2608.20519"]["parser_version"] = "custom-parser-v1"

    with pytest.raises(AiLabeledTaskError, match="lineage or license"):
        validate_dataset(dataset)


def test_partial_corpus_scan_is_rejected() -> None:
    store = _ReadOnlyStore()

    def partial(query: str, **kwargs):
        response = _ReadOnlyStore.search_fulltext_evidence(store, query, **kwargs)
        return copy.deepcopy({**response, "truncated": True})

    store.search_fulltext_evidence = partial  # type: ignore[method-assign]

    with pytest.raises(AiLabeledTaskError, match="complete approved corpus"):
        run_evaluation(store, _dataset(), DATASET_SHA)


def test_non_finite_retrieval_scores_fail_closed() -> None:
    store = _ReadOnlyStore()
    original_search = store.search_fulltext_evidence

    def non_finite_score(query: str, **kwargs):
        response = original_search(query, **kwargs)
        response["items"][0]["score"] = float("nan")
        return response

    store.search_fulltext_evidence = non_finite_score  # type: ignore[method-assign]
    with pytest.raises(AiLabeledTaskError, match="non-finite score"):
        run_evaluation(store, _dataset(), DATASET_SHA)


def test_dense_retrieval_uses_frozen_query_vectors() -> None:
    store = _ReadOnlyStore()
    task_ids = [task["task_id"] for task in _dataset()["tasks"]]
    vectors = {task_id: [0.5, 0.5] for task_id in task_ids}

    report = run_evaluation(
        store,
        _dataset(),
        DATASET_SHA,
        retrieval_method="dense",
        query_embeddings=vectors,
        embedding_model="TEST-embedding-model",
    )

    assert report["retrieval"]["method"] == "dense_cosine_v1"
    assert report["retrieval"]["query_embedding_count"] == 2
    assert store.search_calls[0]["retrieval_method"] == "dense"
    assert store.search_calls[0]["query_embedding"] == [0.5, 0.5]
    assert store.search_calls[0]["embedding_model"] == "TEST-embedding-model"


def test_dense_rerank_uses_frozen_query_vectors_and_keeps_quality_claim_disabled() -> None:
    store = _ReadOnlyStore()
    task_ids = [task["task_id"] for task in _dataset()["tasks"]]
    vectors = {task_id: [0.5, 0.5] for task_id in task_ids}

    report = run_evaluation(
        store,
        _dataset(),
        DATASET_SHA,
        retrieval_method="bm25_dense_rerank",
        query_embeddings=vectors,
        embedding_model="TEST-embedding-model",
    )

    assert report["retrieval"]["method"] == "bm25_dense_rerank_v1"
    assert report["retrieval"]["reranker"] == {
        "type": "dense_embedding_cosine",
        "candidate_generator": "bm25",
        "candidate_limit": 128,
    }
    assert report["retrieval"]["retrieval_latency_ms"]["mean"] >= 0
    assert (
        report["retrieval"]["retrieval_latency_ms"]["includes_query_embedding_provider_latency"]
        is False
    )
    assert report["quality_claim_allowed"] is False
    assert store.search_calls[0]["retrieval_method"] == "bm25_dense_rerank"
    assert store.search_calls[0]["query_embedding"] == [0.5, 0.5]


def test_dense_retrieval_requires_complete_finite_vectors() -> None:
    task_id = _dataset()["tasks"][0]["task_id"]
    with pytest.raises(AiLabeledTaskError, match="one embedding per task"):
        run_evaluation(
            _ReadOnlyStore(),
            _dataset(),
            DATASET_SHA,
            retrieval_method="dense",
            query_embeddings={task_id: [1.0]},
            embedding_model="TEST-model",
        )

    task_ids = [task["task_id"] for task in _dataset()["tasks"]]
    with pytest.raises(AiLabeledTaskError, match="finite vectors"):
        run_evaluation(
            _ReadOnlyStore(),
            _dataset(),
            DATASET_SHA,
            retrieval_method="hybrid",
            query_embeddings={task_id: [float("nan")] for task_id in task_ids},
            embedding_model="TEST-model",
        )


def test_evaluation_requires_a_read_only_store() -> None:
    store = _ReadOnlyStore()
    store.readonly = False

    with pytest.raises(AiLabeledTaskError, match="read-only"):
        run_evaluation(store, _dataset(), DATASET_SHA)
