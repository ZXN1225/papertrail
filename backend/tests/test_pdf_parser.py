from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.retrieval import pdf_parser
from app.retrieval.fulltext import MAX_CHUNK_TOKEN_UPPER_BOUND, chunk_pdf_elements
from app.retrieval.pdf_parser import (
    _column_order,
    _drop_empty_table_rows,
    _extract_positioned_words,
    _extract_table_rows,
    _fully_inside,
    _heading_level,
    _merge_continuation_rows,
    _normalize_scientific_table_header,
    _normalize_subscript_text,
    _reattach_grid_dropped_words,
    _table_candidate_is_structured,
    _table_column_groups,
    _table_header_row_count,
    _table_rows,
    _word_lines,
    parse_pdf,
)


def _word_line(text: str, top: float, x: float = 50.0) -> list[dict[str, object]]:
    words = []
    for part in text.split():
        width = max(len(part) * 5.0, 8.0)
        words.append({"x0": x, "x1": x + width, "top": top, "bottom": top + 10, "text": part})
        x += width + 4
    return words


def test_positioned_word_extraction_uses_spacing_safe_tolerance() -> None:
    observed: list[dict[str, object]] = []
    page = SimpleNamespace(
        extract_words=lambda **kwargs: observed.append(kwargs) or [{"text": "Figure 7"}]
    )

    assert _extract_positioned_words(page) == [{"text": "Figure 7"}]
    assert observed == [{"x_tolerance": 1, "extra_attrs": ["size"]}]


def test_vector_underscore_is_restored_only_at_lower_baseline() -> None:
    words = [
        {"text": "TEST", "x0": 10, "x1": 30, "top": 20, "bottom": 30},
        {"text": "synthetic", "x0": 34, "x1": 70, "top": 20, "bottom": 30},
    ]
    page = SimpleNamespace(
        extract_words=lambda **kwargs: words,
        lines=[{"x0": 30, "x1": 34, "top": 28, "bottom": 28}],
    )
    assert _extract_positioned_words(page)[0]["text"] == "TEST_synthetic"
    page.lines[0].update(top=25, bottom=25)
    assert len(_extract_positioned_words(page)) == 2


def test_table_cell_restores_vector_underscore_from_positioned_words() -> None:
    table = SimpleNamespace(rows=[SimpleNamespace(cells=[(10, 20, 80, 40)])])
    result = _table_rows(
        table,
        [["fori loop"]],
        page=None,
        positioned_words=[{"text": "fori_loop", "x0": 20, "x1": 60, "top": 25, "bottom": 35}],
    )
    assert result[0]["cells"][0]["text"] == "fori_loop"


def _cell(text: str, *box: float) -> dict[str, object]:
    cell: dict[str, object] = {"text": text}
    if box:
        cell["bbox"] = list(box)
    return cell


def test_only_a_table_wholly_inside_a_figure_region_is_rejected() -> None:
    """A figure's text layer is rejected only when it fits entirely in a figure box."""
    figure = [105.1, 145.4, 506.9, 388.4]
    assert _fully_inside([155.1, 195.4, 389.2, 323.4], figure) is True
    # Overlapping but not contained: a real table that merely touches the figure.
    assert _fully_inside([100.0, 195.4, 389.2, 323.4], figure) is False
    assert _fully_inside([155.1, 195.4, 389.2, 420.0], figure) is False
    # Sub-point rounding must not defeat containment.
    assert _fully_inside([105.4, 145.0, 506.5, 388.8], figure) is True


def test_grid_dropped_trailing_word_is_reattached_to_its_row() -> None:
    """A heading glyph outside the last inferred column edge still belongs to the row."""
    table = SimpleNamespace(
        bbox=(10.0, 20.0, 140.0, 40.0),
        rows=[SimpleNamespace(cells=[(10, 20, 120, 40), (120, 20, 140, 40)])],
    )
    rows = [
        {
            "row_index": 0,
            "cells": [_cell("RMSD after", 10, 20, 120, 40), _cell("", 120, 20, 140, 40)],
        }
    ]

    added = _reattach_grid_dropped_words(
        rows,
        [
            {"text": "RMSD", "x0": 20, "x1": 50, "top": 25, "bottom": 35},
            {"text": "after", "x0": 55, "x1": 80, "top": 25, "bottom": 35},
            {"text": "UMA", "x0": 150, "x1": 175, "top": 25, "bottom": 35},
        ],
        (10.0, 20.0, 200.0, 40.0),
    )

    assert added == 1
    assert rows[0]["cells"][0]["text"] == "RMSD after"
    assert rows[0]["cells"][1]["text"] == "UMA"
    assert (
        _table_rows(
            table,
            [["RMSD after", ""]],
            horizontal_bounds=(10.0, 20.0, 200.0, 40.0),
            positioned_words=[{"text": "UMA", "x0": 150, "x1": 175, "top": 25, "bottom": 35}],
        )[0]["cells"][1]["text"]
        == "UMA"
    )


def test_single_glyph_dropped_from_a_cell_is_restored_despite_identical_glyphs_elsewhere() -> None:
    """A subscript glyph is masked by identical characters elsewhere, so count them."""
    rows = [
        {
            "row_index": 0,
            "cells": [
                _cell("E E v", 10, 20, 60, 30),
                _cell("/e v", 60, 20, 110, 30),
            ],
        }
    ]

    added = _reattach_grid_dropped_words(
        rows,
        [
            {"text": "E", "x0": 12, "x1": 20, "top": 22, "bottom": 28},
            {"text": "v", "x0": 22, "x1": 27, "top": 22, "bottom": 28},
            # The first cell's text carries a single "v", so this second one is missing.
            {"text": "v", "x0": 30, "x1": 35, "top": 22, "bottom": 28},
        ],
        (10.0, 20.0, 110.0, 30.0),
    )

    assert added == 1
    assert rows[0]["cells"][0]["text"].count("v") == 2
    assert rows[0]["cells"][1]["text"] == "/e v"


def test_word_present_in_another_row_is_never_duplicated_into_an_empty_row() -> None:
    """A misplaced word is not a dropped word: copying it would duplicate the header."""
    rows = [
        {"row_index": 0, "cells": [_cell("Strict Vital Recall", 10, 20, 110, 30)]},
        {"row_index": 1, "cells": [_cell("", 10, 30, 110, 40)]},
    ]

    added = _reattach_grid_dropped_words(
        rows,
        [
            {"text": "Strict", "x0": 12, "x1": 40, "top": 32, "bottom": 38},
            {"text": "Vital", "x0": 45, "x1": 70, "top": 32, "bottom": 38},
            {"text": "Recall", "x0": 75, "x1": 105, "top": 32, "bottom": 38},
        ],
        (10.0, 20.0, 110.0, 40.0),
    )

    assert added == 0
    assert rows[1]["cells"][0]["text"] == ""


def test_wrapped_cell_continuation_rows_are_merged_into_their_owner() -> None:
    rows = [
        {
            "row_index": 2,
            "cells": [
                _cell("Column loop", 10, 20, 60, 30),
                _cell("vmap", 60, 20, 100, 30),
                _cell("fori_loop", 100, 20, 140, 30),
            ],
        },
        {
            "row_index": 4,
            "cells": [
                _cell("", 10, 20, 60, 30),
                _cell("", 60, 20, 100, 30),
                _cell("jnp.arange", 100, 24, 140, 34),
            ],
        },
        {
            "row_index": 5,
            "cells": [
                _cell("Level loop", 10, 34, 60, 44),
                _cell("jnp.arange", 60, 34, 100, 44),
                _cell("", 100, 34, 140, 44),
            ],
        },
        {
            "row_index": 6,
            "cells": [
                _cell("", 10, 44, 60, 54),
                _cell("", 60, 44, 100, 54),
                _cell(".at[klevs].set", 100, 44, 140, 54),
            ],
        },
    ]

    merged = _merge_continuation_rows(rows)

    assert [row["row_index"] for row in merged] == [2, 5]
    assert [cell["text"] for cell in merged[1]["cells"]] == [
        "Level loop",
        "jnp.arange",
        "jnp.arange .at[klevs].set",
    ]


def test_spanning_single_cell_row_is_not_merged_as_a_continuation() -> None:
    rows = [
        {
            "row_index": 0,
            "cells": [_cell("A", 10, 20, 60, 30), _cell("1", 60, 20, 110, 30)],
        },
        {
            "row_index": 1,
            "cells": [_cell("Total", 10, 32, 110, 42)],
        },
        {
            "row_index": 2,
            "cells": [_cell("", 10, 44, 60, 54), _cell("2", 60, 44, 110, 54)],
        },
    ]

    merged = _merge_continuation_rows(rows)

    assert [row["row_index"] for row in merged] == [0, 1, 2]
    assert merged[1]["cells"][0]["text"] == "Total"


def test_word_lines_preserve_superscripts_and_shifted_math_glyphs() -> None:
    words = [
        {"text": "TEST", "x0": 10, "x1": 30, "top": 20, "bottom": 30},
        {"text": "10", "x0": 35, "x1": 45, "top": 20, "bottom": 30},
        {"text": "6", "x0": 45, "x1": 49, "top": 20.5, "bottom": 27.5},
        {"text": "×", "x0": 53, "x1": 60, "top": 22.5, "bottom": 32.5},
        {"text": "synthetic", "x0": 10, "x1": 50, "top": 34, "bottom": 44},
    ]
    lines = _word_lines(words, 600)
    assert len(lines) == 2
    assert lines[0]["text"] == "TEST 10^{6} ×"
    assert lines[1]["text"] == "synthetic"


def _fake_pdf_module(pages: list[SimpleNamespace]) -> SimpleNamespace:
    class FakePdf:
        def __init__(self) -> None:
            self.pages = pages

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    return SimpleNamespace(open=lambda _path: FakePdf())


def _synthetic_pdf_with_ruled_table() -> bytes:
    """Build a tiny valid PDF using only the standard library for parser integration tests."""
    commands = b"""BT /F1 14 Tf 50 740 Td (Introduction) Tj ET
BT /F1 11 Tf 50 710 Td (TEST synthetic evidence extraction.) Tj ET
BT /F1 11 Tf 50 690 Td (A second synthetic sentence for parser integration.) Tj ET
BT /F1 11 Tf 50 630 Td (Table 1: TEST retrieval evidence) Tj ET
50 615 m 400 615 l S
50 585 m 400 585 l S
50 555 m 400 555 l S
50 615 m 50 555 l S
230 615 m 230 555 l S
400 615 m 400 555 l S
BT /F1 10 Tf 55 595 Td (Method) Tj ET
BT /F1 10 Tf 235 595 Td (Recall) Tj ET
BT /F1 10 Tf 55 565 Td (Hybrid) Tj ET
BT /F1 10 Tf 235 565 Td (0.9) Tj ET
"""
    stream = commands + b"\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"endstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n% TEST-synthetic=true\n")
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_number} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


def test_heading_and_table_guards_reject_layout_noise() -> None:
    assert _heading_level("2.3 Image-processing pipeline") == (
        "2.3 Image-processing pipeline",
        2,
    )
    assert _heading_level("Abstract") == ("Abstract", 1)
    assert _heading_level("6202") is None
    assert _heading_level("S(b)") is None
    assert _heading_level("28 papers") is None
    assert _heading_level("Component Version Role in the platform") is None

    assert _table_candidate_is_structured(
        [["Method", "Recall"], ["BM25", "0.7"], ["Hybrid", "0.9"]]
    )
    assert not _table_candidate_is_structured(
        [["", "", "", "net -9.6%", "", ""], ["", "", "", "", "", ""]]
    )
    assert (
        _table_header_row_count(
            [
                ["", "", "", "V", "", "", "", ""],
                [
                    "",
                    "",
                    "Strict Vital Recall",
                    "Δ vs. Naive strict",
                    "Hallucination",
                    "Δ Halluc.",
                    "Accuracy",
                    "F1",
                ],
                ["System", "Retrieval Strategy", "", "", "", "", "", ""],
                ["", "", "V (%) strict", "[95% CI]", "Rate (%)", "[95% CI]", "(%)", "(%)"],
                ["Naive RAG", "BM25", "63.8", "–", "11.2", "–", "58.8", "63.1"],
                ["Hybrid RAG", "Vector + BM25", "65.5", "+1.7", "9.4", "−1.7", "65.0", "73.3"],
            ]
        )
        == 4
    )


def test_table_header_repairs_delta_subscript_and_unit_order() -> None:
    # TEST-synthetic=true: local parser fixture only; never written to the corpus.
    rows = [
        {"row_index": 0, "cells": [{"text": ""}, {"text": ""}, {"text": ""}, {"text": "V"}]},
        {
            "row_index": 1,
            "cells": [
                {"text": ""},
                {"text": ""},
                {"text": "Strict Vital Recall"},
                {"text": "∆ vs. Naive strict"},
            ],
        },
        {
            "row_index": 3,
            "cells": [
                {"text": ""},
                {"text": ""},
                {"text": "V (%) strict"},
                {"text": "[95% CI]"},
            ],
        },
    ]

    _normalize_scientific_table_header(rows)

    assert rows[0]["cells"][3]["text"] == ""
    assert rows[1]["cells"][3]["text"] == "∆V_strict vs. Naive"
    assert rows[2]["cells"][2]["text"] == "V_strict (%)"


def test_empty_header_row_is_removed_from_logical_count_after_repair() -> None:
    # TEST-synthetic=true: an isolated V is repaired into the next header cell,
    # so it must not leave an empty physical row in the logical table metadata.
    rows = [
        {"row_index": 0, "cells": [{"text": ""}, {"text": ""}, {"text": ""}, {"text": "V"}]},
        {
            "row_index": 1,
            "cells": [
                {"text": ""},
                {"text": ""},
                {"text": "Strict Vital Recall"},
                {"text": "∆ vs. Naive strict"},
                {"text": "Hallucination"},
                {"text": "∆ Halluc. vs. Naive"},
                {"text": "Accuracy"},
                {"text": "F1"},
            ],
        },
        {
            "row_index": 2,
            "cells": [
                {"text": "System"},
                {"text": "Retrieval Strategy"},
                *[{"text": ""} for _ in range(6)],
            ],
        },
        {
            "row_index": 3,
            "cells": [
                {"text": ""},
                {"text": ""},
                {"text": "V (%) strict"},
                {"text": "[95% CI]"},
                {"text": "Rate (%)"},
                {"text": "[95% CI]"},
                {"text": "(%)"},
                {"text": "(%)"},
            ],
        },
        *[
            {
                "row_index": index,
                "cells": [
                    {"text": f"System {index}"},
                    {"text": "BM25"},
                    {"text": "63.8"},
                    {"text": "-"},
                    {"text": "11.2"},
                    {"text": "-"},
                    {"text": "58.8"},
                    {"text": "63.1"},
                ],
            }
            for index in range(4, 9)
        ],
    ]

    _normalize_scientific_table_header(rows)
    logical_rows = _drop_empty_table_rows(rows)

    assert len(logical_rows) == 8
    assert [row["row_index"] for row in logical_rows] == list(range(1, 9))
    assert (
        _table_header_row_count([[cell["text"] for cell in row["cells"]] for row in logical_rows])
        == 3
    )


def test_blank_header_slot_merges_split_continuation_column() -> None:
    # TEST-synthetic=true: local parser fixture only; never written to the corpus.
    rows = [
        ["Attribute", "Categories (examples)", "", "Coverage"],
        ["Tumor type", "Glioblastoma / glioma / brain", "metastases", "predominant"],
    ]

    assert _table_column_groups(rows) == [[0], [1, 2], [3]]
    assert _table_column_groups(rows, merge_continuations=False) == [
        [0],
        [1],
        [2],
        [3],
    ]
    assert _normalize_subscript_text("IVIM (f , D , D ) p t p") == "IVIM (f_p, D_t, D_p)"
    assert _normalize_subscript_text("IVIM (fp, Dt, Dp)") == "IVIM (f_p, D_t, D_p)"


def test_table_rows_merge_split_cell_bbox_and_text() -> None:
    # TEST-synthetic=true: local bbox fixture only; never written to the corpus.
    class Crop:
        def extract_text(self, **_kwargs: object) -> str:
            return "Glioblastoma / glioma / brain metastases"

    page = SimpleNamespace(crop=lambda _box: Crop())
    table = SimpleNamespace(
        rows=[
            SimpleNamespace(
                cells=[(0, 10, 10, 20), (10, 10, 20, 20), (20, 10, 30, 20), (30, 10, 40, 20)]
            )
        ]
    )

    rows = _table_rows(
        table,
        [["Tumor type", "Glioblastoma / glioma / brain", "metastases", "predominant"]],
        page=page,
        column_groups=[[0], [1, 2], [3]],
    )

    assert [cell["text"] for cell in rows[0]["cells"]] == [
        "Tumor type",
        "Glioblastoma / glioma / brain metastases",
        "predominant",
    ]
    assert rows[0]["cells"][1]["bbox"] == [10, 10, 30, 20]


def test_positioned_line_grouping_splits_a_narrow_two_column_gutter() -> None:
    words = [
        {"x0": 54, "x1": 100, "top": 50, "bottom": 60, "text": "left"},
        {"x0": 104, "x1": 299, "top": 50, "bottom": 60, "text": "column-ending"},
        {"x0": 317, "x1": 368, "top": 50, "bottom": 60, "text": "right"},
        {"x0": 372, "x1": 420, "top": 50, "bottom": 60, "text": "column"},
    ]

    assert [line["text"] for line in _word_lines(words, 612)] == [
        "left column-ending",
        "right column",
    ]


def test_column_order_keeps_a_spanning_figure_caption_before_two_columns() -> None:
    lines = [
        {"text": "Figure caption spanning page", "bbox": [54, 30, 560, 42]},
        {"text": "Centered left heading", "bbox": [130, 70, 240, 82]},
        {"text": "Left paragraph one", "bbox": [57, 100, 280, 112]},
        {"text": "Left paragraph two", "bbox": [57, 120, 280, 132]},
        {"text": "Left paragraph three", "bbox": [57, 140, 280, 152]},
        {"text": "Right paragraph one", "bbox": [305, 90, 540, 102]},
        {"text": "Right paragraph two", "bbox": [305, 110, 540, 122]},
        {"text": "Right paragraph three", "bbox": [305, 130, 540, 142]},
    ]

    ordered, ambiguous, split_x = _column_order(lines, 612)

    assert not ambiguous
    assert split_x is not None
    assert [line["text"] for line in ordered] == [
        "Figure caption spanning page",
        "Centered left heading",
        "Left paragraph one",
        "Left paragraph two",
        "Left paragraph three",
        "Right paragraph one",
        "Right paragraph two",
        "Right paragraph three",
    ]


def test_ambiguous_spanning_line_still_labels_columns_to_prevent_paragraph_merge() -> None:
    lines = [
        {"text": "Left paragraph one", "bbox": [54, 50, 280, 62]},
        {"text": "Right paragraph one", "bbox": [305, 55, 540, 67]},
        {"text": "Left paragraph two", "bbox": [54, 75, 280, 87]},
        {"text": "A wide figure annotation", "bbox": [54, 95, 560, 107]},
        {"text": "Right paragraph two", "bbox": [305, 115, 540, 127]},
        {"text": "Left paragraph three", "bbox": [54, 140, 280, 152]},
        {"text": "Right paragraph three", "bbox": [305, 145, 540, 157]},
    ]

    ordered, ambiguous, split_x = _column_order(lines, 612)

    assert ambiguous
    assert split_x is not None
    assert [line["column"] for line in ordered] == [0, 0, 0, 1, 1, 1, 2]
    right_column = [line["text"] for line in ordered if line["column"] == 1]
    assert right_column == [
        "Right paragraph one",
        "Right paragraph two",
        "Right paragraph three",
    ]


def test_spanning_caption_keeps_short_final_line_before_column_prose() -> None:
    lines = [
        {"text": "Left TEST paragraph one", "bbox": [54, 50, 280, 62]},
        {"text": "Right TEST paragraph one", "bbox": [305, 55, 540, 67]},
        {"text": "Left TEST paragraph two", "bbox": [54, 90, 280, 102]},
        {"text": "Right TEST paragraph two", "bbox": [305, 95, 540, 107]},
        {"text": "Left TEST paragraph three", "bbox": [54, 130, 280, 142]},
        {"text": "Right TEST paragraph three", "bbox": [305, 135, 540, 147]},
        {"text": "Figure 5: TEST full-width caption", "bbox": [54, 180, 550, 190]},
        {"text": "(d) TEST transition at 70 nm", "bbox": [54, 192, 550, 202]},
        {"text": "(e) TEST transition at 220 nm", "bbox": [54, 204, 550, 214]},
        {"text": "TEST caption ends here.", "bbox": [54, 216, 240, 226]},
        {"text": "Left TEST body after figure", "bbox": [54, 240, 280, 252]},
        {"text": "Right TEST body after figure", "bbox": [305, 245, 540, 257]},
    ]

    ordered, ambiguous, split_x = _column_order(lines, 612)

    assert ambiguous
    assert split_x is not None
    caption = [line for line in ordered if line["column"] == 2]
    assert [line["text"] for line in caption] == [
        "Figure 5: TEST full-width caption",
        "(d) TEST transition at 70 nm",
        "(e) TEST transition at 220 nm",
        "TEST caption ends here.",
    ]
    assert ordered.index(caption[-1]) < next(
        index for index, line in enumerate(ordered) if line["text"] == "Left TEST body after figure"
    )


def test_parser_rejects_sparse_chart_grid_and_page_number_headings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sparse_chart_grid = SimpleNamespace(
        extract=lambda: [["", "", "", "net -9.6%", "", ""], ["", "", "", "", "", ""]],
        bbox=(100, 100, 500, 350),
        rows=[],
    )
    page = SimpleNamespace(
        width=600,
        height=800,
        find_tables=lambda: [sparse_chart_grid],
        images=[],
        extract_words=lambda: (
            _word_line("2 Methods", 80, 50)
            + _word_line("Main body paragraph follows.", 110, 50)
            + _word_line("6202", 760, 290)
        ),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-chart-grid.pdf"
    path.write_bytes(b"synthetic=true; sparse chart grid")

    result = parse_pdf(path)

    assert result["table_regions"] == 0
    assert not [item for item in result["elements"] if item["element_type"] == "table"]
    assert "sparse_table_candidates_rejected" in {item["code"] for item in result["warnings"]}
    assert not [
        item
        for item in result["elements"]
        if item["element_type"] == "heading" and item["text"] == "6202"
    ]


def test_captioned_text_table_fallback_preserves_paper_table_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = SimpleNamespace(
        extract=lambda: [["Metric", "Value"], ["TEST recall", "0.9"]],
        bbox=(100, 96, 400, 140),
        rows=[
            SimpleNamespace(cells=[(100, 96, 250, 118), (250, 96, 400, 118)]),
            SimpleNamespace(cells=[(100, 118, 250, 140), (250, 118, 400, 140)]),
        ],
    )

    class CroppedPage:
        def find_tables(self, *, table_settings):
            assert table_settings["vertical_strategy"] == "text"
            assert table_settings["horizontal_strategy"] == "text"
            return [table]

    def crop(box):
        assert box[1] < table.bbox[1]
        assert box[3] > table.bbox[3]
        return CroppedPage()

    page = SimpleNamespace(
        width=600,
        height=800,
        find_tables=lambda: [],
        crop=crop,
        images=[],
        extract_words=lambda: (
            _word_line("Table 2: TEST metrics", 50, 50)
            + _word_line("Metric", 100, 100)
            + _word_line("Value", 100, 300)
            + _word_line("TEST recall", 122, 100)
            + _word_line("0.9", 122, 300)
            + _word_line("A prose paragraph follows the table and spans the page.", 160, 50)
        ),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-captioned-text-table.pdf"
    path.write_bytes(b"synthetic=true; captioned text table")

    result = parse_pdf(path)

    assert result["table_regions"] == 1
    table_element = next(item for item in result["elements"] if item["element_type"] == "table")
    assert table_element["text"].startswith("Table 2 (page 1)")
    assert table_element["structured"]["rows"][1]["cells"][0]["text"] == "TEST recall"


def test_captioned_ruled_table_fallback_accepts_roman_numeral_in_two_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = SimpleNamespace(
        extract=lambda **_kwargs: [
            ["Collection", "Unique documents"],
            ["TEST source", "12"],
        ],
        bbox=(112, 120, 504, 142),
        rows=[],
    )

    class CroppedPage:
        def find_tables(self, *, table_settings):
            assert table_settings["vertical_strategy"] == "text"
            assert table_settings["horizontal_strategy"] == "text"
            return [table]

    crop_boxes: list[tuple[float, float, float, float]] = []

    def crop(box):
        crop_boxes.append(box)
        return CroppedPage()

    page = SimpleNamespace(
        width=612,
        height=792,
        find_tables=lambda: [],
        crop=crop,
        lines=[
            {"x0": 112, "x1": 504, "top": 120, "bottom": 120},
            {"x0": 112, "x1": 504, "top": 142, "bottom": 142},
            {"x0": 57, "x1": 296, "top": 220, "bottom": 220},
            {"x0": 57, "x1": 296, "top": 242, "bottom": 242},
        ],
        images=[],
        extract_words=lambda: (
            _word_line("TABLE I. TEST source counts", 50, 54)
            + _word_line("Neighbor column prose", 80, 317)
            + _word_line("TABLE II. Another table", 190, 54)
        ),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-captioned-roman-table.pdf"
    path.write_bytes(b"synthetic=true; roman-captioned ruled table")

    result = parse_pdf(path)

    assert result["table_regions"] == 1
    table_element = next(item for item in result["elements"] if item["element_type"] == "table")
    assert table_element["text"].startswith("Table I (page 1)")
    assert table_element["structured"]["rows"][1]["cells"][0]["text"] == "TEST source"
    assert len(crop_boxes) == 2
    assert crop_boxes[0][3] < 150
    assert crop_boxes[1][1] > 180


def test_captioned_ruled_table_candidate_must_cover_the_ruled_extent() -> None:
    from app.retrieval.pdf_parser import _table_covers_ruled_bbox, _visual_table_lines

    expected = [139.0, 146.2, 456.3, 293.0]
    assert _table_covers_ruled_bbox([138.0, 143.0, 456.0, 297.0], expected)
    assert not _table_covers_ruled_bbox([145.0, 150.0, 359.6, 289.0], expected)
    words = [
        {"x0": 150, "x1": 185, "top": 170, "bottom": 180, "text": "baseline"},
        {"x0": 250, "x1": 270, "top": 171, "bottom": 181, "text": "K=1"},
        {"x0": 150, "x1": 200, "top": 190, "bottom": 200, "text": "capacity"},
        {"x0": 480, "x1": 500, "top": 170, "bottom": 180, "text": "outside"},
    ]
    assert _visual_table_lines(words, expected) == [["baseline K=1"], ["capacity"]]


def test_table_cell_extraction_uses_spacing_safe_tolerance() -> None:
    class SyntheticTable:
        def extract(self, **kwargs: object) -> list[list[str]]:
            assert kwargs == {"x_tolerance": 2}
            return [["Web server and real-time progress streaming"]]

    assert _extract_table_rows(SyntheticTable()) == [
        ["Web server and real-time progress streaming"]
    ]


def test_real_pdfplumber_integration_extracts_synthetic_text_and_table(tmp_path: Path) -> None:
    path = tmp_path / "TEST-synthetic-parser-integration.pdf"
    path.write_bytes(_synthetic_pdf_with_ruled_table())

    result = parse_pdf(path)

    assert result["page_count"] == 1
    paragraphs = [item for item in result["elements"] if item["element_type"] == "paragraph"]
    tables = [item for item in result["elements"] if item["element_type"] == "table"]
    assert any("TEST synthetic evidence extraction." in item["text"] for item in paragraphs)
    assert len(tables) == 1
    assert tables[0]["structured"]["rows"] == [
        {
            "row_index": 0,
            "cells": [
                {"text": "Method", "bbox": [50.0, 177.0, 230.0, 207.0]},
                {"text": "Recall", "bbox": [230.0, 177.0, 400.0, 207.0]},
            ],
        },
        {
            "row_index": 1,
            "cells": [
                {"text": "Hybrid", "bbox": [50.0, 207.0, 230.0, 237.0]},
                {"text": "0.9", "bbox": [230.0, 207.0, 400.0, 237.0]},
            ],
        },
    ]


def test_synthetic_pdf_contract_tracks_sections_tables_and_spatial_captions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = SimpleNamespace(
        extract=lambda: [["Method", "Recall"], ["Hybrid", "0.9"]],
        bbox=(350, 400, 550, 500),
        rows=[
            SimpleNamespace(cells=[(350, 400, 450, 430), (450, 400, 550, 430)]),
            SimpleNamespace(cells=[(350, 430, 450, 500), (450, 430, 550, 500)]),
        ],
    )
    page1 = SimpleNamespace(
        width=600,
        height=800,
        extract_text=lambda layout: "",
        find_tables=lambda: [],
        images=[],
        extract_words=lambda: (
            _word_line("1 Introduction", 40)
            + _word_line("A study of retrieval evidence.", 70)
            + _word_line("Another paragraph starts here.", 92)
        ),
    )
    page2 = SimpleNamespace(
        width=600,
        height=800,
        extract_text=lambda layout: "",
        find_tables=lambda: [table],
        images=[{"x0": 40, "top": 120, "x1": 250, "bottom": 220}],
        extract_words=lambda: (
            _word_line("The same section continues here.", 55)
            + _word_line("Fig. 1: Retrieval architecture", 235, 55)
            + _word_line("Fig. 2: An unmatched caption", 650, 55)
        ),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page1, page2]))
    path = tmp_path / "TEST-synthetic-paper.pdf"
    path.write_bytes(b"synthetic=true; no real paper content")

    result = parse_pdf(path)
    repeated = parse_pdf(path)

    assert result["page_count"] == 2
    assert result["warnings"] == []
    assert [item["element_id"] for item in result["elements"]] == [
        item["element_id"] for item in repeated["elements"]
    ]
    assert [item["order_index"] for item in result["elements"]] == list(
        range(len(result["elements"]))
    )
    required_keys = {
        "element_id",
        "order_index",
        "page_number",
        "page_width",
        "page_height",
        "bbox",
        "element_type",
        "section_path",
        "text",
        "structured",
        "warnings",
    }
    assert all(required_keys <= set(item) for item in result["elements"])

    paragraphs = [item for item in result["elements"] if item["element_type"] == "paragraph"]
    continued = next(item for item in paragraphs if item["page_number"] == 2)
    assert continued["section_path"] == ["1 Introduction"]
    assert continued["bbox"] == [50.0, 55.0, 206.0, 65.0]

    parsed_table = next(item for item in result["elements"] if item["element_type"] == "table")
    assert parsed_table["bbox"] == [350, 400, 550, 500]
    assert parsed_table["structured"]["rows"][0]["cells"][0] == {
        "text": "Method",
        "bbox": [350, 400, 450, 430],
    }
    assert "Method | Recall" in parsed_table["text"]

    figures = [item for item in result["elements"] if item["element_type"] == "figure_caption"]
    matched, unmatched = figures
    assert matched["bbox"] == [55.0, 235.0, 202.0, 245.0]
    assert matched["structured"]["image_relation"]["status"] == "matched"
    assert unmatched["structured"]["image_relation"]["status"] == "unmatched"
    image = next(item for item in result["elements"] if item["element_type"] == "image_region")
    assert image["structured"]["caption_relation"]["status"] == "matched"

    chunks = chunk_pdf_elements(result["elements"])
    assert any(chunk.page_number == 2 and chunk.element_type == "table" for chunk in chunks)
    assert all(chunk.element_id for chunk in chunks)
    continued_chunk = next(chunk for chunk in chunks if chunk.element_id == continued["element_id"])
    assert (
        continued_chunk.text
        == continued["text"][continued_chunk.char_start : continued_chunk.char_end]
    )


def test_table_chunks_repeat_headers_and_preserve_element_local_offsets() -> None:
    long_rows = [f"Synthetic-{index} | " + ("evidence " * 100) for index in range(1, 6)]
    source_text = "Table 1 (page 1)\nMethod | Notes\n" + "\n".join(long_rows)
    rows = [{"cells": [{"text": "Method"}, {"text": "Notes"}]}]
    rows.extend(
        {"cells": [{"text": f"Synthetic-{index}"}, {"text": "evidence " * 100}]}
        for index in range(1, 6)
    )
    chunks = chunk_pdf_elements(
        [
            {
                "element_id": "pdfel_test_table",
                "page_number": 1,
                "element_type": "table",
                "section_path": ["Results"],
                "text": source_text,
                "bbox": [10, 20, 500, 400],
                "structured": {"rows": rows},
            }
        ]
    )

    assert len(chunks) > 1
    for chunk in chunks:
        assert "Method | Notes" in chunk.text
        assert chunk.element_id == "pdfel_test_table"
        assert source_text[chunk.char_start : chunk.char_end].strip() in chunk.text
        assert len(chunk.text) <= 1_800
        assert len(chunk.text.encode("utf-8")) <= MAX_CHUNK_TOKEN_UPPER_BOUND
        assert json.loads(chunk.section_path) == ["Results"]


def test_multirow_table_header_is_not_counted_as_data_in_locator() -> None:
    rows = [
        ["", "", "", "V", "", "", "", ""],
        [
            "",
            "",
            "Strict Vital Recall",
            "Δ vs. Naive strict",
            "Hallucination",
            "Δ Halluc.",
            "Accuracy",
            "F1",
        ],
        ["System", "Retrieval Strategy", "", "", "", "", "", ""],
        ["", "", "V (%) strict", "[95% CI]", "Rate (%)", "[95% CI]", "(%)", "(%)"],
        ["Naive RAG", "BM25", "63.8", "–", "11.2", "–", "58.8", "63.1"],
        ["Hybrid RAG", "Vector + BM25", "65.5", "+1.7", "9.4", "−1.7", "65.0", "73.3"],
        ["Agentic RAG", "Vector + BM25", "66.1", "+2.3", "7.9", "−3.3", "60.6", "67.1"],
        ["GraphRAG", "Vector + BM25 + KG", "69.1", "+5.3", "11.3", "+0.1", "61.9", "69.2"],
        [
            "Agentic GraphRAG (ours)",
            "Vector + BM25 + KG",
            "70.3",
            "+6.4",
            "8.7",
            "−2.5",
            "64.1",
            "71.2",
        ],
    ]
    structured_rows = [
        {"row_index": index, "cells": [{"text": cell} for cell in row]}
        for index, row in enumerate(rows)
    ]
    text = "Table II (page 10)\n" + "\n".join(" | ".join(row) for row in rows)
    element = {
        "element_id": "pdfel_TEST_multiline_table_header",
        "page_number": 10,
        "element_type": "table",
        "section_path": [],
        "text": text,
        "structured": {"rows": structured_rows, "header_row_count": 4},
    }

    chunks = chunk_pdf_elements([element])

    assert len(chunks) == 1
    assert "解析器物理行 5-9" in chunks[0].locator
    assert "解析器物理行 2-9" not in chunks[0].locator
    assert "Agentic GraphRAG (ours)" in chunks[0].text
    assert "Strict Vital Recall" in chunks[0].text
    assert "63.8" in chunks[0].text and "70.3" in chunks[0].text
    assert "Δ vs. Naive strict" in chunks[0].text


def test_table_chunk_joins_only_unambiguous_hyphenated_continuation_rows() -> None:
    source_text = (
        "Table 1 (page 6)\nComponent | Version | Role\n"
        "Flask | 2.3 | streaming-\n"
        " |  | ing\n"
        "Azure | n/a | reasoning\n"
        " |  | (HIPAA-compliant)"
    )
    element = {
        "element_id": "pdfel_TEST_table_hyphen_continuation",
        "page_number": 6,
        "element_type": "table",
        "section_path": ["Methods"],
        "text": source_text,
        "structured": {
            "rows": [
                {
                    "row_index": 0,
                    "cells": [{"text": "Component"}, {"text": "Version"}, {"text": "Role"}],
                },
                {
                    "row_index": 2,
                    "cells": [{"text": "Flask"}, {"text": "2.3"}, {"text": "streaming-"}],
                },
                {"row_index": 3, "cells": [{"text": ""}, {"text": ""}, {"text": "ing"}]},
                {
                    "row_index": 4,
                    "cells": [{"text": "Azure"}, {"text": "n/a"}, {"text": "reasoning"}],
                },
                {
                    "row_index": 5,
                    "cells": [{"text": ""}, {"text": ""}, {"text": "(HIPAA-compliant)"}],
                },
            ]
        },
    }

    chunks = chunk_pdf_elements([element])

    assert len(chunks) == 1
    chunk = chunks[0]
    assert "Flask | 2.3 | streaming" in chunk.text
    assert "Azure | n/a | reasoning\n |  | (HIPAA-compliant)" in chunk.text
    assert "解析器物理行 3-6" in chunk.locator
    assert chunk.evidence_text == source_text[chunk.char_start : chunk.char_end]
    assert "streaming-\n |  | ing" in chunk.evidence_text


def test_table_chunks_collapse_blank_header_column_and_rejoin_split_word() -> None:
    source_text = (
        "Table 2 (page 14)\nAttribute | Categories (examples) |  | Coverage\n"
        "Tumor type | Glioblastoma / glioma / brain | metastases | predominant\n"
        " | Pancreatic adenocarcinoma; h | ead and neck; | secondary\n"
        "Evidence | Original studies, systematic | reviews/meta- | mixed\n"
        " | analyses, position statements |  | "
    )
    element = {
        "element_id": "pdfel_TEST_blank_header_column",
        "page_number": 14,
        "element_type": "table",
        "section_path": ["Methods"],
        "text": source_text,
        "structured": {
            "rows": [
                {
                    "row_index": 0,
                    "cells": [
                        {"text": "Attribute"},
                        {"text": "Categories (examples)"},
                        {"text": ""},
                        {"text": "Coverage"},
                    ],
                },
                {
                    "row_index": 2,
                    "cells": [
                        {"text": "Tumor type"},
                        {"text": "Glioblastoma / glioma / brain"},
                        {"text": "metastases"},
                        {"text": "predominant"},
                    ],
                },
                {
                    "row_index": 3,
                    "cells": [
                        {"text": ""},
                        {"text": "Pancreatic adenocarcinoma; h"},
                        {"text": "ead and neck;"},
                        {"text": "secondary"},
                    ],
                },
                {
                    "row_index": 7,
                    "cells": [
                        {"text": "Evidence"},
                        {"text": "Original studies, systematic"},
                        {"text": "reviews/meta-"},
                        {"text": "mixed"},
                    ],
                },
                {
                    "row_index": 8,
                    "cells": [
                        {"text": ""},
                        {"text": "analyses, position statements"},
                        {"text": ""},
                        {"text": ""},
                    ],
                },
            ]
        },
    }

    chunks = chunk_pdf_elements([element])

    assert len(chunks) == 1
    chunk = chunks[0]
    assert "Attribute | Categories (examples) | Coverage" in chunk.text
    assert "brain metastases" in chunk.text
    assert "Pancreatic adenocarcinoma; head and neck; | secondary" in chunk.text
    assert "Attribute | Categories (examples) | Coverage" in chunk.text
    assert chunk.evidence_text == source_text[chunk.char_start : chunk.char_end]
    assert "reviews/meta-analyses" in chunk.text


def test_oversized_table_row_is_split_without_dropping_header_or_row_text() -> None:
    row = "TEST-Huge | " + ("analysis " * 300)
    source_text = f"Table 2 (page 2)\nMethod | Notes\n{row}"
    chunks = chunk_pdf_elements(
        [
            {
                "element_id": "pdfel_test_oversized_row",
                "page_number": 2,
                "element_type": "table",
                "section_path": ["Results"],
                "text": source_text,
                "structured": {
                    "rows": [
                        {"cells": [{"text": "Method"}, {"text": "Notes"}]},
                        {"cells": [{"text": "TEST-Huge"}, {"text": "analysis " * 300}]},
                    ]
                },
            }
        ]
    )

    assert len(chunks) > 1
    assert all("Method | Notes" in chunk.text for chunk in chunks)
    assert all(len(chunk.text) <= 1_800 for chunk in chunks)
    assert all(len(chunk.text.encode("utf-8")) <= MAX_CHUNK_TOKEN_UPPER_BOUND for chunk in chunks)
    recovered = "".join(source_text[chunk.char_start : chunk.char_end] for chunk in chunks).replace(
        " ", ""
    )
    assert recovered == row.replace(" ", "")


def test_oversized_cjk_table_row_respects_utf8_upper_bound_and_source_offsets() -> None:
    row = "合成方法 | " + ("证据定位准确率较高。" * 180)
    source_text = f"表 3 合成结果\n方法 | 说明\n{row}"
    element = {
        "element_id": "pdfel_TEST_CJK_TABLE",
        "page_number": 3,
        "element_type": "table",
        "section_path": ["结果"],
        "text": source_text,
        "structured": {
            "rows": [
                {"cells": [{"text": "方法"}, {"text": "说明"}]},
                {"cells": [{"text": "合成方法"}, {"text": "证据定位准确率较高。" * 180}]},
            ]
        },
    }

    chunks = chunk_pdf_elements([element])

    assert len(chunks) > 1
    assert all(len(chunk.text.encode("utf-8")) <= MAX_CHUNK_TOKEN_UPPER_BOUND for chunk in chunks)
    assert all("方法 | 说明" in chunk.text for chunk in chunks)
    recovered = "".join(source_text[chunk.char_start : chunk.char_end] for chunk in chunks)
    assert recovered.replace(" ", "") == row.replace(" ", "")


def test_pdf_partial_extraction_failure_is_returned_as_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = SimpleNamespace(
        width=400,
        height=600,
        extract_text=lambda layout: "Abstract\nSynthetic fallback text.",
        find_tables=lambda: (_ for _ in ()).throw(RuntimeError("synthetic table failure")),
        images=[],
        extract_words=lambda: (_ for _ in ()).throw(RuntimeError("synthetic word failure")),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-partial.pdf"
    path.write_bytes(b"synthetic=true; no real paper content")

    result = parse_pdf(path)

    codes = {warning["code"] for warning in result["warnings"]}
    assert "table_extraction_failed:RuntimeError" in codes
    assert "word_extraction_failed:RuntimeError" in codes
    assert "positioned_words_unavailable_page_bbox_used" in codes
    body = next(item for item in result["elements"] if "Synthetic fallback text" in item["text"])
    assert body["bbox"] == [0, 0, 400, 600]
    assert "bbox_is_page_level_fallback" in body["warnings"]


def test_synthetic_two_column_reading_order_keeps_heading_paths_and_carries_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page1 = SimpleNamespace(
        width=600,
        height=800,
        find_tables=lambda: [],
        images=[],
        extract_words=lambda: (
            _word_line("1 Introduction", 40, 50)
            + _word_line("Left column starts here.", 70, 50)
            + _word_line("Left column continues.", 92, 50)
            + _word_line("2 Methods", 40, 330)
            + _word_line("Right column starts here.", 70, 330)
            + _word_line("Right column continues.", 92, 330)
        ),
    )
    page2 = SimpleNamespace(
        width=600,
        height=800,
        find_tables=lambda: [],
        images=[],
        extract_words=lambda: _word_line("This continues after the page break.", 60, 50),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page1, page2]))
    path = tmp_path / "TEST-synthetic-two-columns.pdf"
    path.write_bytes(b"synthetic=true; two-column fixture")

    result = parse_pdf(path)

    bodies = [item for item in result["elements"] if item["element_type"] == "paragraph"]
    assert result["warnings"][0]["code"] == "two_column_layout_detected"
    assert [item["text"] for item in bodies[:2]] == [
        "Left column starts here.\nLeft column continues.",
        "Right column starts here.\nRight column continues.",
    ]
    assert bodies[0]["section_path"] == ["1 Introduction"]
    assert bodies[1]["section_path"] == ["2 Methods"]
    assert bodies[2]["section_path"] == ["2 Methods"]


def test_empty_word_extraction_deduplicates_table_lines_and_preserves_cell_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = SimpleNamespace(
        extract=lambda: [["Method", "Recall"], ["", ""], ["Hybrid", "0.9"]],
        bbox=(300, 200, 550, 350),
        rows=[
            SimpleNamespace(cells=[(300, 200, 400, 230), (400, 200, 550, 230)]),
            SimpleNamespace(cells=[(300, 230, 400, 250), (400, 230, 550, 250)]),
            SimpleNamespace(cells=[(300, 250, 400, 350), (400, 250, 550, 350)]),
        ],
    )
    page = SimpleNamespace(
        width=600,
        height=800,
        find_tables=lambda: [table],
        images=[],
        extract_words=lambda: [],
        extract_text=lambda layout: (
            "Results\nUseful prose above the table.\nMethod Recall\nHybrid 0.9\n"
            "Useful prose below the table."
        ),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-table-fallback.pdf"
    path.write_bytes(b"synthetic=true; table cell fixture")

    result = parse_pdf(path)

    paragraph_text = "\n".join(
        element["text"] for element in result["elements"] if element["element_type"] == "paragraph"
    )
    assert "Method Recall" not in paragraph_text
    assert "Hybrid 0.9" not in paragraph_text
    assert "Useful prose above the table." in paragraph_text
    assert "Useful prose below the table." in paragraph_text
    assert {warning["code"] for warning in result["warnings"]} >= {
        "positioned_words_unavailable_page_bbox_used",
        "table_text_deduplicated_without_word_geometry",
    }

    table_element = next(
        element for element in result["elements"] if element["element_type"] == "table"
    )
    assert table_element["structured"]["rows"][1]["row_index"] == 2
    assert table_element["structured"]["rows"][1]["cells"][0] == {
        "text": "Hybrid",
        "bbox": [300, 250, 400, 350],
    }
    row_chunks = chunk_pdf_elements([table_element])
    assert "解析器物理行 3" in row_chunks[0].locator
    chunk = next(chunk for chunk in row_chunks if "Hybrid" in chunk.text)
    assert table_element["text"][chunk.char_start : chunk.char_end] == "Hybrid | 0.9"


def test_ambiguous_multi_image_caption_is_not_forced_and_duplicate_ids_get_occurrences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = {"x0": 50, "top": 100, "x1": 260, "bottom": 220}
    page = SimpleNamespace(
        width=600,
        height=800,
        find_tables=lambda: [],
        images=[image, dict(image)],
        extract_words=lambda: _word_line("Fig. 3: Equidistant images", 240, 60),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-ambiguous-figure.pdf"
    path.write_bytes(b"synthetic=true; repeated-image fixture")

    first = parse_pdf(path)
    second = parse_pdf(path)

    images = [element for element in first["elements"] if element["element_type"] == "image_region"]
    caption = next(
        element for element in first["elements"] if element["element_type"] == "figure_caption"
    )
    ids = [element["element_id"] for element in first["elements"]]
    assert len(ids) == len(set(ids))
    assert ids == [element["element_id"] for element in second["elements"]]
    assert images[0]["element_id"] != images[1]["element_id"]
    assert caption["structured"]["image_relation"]["status"] == "ambiguous"
    assert caption["structured"]["image_relation"]["image_element_id"] is None
    assert caption["structured"]["image_relation"]["confidence"] == 0.0
    assert len(caption["structured"]["image_relation"]["candidate_image_ids"]) == 2
    assert all(image["structured"]["caption_relation"]["status"] == "unmatched" for image in images)


def test_vector_figure_boundary_is_linked_to_nearby_caption(tmp_path: Path, monkeypatch) -> None:
    page = SimpleNamespace(
        width=600,
        height=800,
        find_tables=lambda: [],
        images=[],
        rects=[
            {"x0": 100, "top": 100, "x1": 500, "bottom": 380},
            {"x0": 140, "top": 140, "x1": 460, "bottom": 340},
        ],
        extract_words=lambda: _word_line("Figure 1: Vector plot", 390, 100),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-vector-figure.pdf"
    path.write_bytes(b"synthetic=true; vector figure boundary")

    result = parse_pdf(path)

    region = next(item for item in result["elements"] if item["element_type"] == "image_region")
    caption = next(item for item in result["elements"] if item["element_type"] == "figure_caption")
    assert region["bbox"] == [98.0, 88.0, 502.0, 380.0]
    assert region["structured"]["region_source"] == "vector_boundary"
    assert region["structured"]["caption_relation"]["status"] == "matched"
    assert caption["structured"]["image_relation"]["status"] == "matched"
    assert caption["structured"]["image_relation"]["region_source"] == "vector_boundary"


def test_vector_figure_bbox_horizontal_padding_is_clamped_to_page(
    tmp_path: Path, monkeypatch
) -> None:
    page = SimpleNamespace(
        width=600,
        height=800,
        find_tables=lambda: [],
        images=[],
        rects=[{"x0": 1, "top": 100, "x1": 599, "bottom": 380}],
        extract_words=lambda: _word_line("Figure 1: TEST edge-to-edge plot", 390, 72),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-vector-figure-page-edge.pdf"
    path.write_bytes(b"synthetic=true; vector figure at page edges")

    result = parse_pdf(path)

    region = next(item for item in result["elements"] if item["element_type"] == "image_region")
    assert region["bbox"] == [0.0, 88.0, 600.0, 380.0]


def test_adjacent_vector_panels_are_grouped_for_multiplot_caption(
    tmp_path: Path, monkeypatch
) -> None:
    page = SimpleNamespace(
        width=600,
        height=800,
        find_tables=lambda: [],
        images=[{"x0": 120, "top": 200, "x1": 190, "bottom": 204}],
        rects=[
            {"x0": 50, "top": 100, "x1": 250, "bottom": 280},
            {"x0": 260, "top": 100, "x1": 460, "bottom": 280},
            {"x0": 50, "top": 292, "x1": 250, "bottom": 472},
            {"x0": 260, "top": 292, "x1": 460, "bottom": 472},
            {"x0": 80, "top": 130, "x1": 220, "bottom": 250},
        ],
        extract_words=lambda: _word_line("Figure 5: TEST four-panel measurements", 490, 50),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-four-panel-figure.pdf"
    path.write_bytes(b"synthetic=true; adjacent vector panel fixture")

    result = parse_pdf(path)

    regions = [
        item
        for item in result["elements"]
        if item["element_type"] == "image_region"
        and item.get("structured", {}).get("region_source") == "vector_boundary"
    ]
    caption = next(item for item in result["elements"] if item["element_type"] == "figure_caption")
    assert len(regions) == 1
    assert regions[0]["bbox"] == [48.0, 88.0, 462.0, 472.0]
    assert caption["structured"]["image_relation"]["status"] == "matched"
    assert caption["structured"]["image_relation"]["region_source"] == "vector_boundary"


def test_separated_vector_panel_groups_are_not_joined(tmp_path: Path, monkeypatch) -> None:
    page = SimpleNamespace(
        width=600,
        height=800,
        find_tables=lambda: [],
        images=[],
        rects=[
            {"x0": 50, "top": 100, "x1": 250, "bottom": 260},
            {"x0": 260, "top": 100, "x1": 460, "bottom": 260},
            {"x0": 50, "top": 500, "x1": 250, "bottom": 660},
            {"x0": 260, "top": 500, "x1": 460, "bottom": 660},
        ],
        extract_words=lambda: _word_line("Figure 1: TEST upper panel group", 280, 50),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-separated-figure-groups.pdf"
    path.write_bytes(b"synthetic=true; separated vector groups fixture")

    result = parse_pdf(path)

    regions = [
        item
        for item in result["elements"]
        if item["element_type"] == "image_region"
        and item.get("structured", {}).get("region_source") == "vector_boundary"
    ]
    caption = next(item for item in result["elements"] if item["element_type"] == "figure_caption")
    assert len(regions) == 1
    assert regions[0]["bbox"] == [48.0, 88.0, 462.0, 260.0]
    assert caption["structured"]["image_relation"]["status"] == "matched"


def test_thin_image_fragment_is_not_linked_as_figure_region(tmp_path: Path, monkeypatch) -> None:
    page = SimpleNamespace(
        width=600,
        height=800,
        find_tables=lambda: [],
        images=[{"x0": 205, "top": 640, "x1": 275, "bottom": 644}],
        extract_words=lambda: _word_line("Figure 5: TEST six-panel figure caption", 666, 72),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-thin-figure-fragment.pdf"
    path.write_bytes(b"synthetic=true; thin image fragment fixture")

    result = parse_pdf(path)

    region = next(item for item in result["elements"] if item["element_type"] == "image_region")
    caption = next(item for item in result["elements"] if item["element_type"] == "figure_caption")
    assert region["bbox"] == [205.0, 640.0, 275.0, 644.0]
    assert region["structured"]["caption_relation"]["status"] == "unmatched"
    assert caption["structured"]["image_relation"]["status"] == "unmatched"
    assert caption["structured"]["image_relation"]["candidate_image_ids"] == []


def test_script_tokens_do_not_break_caption_and_prose_reference_is_not_caption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    words = _word_line("Figure 2: TEST synthetic pCO", 200)
    anchor = words[-1]
    words.append(
        {"text": "2", "x0": anchor["x1"], "x1": anchor["x1"] + 4, "top": 204, "bottom": 211}
    )
    words += _word_line("continues through the final sentence.", 212)
    words += _word_line("Figure 2 shows TEST prose, not a caption.", 245)
    page = SimpleNamespace(
        width=600, height=800, find_tables=lambda: [], images=[], extract_words=lambda: words
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-script-caption.pdf"
    path.write_bytes(b"synthetic=true")
    parsed = parse_pdf(path)
    captions = [e for e in parsed["elements"] if e["element_type"] == "figure_caption"]
    assert len(captions) == 1
    assert "pCO_{2}" in captions[0]["text"]
    assert "final sentence." in captions[0]["text"]
    assert "shows" not in captions[0]["text"]
    assert any(
        e["element_type"] == "paragraph" and "Figure 2 shows" in e["text"]
        for e in parsed["elements"]
    )


def test_multiline_figure_caption_keeps_subfigure_labels_with_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = SimpleNamespace(
        width=600,
        height=800,
        find_tables=lambda: [],
        images=[{"x0": 45, "top": 100, "x1": 450, "bottom": 255}],
        extract_words=lambda: (
            _word_line("Figure 5: TEST synthetic transition measurements", 270)
            + _word_line("(d) Transition loss for 70 nm a-Si:H.", 282)
            + _word_line("(e) Transition loss for 220 nm a-Si:H.", 294)
            + _word_line("A separate TEST paragraph follows.", 325)
        ),
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-multiline-caption.pdf"
    path.write_bytes(b"synthetic=true; figure-caption continuation fixture")

    parsed = parse_pdf(path)
    captions = [item for item in parsed["elements"] if item["element_type"] == "figure_caption"]
    assert len(captions) == 1
    caption = captions[0]
    assert "(d) Transition loss for 70 nm" in caption["text"]
    assert "(e) Transition loss for 220 nm" in caption["text"]
    assert "separate TEST paragraph" not in caption["text"]
    assert caption["bbox"][1] == 270
    assert caption["bbox"][3] == 304
    chunks = chunk_pdf_elements(parsed["elements"])
    assert any(
        chunk.element_type == "figure_caption"
        and "(d) Transition loss for 70 nm" in chunk.text
        and "(e) Transition loss for 220 nm" in chunk.text
        for chunk in chunks
    )


def test_pdf_elements_keep_table_figure_caption_and_page_location(tmp_path: Path) -> None:
    fake_page = SimpleNamespace(
        width=600,
        height=800,
        extract_text=lambda layout: (
            "ABSTRACT\nA study of retrieval.\nFig. 1: Retrieval architecture"
        ),
        find_tables=lambda: [
            SimpleNamespace(
                extract=lambda: [["Method", "Recall"], ["Hybrid", "0.9"]],
                bbox=(350, 400, 550, 500),
                rows=[],
            )
        ],
        images=[{"x0": 30, "top": 100, "x1": 300, "bottom": 250}],
        extract_words=lambda: [
            {"x0": x0, "x1": x1, "top": 260, "bottom": 270, "text": word}
            for word, x0, x1 in (
                ("Fig.", 30, 45),
                ("1:", 49, 59),
                ("Retrieval", 63, 108),
                ("architecture", 112, 172),
            )
        ],
    )
    old_module = sys.modules.get("pdfplumber")
    sys.modules["pdfplumber"] = _fake_pdf_module([fake_page])
    try:
        path = tmp_path / "TEST-synthetic-legacy.pdf"
        path.write_bytes(b"synthetic=true")
        result = parse_pdf(path)
    finally:
        if old_module is None:
            sys.modules.pop("pdfplumber", None)
        else:
            sys.modules["pdfplumber"] = old_module

    assert result["page_count"] == 1
    assert result["image_regions"] == 1
    table = next(item for item in result["elements"] if item["element_type"] == "table")
    figure = next(item for item in result["elements"] if item["element_type"] == "figure_caption")
    assert "Method | Recall" in table["text"]
    assert table["bbox"] == [350, 400, 550, 500]
    assert figure["text"] == "Fig. 1: Retrieval architecture"
    assert figure["structured"]["image_relation"]["status"] == "matched"
    chunks = chunk_pdf_elements(result["elements"])
    assert any(chunk.page_number == 1 and chunk.element_type == "table" for chunk in chunks)


def test_visual_line_table_fallback_does_not_claim_grid_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    words = [
        {"text": "TESTheader", "x0": 45, "x1": 75, "top": 102, "bottom": 112, "size": 10},
        {"text": "TESTbody", "x0": 45, "x1": 75, "top": 130, "bottom": 140, "size": 10},
    ]
    broken_grid = SimpleNamespace(
        bbox=(0, 100, 100, 160),
        rows=[SimpleNamespace(cells=[(0, 100, 50, 115), (50, 100, 100, 115)])],
    )
    record = {
        "table": broken_grid,
        "normalized_rows": [["TESTheader", "cell"]],
        "source_row_indexes": [0],
        "width": 2,
        "caption_number": "TEST-1",
        "expected_ruled_bbox": [0, 100, 100, 160],
        "header_bottom": 120,
    }
    page = SimpleNamespace(
        width=200,
        height=200,
        find_tables=lambda: [],
        extract_words=lambda **_kwargs: words,
        extract_text=lambda **_kwargs: "",
        lines=[],
        chars=[],
        images=[],
        rects=[],
    )
    monkeypatch.setattr(pdf_parser, "_captioned_text_tables", lambda *_args: [record])
    monkeypatch.setattr(pdf_parser, "reconstruct_gutter_rows", lambda *_args, **_kwargs: None)
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-visual-table-fallback.pdf"
    path.write_bytes(b"synthetic=true")

    result = parse_pdf(path)

    table = next(item for item in result["elements"] if item["element_type"] == "table")
    assert table["structured"]["column_count"] == 1
    assert table["structured"]["structure_status"] == "visual_lines_only_unstructured"
    assert table["structured"]["row_semantics"] == "visual_lines"
    assert "table_structure_unavailable_visual_lines_only" in table["warnings"]


def test_pdf_parser_preserves_clean_body_grid_when_table_bbox_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    words = [
        {"text": "TEST-left", "x0": 10, "x1": 40, "top": 130, "bottom": 140, "size": 10},
        {"text": "TEST-right", "x0": 60, "x1": 90, "top": 130, "bottom": 140, "size": 10},
    ]
    grid = SimpleNamespace(
        bbox=(0, 100, 100, 150),
        rows=[
            SimpleNamespace(cells=[(0, 100, 50, 125), (50, 100, 100, 125)]),
            SimpleNamespace(cells=[(0, 125, 50, 150), (50, 125, 100, 150)]),
        ],
    )
    record = {
        "table": grid,
        "normalized_rows": [["TEST header left", "TEST header right"], ["TEST-left", "TEST-right"]],
        "source_row_indexes": [0, 1],
        "width": 2,
        "caption_number": "TEST-2",
        "expected_ruled_bbox": [0, 100, 100, 180],
        "header_bottom": 125,
    }
    page = SimpleNamespace(
        width=200,
        height=200,
        find_tables=lambda: [],
        extract_words=lambda **_kwargs: words,
        extract_text=lambda **_kwargs: "",
        lines=[],
        chars=[],
        images=[],
        rects=[],
    )
    monkeypatch.setattr(pdf_parser, "_captioned_text_tables", lambda *_args: [record])
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-preserved-grid.pdf"
    path.write_bytes(b"synthetic=true")

    result = parse_pdf(path)

    table = next(item for item in result["elements"] if item["element_type"] == "table")
    assert table["structured"]["column_count"] == 2
    assert table["structured"]["structure_status"] == "grid_columns_preserved_bbox_incomplete"
    assert table["bbox"] == [0, 100, 100, 180]
    assert "table_body_grid_preserved_no_body_text_cut" in table["warnings"]


def test_pdf_parser_excludes_positioned_words_outside_page_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = SimpleNamespace(
        width=200,
        height=200,
        find_tables=lambda: [],
        extract_words=lambda **_kwargs: [
            {"text": "TEST-visible", "x0": 20, "x1": 80, "top": 30, "bottom": 40},
            {"text": "TEST-off-page", "x0": 20, "x1": 80, "top": 210, "bottom": 220},
        ],
        extract_text=lambda **_kwargs: "",
        lines=[],
        chars=[],
        images=[],
        rects=[],
    )
    monkeypatch.setitem(sys.modules, "pdfplumber", _fake_pdf_module([page]))
    path = tmp_path / "TEST-synthetic-off-page-text.pdf"
    path.write_bytes(b"synthetic=true")

    result = parse_pdf(path)

    assert [element["text"] for element in result["elements"]] == ["TEST-visible"]
    assert {warning["code"] for warning in result["warnings"]} == {"out_of_page_text_excluded"}


def test_pdf_parser_rejects_non_pdf_paths(tmp_path: Path) -> None:
    source = tmp_path / "paper.txt"
    source.write_text("not a PDF", encoding="utf-8")
    with pytest.raises(ValueError, match=r"\.pdf"):
        parse_pdf(source)


def test_pdf_parser_extracts_text_from_a_real_minimal_pdf(tmp_path: Path) -> None:
    stream = (
        b"BT /F1 12 Tf 50 760 Td (ABSTRACT) Tj 0 -18 Td (Retrieval evidence on page one.) Tj ET"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, content in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode() + content + b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    source = tmp_path / "minimal.pdf"
    source.write_bytes(pdf)

    result = parse_pdf(source)

    assert result["page_count"] == 1
    assert any("Retrieval evidence on page one." in item["text"] for item in result["elements"])
