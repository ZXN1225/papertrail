"""TEST synthetic=true geometry regressions; no licensed paper text."""

from types import SimpleNamespace

from app.retrieval.pdf_table_refinement import (
    body_grid_cuts_text,
    caption_table_rules,
    grid_has_text_support,
    header_grid_cuts_text,
    reconstruct_gutter_rows,
    reconstruct_header_anchored_rows,
)


def test_sparse_plot_grid_keeps_empty_rows_in_density() -> None:
    rows = [["", "", "", "", ""] for _ in range(8)]
    rows[0] = ["", "", "", "TEST legend", "A"]
    rows[1] = ["", "", "", "TEST legend", "B"]
    rows[5] = ["", "1.2", "", "TEST", "annotation"]
    assert not grid_has_text_support(rows)
    assert grid_has_text_support([["TEST metric", "value"], ["synthetic=true", "2"]])


def test_missing_cells_count_against_grid_support() -> None:
    assert not grid_has_text_support([["TEST", "A", "B", "C"], [], [], ["1"]])
    assert not grid_has_text_support([])


def test_long_caption_does_not_truncate_bottom_table_rule() -> None:
    rules = [{"x0": 90, "x1": 520, "top": top, "bottom": top} for top in (175, 208, 365)]
    result = caption_table_rules(
        rules, caption_bbox=[72, 82, 540, 92], next_caption_top=700, page_width=612
    )
    assert result == [(175.0, 90.0, 520.0), (208.0, 90.0, 520.0), (365.0, 90.0, 520.0)]


def test_rule_collection_excludes_next_table_and_unaligned_rules() -> None:
    rules = [
        {"x0": left, "x1": right, "top": top}
        for top, left, right in [(120, 80, 500), (135, 80, 300), (180, 80, 500), (310, 80, 500)]
    ]
    assert caption_table_rules(
        rules, caption_bbox=[72, 80, 540, 95], next_caption_top=300, page_width=612
    ) == [(120.0, 80.0, 500.0), (180.0, 80.0, 500.0)]


def test_distant_rule_is_not_attached_to_caption() -> None:
    assert not caption_table_rules(
        [{"x0": 80, "x1": 500, "top": 450}],
        caption_bbox=[72, 80, 540, 95],
        next_caption_top=700,
        page_width=612,
    )


def test_header_cut_requires_actual_word_interior_intersection() -> None:
    table = SimpleNamespace(
        bbox=(0, 10, 100, 100),
        rows=[SimpleNamespace(cells=[(0, 10, 50, 20), (50, 10, 100, 20)])],
    )
    word = {"text": "TEST", "x0": 45, "x1": 60, "top": 11, "bottom": 19}
    assert header_grid_cuts_text(table, [word], header_bottom=20)
    assert not header_grid_cuts_text(table, [dict(word, x0=50)], header_bottom=20)
    assert not header_grid_cuts_text(table, [dict(word, top=40, bottom=49)], header_bottom=20)


def test_body_grid_cut_detects_words_bisected_by_inferred_columns() -> None:
    table = SimpleNamespace(
        bbox=(0, 10, 100, 100),
        rows=[
            SimpleNamespace(cells=[(0, 10, 50, 20), (50, 10, 100, 20)]),
            SimpleNamespace(cells=[(0, 20, 50, 30), (50, 20, 100, 30)]),
        ],
    )
    word = {"text": "TEST-cell", "x0": 45, "x1": 60, "top": 40, "bottom": 50}
    assert body_grid_cuts_text(table, [word], body_start=30)
    assert not body_grid_cuts_text(table, [dict(word, x0=50)], body_start=30)
    assert not body_grid_cuts_text(table, [word], body_start=60)


def test_script_induced_row_boundary_bisects_header_glyph() -> None:
    table = SimpleNamespace(
        bbox=(0, 10, 100, 100),
        rows=[SimpleNamespace(cells=[(0, 10, 100, 15), (0, 15, 100, 22)])],
    )
    char = {"text": "T", "x0": 30, "x1": 36, "top": 11, "bottom": 21}
    assert header_grid_cuts_text(table, [], chars=[char], header_bottom=24)
    assert not header_grid_cuts_text(table, [], chars=[dict(char, top=15)], header_bottom=24)


def _render_synthetic_words(words: list[dict]) -> list[dict]:
    return [
        {"text": word["text"], "bbox": [word["x0"], word["top"], word["x1"], word["bottom"]]}
        for word in sorted(words, key=lambda word: (word["top"], word["x0"]))
    ]


def _gutter_words() -> list[dict]:
    return [
        {
            "text": f"TEST-{row}-{col}",
            "x0": col * 60,
            "x1": col * 60 + 40,
            "top": top,
            "bottom": top + 10,
            "size": 10,
        }
        for row, top in enumerate((1, 21, 41))
        for col in range(3)
    ]


def test_gutters_recover_columns_and_preserve_visual_row_semantics() -> None:
    result = reconstruct_gutter_rows(
        _gutter_words(),
        bbox=[0, 0, 180, 60],
        header_bottom=15,
        render_lines=_render_synthetic_words,
    )
    assert result is not None
    assert result["rows"] == [[f"TEST-{row}-{col}" for col in range(3)] for row in range(3)]
    assert result["column_edges"] == [0, 50, 110, 180]
    assert result["row_semantics"] == "visual_lines_with_joined_header"


def test_gutters_do_not_guess_missing_heading_or_continuation_semantics() -> None:
    words = _gutter_words()
    words = [word for word in words if word["text"] != "TEST-2-0"]
    result = reconstruct_gutter_rows(
        words,
        bbox=[0, 0, 180, 60],
        header_bottom=15,
        render_lines=_render_synthetic_words,
    )
    assert result is not None
    assert result["continuation_candidates"] == [2]
    assert len(result["rows"]) == 3
    words = [word for word in words if word["text"] != "TEST-0-1"]
    assert (
        reconstruct_gutter_rows(
            words,
            bbox=[0, 0, 180, 60],
            header_bottom=15,
            render_lines=_render_synthetic_words,
        )
        is None
    )


def test_gutters_join_disjoint_same_baseline_fragments_in_one_cell() -> None:
    words = _gutter_words()
    words = [word for word in words if word["text"] != "TEST-1-1"]
    words.extend(
        [
            {"text": "TEST", "x0": 60, "x1": 78, "top": 21, "bottom": 31, "size": 10},
            {"text": "synthetic=true", "x0": 80, "x1": 100, "top": 21, "bottom": 31, "size": 10},
        ]
    )
    result = reconstruct_gutter_rows(
        words,
        bbox=[0, 0, 180, 60],
        header_bottom=15,
        render_lines=_render_synthetic_words,
    )
    assert result is not None
    assert result["rows"][1][1] == "TEST synthetic=true"


def test_header_anchors_recover_subscript_and_variable_width_cells() -> None:
    words = [
        {"text": "Symbol", "x0": 145, "x1": 180, "top": 150, "bottom": 160, "size": 11},
        {"text": "Value", "x0": 192, "x1": 219, "top": 150, "bottom": 160, "size": 11},
        {"text": "Meaning", "x0": 259, "x1": 300, "top": 150, "bottom": 160, "size": 11},
        {"text": "K", "x0": 145, "x1": 154, "top": 169, "bottom": 180, "size": 11},
        {"text": "min", "x0": 154, "x1": 170, "top": 173, "bottom": 181, "size": 8},
        {"text": "1", "x0": 192, "x1": 198, "top": 169, "bottom": 180, "size": 11},
        {"text": "baseline", "x0": 259, "x1": 297, "top": 169, "bottom": 180, "size": 11},
        {"text": "carrying", "x0": 300, "x1": 340, "top": 169, "bottom": 180, "size": 11},
        {"text": "capacity", "x0": 343, "x1": 383, "top": 169, "bottom": 180, "size": 11},
        {"text": "delta", "x0": 145, "x1": 163, "top": 190, "bottom": 201, "size": 11},
        {"text": "1.5", "x0": 192, "x1": 211, "top": 190, "bottom": 201, "size": 11},
        {"text": "×", "x0": 214, "x1": 222, "top": 190, "bottom": 201, "size": 11},
        {"text": "10^-3", "x0": 225, "x1": 247, "top": 190, "bottom": 201, "size": 11},
        {"text": "degradation", "x0": 259, "x1": 316, "top": 190, "bottom": 201, "size": 11},
    ]

    result = reconstruct_header_anchored_rows(
        words,
        bbox=[139, 146, 456, 211],
        header_bottom=165,
        render_lines=_render_synthetic_words,
    )

    assert result is not None
    assert result["column_edges"] == [139, 191.0, 258.0, 456]
    assert result["rows"][0] == ["Symbol", "Value", "Meaning"]
    assert result["rows"][1] == ["K min", "1", "baseline carrying capacity"]
    assert result["rows"][2] == ["delta", "1.5 × 10^-3", "degradation"]
    assert result["row_semantics"] == "visual_lines_with_joined_header"


def test_header_anchor_boundary_keeps_nearby_value_start_in_its_column() -> None:
    words = [
        {"text": "TEST-A", "x0": 0, "x1": 25, "top": 1, "bottom": 10, "size": 10},
        {"text": "TEST-B", "x0": 60.4, "x1": 85, "top": 1, "bottom": 10, "size": 10},
        {"text": "TEST-C", "x0": 110.4, "x1": 135, "top": 1, "bottom": 10, "size": 10},
        {"text": "TEST-a", "x0": 0, "x1": 20, "top": 20, "bottom": 30, "size": 10},
        {"text": "TEST-1", "x0": 60, "x1": 75, "top": 20, "bottom": 30, "size": 10},
        {"text": "TEST-x", "x0": 110, "x1": 130, "top": 20, "bottom": 30, "size": 10},
        {"text": "TEST-b", "x0": 0, "x1": 20, "top": 40, "bottom": 50, "size": 10},
        {"text": "TEST-2", "x0": 60, "x1": 75, "top": 40, "bottom": 50, "size": 10},
        {"text": "TEST-y", "x0": 110, "x1": 130, "top": 40, "bottom": 50, "size": 10},
    ]
    result = reconstruct_header_anchored_rows(
        words,
        bbox=[0, 0, 150, 60],
        header_bottom=15,
        render_lines=_render_synthetic_words,
    )

    assert result is not None
    assert result["rows"][1] == ["TEST-a", "TEST-1", "TEST-x"]


def test_header_anchors_reject_words_crossing_inferred_boundaries() -> None:
    words = [
        {"text": "Symbol", "x0": 0, "x1": 25, "top": 1, "bottom": 10, "size": 10},
        {"text": "Value", "x0": 50, "x1": 75, "top": 1, "bottom": 10, "size": 10},
        {"text": "Meaning", "x0": 100, "x1": 135, "top": 1, "bottom": 10, "size": 10},
        {"text": "TEST-A", "x0": 0, "x1": 20, "top": 20, "bottom": 30, "size": 10},
        {"text": "TEST-1", "x0": 50, "x1": 70, "top": 20, "bottom": 30, "size": 10},
        {"text": "TEST-text", "x0": 90, "x1": 105, "top": 20, "bottom": 30, "size": 10},
        {"text": "TEST-B", "x0": 0, "x1": 20, "top": 40, "bottom": 50, "size": 10},
        {"text": "TEST-2", "x0": 50, "x1": 70, "top": 40, "bottom": 50, "size": 10},
        {"text": "TEST-other", "x0": 100, "x1": 125, "top": 40, "bottom": 50, "size": 10},
    ]

    assert (
        reconstruct_header_anchored_rows(
            words,
            bbox=[0, 0, 150, 60],
            header_bottom=15,
            render_lines=_render_synthetic_words,
        )
        is None
    )
