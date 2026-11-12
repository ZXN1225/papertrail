from __future__ import annotations

import pytest

from app.evaluation.chunking import ChunkStrategyEvaluationError, _span_is_covered, run_evaluation
from app.retrieval.fulltext import chunk_pdf_elements


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


def test_chunk_size_rejects_out_of_range_or_boolean_values():
    with pytest.raises(ValueError, match="max_chunk_bytes"):
        chunk_pdf_elements([_element("TEST-e", "paragraph", "TEST text")], max_chunk_bytes=700)
    with pytest.raises(ValueError, match="max_chunk_bytes"):
        chunk_pdf_elements([_element("TEST-e", "paragraph", "TEST text")], max_chunk_bytes=True)


def test_strategy_evaluation_rejects_a_writable_store_before_loading_any_corpus():
    class WritableStore:
        readonly = False

    with pytest.raises(ChunkStrategyEvaluationError, match="read-only"):
        run_evaluation(WritableStore(), {"synthetic": True}, "0" * 64)
