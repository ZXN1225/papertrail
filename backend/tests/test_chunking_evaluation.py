from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.evaluation.chunking import (
    ChunkStrategyEvaluationError,
    _map_candidates_to_current_chunks,
    _parent_embedding_proxy_rerank,
    _resolve_reference_anchor,
    _retrieval_metrics,
    _span_is_covered,
    run_evaluation,
)
from app.evaluation.fulltext_retrieval import SCHEMA
from app.retrieval.fulltext import ChunkSizeInfeasibleError, chunk_pdf_elements


def _element(
    element_id: str,
    element_type: str,
    text: str,
    *,
    structured: dict | None = None,
) -> dict:
    return {
        "element_id": element_id,
        "order_index": 0,
        "page_number": 7,
        "element_type": element_type,
        "text": text,
        "section_path": ["TEST Results"],
        "bbox": [12.0, 24.0, 120.0, 240.0],
        "structured": structured or {},
    }


def test_size_arms_preserve_exact_offsets_and_keep_visual_analysis_out_of_text():
    body = "TEST evidence phrase " * 140
    paragraph = _element("TEST-paragraph", "paragraph", body)
    figure = _element(
        "TEST-figure",
        "figure",
        "TEST Figure 1 caption",
        structured={
            "papertrail_visual_analysis": {
                "status": "model_generated_unverified",
                "description": "TEST generated chart trend description",
            }
        },
    )

    small = chunk_pdf_elements([paragraph, figure], max_chunk_bytes=900)
    current = chunk_pdf_elements([paragraph, figure], max_chunk_bytes=1800)

    assert current == chunk_pdf_elements([paragraph, figure])
    small_paragraphs = [chunk for chunk in small if chunk.element_id == "TEST-paragraph"]
    current_paragraphs = [chunk for chunk in current if chunk.element_id == "TEST-paragraph"]
    assert len(small_paragraphs) > len(current_paragraphs)
    for chunk in small_paragraphs:
        assert chunk.element_type == "paragraph"
        assert chunk.page_number == 7
        assert chunk.bbox == "[12.0,24.0,120.0,240.0]"
        assert chunk.evidence_text == body[chunk.char_start : chunk.char_end]
        assert len(chunk.text.encode("utf-8")) <= 900

    figure_chunk = next(chunk for chunk in small if chunk.element_id == "TEST-figure")
    assert figure_chunk.text == "TEST Figure 1 caption"
    assert "generated chart trend description" not in figure_chunk.text


def test_overlap_ablation_preserves_utf8_spans_and_leaves_table_chunks_unchanged():
    body = "测试证据 evidence phrase " * 180
    paragraph = _element("TEST-overlap-paragraph", "paragraph", body)
    table = _element(
        "TEST-overlap-table",
        "table",
        "Table 1\nName | Value\nTEST-a | 1\nTEST-b | 2",
        structured={
            "rows": [
                {"cells": [{"text": "Name"}, {"text": "Value"}]},
                {"row_index": 0, "cells": [{"text": "TEST-a"}, {"text": "1"}]},
                {"row_index": 1, "cells": [{"text": "TEST-b"}, {"text": "2"}]},
            ]
        },
    )

    baseline = chunk_pdf_elements([paragraph], max_chunk_bytes=900)
    overlapped = chunk_pdf_elements([paragraph], max_chunk_bytes=900, max_overlap_bytes=90)
    baseline_table = chunk_pdf_elements([table], max_chunk_bytes=900)
    overlapped_table = chunk_pdf_elements([table], max_chunk_bytes=900, max_overlap_bytes=90)

    assert len(overlapped) > len(baseline)
    assert all(len(chunk.text.encode("utf-8")) <= 900 for chunk in overlapped)
    assert all(
        chunk.evidence_text == body[chunk.char_start : chunk.char_end] for chunk in overlapped
    )
    assert all(
        left.char_start < right.char_start < left.char_end
        for left, right in zip(overlapped, overlapped[1:], strict=False)
    )
    assert all(
        len(body[right.char_start : left.char_end].encode("utf-8")) <= 90
        for left, right in zip(overlapped, overlapped[1:], strict=False)
    )
    assert baseline_table == overlapped_table

    unspaced_text = "测" * 900
    unspaced = _element("TEST-unspaced", "paragraph", unspaced_text)
    exact_target_chunks = chunk_pdf_elements([unspaced], max_chunk_bytes=900, max_overlap_bytes=90)
    assert len(exact_target_chunks) > 1
    assert all(
        len(unspaced_text[right.char_start : left.char_end].encode("utf-8")) <= 90
        for left, right in zip(exact_target_chunks, exact_target_chunks[1:], strict=False)
    )


def test_small_table_chunks_repeat_header_and_retain_row_spans():
    rows = [
        {"row_index": index, "cells": [{"text": f"TEST-{index}"}, {"text": "x" * 80}]}
        for index in range(18)
    ]
    lines = ["Table 2", "Parameter | Value"] + [f"TEST-{index} | {'x' * 80}" for index in range(18)]
    text = "\n".join(lines)
    element = _element(
        "TEST-table",
        "table",
        text,
        structured={"rows": [{"cells": [{"text": "Parameter"}, {"text": "Value"}]}, *rows]},
    )

    chunks = chunk_pdf_elements([element], max_chunk_bytes=900)

    assert len(chunks) > 1
    assert all("Parameter | Value" in chunk.text for chunk in chunks)
    for chunk in chunks:
        assert chunk.element_type == "table"
        assert chunk.evidence_text == text[chunk.char_start : chunk.char_end]
        assert len(chunk.text.encode("utf-8")) <= 900


def test_smaller_strategy_marks_a_wide_table_header_infeasible_without_changing_baseline():
    header = "TEST-wide-header-" + "x" * 950
    source = f"Table 3\n{header}\nTEST-row | 42"
    element = _element(
        "TEST-wide-table",
        "table",
        source,
        structured={
            "rows": [
                {"cells": [{"text": header}]},
                {"row_index": 0, "cells": [{"text": "TEST-row"}, {"text": "42"}]},
            ]
        },
    )

    with pytest.raises(ChunkSizeInfeasibleError):
        chunk_pdf_elements([element], max_chunk_bytes=900)
    baseline = chunk_pdf_elements([element], max_chunk_bytes=1800)

    assert baseline
    assert all(chunk.element_id == "TEST-wide-table" for chunk in baseline)


def test_span_coverage_accepts_only_whitespace_gaps_between_retrieved_chunks():
    anchor = {
        "source_id": "TEST-doc",
        "element_id": "TEST-paragraph",
        "char_start": 0,
        "char_end": 12,
        "source_text": "alpha beta!!",
    }
    chunks = [
        {"source_id": "TEST-doc", "element_id": "TEST-paragraph", "char_start": 0, "char_end": 5},
        {"source_id": "TEST-doc", "element_id": "TEST-paragraph", "char_start": 6, "char_end": 12},
    ]
    assert _span_is_covered(chunks, anchor)
    assert not _span_is_covered(chunks[:1], anchor)
    assert not _span_is_covered(
        [
            chunks[0],
            {**chunks[1], "char_start": 8},
        ],
        anchor,
    )


def test_chunk_strategy_metrics_report_precision_recall_and_ranking_at_each_cutoff():
    metrics = _retrieval_metrics(
        ["TEST-irrelevant", "TEST-relevant-a", "TEST-relevant-b"],
        {"TEST-relevant-a": 1, "TEST-relevant-b": 1},
        (1, 3),
    )

    assert metrics["hit@1"] == 0.0
    assert metrics["hit@3"] == 1.0
    assert metrics["precision@1"] == 0.0
    assert metrics["recall@1"] == 0.0
    assert metrics["precision@3"] == pytest.approx(2 / 3)
    assert metrics["recall@3"] == 1.0
    assert metrics["mrr@3"] == 0.5


def test_chunk_size_rejects_out_of_range_or_boolean_values():
    with pytest.raises(ValueError, match="max_chunk_bytes"):
        chunk_pdf_elements([_element("TEST-e", "paragraph", "TEST text")], max_chunk_bytes=700)
    with pytest.raises(ValueError, match="max_chunk_bytes"):
        chunk_pdf_elements([_element("TEST-e", "paragraph", "TEST text")], max_chunk_bytes=True)
    with pytest.raises(ValueError, match="max_overlap_bytes"):
        chunk_pdf_elements(
            [_element("TEST-e", "paragraph", "TEST text")],
            max_chunk_bytes=900,
            max_overlap_bytes=True,
        )
    with pytest.raises(ValueError, match="max_overlap_bytes"):
        chunk_pdf_elements(
            [_element("TEST-e", "paragraph", "TEST text")],
            max_chunk_bytes=900,
            max_overlap_bytes=451,
        )


def test_strategy_evaluation_rejects_a_writable_store_before_loading_any_corpus():
    class WritableStore:
        readonly = False

    with pytest.raises(ChunkStrategyEvaluationError, match="read-only"):
        run_evaluation(WritableStore(), {"synthetic": True}, "0" * 64)


def test_strategy_evaluation_runs_both_arms_against_a_read_only_synthetic_snapshot():
    source_id = "2401.00001"
    source_hash = "a" * 64
    pdf_hash = "b" * 64
    text = "TEST retrieval evidence names the verified experimental result."
    element = {
        **_element("TEST-element", "paragraph", text),
        "bbox": [1.0, 2.0, 3.0, 4.0],
    }
    source = {
        "content_sha256": source_hash,
        "source_document_sha256": pdf_hash,
        "license_id": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "parser_version": "pdfplumber-layout-v1",
    }
    dataset = {
        "schema": SCHEMA,
        "dataset_id": "TEST-chunk-strategy",
        "synthetic": False,
        "gold_standard": False,
        "quality_claim_allowed": False,
        "reference_status": "single_reviewer_selected_reference",
        "retrieval_method": "bm25",
        "top_k": 3,
        "sources": {source_id: source},
        "tasks": [
            {
                "task_id": "R1",
                "source_id": source_id,
                "question": "TEST verified experimental result",
                "reference_chunk_id": f"arxiv:{source_id}:TEST-old-chunk",
                "reference_page": 7,
                "reference_element_type": "paragraph",
            }
        ],
    }
    reference = {
        "chunk_id": dataset["tasks"][0]["reference_chunk_id"],
        "source_id": source_id,
        "content_sha256": source_hash,
        "title": "TEST paper",
        "text": text,
        "evidence_text": text,
        "element_id": element["element_id"],
        "page_number": 7,
        "element_type": "paragraph",
        "char_start": 0,
        "char_end": len(text),
        "bbox_json": "[1.0,2.0,3.0,4.0]",
    }

    class ReadOnlySnapshot:
        readonly = True

        def get_current_fulltext_metadata(self, **kwargs):
            assert kwargs == {"source_type": "arxiv", "source_id": source_id}
            return {
                **source,
                "source_type": "arxiv",
                "source_id": source_id,
                "title": "TEST paper",
                "chunk_count": 1,
                "status": "approved",
            }

        def list_current_fulltext_chunks(self, **kwargs):
            assert kwargs == {"source_type": "arxiv", "source_id": source_id}
            return [reference]

        def list_current_fulltext_elements(self, **kwargs):
            assert kwargs == {"source_type": "arxiv", "source_id": source_id}
            return [element]

        def list_current_fulltext_embeddings(self, **kwargs):
            assert kwargs == {
                "source_type": "arxiv",
                "source_ids": [source_id],
                "model": "TEST-embedding-v1",
                "dimensions": 2,
            }
            return {reference["chunk_id"]: [1.0, 0.0]}

    report = run_evaluation(ReadOnlySnapshot(), dataset, "c" * 64)

    assert report["dataset"]["synthetic"] is False
    assert report["dataset"]["gold_standard"] is False
    assert report["dataset"]["quality_claim_allowed"] is False
    assert report["retrieval"]["retrieval_provider_calls"] == 0
    assert all(item["status"] == "completed" for item in report["strategies"].values())
    assert (
        report["strategies"]["pdf_structure_900_bytes_10pct_overlap_v1"]["max_overlap_bytes"] == 90
    )
    assert (
        report["strategies"]["pdf_structure_1200_bytes_10pct_overlap_v1"]["max_overlap_bytes"]
        == 120
    )
    assert (
        report["strategies"]["pdf_structure_1800_bytes_10pct_overlap_v1"]["max_overlap_bytes"]
        == 180
    )
    assert all(
        item["tasks"][0]["reference_anchor_resolution"] == "current_chunk"
        for item in report["strategies"].values()
    )

    reranked = run_evaluation(
        ReadOnlySnapshot(),
        dataset,
        "c" * 64,
        query_embeddings={"R1": [1.0, 0.0]},
        embedding_model="TEST-embedding-v1",
    )
    assert reranked["retrieval"]["reranker_type"] == (
        "parent_chunk_embedding_proxy_not_child_dense_or_cross_encoder"
    )
    for strategy in reranked["strategies"].values():
        method = strategy["retrieval_methods"]["bm25_parent_embedding_proxy_rerank"]
        assert method["status"] == "completed"
        assert method["reranker"] == "existing_1800_byte_parent_embedding_proxy"
        assert method["candidate_parent_limit"] == 128
        assert method["tasks"][0]["reference_span"] == [0, len(text)]


def test_chunk_rerank_fails_closed_when_current_embedding_index_is_incomplete():
    source_id = "2401.00001"
    source_hash = "a" * 64
    source = {
        "content_sha256": source_hash,
        "source_document_sha256": "b" * 64,
        "license_id": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "parser_version": "pdfplumber-layout-v1",
    }
    text = "TEST evidence remains exactly locatable."
    element = _element("TEST-element", "paragraph", text)
    reference = {
        "chunk_id": f"arxiv:{source_id}:TEST-current",
        "source_id": source_id,
        "content_sha256": source_hash,
        "title": "TEST paper",
        "text": text,
        "evidence_text": text,
        "element_id": element["element_id"],
        "page_number": 7,
        "element_type": "paragraph",
        "char_start": 0,
        "char_end": len(text),
        "bbox_json": "[12.0,24.0,120.0,240.0]",
    }
    dataset = {
        "schema": SCHEMA,
        "dataset_id": "TEST-chunk-rerank-missing-vector",
        "synthetic": False,
        "gold_standard": False,
        "quality_claim_allowed": False,
        "reference_status": "single_reviewer_selected_reference",
        "retrieval_method": "bm25",
        "top_k": 2,
        "sources": {source_id: source},
        "tasks": [
            {
                "task_id": "R1",
                "source_id": source_id,
                "question": "TEST evidence",
                "reference_chunk_id": reference["chunk_id"],
                "reference_page": 7,
                "reference_element_type": "paragraph",
            }
        ],
    }

    class ReadOnlySnapshot:
        readonly = True

        def get_current_fulltext_metadata(self, **kwargs):
            return source | {"title": "TEST paper", "chunk_count": 1, "status": "approved"}

        def list_current_fulltext_chunks(self, **kwargs):
            return [reference]

        def list_current_fulltext_elements(self, **kwargs):
            return [element]

        def list_current_fulltext_embeddings(self, **kwargs):
            return {reference["chunk_id"]: None}

    report = run_evaluation(
        ReadOnlySnapshot(),
        dataset,
        "c" * 64,
        query_embeddings={"R1": [1.0, 0.0]},
        embedding_model="TEST-embedding-v1",
    )

    assert all(
        strategy["retrieval_methods"]["bm25_parent_embedding_proxy_rerank"]["failure_reason"]
        == "current_chunk_embedding_index_incomplete"
        for strategy in report["strategies"].values()
    )


def test_parent_embedding_mapping_requires_exact_single_source_span_containment():
    candidates = [
        {
            "chunk_id": "TEST-candidate",
            "source_id": "TEST-source",
            "content_sha256": "a" * 64,
            "element_id": "TEST-element",
            "element_type": "paragraph",
            "page_number": 7,
            "char_start": 5,
            "char_end": 10,
        }
    ]
    parent = {
        "content_sha256": "a" * 64,
        "element_id": "TEST-element",
        "element_type": "paragraph",
        "page_number": 7,
        "char_start": 0,
        "char_end": 20,
    }
    assert _map_candidates_to_current_chunks(
        candidates, {"TEST-source": {"TEST-parent": parent}}
    ) == {"TEST-candidate": "TEST-parent"}
    with pytest.raises(ChunkStrategyEvaluationError, match="one current parent"):
        _map_candidates_to_current_chunks(
            [{**candidates[0], "char_start": 19, "char_end": 21}],
            {"TEST-source": {"TEST-parent": parent}},
        )
    with pytest.raises(ChunkStrategyEvaluationError, match="one current parent"):
        _map_candidates_to_current_chunks(
            candidates,
            {"TEST-source": {"TEST-parent": parent, "TEST-duplicate": parent}},
        )


def test_parent_proxy_rerank_budgets_unique_parents_and_uses_bm25_tie_breaks():
    candidates = [
        {"chunk_id": "TEST-child-a", "source_id": "TEST-source"},
        {"chunk_id": "TEST-child-b", "source_id": "TEST-source"},
        {"chunk_id": "TEST-child-c", "source_id": "TEST-source"},
    ]
    hits = [
        SimpleNamespace(openalex_id="TEST-child-a"),
        SimpleNamespace(openalex_id="TEST-child-b"),
        SimpleNamespace(openalex_id="TEST-child-c"),
    ]
    ranked, parent_count = _parent_embedding_proxy_rerank(
        hits,
        candidates,
        {
            "TEST-child-a": "TEST-parent-1",
            "TEST-child-b": "TEST-parent-1",
            "TEST-child-c": "TEST-parent-2",
        },
        {"TEST-parent-1": [0.0, 1.0], "TEST-parent-2": [1.0, 0.0]},
        [1.0, 0.0],
        limit=3,
    )

    assert parent_count == 2
    assert ranked == ["TEST-child-c", "TEST-child-a", "TEST-child-b"]


def test_historical_anchor_remaps_only_exact_unique_text_from_the_same_pdf():
    source_hash = "a" * 64
    selected_text = "TEST exact selected span"
    element = _element("TEST-current-element", "paragraph", f"Before. {selected_text} After.")

    class ReadOnlyStore:
        def get_approved_fulltext_chunk_by_id(self, **kwargs):
            assert kwargs["source_id"] == "TEST-source"
            return {
                "source_document_sha256": source_hash,
                "license_id": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "page_number": 7,
                "element_type": "paragraph",
                "evidence_text": selected_text,
            }

    task = {
        "task_id": "R1",
        "source_id": "TEST-source",
        "reference_chunk_id": "TEST-old-chunk",
        "reference_page": 7,
        "reference_element_type": "paragraph",
    }
    expected_source = {
        "content_sha256": "b" * 64,
        "source_document_sha256": source_hash,
        "license_id": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
    }

    anchor, resolved_element, resolution = _resolve_reference_anchor(
        ReadOnlyStore(), task, expected_source, {}, [element]
    )

    assert resolution == "exact_text_remap_same_pdf"
    assert resolved_element == element
    assert element["text"][anchor["char_start"] : anchor["char_end"]] == selected_text


def test_historical_anchor_fails_closed_when_text_is_ambiguous_or_pdf_changed():
    selected_text = "TEST repeated evidence"
    element = _element("TEST-current-element", "paragraph", f"{selected_text} then {selected_text}")

    class ReadOnlyStore:
        source_document_sha256 = "c" * 64

        def get_approved_fulltext_chunk_by_id(self, **kwargs):
            return {
                "source_document_sha256": self.source_document_sha256,
                "license_id": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "page_number": 7,
                "element_type": "paragraph",
                "evidence_text": selected_text,
            }

    task = {
        "task_id": "R2",
        "source_id": "TEST-source",
        "reference_chunk_id": "TEST-old-chunk",
        "reference_page": 7,
        "reference_element_type": "paragraph",
    }
    expected_source = {
        "content_sha256": "d" * 64,
        "source_document_sha256": "e" * 64,
        "license_id": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
    }

    store = ReadOnlyStore()
    with pytest.raises(ChunkStrategyEvaluationError, match="not verified against the current PDF"):
        _resolve_reference_anchor(store, task, expected_source, {}, [element])
    store.source_document_sha256 = expected_source["source_document_sha256"]
    with pytest.raises(ChunkStrategyEvaluationError, match="does not map uniquely"):
        _resolve_reference_anchor(store, task, expected_source, {}, [element])
