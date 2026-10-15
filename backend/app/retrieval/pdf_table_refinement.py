"""Conservative geometry checks for PDF tables, independent of paper content."""

from collections.abc import Callable, Iterable, Mapping, Sequence
from statistics import median
from typing import Any


def grid_has_text_support(rows: Sequence[Sequence[str | None]]) -> bool:
    """Require text support across the original grid, including empty rows.

    Plot grids often have text only in a legend and an annotation. Dropping empty
    grid rows before measuring density makes those fragments resemble a table.
    This check is for uncaptioned line-grid candidates, not caption-anchored
    text-strategy recovery, whose empty spacer rows have a different meaning.
    """
    width = max((len(row) for row in rows), default=0)
    if len(rows) < 2 or width < 2:
        return False
    occupied = sum(bool(str(cell or "").strip()) for row in rows for cell in row)
    return occupied / (len(rows) * width) >= 0.35


def caption_table_rules(
    rules: Iterable[Mapping[str, Any]],
    *,
    caption_bbox: Sequence[float],
    next_caption_top: float,
    page_width: float,
    first_rule_distance: float = 260.0,
    max_rule_gap: float = 260.0,
) -> list[tuple[float, float, float]]:
    """Find a ruled table using its first rule, then its matching horizontal span.

    A long caption must not consume the table-height allowance. Only the first
    rule is bounded relative to the caption; subsequent aligned rules are bounded
    relative to the preceding rule and the next explicit table caption.
    """
    caption_left, _, caption_right, caption_bottom = map(float, caption_bbox)
    candidates: list[tuple[float, float, float]] = []
    for rule in rules:
        try:
            left = float(rule.get("x0", 0))
            right = float(rule.get("x1", 0))
            top = float(rule.get("top", 0))
            bottom = float(rule.get("bottom", top))
        except (TypeError, ValueError):
            continue
        if (
            caption_bottom <= top < next_caption_top
            and abs(bottom - top) <= 1.5
            and right - left >= 80
            and left <= caption_right + 16
            and right >= caption_left - 16
            and right <= page_width * 0.98
        ):
            candidates.append((top, left, right))
    candidates.sort()
    if not candidates or candidates[0][0] - caption_bottom > first_rule_distance:
        return []
    first = candidates[0]
    selected = [first]
    for rule in candidates[1:]:
        # Ignore short subtotal rules and neighboring columns. They cannot define
        # the outer bottom boundary of this table.
        if abs(rule[1] - first[1]) > 5 or abs(rule[2] - first[2]) > 5:
            continue
        if rule[0] - selected[-1][0] > max_rule_gap:
            break
        selected.append(rule)
    return selected


def header_grid_cuts_text(
    table: Any,
    words: Sequence[Mapping[str, Any]],
    *,
    header_bottom: float,
    chars: Sequence[Mapping[str, Any]] = (),
) -> bool:
    """Detect inferred column boundaries running through header words.

    Do not repair the resulting word fragments or guess column relationships.
    Callers can preserve the ruled region as geometry-ordered visual lines with
    an explicit unavailable-structure warning instead.
    """
    bbox = getattr(table, "bbox", None)
    rows = getattr(table, "rows", None) or []
    if not bbox or not rows:
        return False
    left, top, right, _ = map(float, bbox)
    boundaries = {
        float(cell[2])
        for row in rows
        for cell in (getattr(row, "cells", None) or [])
        if cell and left + 1 < float(cell[2]) < right - 1
    }
    for word in words:
        text = str(word.get("text", "")).strip()
        if len(text) < 2:
            continue
        x0, x1 = float(word["x0"]), float(word["x1"])
        center_y = (float(word["top"]) + float(word["bottom"])) / 2
        if not top <= center_y <= header_bottom:
            continue
        inset = max(0.75, (x1 - x0) * 0.1)
        if any(x0 + inset < edge < x1 - inset for edge in boundaries):
            return True
    horizontal_boundaries = {
        float(cell[3])
        for row in rows
        for cell in (getattr(row, "cells", None) or [])
        if cell and top + 1 < float(cell[3]) < header_bottom - 1
    }
    for char in chars:
        if not str(char.get("text", "")).strip():
            continue
        char_left, char_right = float(char["x0"]), float(char["x1"])
        char_top, char_bottom = float(char["top"]), float(char["bottom"])
        if not left <= (char_left + char_right) / 2 <= right:
            continue
        if not top <= (char_top + char_bottom) / 2 <= header_bottom:
            continue
        inset = max(0.75, (char_bottom - char_top) * 0.15)
        if any(char_top + inset < edge < char_bottom - inset for edge in horizontal_boundaries):
            return True
    return False


def body_grid_cuts_text(
    table: Any,
    words: Sequence[Mapping[str, Any]],
    *,
    body_start: float,
) -> bool:
    """Detect body words bisected by a grid's inferred column boundaries.

    A broken multi-line header does not necessarily invalidate the data columns.
    This check lets callers preserve those columns only when body words remain
    intact; it does not assess header meaning or cell semantics.
    """
    bbox = getattr(table, "bbox", None)
    rows = getattr(table, "rows", None) or []
    if not bbox or not rows:
        return True
    left, top, right, bottom = map(float, bbox)
    boundaries = {
        float(cell[2])
        for row in rows
        for cell in (getattr(row, "cells", None) or [])
        if cell and left + 1 < float(cell[2]) < right - 1
    }
    for word in words:
        if not str(word.get("text", "")).strip():
            continue
        x0, x1 = float(word["x0"]), float(word["x1"])
        center_y = (float(word["top"]) + float(word["bottom"])) / 2
        if not max(top, body_start) <= center_y <= bottom:
            continue
        inset = max(0.75, (x1 - x0) * 0.1)
        if any(x0 + inset < edge < x1 - inset for edge in boundaries):
            return True
    return False


def reconstruct_gutter_rows(
    words: Sequence[Mapping[str, Any]],
    *,
    bbox: Sequence[float],
    header_bottom: float,
    render_lines: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """Recover consistently spaced columns without splitting positioned words.

    Accept only at least two similarly sized wide gutters that remain empty
    throughout the ruled region, including its header. Rows retain visual line
    semantics: wrapped cells are not claimed to be separate logical records.
    The caller supplies its script-aware line renderer. No text is corrected or
    inferred from a paper-specific vocabulary.
    """
    left, top, right, bottom = map(float, bbox)
    bounded = [
        dict(word)
        for word in words
        if str(word.get("text", "")).strip()
        and left <= (float(word["x0"]) + float(word["x1"])) / 2 <= right
        and top <= (float(word["top"]) + float(word["bottom"])) / 2 <= bottom
    ]
    if not bounded or not top < header_bottom < bottom:
        return None
    sizes = [
        float(word.get("size", float(word["bottom"]) - float(word["top"]))) for word in bounded
    ]
    min_gap = max(3.0, median(sizes) * 0.5)
    visual_rows: list[list[dict[str, Any]]] = []
    for word in sorted(bounded, key=lambda value: (float(value["top"]), float(value["x0"]))):
        if (
            visual_rows
            and abs(float(word["top"]) - median(float(item["top"]) for item in visual_rows[-1]))
            <= 3
        ):
            visual_rows[-1].append(word)
        else:
            visual_rows.append([word])
    candidates: list[float] = []
    for row in visual_rows:
        ordered = sorted(row, key=lambda value: float(value["x0"]))
        for first, second in zip(ordered, ordered[1:], strict=False):
            gap = float(second["x0"]) - float(first["x1"])
            if gap >= min_gap:
                candidates.append((float(first["x1"]) + float(second["x0"])) / 2)
    if not candidates:
        return None
    # Small tables still need support from at least two visual rows. Requiring
    # three makes one missing body cell erase a stable gutter in a header plus
    # two-row table; header completeness below remains a separate safeguard.
    minimum_support = max(2, min(3, round(len(visual_rows) * 0.4)))
    gutters = []
    for center in sorted(candidates):
        if any(abs(center - other) < min_gap for other in gutters):
            continue
        support = sum(
            any(float(word["x1"]) <= center for word in row)
            and any(float(word["x0"]) >= center for word in row)
            for row in visual_rows
        )
        crossing = sum(
            any(float(word["x0"]) < center < float(word["x1"]) for word in row)
            for row in visual_rows
        )
        if support >= minimum_support and crossing <= len(visual_rows) * 0.15:
            gutters.append(center)
    if not 2 <= len(gutters) <= 15:
        return None
    edges = [left, *gutters, right]
    column_lines: list[list[dict[str, Any]]] = []
    header: list[str] = []
    for x0, x1 in zip(edges, edges[1:], strict=False):
        members = [word for word in bounded if x0 <= (word["x0"] + word["x1"]) / 2 < x1]
        headings = [word for word in members if (word["top"] + word["bottom"]) / 2 < header_bottom]
        body = [word for word in members if (word["top"] + word["bottom"]) / 2 >= header_bottom]
        header.append(" ".join(line["text"] for line in render_lines(headings)))
        column_lines.append(render_lines(body))
    if any(not text for text in header) or any(not lines for lines in column_lines):
        return None
    tagged = sorted(
        [(column, line) for column, lines in enumerate(column_lines) for line in lines],
        key=lambda item: float(item[1]["bbox"][1]),
    )
    bands: list[list[tuple[int, dict[str, Any]]]] = []
    for column, line in tagged:
        y = float(line["bbox"][1])
        if bands and abs(y - median(float(item[1]["bbox"][1]) for item in bands[-1])) <= 3:
            previous = next((item for item in bands[-1] if item[0] == column), None)
            if previous:
                prior_line = previous[1]
                first, second = sorted([prior_line, line], key=lambda value: value["bbox"][0])
                if float(first["bbox"][2]) > float(second["bbox"][0]) + 0.1:
                    return None
                prior_line["text"] = first["text"] + " " + second["text"]
                prior_line["bbox"] = [
                    min(first["bbox"][0], second["bbox"][0]),
                    min(first["bbox"][1], second["bbox"][1]),
                    max(first["bbox"][2], second["bbox"][2]),
                    max(first["bbox"][3], second["bbox"][3]),
                ]
                continue
            bands[-1].append((column, line))
        else:
            bands.append([(column, line)])
    rows = [header]
    row_boxes = [[left, top, right, header_bottom]]
    for band in bands:
        row = [""] * len(header)
        for column, line in band:
            row[column] = line["text"]
        rows.append(row)
        row_boxes.append(
            [
                left,
                min(float(line["bbox"][1]) for _, line in band),
                right,
                max(float(line["bbox"][3]) for _, line in band),
            ]
        )
    return {
        "rows": rows,
        "column_edges": edges,
        "row_boxes": row_boxes,
        "row_semantics": "visual_lines_with_joined_header",
        "continuation_candidates": [
            index for index, row in enumerate(rows) if index and not row[0]
        ],
    }


def reconstruct_header_anchored_rows(
    words: Sequence[Mapping[str, Any]],
    *,
    bbox: Sequence[float],
    header_bottom: float,
    render_lines: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """Infer columns from header starts confirmed by repeated body alignment.

    This fallback is intended for captioned ruled tables where text-grid
    boundaries cut words and subscript glyphs make whitespace gutters unstable.
    It is deliberately strict: the header must contain distinct aligned starts,
    each must recur in multiple body rows, and no positioned word may cross a
    proposed boundary. Rows remain visual lines, not inferred logical records.
    """
    left, top, right, bottom = map(float, bbox)
    bounded = [
        dict(word)
        for word in words
        if str(word.get("text", "")).strip()
        and left <= (float(word["x0"]) + float(word["x1"])) / 2 <= right
        and top <= (float(word["top"]) + float(word["bottom"])) / 2 <= bottom
    ]
    if not bounded or not top < header_bottom < bottom:
        return None
    sizes = [
        float(word.get("size", float(word["bottom"]) - float(word["top"]))) for word in bounded
    ]
    min_gap = max(3.0, median(sizes) * 0.5)
    row_tolerance = max(3.0, min(6.0, median(sizes) * 0.5))

    visual_rows: list[list[dict[str, Any]]] = []
    for word in sorted(bounded, key=lambda value: (float(value["top"]), float(value["x0"]))):
        if (
            visual_rows
            and abs(float(word["top"]) - median(float(item["top"]) for item in visual_rows[-1]))
            <= row_tolerance
        ):
            visual_rows[-1].append(word)
        else:
            visual_rows.append([word])

    header_rows = [
        sorted(row, key=lambda value: float(value["x0"]))
        for row in visual_rows
        if all((float(word["top"]) + float(word["bottom"])) / 2 < header_bottom for word in row)
    ]
    body_rows = [
        sorted(row, key=lambda value: float(value["x0"]))
        for row in visual_rows
        if all((float(word["top"]) + float(word["bottom"])) / 2 >= header_bottom for word in row)
    ]
    if len(body_rows) < 2 or not header_rows:
        return None

    # The widest empty gaps in a header line separate candidate headings.
    # Body alignment below rejects spaces between words inside a multiword cell.
    candidates: list[list[float]] = []
    for row in header_rows:
        starts = [float(row[0]["x0"])]
        for first, second in zip(row, row[1:], strict=False):
            if float(second["x0"]) - float(first["x1"]) >= min_gap:
                starts.append(float(second["x0"]))
        if 2 <= len(starts) <= 15:
            candidates.append(starts)
    if not candidates:
        return None
    anchors = max(candidates, key=lambda values: (len(values), -values[0]))
    tolerance = max(3.0, min(6.0, median(sizes) * 0.35))

    for anchor in anchors:
        support = sum(
            any(abs(float(word["x0"]) - anchor) <= tolerance for word in row) for row in body_rows
        )
        if support < max(2, (len(body_rows) + 1) // 2):
            return None

    # Use a small left padding from the next heading's start: PDF text boxes for
    # equivalent glyphs can differ by fractions of a point, and a body token
    # beginning just left of the heading anchor must remain in its value cell.
    boundary_pad = min(1.0, min_gap * 0.2)
    edges = [left, *(anchor - boundary_pad for anchor in anchors[1:]), right]
    if any(first >= second for first, second in zip(edges, edges[1:], strict=False)):
        return None
    if any(
        float(word["x0"]) + 0.25 < edge < float(word["x1"]) - 0.25
        for word in bounded
        for edge in edges[1:-1]
    ):
        return None

    def render_cell(row: Sequence[dict[str, Any]], column: int) -> str:
        start, end = edges[column], edges[column + 1]
        cell_words = [word for word in row if start <= float(word["x0"]) < end]
        lines = render_lines(cell_words)
        return " ".join(str(line["text"]).strip() for line in lines if str(line["text"]).strip())

    header_source = max(header_rows, key=lambda row: len(row))
    header = [render_cell(header_source, index) for index in range(len(edges) - 1)]
    if any(not value for value in header):
        return None
    rows = [header]
    row_boxes = [[left, top, right, header_bottom]]
    for row in body_rows:
        values = [render_cell(row, index) for index in range(len(edges) - 1)]
        if not any(values):
            continue
        rows.append(values)
        row_boxes.append(
            [
                left,
                min(float(word["top"]) for word in row),
                right,
                max(float(word["bottom"]) for word in row),
            ]
        )
    if len(rows) < 3:
        return None
    return {
        "rows": rows,
        "column_edges": edges,
        "row_boxes": row_boxes,
        "row_semantics": "visual_lines_with_joined_header",
        "continuation_candidates": [
            index for index, row in enumerate(rows) if index and not row[0]
        ],
    }
