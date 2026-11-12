"""Bounded local PDF extraction with page-layout evidence and partial warnings.

The output is intentionally a small, JSON-serializable element contract. Coordinates
are pdfplumber points with a top-left origin: ``[x0, top, x1, bottom]``.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import math
import os
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.retrieval.pdf_table_refinement import (
    body_grid_cuts_text,
    caption_table_rules,
    grid_has_text_support,
    header_grid_cuts_text,
    reconstruct_gutter_rows,
    reconstruct_header_anchored_rows,
)

PARSER_VERSION = "pdfplumber-layout-v27"
MAX_PDF_BYTES = 40_000_000
MAX_PDF_PAGES = 500
MINERU_ADAPTER_VERSION = "papertrail-v11"
MAX_PDF_TEXT_CHARS = 2_000_000
MAX_PDF_ELEMENTS = 20_000

_HEADING = re.compile(r"^(?P<number>\d+(?:\.\d+)*)(?:[.)])?\s+(?P<title>[A-Za-z][^.!?]{1,120})$")
_CAPTION = re.compile(r"^(?:fig(?:ure)?\.?|图)\s*\d+[A-Za-z]?(?:\s*[:.)-]\s*|$)", re.I)
_MINERU_FIGURE_CAPTION = re.compile(
    r"^(?:supplementary\s+)?fig(?:ure)?\.?\s*\d+[A-Za-z]?(?:\s*[:.)—–-]\s*|$)",
    re.I,
)
_MINERU_FIGURE_NUMBER = re.compile(
    r"^\s*(?:supplementary\s+)?[\[(]?\s*fig(?:ure)?\.?\s*(?P<number>\d+[a-z]?)\b",
    re.I,
)
_MINERU_DIAGRAM_CAPTION = re.compile(r"^(?:diagram|chart)\s+\d+\b", re.I)
_MINERU_PAGE_SELF_DESCRIPTION = re.compile(
    r"^(?:the\s+)?image\s+contains\s+no\s+(?:text|content)\b", re.I
)
_TABLE_CAPTION = re.compile(r"^table\s*(?P<number>\d+[A-Za-z]?|[IVXLCDM]+)\s*[:.)-]", re.I)
_TEXT_X_TOLERANCE = 2
_WORD_X_TOLERANCE = 1
_VECTOR_FIGURE_HORIZONTAL_PADDING = 2.0
_NAMED_HEADINGS = {
    "abstract",
    "introduction",
    "background",
    "related work",
    "methods",
    "methodology",
    "materials and methods",
    "results",
    "discussion",
    "conclusion",
    "references",
    "acknowledgments",
    "ethics approval",
    "data availability statement",
    "摘要",
    "引言",
    "相关工作",
    "方法",
    "实验结果",
    "讨论",
    "结论",
    "参考文献",
}


def _rounded_bbox(box: tuple[float, float, float, float] | list[float]) -> list[float]:
    return [round(float(value), 2) for value in box]


def _stable_element_id(
    page_number: int,
    element_type: str,
    text: str,
    bbox: list[float],
) -> str:
    """Return a repeatable ID for the same parser output on the same source page."""
    payload = json.dumps(
        [PARSER_VERSION, page_number, element_type, bbox, text],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return "pdfel_" + hashlib.sha256(payload).hexdigest()[:24]


def _word_lines(words: list[dict[str, Any]], page_width: float) -> list[dict[str, Any]]:
    """Group positioned words into visual lines, splitting wide column gutters."""
    buckets: dict[int, list[dict[str, Any]]] = {}
    for word in words:
        if not all(key in word for key in ("x0", "x1", "top", "bottom", "text")):
            continue
        top = float(word["top"])
        buckets.setdefault(round(top / 2), []).append(word)

    # Font metrics can move same-size math glyphs or monospace runs a few points
    # off the surrounding baseline. Merge these before handling smaller scripts.
    for key in sorted(buckets, key=lambda item: len(buckets[item]), reverse=True):
        bucket = buckets[key]
        if not bucket:
            continue
        reference = bucket[0]
        height = float(reference["bottom"]) - float(reference["top"])
        for other_key, other in buckets.items():
            if other_key == key or not other or abs(other_key - key) > 2:
                continue
            for word in list(other):
                other_height = float(word["bottom"]) - float(word["top"])
                if (
                    abs(float(word["top"]) - float(reference["top"])) <= 3
                    and abs(other_height - height) < height * 0.1
                ):
                    bucket.append(word)
                    other.remove(word)

    # Small superscript/subscript tokens share the baseline's visual line.
    # Keeping them as separate lines interrupts captions and loses formula order.
    for key, bucket in list(buckets.items()):
        for word in list(bucket):
            if word.get("script_token"):
                continue
            height = float(word["bottom"]) - float(word["top"])
            candidates = []
            for other_key, others in buckets.items():
                if abs(other_key - key) > 6:
                    continue
                for anchor in others:
                    anchor_height = float(anchor["bottom"]) - float(anchor["top"])
                    gap = float(word["x0"]) - float(anchor["x1"])
                    overlap = min(float(word["bottom"]), float(anchor["bottom"])) - max(
                        float(word["top"]), float(anchor["top"])
                    )
                    if 0 < height <= anchor_height * 0.88 and -0.5 <= gap <= 2 and overlap > 0:
                        candidates.append((abs(gap), other_key, anchor))
            if candidates:
                _, target, anchor = min(candidates, key=lambda item: item[0])
                copied = dict(word)
                marker = "^" if float(word["bottom"]) < float(anchor["bottom"]) - 1 else "_"
                copied["text"] = marker + "{" + str(word["text"]) + "}"
                copied["script_token"] = True
                bucket.remove(word)
                buckets[target].append(copied)

    lines: list[dict[str, Any]] = []
    # Real two-column papers often leave only a 15–25 pt gutter. A much wider
    # threshold lets the last word of the left column merge with the first word
    # of the right column before `_column_order` can detect the layout.
    gutter = max(10.0, page_width * 0.02)
    for bucket in buckets.values():
        ordered = sorted(bucket, key=lambda word: (float(word["x0"]), float(word["top"])))
        segments: list[list[dict[str, Any]]] = [[]]
        prior_x1: float | None = None
        for word in ordered:
            x0 = float(word["x0"])
            if prior_x1 is not None and x0 - prior_x1 > gutter:
                segments.append([])
            segments[-1].append(word)
            prior_x1 = float(word["x1"])
        for segment in segments:
            if not segment:
                continue
            line_text = ""
            for word in segment:
                separator = "" if word.get("script_token") else " "
                line_text += separator + str(word["text"]).strip()
            line_text = line_text.strip()
            if not line_text:
                continue
            lines.append(
                {
                    "text": line_text,
                    "bbox": [
                        min(float(word["x0"]) for word in segment),
                        min(float(word["top"]) for word in segment),
                        max(float(word["x1"]) for word in segment),
                        max(float(word["bottom"]) for word in segment),
                    ],
                }
            )
    return sorted(lines, key=lambda line: (line["bbox"][1], line["bbox"][0]))


def _heading_level(text: str) -> tuple[str, int] | None:
    stripped = text.strip().rstrip("#").strip()
    if len(stripped) > 140 or _CAPTION.match(stripped):
        return None
    if stripped.lower() in _NAMED_HEADINGS:
        return stripped, 1
    match = _HEADING.match(stripped)
    if match:
        number = match.group("number")
        title = match.group("title").strip()
        if title[:1].isupper() and not _CAPTION.match(title):
            return stripped, number.count(".") + 1
    # Unnumbered headings are accepted only from the explicit vocabulary above.
    # Generic title-case detection promoted page numbers, table headers, and equations
    # to section headings in real publisher PDFs.
    return None


def _table_candidate_is_structured(rows: list[list[str]]) -> bool:
    """Reject sparse plot grids that pdfplumber mistakes for data tables."""
    nonempty_rows = [row for row in rows if any(cell.strip() for cell in row)]
    if len(nonempty_rows) < 2:
        return False
    width = max((len(row) for row in nonempty_rows), default=0)
    if width < 2 or width > 16:
        return False
    nonempty_cell_count = sum(bool(cell.strip()) for row in nonempty_rows for cell in row)
    density = nonempty_cell_count / (len(nonempty_rows) * width)
    rows_with_multiple_cells = sum(
        sum(bool(cell.strip()) for cell in row) >= 2 for row in nonempty_rows
    )
    return nonempty_cell_count >= 4 and density >= 0.25 and rows_with_multiple_cells >= 2


def _table_header_row_count(rows: list[list[str]]) -> int:
    """Find a short multi-row header before rows that contain measured decimals.

    Most tables keep a single header row. Some scientific tables use several
    stacked label/unit rows; only skip those when a later row has multiple
    decimal-valued cells, which is a conservative signal of the data body.
    """
    for index, row in enumerate(rows[1 : min(len(rows), 8)], start=1):
        decimal_cells = sum(
            bool(re.search(r"(?<![\w.])[+-]?\d+\.\d+(?:%|)?(?!\w)", cell)) for cell in row
        )
        if decimal_cells >= 3:
            return index
    return 1


def _extract_table_rows(table: Any) -> list[list[Any]]:
    """Extract table cells with a tighter word-gap threshold for reliable spacing."""
    try:
        extracted = table.extract(x_tolerance=_TEXT_X_TOLERANCE)
    except TypeError as error:
        # Keep compatibility with small third-party/test adapters whose extract()
        # method does not expose pdfplumber's keyword arguments.
        if "unexpected keyword argument" not in str(error):
            raise
        extracted = table.extract()
    return extracted or []


def _extract_positioned_words(page: Any) -> list[dict[str, Any]]:
    """Keep body words separate when glyph spacing is narrow in scientific PDFs."""
    extract_words = page.extract_words
    try:
        words = extract_words(x_tolerance=_WORD_X_TOLERANCE, extra_attrs=["size"]) or []
    except TypeError as error:
        # Keep compatibility with small adapters whose method has no pdfplumber kwargs.
        if "unexpected keyword argument" not in str(error):
            raise
        return extract_words() or []
    # TeX may draw a code identifier's underscore as a short vector stroke.
    # Restore only a stroke bridging two adjacent words at the baseline's bottom.
    rules = getattr(page, "lines", []) or []
    removed: set[int] = set()
    output = [dict(word) for word in words]
    for index, word in enumerate(output):
        if index in removed or not all(k in word for k in ("x0", "x1", "top", "bottom")):
            continue
        height = float(word["bottom"]) - float(word["top"])
        for following_index in range(index + 1, min(len(output), index + 4)):
            following = output[following_index]
            if following_index in removed:
                continue
            if not (
                abs(float(following["top"]) - float(word["top"])) < 1
                and 1 < float(following["x0"]) - float(word["x1"]) < height * 0.8
            ):
                continue
            if any(
                abs(float(rule.get("bottom", 0)) - float(rule.get("top", 0))) < 0.5
                and abs(float(rule.get("x0", 0)) - float(word["x1"])) < 1
                and abs(float(rule.get("x1", 0)) - float(following["x0"])) < 1
                and float(word["top"]) + height * 0.72
                < float(rule.get("top", 0))
                < float(word["bottom"])
                for rule in rules
            ):
                word["text"] += "_" + following["text"]
                word["x1"] = following["x1"]
                removed.add(following_index)
    return [word for index, word in enumerate(output) if index not in removed]


def _captioned_text_tables(
    page: Any,
    lines: list[dict[str, Any]],
    page_width: float,
    page_height: float,
    existing_boxes: list[list[float]],
) -> list[dict[str, Any]]:
    """Recover text-aligned tables anchored by an explicit Table N caption.

    This bounded fallback avoids applying pdfplumber's text strategy to an entire
    page, where ordinary paragraphs and vector plots become false tables.
    """
    crop_page = getattr(page, "crop", None)
    if not callable(crop_page):
        return []
    records: list[dict[str, Any]] = []
    captions = [line for line in lines if _TABLE_CAPTION.match(str(line["text"]).strip())]
    for caption in captions:
        caption_box = caption["bbox"]
        caption_x = float(caption_box[0])
        caption_bottom = float(caption_box[3])
        caption_match = _TABLE_CAPTION.match(str(caption["text"]).strip())
        assert caption_match is not None

        # Some two-column LaTeX PDFs have ruled tables whose vector lines do not
        # form a detectable table on the full page. When an explicit caption is
        # present, use the matching horizontal rules to crop just that table's
        # column before applying pdfplumber's text strategy. This avoids treating
        # a neighboring prose column or plot grid as a table.
        ruled_lines = []
        next_caption_tops = [
            float(other["bbox"][1])
            for other in captions
            if other is not caption and float(other["bbox"][1]) > float(caption_box[1])
        ]
        next_caption_top = min(next_caption_tops, default=page_height)
        try:
            ruled_lines = caption_table_rules(
                getattr(page, "lines", []) or [],
                caption_bbox=caption_box,
                next_caption_top=next_caption_top,
                page_width=page_width,
            )
        except (TypeError, ValueError, AttributeError):
            ruled_lines = []

        ruled_candidates: list[Any] = []
        if len(ruled_lines) >= 2:
            ruled_lines.sort()
            first_rule = ruled_lines[0][0]
            # Stop at a large vertical gap; unrelated later rules must not be
            # pulled into the captioned table crop.
            table_rules = [ruled_lines[0]]
            for rule in ruled_lines[1:]:
                if rule[0] - table_rules[-1][0] > 260:
                    break
                table_rules.append(rule)
            left = min(rule[1] for rule in table_rules)
            right = max(rule[2] for rule in table_rules)
            try:
                ruled_crop = crop_page(
                    (
                        max(0.0, left - 3),
                        max(0.0, first_rule - 3),
                        min(page_width, right + 3),
                        min(page_height, table_rules[-1][0] + 4),
                    )
                )
                ruled_candidates = (
                    ruled_crop.find_tables(
                        table_settings={
                            "vertical_strategy": "text",
                            "horizontal_strategy": "text",
                            "text_x_tolerance": 3,
                            "text_y_tolerance": 3,
                            "snap_tolerance": 3,
                            "join_tolerance": 3,
                        }
                    )
                    or []
                )
            except Exception:
                ruled_candidates = []

        candidate_sources = [(table, True) for table in ruled_candidates]
        body_candidates = [
            line
            for line in lines
            if float(line["bbox"][1]) >= caption_bottom
            and float(line["bbox"][1]) - caption_bottom <= 120
            and float(line["bbox"][0]) >= caption_x + 20
            and float(line["bbox"][2]) - float(line["bbox"][0]) < page_width * 0.9
        ]
        if body_candidates and not ruled_candidates:
            body_start = min(body_candidates, key=lambda line: float(line["bbox"][1]))
            body_top = float(body_start["bbox"][1])
            following_prose = [
                line
                for line in lines
                if float(line["bbox"][1]) > body_top + 24
                and float(line["bbox"][0]) <= caption_x + 12
                and float(line["bbox"][2]) - float(line["bbox"][0]) >= page_width * 0.5
            ]
            body_bottom = (
                min(float(line["bbox"][1]) for line in following_prose) - 6
                if following_prose
                else page_height - 30
            )
            if body_bottom > body_top + 18:
                try:
                    cropped = crop_page(
                        (max(0.0, caption_x), max(0.0, body_top - 15), page_width, body_bottom)
                    )
                    text_candidates = (
                        cropped.find_tables(
                            table_settings={
                                "vertical_strategy": "text",
                                "horizontal_strategy": "text",
                                "text_x_tolerance": 3,
                                "text_y_tolerance": 3,
                                "snap_tolerance": 3,
                                "join_tolerance": 3,
                            }
                        )
                        or []
                    )
                    candidate_sources.extend((table, False) for table in text_candidates)
                except Exception:
                    pass

        for table, _from_ruled_crop in candidate_sources:
            box = _rounded_bbox(table.bbox) if getattr(table, "bbox", None) else None
            if box is None or any(
                _inside(box, old) and _inside(old, box) for old in existing_boxes
            ):
                continue
            try:
                extracted = _extract_table_rows(table)
            except Exception:
                continue
            normalized_rows = [
                [str(cell or "").strip().replace("\n", " ") for cell in row] for row in extracted
            ]
            if not _table_candidate_is_structured(normalized_rows):
                continue
            nonempty = [
                (source_index, row) for source_index, row in enumerate(normalized_rows) if any(row)
            ]
            width = max(len(row) for _, row in nonempty)
            normalized = [row + [""] * (width - len(row)) for _, row in nonempty]
            records.append(
                {
                    "table_index": len(existing_boxes) + len(records) + 1,
                    "caption_number": caption_match.group("number"),
                    "table": table,
                    "normalized_rows": normalized,
                    "source_row_indexes": [index for index, _ in nonempty],
                    "width": width,
                    "expected_ruled_bbox": (
                        [left, first_rule, right, table_rules[-1][0]] if _from_ruled_crop else None
                    ),
                    "header_bottom": table_rules[1][0] if _from_ruled_crop else None,
                }
            )
            existing_boxes.append(box)
            break
    return records


def _inside(box: list[float], outer: list[float]) -> bool:
    x0, top, x1, bottom = box
    ox0, otop, ox1, obottom = outer
    center_x = (x0 + x1) / 2
    center_y = (top + bottom) / 2
    return ox0 <= center_x <= ox1 and otop <= center_y <= obottom


def _fully_inside(box: list[float], outer: list[float], *, tolerance: float = 1.0) -> bool:
    """True when a box lies entirely within another, ignoring sub-point rounding."""
    return (
        outer[0] - tolerance <= box[0]
        and outer[1] - tolerance <= box[1]
        and box[2] <= outer[2] + tolerance
        and box[3] <= outer[3] + tolerance
    )


def _table_covers_ruled_bbox(
    table_bbox: list[float], expected_bbox: list[float], *, tolerance: float = 18.0
) -> bool:
    """Reject a text-strategy table that truncates a captioned ruled region."""
    x0, top, x1, bottom = table_bbox
    expected_x0, expected_top, expected_x1, expected_bottom = expected_bbox
    return (
        x0 <= expected_x0 + tolerance
        and x1 >= expected_x1 - tolerance
        and top <= expected_top + tolerance
        and bottom >= expected_bottom - tolerance
    )


def _visual_table_lines(
    words: list[dict[str, Any]], bbox: list[float], *, y_tolerance: float = 4.5
) -> list[list[str]]:
    """Keep text from an unreliable table as ordered visual lines, never fake columns."""
    x0, top, x1, bottom = bbox
    in_region = [
        word
        for word in words
        if x0 <= (float(word["x0"]) + float(word["x1"])) / 2 <= x1
        and top <= (float(word["top"]) + float(word["bottom"])) / 2 <= bottom
        and str(word["text"]).strip()
    ]
    visual_lines = _word_lines(in_region, x1)
    clusters: list[list[dict[str, Any]]] = []
    for line in visual_lines:
        word_top = float(line["bbox"][1])
        if clusters:
            prior_top = min(float(item["bbox"][1]) for item in clusters[-1])
            if abs(word_top - prior_top) <= min(y_tolerance, 3):
                clusters[-1].append(line)
                continue
        clusters.append([line])
    return [
        [
            " ".join(
                str(word["text"]).strip()
                for word in sorted(row, key=lambda item: float(item["bbox"][0]))
            )
        ]
        for row in clusters
    ]


def _vector_figure_boxes(page: Any, page_width: float, page_height: float) -> list[list[float]]:
    """Return explicit vector rectangles or adjacent panel groups for figures.

    This only locates vector artwork. It does not interpret plotted data or infer
    figure semantics, and callers must still associate a candidate with a caption.
    """
    try:
        rectangles = getattr(page, "rects", []) or []
    except Exception:
        return []
    candidates: list[list[float]] = []
    page_area = max(1.0, page_width * page_height)
    for rectangle in rectangles:
        try:
            box = _rounded_bbox([rectangle[key] for key in ("x0", "top", "x1", "bottom")])
        except (KeyError, TypeError, ValueError):
            continue
        width = box[2] - box[0]
        height = box[3] - box[1]
        if (
            width >= page_width * 0.12
            and height >= page_height * 0.08
            and width * height >= page_area * 0.012
        ):
            candidates.append(box)
    # Prefer each panel's outer border over nested axes or plot boxes.
    candidates.sort(
        key=lambda box: ((box[2] - box[0]) * (box[3] - box[1]), box[3] - box[1]),
        reverse=True,
    )
    enclosing = [
        box
        for box in candidates
        if not any(
            box != other
            and other[0] <= box[0]
            and other[1] <= box[1]
            and box[2] <= other[2]
            and box[3] <= other[3]
            for other in candidates
        )
    ]

    # Multi-panel figures often have no single enclosing rectangle. Group only
    # panel-sized rectangles that touch in one dimension while substantially
    # overlapping in the other, then return their union as a geometric region.
    horizontal_gap_limit = max(18.0, page_width * 0.05)
    vertical_gap_limit = max(18.0, page_height * 0.03)

    def adjacent(first: list[float], second: list[float]) -> bool:
        horizontal_overlap = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
        vertical_overlap = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
        first_width = first[2] - first[0]
        second_width = second[2] - second[0]
        first_height = first[3] - first[1]
        second_height = second[3] - second[1]
        horizontal_gap = max(0.0, max(first[0], second[0]) - min(first[2], second[2]))
        vertical_gap = max(0.0, max(first[1], second[1]) - min(first[3], second[3]))
        same_row = (
            vertical_overlap >= 0.5 * min(first_height, second_height)
            and horizontal_gap <= horizontal_gap_limit
        )
        same_column = (
            horizontal_overlap >= 0.5 * min(first_width, second_width)
            and vertical_gap <= vertical_gap_limit
        )
        return same_row or same_column

    remaining = list(enclosing)
    regions: list[list[float]] = []
    while remaining:
        component = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            for candidate in remaining[:]:
                if any(adjacent(candidate, member) for member in component):
                    component.append(candidate)
                    remaining.remove(candidate)
                    changed = True
        regions.append(
            [
                max(
                    0.0,
                    min(box[0] for box in component) - _VECTOR_FIGURE_HORIZONTAL_PADDING,
                ),
                max(0.0, min(box[1] for box in component) - 12.0),
                min(
                    page_width,
                    max(box[2] for box in component) + _VECTOR_FIGURE_HORIZONTAL_PADDING,
                ),
                max(box[3] for box in component),
            ]
        )
    return regions


def _table_header_index(rows: list[list[str]]) -> int:
    """Choose the first early row with multiple populated cells as the header."""
    for index, row in enumerate(rows[:6]):
        if sum(bool(cell.strip()) for cell in row) >= 2:
            return index
    return 0


def _table_column_groups(
    rows: list[list[str]], *, merge_continuations: bool = True
) -> list[list[int]]:
    """Merge blank header slots that split one logical column in text tables."""
    width = max((len(row) for row in rows), default=0)
    if width == 0:
        return []
    header_index = _table_header_index(rows)
    header = rows[header_index] + [""] * (width - len(rows[header_index]))
    groups: list[list[int]] = []
    for column in range(width):
        if (
            merge_continuations
            and not header[column].strip()
            and groups
            and column + 1 < width
            and header[column - 1].strip()
            and any(value.strip() for value in header[column + 1 :])
        ):
            groups[-1].append(column)
        else:
            groups.append([column])
    return groups


def _normalize_scientific_table_header(rows: list[dict[str, Any]]) -> None:
    """Reattach common PDF-extracted delta/subscript fragments in table headers."""
    text_rows = [[cell["text"] for cell in row["cells"]] for row in rows]
    if not text_rows:
        return
    header_index = _table_header_index(text_rows)
    if header_index > 0:
        previous = rows[header_index - 1]["cells"]
        current = rows[header_index]["cells"]
        for column, cell in enumerate(current):
            label = cell["text"]
            if (
                column < len(previous)
                and previous[column]["text"].strip() == "V"
                and re.match(r"^[∆Δ]\s+vs\.", label)
                and label.rstrip().endswith("strict")
            ):
                cell["text"] = re.sub(
                    r"^([∆Δ])\s+vs\.(.*)\s+strict$",
                    r"\1V_strict vs.\2",
                    label,
                )
                previous[column]["text"] = ""

    for row in rows[: min(len(rows), 6)]:
        for cell in row["cells"]:
            cell["text"] = re.sub(r"\bV\s*\(\s*%\s*\)\s+strict\b", "V_strict (%)", cell["text"])


def _drop_empty_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exclude rows emptied by header repairs while preserving physical row indexes."""
    return [
        row
        for row in rows
        if any(str(cell.get("text", "")).strip() for cell in row.get("cells", []))
    ]


def _normalize_subscript_text(text: str) -> str:
    """Restore simple scientific subscripts split onto a separate extracted line."""
    flattened = re.sub(r"\s+", " ", text).strip()
    flattened = re.sub(
        r"\(\s*([fD])\s*,\s*([fD])\s*,\s*([fD])\s*\)\s*([pt])\s+([pt])\s+([pt])",
        r"(\1_\4, \2_\5, \3_\6)",
        flattened,
    )
    return re.sub(
        r"\bIVIM\s*\(\s*f\s*_?\s*p\s*,\s*D\s*_?\s*t\s*,\s*D\s*_?\s*p\s*\)",
        "IVIM (f_p, D_t, D_p)",
        flattened,
    )


def _row_box(cells: Sequence[Mapping[str, Any]]) -> list[float] | None:
    """Union box of the cells of one table row."""
    boxes = [cell["bbox"] for cell in cells if cell.get("bbox")]
    if not boxes:
        return None
    return [
        min(float(box[0]) for box in boxes),
        min(float(box[1]) for box in boxes),
        max(float(box[2]) for box in boxes),
        max(float(box[3]) for box in boxes),
    ]


def _cell_center_x(cell: Mapping[str, Any]) -> float:
    box = cell.get("bbox")
    if not box:
        return float("inf")
    return (float(box[0]) + float(box[2])) / 2


def _reattach_grid_dropped_words(
    rows: list[dict[str, Any]],
    positioned_words: Sequence[Mapping[str, Any]],
    table_bbox: Sequence[float] | None = None,
) -> int:
    """Re-attach words inside the table that pdfplumber's extraction dropped entirely.

    Inferred column edges can fall outside a heading's last glyph, so
    ``Table.extract`` silently returns nothing for it (a trailing ``UMA`` is a real
    example). Two references are used, because one does not cover both failure shapes:

    * Multi-character words are checked against the text of the **whole table**. A word
      that already sits in a neighbouring row is merely misplaced, and copying it again
      would duplicate header text. A per-cell presence test was tried and rejected: when a
      header band sits below its glyphs, the word's nearest cell is the empty one it does
      not belong to, so the text is appended a second time.
    * Single glyphs are checked against the character budget of the one cell they belong
      to. An identical character almost always occurs elsewhere in the table (a subscript
      ``v``, the ``p`` of ``max_k p_k``), which would mask the loss.

    Known limit: a multi-character unit fragment that is cut off by column lines *and*
    happens to occur elsewhere in the table as a substring is still not recovered (one
    ``s`` in ``2610.06874`` p14). Existing cell text is never rewritten and nothing is
    inferred from paper-specific vocabulary.
    """
    if not rows or not positioned_words:
        return 0
    row_boxes = [_row_box(row.get("cells") or []) for row in rows]
    known = [box for box in row_boxes if box]
    if not known:
        return 0
    left = min(box[0] for box in known)
    top = min(box[1] for box in known)
    right = max(box[2] for box in known)
    bottom = max(box[3] for box in known)
    if table_bbox:
        left = min(left, float(table_bbox[0]))
        top = min(top, float(table_bbox[1]))
        right = max(right, float(table_bbox[2]))
        bottom = max(bottom, float(table_bbox[3]))
    present = _compact_text(
        " ".join(str(cell.get("text", "")) for row in rows for cell in row.get("cells") or [])
    )
    budgets: dict[tuple[int, int], Counter[str]] = {}

    def cell_budget(row_index: int, cell_index: int) -> Counter[str]:
        key = (row_index, cell_index)
        if key not in budgets:
            budgets[key] = Counter(
                _compact_text(str(rows[row_index]["cells"][cell_index].get("text", "")))
            )
        return budgets[key]

    def locate(center_x: float, center_y: float) -> tuple[int, int]:
        for row_index, row in enumerate(rows):
            for cell_index, cell in enumerate(row.get("cells") or []):
                box = cell.get("bbox")
                if not box:
                    continue
                if box[0] <= center_x <= box[2] and box[1] - 0.5 <= center_y <= box[3] + 0.5:
                    return row_index, cell_index
        row_index = min(
            range(len(rows)),
            key=lambda index: (
                abs(center_y - (row_boxes[index][1] + row_boxes[index][3]) / 2)
                if row_boxes[index]
                else float("inf")
            ),
        )
        cells = rows[row_index]["cells"]
        cell_index = min(
            range(len(cells)), key=lambda index: abs(center_x - _cell_center_x(cells[index]))
        )
        return row_index, cell_index

    ordered = sorted(
        (
            word
            for word in positioned_words
            if str(word.get("text", "")).strip()
            and left - 1.0 <= (float(word["x0"]) + float(word["x1"])) / 2 <= right + 1.0
            and top - 0.5 <= (float(word["top"]) + float(word["bottom"])) / 2 <= bottom + 0.5
        ),
        key=lambda word: (float(word["top"]), float(word["x0"])),
    )
    added = 0
    for word in ordered:
        text = str(word.get("text", "")).strip()
        token = _compact_text(text)
        if not token:
            continue
        center_x = (float(word["x0"]) + float(word["x1"])) / 2
        center_y = (float(word["top"]) + float(word["bottom"])) / 2
        row_index, cell_index = locate(center_x, center_y)
        if len(token) == 1:
            # A single glyph is judged against the target cell's own character budget.
            # An identical character elsewhere in the table would otherwise mask the loss.
            remaining = cell_budget(row_index, cell_index)
            if remaining[token] > 0:
                remaining[token] -= 1
                continue
        elif token in present:
            # A multi-character word that the table already records is misplaced rather
            # than lost; appending it again would duplicate header text.
            continue
        cells = rows[row_index]["cells"]
        existing = str(cells[cell_index].get("text", "")).strip()
        cells[cell_index]["text"] = _normalize_subscript_text(f"{existing} {text}".strip())
        present += token
        # The cell budget is deliberately not recomputed: the characters just appended are
        # accounted for by the word that carried them, so re-reading the cell text would
        # credit them again and mask a following identical glyph.
        added += 1
    return added


def _is_continuation_neighbour(
    cell: Mapping[str, Any], neighbour: Mapping[str, Any], column: int
) -> bool:
    """Decide whether a single-cell row continues the given neighbouring row."""
    cells = neighbour.get("cells") or []
    if column >= len(cells) or str(cells[column].get("text", "")).strip():
        return False
    if sum(bool(str(item.get("text", "")).strip()) for item in cells) < 2:
        return False
    cell_box = cell.get("bbox")
    other_box = cells[column].get("bbox")
    if not cell_box or not other_box:
        return True
    cell_width = float(cell_box[2]) - float(cell_box[0])
    other_width = float(other_box[2]) - float(other_box[0])
    # A spanning cell is never a wrapped continuation of a normal column.
    if cell_width > 1.6 * max(1e-6, other_width):
        return False
    height = max(
        float(cell_box[3]) - float(cell_box[1]), float(other_box[3]) - float(other_box[1]), 1.0
    )
    gap = abs(
        (float(cell_box[1]) + float(cell_box[3])) / 2
        - (float(other_box[1]) + float(other_box[3])) / 2
    )
    return gap <= max(8.0, 1.8 * height)


def _merge_continuation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join a single-cell row to the row whose wrapped cell it belongs to.

    pdfplumber's row boundaries can fall between the two visual lines of a
    wrapped cell. That continuation then surfaces as its own row holding one
    value while the owning row has an empty slot in the same column. The owning
    row is the only adjacent row with that slot empty, and the shared column must
    keep its width and vertical spacing, so standalone spanning rows survive.
    """
    if len(rows) < 3:
        return rows
    merged = [
        {"row_index": row["row_index"], "cells": [dict(cell) for cell in row["cells"]]}
        for row in rows
    ]
    keep = [True] * len(merged)
    for index, row in enumerate(rows):
        populated = [
            column for column, cell in enumerate(row["cells"]) if str(cell.get("text", "")).strip()
        ]
        if len(populated) != 1:
            continue
        column = populated[0]
        cell = row["cells"][column]
        previous = index - 1 if index else None
        following = index + 1 if index + 1 < len(rows) else None
        target = None
        if previous is not None and _is_continuation_neighbour(cell, rows[previous], column):
            target = previous
        elif following is not None and _is_continuation_neighbour(cell, rows[following], column):
            target = following
        if target is None or not keep[target]:
            continue
        existing = str(merged[target]["cells"][column].get("text", "")).strip()
        merged[target]["cells"][column]["text"] = _normalize_subscript_text(
            f"{existing} {cell['text']}".strip()
        )
        keep[index] = False
    return [row for index, row in enumerate(merged) if keep[index]]


def _table_rows(
    table: Any,
    extracted: list[list[Any]],
    source_row_indexes: list[int] | None = None,
    *,
    page: Any | None = None,
    column_groups: list[list[int]] | None = None,
    positioned_words: list[dict[str, Any]] | None = None,
    horizontal_bounds: Sequence[float] | None = None,
) -> list[dict[str, Any]]:
    table_rows = getattr(table, "rows", None) or []
    output: list[dict[str, Any]] = []
    source_row_indexes = source_row_indexes or list(range(len(extracted)))
    for compact_index, row in enumerate(extracted):
        source_index = source_row_indexes[compact_index]
        row_cells = (
            getattr(table_rows[source_index], "cells", []) if source_index < len(table_rows) else []
        )
        groups = column_groups or [[index] for index in range(len(row))]
        cells: list[dict[str, Any]] = []
        for group in groups:
            fragments = [str(row[index] or "").strip() for index in group if index < len(row)]
            value = " ".join(fragment for fragment in fragments if fragment)
            boxes = [
                row_cells[index] for index in group if index < len(row_cells) and row_cells[index]
            ]
            box = None
            if boxes:
                try:
                    box = [
                        min(float(item[0]) for item in boxes),
                        min(float(item[1]) for item in boxes),
                        max(float(item[2]) for item in boxes),
                        max(float(item[3]) for item in boxes),
                    ]
                except (TypeError, ValueError):
                    box = None
            if box is not None and positioned_words:
                x0, top, x1, bottom = map(float, box)
                cell_words = [
                    word
                    for word in positioned_words
                    if x0 <= (float(word["x0"]) + float(word["x1"])) / 2 <= x1
                    and top <= (float(word["top"]) + float(word["bottom"])) / 2 <= bottom
                    and "_" in str(word["text"])
                ]
                for word in cell_words:
                    match = re.search(r"(?<!\w)([^\W_]+)_([^\W_]+)(?!\w)", str(word["text"]))
                    if match:
                        separated = (
                            rf"\b{re.escape(match.group(1))}\s+{re.escape(match.group(2))}\b"
                        )
                        value = re.sub(separated, str(word["text"]), value)
            if len(group) > 1 and box is not None and page is not None:
                try:
                    crop_box = (box[0], box[1], max(box[0], box[2] - 0.5), box[3])
                    extracted_text = page.crop(crop_box).extract_text(
                        x_tolerance=_TEXT_X_TOLERANCE, y_tolerance=3
                    )
                    if extracted_text:
                        value = extracted_text.replace("\n", " ")
                except (TypeError, ValueError, AttributeError):
                    pass
            cell: dict[str, Any] = {"text": _normalize_subscript_text(value)}
            if box is not None:
                cell["bbox"] = _rounded_bbox(box)
            cells.append(cell)
        output.append({"row_index": source_index, "cells": cells})
    if positioned_words:
        _reattach_grid_dropped_words(output, positioned_words, horizontal_bounds)
    return output


def _column_order(
    lines: list[dict[str, Any]], page_width: float
) -> tuple[list[dict[str, Any]], bool, float | None]:
    """Detect a strong two-column layout and return column-major reading order.

    The heuristic only activates when both x-start clusters contain multiple lines,
    a wide gutter separates them, and their vertical spans overlap. Borderline pages
    retain the extractor's top-to-bottom order and receive an ambiguity warning.
    """
    if len(lines) < 4:
        return [dict(line, column=0) for line in lines], False, None
    starts = sorted(
        ((float(line["bbox"][0]), line) for line in lines),
        key=lambda item: item[0],
    )
    gap_candidates = [
        (starts[index + 1][0] - starts[index][0], index)
        for index in range(len(starts) - 1)
        if starts[index + 1][0] - starts[index][0] >= page_width * 0.12
        and page_width * 0.20 <= (starts[index + 1][0] + starts[index][0]) / 2 <= page_width * 0.65
    ]
    if not gap_candidates:
        return [dict(line, column=0) for line in lines], False, None
    # Prefer a balanced split over the single largest gap: centered figure labels
    # and subsection headings can create larger gaps inside one true column.
    _, split_index = max(
        gap_candidates,
        key=lambda item: (min(item[1] + 1, len(starts) - item[1] - 1), item[0]),
    )
    split_x = (starts[split_index][0] + starts[split_index + 1][0]) / 2
    left = [line for line in lines if float(line["bbox"][0]) < split_x]
    right = [line for line in lines if float(line["bbox"][0]) >= split_x]
    if min(len(left), len(right)) < 3:
        return [dict(line, column=0) for line in lines], False, None
    # A large x-start gap can also come from centered page numbers, equations, chart
    # labels, or a one-column paragraph. Confirm that both sides contain several
    # genuinely column-width lines before declaring a two-column layout.
    max_column_line_width = page_width * 0.68
    left_column_lines = [
        line
        for line in left
        if float(line["bbox"][2]) - float(line["bbox"][0]) <= max_column_line_width
        and not str(line["text"]).strip().isdigit()
    ]
    right_column_lines = [
        line
        for line in right
        if float(line["bbox"][2]) - float(line["bbox"][0]) <= max_column_line_width
        and not str(line["text"]).strip().isdigit()
    ]
    if min(len(left_column_lines), len(right_column_lines)) < 3:
        return [dict(line, column=0) for line in lines], False, None
    for candidates in (left_column_lines, right_column_lines):
        starts = [float(line["bbox"][0]) for line in candidates]
        center_start = sorted(starts)[len(starts) // 2]
        core_lines = [
            line
            for line in candidates
            if abs(float(line["bbox"][0]) - center_start) <= page_width * 0.10
        ]
        if len(core_lines) < 3:
            return [dict(line, column=0) for line in lines], False, None
        if sum(len(str(line["text"])) for line in core_lines) < 50:
            return [dict(line, column=0) for line in lines], False, None
    wide = [line for line in lines if line["bbox"][2] - line["bbox"][0] > page_width * 0.72]
    left_content = [line for line in left if line not in wide]
    right_content = [line for line in right if line not in wide]
    if min(len(left_content), len(right_content)) < 3:
        return [dict(line, column=0) for line in lines], False, None
    left_top = min(float(line["bbox"][1]) for line in left_content)
    left_bottom = max(float(line["bbox"][3]) for line in left_content)
    right_top = min(float(line["bbox"][1]) for line in right_content)
    right_bottom = max(float(line["bbox"][3]) for line in right_content)
    overlap = max(0.0, min(left_bottom, right_bottom) - max(left_top, right_top))
    shorter_span = max(1.0, min(left_bottom - left_top, right_bottom - right_top))
    if overlap / shorter_span < 0.4:
        return [dict(line, column=0) for line in lines], False, None

    column_top = min(left_top, right_top)
    column_bottom = max(left_bottom, right_bottom)
    wide_overlapping_columns = [
        line
        for line in wide
        if float(line["bbox"][3]) > column_top and float(line["bbox"][1]) < column_bottom
    ]
    if wide_overlapping_columns:
        # A spanning line makes global reading order uncertain. Preserve the
        # pre-caption diagram block, then keep post-caption body text column-major
        # so alternating y positions cannot fragment or join left/right prose.
        wide_caption_lines = [line for line in wide if _CAPTION.match(str(line["text"]).strip())]
        caption_top = min(
            (float(line["bbox"][1]) for line in wide_caption_lines), default=float("inf")
        )
        before_caption = (
            [line for line in lines if float(line["bbox"][3]) <= caption_top]
            if wide_caption_lines
            else []
        )
        # The first line can span both columns while the final caption line is
        # short. Collect the complete aligned visual block before assigning
        # columns, otherwise its tail is reordered as ordinary left-column prose.
        caption_block: list[dict[str, Any]] = []
        visual_lines = sorted(lines, key=lambda item: (item["bbox"][1], item["bbox"][0]))
        for starter in sorted(wide_caption_lines, key=lambda item: item["bbox"][1]):
            if starter in caption_block:
                continue
            caption_block.append(starter)
            previous = starter
            for following in visual_lines:
                if float(following["bbox"][1]) <= float(previous["bbox"][1]):
                    continue
                gap = float(following["bbox"][1]) - float(previous["bbox"][3])
                if gap > 6:
                    break
                if (
                    gap < -1
                    or abs(float(following["bbox"][0]) - float(starter["bbox"][0])) > 14
                    or float(following["bbox"][3]) - float(starter["bbox"][1]) > 170
                    or _CAPTION.match(str(following["text"]).strip())
                    or _TABLE_CAPTION.match(str(following["text"]).strip())
                    or _heading_level(str(following["text"])) is not None
                ):
                    continue
                caption_block.append(following)
                previous = following
        caption_ids = {id(line) for line in caption_block}
        before_ids = {id(line) for line in before_caption}
        after_caption = [line for line in lines if id(line) not in before_ids | caption_ids]
        after_left = [
            line for line in after_caption if line not in wide and float(line["bbox"][0]) < split_x
        ]
        after_right = [
            line for line in after_caption if line not in wide and float(line["bbox"][0]) >= split_x
        ]
        after_wide = [line for line in wide if id(line) not in caption_ids]
        before_caption.sort(key=lambda line: (line["bbox"][1], line["bbox"][0]))
        caption_block.sort(key=lambda line: (line["bbox"][1], line["bbox"][0]))
        after_left.sort(key=lambda line: (line["bbox"][1], line["bbox"][0]))
        after_right.sort(key=lambda line: (line["bbox"][1], line["bbox"][0]))
        after_wide.sort(key=lambda line: (line["bbox"][1], line["bbox"][0]))
        labelled = [
            dict(line, column=0 if float(line["bbox"][0]) < split_x else 1)
            for line in before_caption
        ]
        labelled.extend(dict(line, column=2) for line in caption_block)
        labelled.extend(dict(line, column=0) for line in after_left)
        labelled.extend(dict(line, column=1) for line in after_right)
        labelled.extend(dict(line, column=2) for line in after_wide)
        return labelled, True, split_x
    left_content.sort(key=lambda line: (line["bbox"][1], line["bbox"][0]))
    right_content.sort(key=lambda line: (line["bbox"][1], line["bbox"][0]))
    wide.sort(key=lambda line: (line["bbox"][1], line["bbox"][0]))
    wide_before = [line for line in wide if float(line["bbox"][3]) <= column_top]
    wide_after = [line for line in wide if float(line["bbox"][1]) >= column_bottom]
    ordered = [dict(line, column=0) for line in wide_before]
    ordered.extend(dict(line, column=0) for line in left_content)
    ordered.extend(dict(line, column=1) for line in right_content)
    ordered.extend(dict(line, column=1) for line in wide_after)
    return ordered, False, split_x


def _compact_text(value: str) -> str:
    return re.sub(r"\W+", "", value, flags=re.UNICODE).casefold()


def parse_pdf(path: Path) -> dict[str, Any]:
    """Read a PDF once, then parse that immutable byte snapshot."""
    return parse_pdf_bytes(read_pdf_bytes(path))


def read_pdf_bytes(path: Path) -> bytes:
    """Read a bounded source snapshot that can be hashed and parsed without reopening."""
    if path.suffix.lower() != ".pdf":
        raise ValueError("PDF input must use the .pdf extension")
    with path.open("rb") as source:
        pdf_bytes = source.read(MAX_PDF_BYTES + 1)
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds the 40 MB limit")
    return pdf_bytes


def parse_pdf_bytes(pdf_bytes: bytes) -> dict[str, Any]:
    """Parse exactly the supplied bytes, allowing callers to hash the same snapshot."""
    if not isinstance(pdf_bytes, bytes):
        raise ValueError("PDF input must be bytes")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds the 40 MB limit")
    # A page may still produce useful elements when one extractor fails. Such cases
    # are surfaced in the top-level ``warnings`` array and, where possible, on the
    # affected element. This parser does not OCR scanned pages or describe images.
    try:
        import pdfplumber
    except ImportError as error:
        raise ValueError("PDF import requires the optional pdfplumber dependency") from error

    elements: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    image_regions = 0
    table_regions = 0
    figure_captions = 0
    total_chars = 0
    page_count = 0
    order_index = 0
    column_splits: dict[int, float] = {}
    relation_links: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    section_stack: list[str] = []

    def add_element(
        *,
        page_number: int,
        page_width: float,
        page_height: float,
        element_type: str,
        text: str,
        section_path: list[str],
        bbox: list[float],
        structured: dict[str, Any] | None = None,
        element_warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        nonlocal order_index
        value = {
            "element_id": _stable_element_id(page_number, element_type, text, bbox),
            "order_index": order_index,
            "page_number": page_number,
            "page_width": round(float(page_width), 2),
            "page_height": round(float(page_height), 2),
            "bbox": bbox,
            "element_type": element_type,
            "section_path": list(section_path),
            "text": text,
            "structured": structured or {},
            "warnings": list(element_warnings or []),
        }
        order_index += 1
        elements.append(value)
        return value

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if not pdf.pages or len(pdf.pages) > MAX_PDF_PAGES:
            raise ValueError("PDF must contain between 1 and 500 pages")
        page_count = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages, start=1):
            page_width = float(page.width)
            page_height = float(page.height)
            page_start_section = section_stack.copy()
            heading_records: list[tuple[float, int, list[str]]] = []
            page_warning_items: list[str] = []
            try:
                tables = page.find_tables() or []
            except Exception as error:  # partial extraction is observable by design
                tables = []
                page_warning_items.append(f"table_extraction_failed:{type(error).__name__}")
            table_boxes: list[list[float]] = []
            table_records: list[dict[str, Any]] = []
            table_text_fingerprints: set[str] = set()
            rejected_table_candidates = False
            for table_index, table in enumerate(tables, start=1):
                try:
                    raw_rows = _extract_table_rows(table)
                except Exception as error:
                    page_warning_items.append(
                        f"table_cells_extraction_failed:{type(error).__name__}"
                    )
                    continue
                normalized_rows = [
                    [str(cell or "").strip().replace("\n", " ") for cell in row] for row in raw_rows
                ]
                if not grid_has_text_support(raw_rows) or not _table_candidate_is_structured(
                    normalized_rows
                ):
                    rejected_table_candidates = True
                    continue
                nonempty = [
                    (source_index, row)
                    for source_index, row in enumerate(normalized_rows)
                    if any(row)
                ]
                if not nonempty:
                    continue
                width = max(len(row) for _, row in nonempty)
                normalized = [row + [""] * (width - len(row)) for _, row in nonempty]
                row_indexes = [source_index for source_index, _ in nonempty]
                for row in normalized:
                    fingerprint = _compact_text(" ".join(cell for cell in row if cell))
                    if fingerprint:
                        table_text_fingerprints.add(fingerprint)
                table_records.append(
                    {
                        "table_index": table_index,
                        "table": table,
                        "normalized_rows": normalized,
                        "source_row_indexes": row_indexes,
                        "width": width,
                    }
                )
            table_boxes = [
                _rounded_bbox(record["table"].bbox)
                for record in table_records
                if getattr(record["table"], "bbox", None)
            ]
            if rejected_table_candidates:
                page_warning_items.append("sparse_table_candidates_rejected")

            try:
                raw_words = _extract_positioned_words(page)
            except Exception as error:
                raw_words = []
                page_warning_items.append(f"word_extraction_failed:{type(error).__name__}")
            geometry_words = [
                word
                for word in raw_words
                if all(key in word for key in ("x0", "x1", "top", "bottom", "text"))
            ]
            if len(geometry_words) < len(raw_words):
                page_warning_items.append("word_geometry_unavailable")
            upright_words = [word for word in geometry_words if word.get("upright", True)]
            if len(upright_words) < len(geometry_words):
                page_warning_items.append("rotated_text_excluded")
            positioned_words = [
                word
                for word in upright_words
                if float(word["x0"]) >= 0
                and float(word["x1"]) <= page_width
                and float(word["top"]) >= 0
                and float(word["bottom"]) <= page_height
            ]
            if len(positioned_words) < len(upright_words):
                page_warning_items.append("out_of_page_text_excluded")
            if positioned_words:
                lines = _word_lines(positioned_words, page_width)
            else:
                try:
                    fallback_text = page.extract_text(layout=True) or ""
                except Exception as error:
                    fallback_text = ""
                    page_warning_items.append(
                        f"layout_text_extraction_failed:{type(error).__name__}"
                    )
                lines = []
                deduplicated_table_text = False
                for line_number, text in enumerate(fallback_text.splitlines()):
                    stripped = text.strip()
                    if stripped:
                        compact = _compact_text(stripped)
                        if compact and compact in table_text_fingerprints:
                            deduplicated_table_text = True
                            continue
                        # Without word positions, use page-level bounds and attach a warning.
                        lines.append(
                            {
                                "text": stripped,
                                "bbox": [0.0, 0.0, page_width, page_height],
                                "fallback_line": line_number,
                            }
                        )
                if lines:
                    page_warning_items.append("positioned_words_unavailable_page_bbox_used")
                if deduplicated_table_text:
                    page_warning_items.append("table_text_deduplicated_without_word_geometry")

            try:
                text_table_records = _captioned_text_tables(
                    page,
                    lines,
                    page_width,
                    page_height,
                    list(table_boxes),
                )
            except Exception as error:
                text_table_records = []
                page_warning_items.append(
                    f"captioned_table_extraction_failed:{type(error).__name__}"
                )
            for record in text_table_records:
                expected_ruled_bbox = record.get("expected_ruled_bbox")
                table_bbox = _rounded_bbox(record["table"].bbox)
                unreliable_header = bool(expected_ruled_bbox) and header_grid_cuts_text(
                    record["table"],
                    positioned_words,
                    chars=getattr(page, "chars", []) or [],
                    header_bottom=record.get("header_bottom") or table_bbox[1] + 25,
                )
                has_grid_rows = bool(getattr(record["table"], "rows", None))
                body_text_cut = bool(expected_ruled_bbox and has_grid_rows) and body_grid_cuts_text(
                    record["table"],
                    positioned_words,
                    body_start=record.get("header_bottom") or table_bbox[1] + 25,
                )
                if expected_ruled_bbox and (
                    unreliable_header
                    or not _table_covers_ruled_bbox(table_bbox, expected_ruled_bbox)
                    or body_text_cut
                ):
                    reason = (
                        "table_header_geometry_unreliable"
                        if unreliable_header
                        else "captioned_table_geometry_incomplete"
                        if not _table_covers_ruled_bbox(table_bbox, expected_ruled_bbox)
                        else "table_body_grid_cuts_text"
                    )
                    body_start = record.get("header_bottom") or table_bbox[1] + 25
                    if not body_text_cut:
                        record["table_index"] = len(table_records) + 1
                        record["bbox_override"] = list(expected_ruled_bbox)
                        warnings = list(record.get("warnings", []))
                        warnings.extend([reason, "table_body_grid_preserved_no_body_text_cut"])
                        record["warnings"] = list(dict.fromkeys(warnings))
                        if unreliable_header:
                            record["structure_status"] = (
                                "grid_body_columns_preserved_header_unreliable"
                            )
                            record["row_semantics"] = "grid_body_rows_header_uncertain"
                        else:
                            record["structure_status"] = "grid_columns_preserved_bbox_incomplete"
                            record["row_semantics"] = "pdfplumber_grid"
                        for row in record["normalized_rows"]:
                            fingerprint = _compact_text(" ".join(cell for cell in row if cell))
                            if fingerprint:
                                table_text_fingerprints.add(fingerprint)
                        table_records.append(record)
                        table_boxes.append(expected_ruled_bbox)
                        page_warning_items.append(reason)
                        continue

                    recovered = None
                    if unreliable_header:
                        recovered = reconstruct_gutter_rows(
                            positioned_words,
                            bbox=expected_ruled_bbox,
                            header_bottom=record.get("header_bottom") or table_bbox[1] + 25,
                            render_lines=lambda selected, width=page_width: _word_lines(
                                selected, width
                            ),
                        )
                    recovery_kind = "whitespace"
                    if recovered is None:
                        recovered = reconstruct_header_anchored_rows(
                            positioned_words,
                            bbox=expected_ruled_bbox,
                            header_bottom=body_start,
                            render_lines=lambda selected, width=page_width: _word_lines(
                                selected, width
                            ),
                        )
                        recovery_kind = "header_anchored"
                    if recovered is not None:
                        edges = recovered["column_edges"]
                        row_boxes = recovered["row_boxes"]
                        recovered_table = SimpleNamespace(
                            bbox=tuple(expected_ruled_bbox),
                            rows=[
                                SimpleNamespace(
                                    cells=[
                                        (edges[i], row_box[1], edges[i + 1], row_box[3])
                                        for i in range(len(edges) - 1)
                                    ]
                                )
                                for row_box in row_boxes
                            ],
                        )
                        table_records.append(
                            {
                                "table_index": len(table_records) + 1,
                                "caption_number": record.get("caption_number"),
                                "table": recovered_table,
                                "normalized_rows": recovered["rows"],
                                "source_row_indexes": list(range(len(recovered["rows"]))),
                                "width": len(edges) - 1,
                                "warnings": [
                                    (
                                        "table_header_geometry_reconstructed_from_whitespace"
                                        if recovery_kind == "whitespace"
                                        else "table_geometry_reconstructed_from_header_anchors"
                                    ),
                                    "table_rows_are_visual_lines",
                                ],
                                "structure_status": "geometry_inferred_visual_lines",
                                "row_semantics": recovered["row_semantics"],
                            }
                        )
                        table_boxes.append(expected_ruled_bbox)
                        continue
                    page_warning_items.append(reason)
                    visual_rows = _visual_table_lines(positioned_words, expected_ruled_bbox)
                    if visual_rows:
                        fallback_table = SimpleNamespace(bbox=tuple(expected_ruled_bbox), rows=[])
                        table_records.append(
                            {
                                "table_index": len(table_records) + 1,
                                "caption_number": record.get("caption_number"),
                                "table": fallback_table,
                                "normalized_rows": visual_rows,
                                "source_row_indexes": list(range(len(visual_rows))),
                                "width": 1,
                                "warnings": ["table_structure_unavailable_visual_lines_only"],
                                "structure_status": "visual_lines_only_unstructured",
                                "row_semantics": "visual_lines",
                            }
                        )
                        table_boxes.append(expected_ruled_bbox)
                        page_warning_items.append("table_structure_unavailable_visual_lines_only")
                    continue
                record["table_index"] = len(table_records) + 1
                for row in record["normalized_rows"]:
                    fingerprint = _compact_text(" ".join(cell for cell in row if cell))
                    if fingerprint:
                        table_text_fingerprints.add(fingerprint)
                table_records.append(record)
                if getattr(record["table"], "bbox", None):
                    table_boxes.append(_rounded_bbox(record["table"].bbox))
            table_regions += len(table_records)

            if positioned_words:
                lines = [
                    line
                    for line in lines
                    if not any(_inside(_rounded_bbox(line["bbox"]), box) for box in table_boxes)
                ]
            lines, layout_ambiguous, column_split = _column_order(lines, page_width)
            if column_split is not None:
                column_splits[page_number] = column_split
                if layout_ambiguous:
                    page_warning_items.append("multi_column_reading_order_ambiguous")
                else:
                    page_warning_items.append("two_column_layout_detected")
            elif layout_ambiguous:
                page_warning_items.append("multi_column_reading_order_ambiguous")
            column_sections = {
                0: page_start_section.copy(),
                1: page_start_section.copy(),
                2: page_start_section.copy(),
            }

            image_candidates: list[dict[str, Any]] = []
            vector_figure_boxes = _vector_figure_boxes(page, page_width, page_height)
            try:
                page_images = page.images or []
            except Exception as error:
                page_images = []
                page_warning_items.append(f"image_regions_unavailable:{type(error).__name__}")
            image_regions += len(page_images)
            for image in page_images:
                try:
                    box = _rounded_bbox([image[key] for key in ("x0", "top", "x1", "bottom")])
                except (KeyError, TypeError, ValueError):
                    page_warning_items.append("image_region_missing_bbox")
                    continue
                image_element = add_element(
                    page_number=page_number,
                    page_width=page_width,
                    page_height=page_height,
                    element_type="image_region",
                    text="",
                    section_path=section_stack.copy(),
                    bbox=box,
                    structured={"caption_relation": {"status": "unmatched", "confidence": 0.0}},
                )
                image_candidates.append(
                    {
                        "bbox": box,
                        "element": image_element,
                        # PDF image objects can be tiny texture/line fragments
                        # inside a vector figure. Keep them as located regions,
                        # but never treat a sliver as the whole caption target.
                        "matched": False,
                        "caption_matchable": (box[2] - box[0]) >= 8.0 and (box[3] - box[1]) >= 8.0,
                    }
                )

            body_lines: list[dict[str, Any]] = []
            body_bbox: list[float] | None = None
            body_section = section_stack.copy()

            def flush_body(
                active_section: list[str],
                local_page_number: int = page_number,
                local_page_width: float = page_width,
                local_page_height: float = page_height,
                has_positioned_words: bool = bool(positioned_words),
            ) -> None:
                nonlocal total_chars, body_bbox, body_lines, body_section
                text = "\n".join(line["text"] for line in body_lines).strip()
                if text and body_bbox:
                    element_warning = []
                    if not has_positioned_words:
                        element_warning.append("bbox_is_page_level_fallback")
                    add_element(
                        page_number=local_page_number,
                        page_width=local_page_width,
                        page_height=local_page_height,
                        element_type="paragraph",
                        text=text,
                        section_path=body_section,
                        bbox=_rounded_bbox(body_bbox),
                        element_warnings=element_warning,
                    )
                    total_chars += len(text)
                body_lines = []
                body_bbox = None
                body_section = active_section.copy()

            caption_lines: list[dict[str, Any]] = []
            active_caption: dict[str, Any] | None = None
            for line in lines:
                line_bbox = _rounded_bbox(line["bbox"])
                column = int(line.get("column", 0))
                active_section = (
                    column_sections[column] if column_split is not None else section_stack
                )
                text = line["text"].strip()
                if not text:
                    active_caption = None
                    flush_body(active_section)
                    continue
                if active_caption is not None:
                    previous_box = active_caption["last_line_bbox"]
                    caption_box = active_caption["bbox"]
                    line_gap = line_bbox[1] - previous_box[3]
                    same_column = active_caption["column"] == column
                    aligned = abs(line_bbox[0] - caption_box[0]) <= 14
                    if (
                        same_column
                        and aligned
                        and -1 <= line_gap <= 6
                        and line_bbox[3] - caption_box[1] <= 170
                        and active_caption["line_count"] < 18
                        and len(active_caption["text"]) + len(text) < 1_800
                        and not _CAPTION.match(text)
                        and not _TABLE_CAPTION.match(text)
                        and _heading_level(text) is None
                    ):
                        active_caption["text"] += "\n" + text
                        active_caption["bbox"] = [
                            min(caption_box[0], line_bbox[0]),
                            caption_box[1],
                            max(caption_box[2], line_bbox[2]),
                            max(caption_box[3], line_bbox[3]),
                        ]
                        active_caption["last_line_bbox"] = line_bbox
                        active_caption["line_count"] += 1
                        continue
                    active_caption = None
                heading = _heading_level(text)
                if heading is not None:
                    flush_body(active_section)
                    heading_text, level = heading
                    next_section = active_section[: max(level - 1, 0)]
                    next_section.append(heading_text[:140])
                    if column_split is not None:
                        column_sections[column] = next_section
                    else:
                        section_stack = next_section
                        column_sections[0] = next_section.copy()
                    heading_records.append((line_bbox[1], column, next_section.copy()))
                    add_element(
                        page_number=page_number,
                        page_width=page_width,
                        page_height=page_height,
                        element_type="heading",
                        text=heading_text,
                        section_path=next_section,
                        bbox=line_bbox,
                    )
                    total_chars += len(heading_text)
                    continue
                if _CAPTION.match(text):
                    flush_body(active_section)
                    active_caption = {
                        "text": text,
                        "bbox": line_bbox,
                        "last_line_bbox": line_bbox,
                        "line_count": 1,
                        "column": column,
                        "section_path": active_section.copy(),
                    }
                    caption_lines.append(active_caption)
                    continue

                # A visual line gap or a column jump begins a new paragraph.
                if body_lines:
                    previous = body_lines[-1]["bbox"]
                    vertical_gap = line_bbox[1] - previous[3]
                    horizontal_gap = max(previous[0] - line_bbox[2], line_bbox[0] - previous[2], 0)
                    horizontal_start_shift = abs(line_bbox[0] - previous[0])
                    column_changed = int(body_lines[-1].get("column", 0)) != column
                    if (
                        column_changed
                        or horizontal_start_shift > page_width * 0.25
                        or vertical_gap > 16
                        or horizontal_gap > max(72, page_width * 0.12)
                    ):
                        flush_body(active_section)
                if not body_lines:
                    body_section = active_section.copy()
                    body_bbox = list(line_bbox)
                else:
                    body_bbox = [
                        min(body_bbox[0], line_bbox[0]),
                        min(body_bbox[1], line_bbox[1]),
                        max(body_bbox[2], line_bbox[2]),
                        max(body_bbox[3], line_bbox[3]),
                    ]
                body_lines.append(line)
            final_section = column_sections[1] if column_split is not None else section_stack
            flush_body(final_section)

            def section_at(
                y: float,
                x: float,
                start_section: list[str] = page_start_section,
                local_headings: list[tuple[float, int, list[str]]] = heading_records,
                split_x: float | None = column_split,
            ) -> list[str]:
                selected = start_section.copy()
                target_column = 0 if split_x is None or x < split_x else 1
                for heading_y, heading_column, heading_section in local_headings:
                    if heading_y <= y and heading_column == target_column:
                        selected = heading_section.copy()
                return selected

            for element in elements:
                if (
                    element["page_number"] == page_number
                    and element["element_type"] == "image_region"
                ):
                    center_x = (element["bbox"][0] + element["bbox"][2]) / 2
                    element["section_path"] = section_at(element["bbox"][1], center_x)

            # Keep cell locations when pdfplumber exposes them.
            figure_boxes: list[list[float]] = [
                [float(value) for value in image["bbox"]]
                for image in image_candidates
                if image.get("bbox")
            ]
            figure_boxes.extend([float(value) for value in box] for box in vector_figure_boxes)
            for record in table_records:
                table_index = record["table_index"]
                table = record["table"]
                normalized = record["normalized_rows"]
                if "caption_number" not in record and getattr(table, "bbox", None):
                    # A figure's own text layer (axis labels, data-point values, tick
                    # numbers) can look like a grid. Without an explicit `Table N:`
                    # caption there is nothing that says it is a table, so a candidate
                    # lying wholly inside a figure region is rejected rather than
                    # emitted as a confident grid with a fabricated caption.
                    candidate_bbox = _rounded_bbox(table.bbox)
                    if any(
                        _fully_inside(candidate_bbox, box)
                        and (box[2] - box[0]) * (box[3] - box[1]) < 0.8 * page_width * page_height
                        for box in figure_boxes
                    ):
                        page_warning_items.append("table_inside_figure_region_rejected")
                        continue
                column_groups = _table_column_groups(
                    normalized, merge_continuations="caption_number" in record
                )
                rows = _table_rows(
                    table,
                    normalized,
                    record["source_row_indexes"],
                    page=page,
                    column_groups=column_groups,
                    positioned_words=positioned_words,
                    horizontal_bounds=(
                        record.get("bbox_override")
                        or record.get("expected_ruled_bbox")
                        or (list(table.bbox) if getattr(table, "bbox", None) else None)
                    ),
                )
                _normalize_scientific_table_header(rows)
                rows = _merge_continuation_rows(rows)
                rows = _drop_empty_table_rows(rows)
                normalized = [[cell["text"] for cell in row["cells"]] for row in rows]
                width = len(column_groups)
                header_index = _table_header_index(normalized)
                header = normalized[header_index] if normalized else []
                table_label = record.get("caption_number", table_index)
                rendered = [f"Table {table_label} (page {page_number})", " | ".join(header)]
                rendered.extend(
                    " | ".join(row)
                    for index, row in enumerate(normalized)
                    if index != header_index and any(cell.strip() for cell in row)
                )
                table_text = "\n".join(rendered)
                header_row_count = _table_header_row_count(normalized)
                table_bbox = (
                    record.get("bbox_override") or _rounded_bbox(table.bbox)
                    if getattr(table, "bbox", None)
                    else [0, 0, page_width, page_height]
                )
                table_warnings = (
                    []
                    if getattr(table, "bbox", None)
                    else ["table_bbox_unavailable_page_bbox_used"]
                )
                table_warnings.extend(record.get("warnings", []))
                table_warnings = list(dict.fromkeys(table_warnings))
                add_element(
                    page_number=page_number,
                    page_width=page_width,
                    page_height=page_height,
                    element_type="table",
                    text=table_text,
                    section_path=section_at(table_bbox[1], (table_bbox[0] + table_bbox[2]) / 2),
                    bbox=table_bbox,
                    structured={
                        "rows": rows,
                        "header": rows[header_index]["cells"] if rows else [],
                        "row_count": len(rows),
                        "column_count": width,
                        "header_row_count": header_row_count,
                        "structure_status": record.get("structure_status", "pdfplumber_grid"),
                        "row_semantics": record.get(
                            "row_semantics", record.get("structure_status", "pdfplumber_grid")
                        ),
                    },
                    element_warnings=table_warnings,
                )
                total_chars += len(table_text)

            for caption in caption_lines:
                cap_box = caption["bbox"]
                candidates: list[tuple[float, dict[str, Any]]] = []
                for image in image_candidates:
                    if image["matched"] or not image["caption_matchable"]:
                        continue
                    img_box = image["bbox"]
                    x_overlap = max(0.0, min(cap_box[2], img_box[2]) - max(cap_box[0], img_box[0]))
                    min_width = max(1.0, min(cap_box[2] - cap_box[0], img_box[2] - img_box[0]))
                    overlap_ratio = x_overlap / min_width
                    vertical_delta = cap_box[1] - img_box[3]
                    if overlap_ratio < 0.10 or abs(vertical_delta) > 160:
                        continue
                    vertical_score = abs(vertical_delta) / 160
                    above_penalty = 0.20 if vertical_delta < 0 else 0.0
                    score = 0.65 * vertical_score + 0.35 * (1 - overlap_ratio) + above_penalty
                    candidates.append((score, image))
                if not candidates:
                    vector_candidates: list[tuple[float, list[float]]] = []
                    for box in vector_figure_boxes:
                        x_overlap = max(0.0, min(cap_box[2], box[2]) - max(cap_box[0], box[0]))
                        min_width = max(1.0, min(cap_box[2] - cap_box[0], box[2] - box[0]))
                        overlap_ratio = x_overlap / min_width
                        vertical_delta = cap_box[1] - box[3]
                        if overlap_ratio < 0.10 or abs(vertical_delta) > 160:
                            continue
                        vertical_score = abs(vertical_delta) / 160
                        above_penalty = 0.20 if vertical_delta < 0 else 0.0
                        score = 0.65 * vertical_score + 0.35 * (1 - overlap_ratio) + above_penalty
                        vector_candidates.append((score, box))
                    vector_candidates.sort(key=lambda item: item[0])
                    if (
                        vector_candidates
                        and vector_candidates[0][0] < 0.75
                        and (
                            len(vector_candidates) == 1
                            or vector_candidates[1][0] - vector_candidates[0][0] > 0.12
                        )
                    ):
                        score, box = vector_candidates[0]
                        vector_element = add_element(
                            page_number=page_number,
                            page_width=page_width,
                            page_height=page_height,
                            element_type="image_region",
                            text="",
                            section_path=caption.get("section_path", section_stack.copy()),
                            bbox=box,
                            structured={
                                "region_source": "vector_boundary",
                                "caption_relation": {"status": "matched", "confidence": 0.0},
                            },
                        )
                        image_regions += 1
                        confidence = round(max(0.0, 1 - score / 1.25), 3)
                        relation = {
                            "status": "matched",
                            "image_element_id": vector_element["element_id"],
                            "confidence": confidence,
                            "candidate_image_ids": [vector_element["element_id"]],
                            "region_source": "vector_boundary",
                        }
                        vector_element["structured"]["caption_relation"]["confidence"] = confidence
                        caption_element = add_element(
                            page_number=page_number,
                            page_width=page_width,
                            page_height=page_height,
                            element_type="figure_caption",
                            text=caption["text"],
                            section_path=caption.get("section_path", section_stack.copy()),
                            bbox=cap_box,
                            structured={"image_relation": relation},
                        )
                        relation_links.append((relation, "image_element_id", vector_element))
                        relation_links.append(
                            (
                                vector_element["structured"]["caption_relation"],
                                "caption_element_id",
                                caption_element,
                            )
                        )
                        figure_captions += 1
                        total_chars += len(caption["text"])
                        continue
                candidates.sort(key=lambda item: item[0])
                candidate_ids = [candidate["element"]["element_id"] for _, candidate in candidates]
                ambiguous = len(candidates) > 1 and candidates[1][0] - candidates[0][0] <= 0.12
                if candidates and not ambiguous and candidates[0][0] < 0.75:
                    score, matched_image = candidates[0]
                    matched_image["matched"] = True
                    confidence = round(max(0.0, 1 - score / 1.25), 3)
                    relation = {
                        "status": "matched",
                        "image_element_id": matched_image["element"]["element_id"],
                        "confidence": confidence,
                        "candidate_image_ids": candidate_ids,
                    }
                    image_relation = matched_image["element"]["structured"]["caption_relation"]
                    image_relation.update({"status": "matched", "confidence": confidence})
                    caption_element = add_element(
                        page_number=page_number,
                        page_width=page_width,
                        page_height=page_height,
                        element_type="figure_caption",
                        text=caption["text"],
                        section_path=caption.get("section_path", section_stack.copy()),
                        bbox=cap_box,
                        structured={"image_relation": relation},
                    )
                    relation_links.append((relation, "image_element_id", matched_image["element"]))
                    relation_links.append((image_relation, "caption_element_id", caption_element))
                    figure_captions += 1
                    total_chars += len(caption["text"])
                    continue
                elif ambiguous or candidates:
                    relation = {
                        "status": "ambiguous",
                        "image_element_id": None,
                        "confidence": 0.0,
                        "candidate_image_ids": candidate_ids,
                    }
                else:
                    relation = {
                        "status": "unmatched",
                        "image_element_id": None,
                        "confidence": 0.0,
                        "candidate_image_ids": [],
                    }
                add_element(
                    page_number=page_number,
                    page_width=page_width,
                    page_height=page_height,
                    element_type="figure_caption",
                    text=caption["text"],
                    section_path=caption.get("section_path", section_stack.copy()),
                    bbox=cap_box,
                    structured={"image_relation": relation},
                )
                total_chars += len(caption["text"])

            if column_split is not None:
                section_stack = column_sections[1].copy()

            if page_warning_items:
                warnings.extend(
                    {"page_number": page_number, "code": warning} for warning in page_warning_items
                )
                # Preserve a warning breadcrumb on every usable page element.
                for element in elements:
                    if element["page_number"] == page_number:
                        element["warnings"].extend(page_warning_items)
            if total_chars > MAX_PDF_TEXT_CHARS:
                raise ValueError("extracted PDF text exceeds the 2,000,000 character limit")

    # Preserve column-major reading order when a strong two-column layout was found.
    elements.sort(key=lambda element: _element_order_key(element, column_splits))
    seen_element_ids: dict[str, int] = {}
    id_by_object: dict[int, str] = {}
    ids_by_base: dict[str, list[str]] = {}
    for index, element in enumerate(elements):
        element["order_index"] = index
        base_id = element["element_id"]
        occurrence = seen_element_ids.get(base_id, 0) + 1
        seen_element_ids[base_id] = occurrence
        if occurrence > 1:
            element["element_id"] = f"{base_id}_{occurrence}"
        id_by_object[id(element)] = element["element_id"]
        ids_by_base.setdefault(base_id, []).append(element["element_id"])
    for relation, key, target in relation_links:
        relation[key] = id_by_object[id(target)]
    for element in elements:
        for relation_key in ("image_relation", "caption_relation"):
            relation = element["structured"].get(relation_key)
            if not isinstance(relation, dict):
                continue
            candidate_ids = relation.get("candidate_image_ids")
            if isinstance(candidate_ids, list):
                expanded: list[str] = []
                for candidate_id in candidate_ids:
                    for unique_id in ids_by_base.get(candidate_id, [candidate_id]):
                        if unique_id not in expanded:
                            expanded.append(unique_id)
                relation["candidate_image_ids"] = expanded
    return {
        "elements": elements,
        "page_count": page_count,
        "table_regions": table_regions,
        "image_regions": image_regions,
        "figure_captions": figure_captions,
        "warnings": warnings,
    }


def _bbox_edge_gap(first: Sequence[float], second: Sequence[float]) -> float:
    horizontal_gap = max(0.0, first[0] - second[2], second[0] - first[2])
    vertical_gap = max(0.0, first[1] - second[3], second[1] - first[3])
    return horizontal_gap + vertical_gap


def _is_textual_equation(text: str) -> bool:
    """Catch short prose labels that layout models sometimes emit as equations."""
    normalized = re.sub(r"\\text\s*\{(.*?)\}", r"\1", text, flags=re.S).strip()
    if len(normalized) > 200 or re.search(r"[\d=+*/^_{}<>≤≥≈∑∫√×÷∂∇]", normalized):
        return False
    return len(re.findall(r"[A-Za-z]+", normalized)) >= 3


def parse_pdf_bytes_mineru(pdf_bytes: bytes, *, tier: str = "standard") -> dict[str, Any]:
    """Parse a bounded PDF with the optional local MinerU SDK into PaperTrail elements."""
    if len(pdf_bytes) > MAX_PDF_BYTES or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("MinerU input must be a valid PDF no larger than 40 MB")
    if tier not in {"basic", "standard", "advanced"}:
        raise ValueError("MinerU tier must be basic, standard, or advanced")
    image_analysis_enabled = tier == "advanced"
    import tempfile

    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as source_pdf:
            if not source_pdf.pages or len(source_pdf.pages) > MAX_PDF_PAGES:
                raise ValueError("PDF must contain between 1 and 500 pages")
            page_sizes = [(float(page.width), float(page.height)) for page in source_pdf.pages]
            # MinerU's native-text path preserves small scientific subscripts that
            # its OCR path can misread. Keep OCR for scans and mixed PDFs.
            ocr_mode = (
                "txt"
                if all(
                    sum(str(char.get("text", "")).isalnum() for char in page.chars) >= 30
                    for page in source_pdf.pages
                )
                else "auto"
            )
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("could not verify source PDF geometry") from error

    previous_source = os.environ.get("MINERU_MODEL_SOURCE")
    os.environ.setdefault("MINERU_MODEL_SOURCE", "local")
    try:
        try:
            from mineru.parser import parse
        except ImportError as error:
            raise ValueError(
                "MinerU is not installed; install the pdf-mineru optional dependency"
            ) from error
        with tempfile.TemporaryDirectory(prefix="papertrail-mineru-") as temporary_dir:
            source_path = Path(temporary_dir) / "source.pdf"
            source_path.write_bytes(pdf_bytes)
            result = parse(
                source_path,
                tier=tier,
                ocr_mode=ocr_mode,
                image_analysis=image_analysis_enabled,
            )
    finally:
        if previous_source is None:
            os.environ.pop("MINERU_MODEL_SOURCE", None)

    middle = result.middle_json
    if len(middle.pages) != len(page_sizes):
        raise ValueError("MinerU returned incomplete PDF pages")
    elements: list[dict[str, Any]] = []
    section_path: list[str] = []
    total_chars = 0
    table_count = 0
    image_count = 0
    figure_captions = 0
    warnings: list[dict[str, Any]] = []
    seen_pages: set[int] = set()

    def text_value(value: Any) -> str:
        if isinstance(value, str):
            return value
        if hasattr(value, "model_dump"):
            return text_value(value.model_dump(mode="json"))
        if isinstance(value, list):
            return "".join(text_value(item) for item in value)
        if isinstance(value, dict):
            for key in ("content", "text", "latex", "html"):
                if key in value:
                    return text_value(value[key])
        return ""

    def without_image_data(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: without_image_data(item)
                for key, item in value.items()
                if key != "image_base64"
            }
        if isinstance(value, list):
            return [without_image_data(item) for item in value]
        return value

    kind_map = {
        "text": "paragraph",
        "ref_text": "paragraph",
        "doc_title": "title",
        "paragraph_title": "heading",
        "equation": "formula",
        "table": "table",
        "image": "figure",
        "chart": "figure",
        "code": "code",
        "list": "list",
        "page_footnote": "footnote",
    }
    for page in middle.pages:
        if not isinstance(page.page_idx, int) or not 0 <= page.page_idx < len(page_sizes):
            raise ValueError("MinerU returned a page outside the source PDF")
        if page.page_idx in seen_pages:
            raise ValueError("MinerU returned duplicate PDF pages")
        seen_pages.add(page.page_idx)
        page_number = page.page_idx + 1
        page_width, page_height = page_sizes[page.page_idx]
        block_data = [
            without_image_data(block.model_dump(mode="json", exclude={"image_base64"}))
            for block in page.blocks
        ]
        table_indices = [index for index, block in enumerate(page.blocks) if block.type == "table"]
        positioned_tables = [
            index
            for index in table_indices
            if isinstance(page.blocks[index].bbox, (list, tuple))
            and len(page.blocks[index].bbox) == 4
        ]
        assigned_captions: dict[int, list[str]] = {index: [] for index in table_indices}
        for origin in table_indices:
            content = block_data[origin].get("content")
            for item in content if isinstance(content, list) else []:
                if not isinstance(item, dict) or item.get("type") != "table_caption":
                    continue
                caption = text_value(item.get("content")).strip()
                if not caption:
                    continue
                caption_bbox = item.get("bbox")
                if (
                    not isinstance(caption_bbox, list)
                    or len(caption_bbox) != 4
                    or not positioned_tables
                ):
                    assigned_captions[origin].append(caption)
                    continue

                target = min(
                    [
                        (_bbox_edge_gap(caption_bbox, page.blocks[index].bbox), index)
                        for index in positioned_tables
                    ]
                )[1]
                assigned_captions[target].append(caption)
        figure_indices = [
            index for index, block in enumerate(page.blocks) if block.type in {"image", "chart"}
        ]
        assigned_figure_captions: dict[int, list[str]] = {index: [] for index in figure_indices}
        group_figure_captions: list[dict[str, Any]] = []
        for origin in figure_indices:
            content = block_data[origin].get("content")
            for item in content if isinstance(content, list) else []:
                if not isinstance(item, dict) or item.get("type") not in {
                    "image_caption",
                    "chart_caption",
                }:
                    continue
                caption = text_value(item.get("content")).strip()
                if not caption:
                    continue
                caption_bbox = item.get("bbox")
                if not isinstance(caption_bbox, list) or len(caption_bbox) != 4:
                    assigned_figure_captions[origin].append(caption)
                    continue
                if _MINERU_FIGURE_CAPTION.match(caption):
                    group_candidates = [
                        index
                        for index in figure_indices
                        if isinstance(page.blocks[index].bbox, (list, tuple))
                        and len(page.blocks[index].bbox) == 4
                        and 0 <= caption_bbox[1] - page.blocks[index].bbox[3] <= 0.08
                        and min(caption_bbox[2], page.blocks[index].bbox[2])
                        > max(caption_bbox[0], page.blocks[index].bbox[0])
                    ]
                    if group_candidates:
                        adjacent_group_candidates = set(group_candidates)
                        while True:
                            adjacent_to_group = {
                                index
                                for index in figure_indices
                                if index not in adjacent_group_candidates
                                and any(
                                    _bbox_edge_gap(
                                        page.blocks[index].bbox,
                                        page.blocks[group_index].bbox,
                                    )
                                    <= 0.05
                                    for group_index in adjacent_group_candidates
                                )
                            }
                            if not adjacent_to_group:
                                break
                            adjacent_group_candidates.update(adjacent_to_group)
                        group_candidates = sorted(adjacent_group_candidates)
                        caption_width = caption_bbox[2] - caption_bbox[0]
                        group_left = min(page.blocks[index].bbox[0] for index in group_candidates)
                        group_right = max(page.blocks[index].bbox[2] for index in group_candidates)
                        group_width = group_right - group_left
                        if len(group_candidates) >= 2 and caption_width >= 0.8 * group_width:
                            group_figure_captions.append(
                                {
                                    "origin": origin,
                                    "text": caption,
                                    "bbox": caption_bbox,
                                    "candidate_indices": group_candidates,
                                    "source": item,
                                }
                            )
                            continue
                candidates = [
                    index
                    for index in figure_indices
                    if isinstance(page.blocks[index].bbox, (list, tuple))
                    and len(page.blocks[index].bbox) == 4
                    and 0 <= caption_bbox[1] - page.blocks[index].bbox[3] <= 0.05
                    and min(caption_bbox[2], page.blocks[index].bbox[2])
                    > max(caption_bbox[0], page.blocks[index].bbox[0])
                ]
                target = (
                    min(candidates, key=lambda index: caption_bbox[1] - page.blocks[index].bbox[3])
                    if candidates
                    else origin
                )
                assigned_figure_captions[target].append(caption)
        for block in page.blocks:
            if block.type not in {"text", "ref_text"} or not block.bbox or len(block.bbox) != 4:
                continue
            caption = text_value(block.content).strip()
            if len(caption) > 1200:
                continue
            candidates = [
                index
                for index in figure_indices
                if isinstance(page.blocks[index].bbox, (list, tuple))
                and len(page.blocks[index].bbox) == 4
                and 0 <= block.bbox[1] - page.blocks[index].bbox[3] <= 0.05
                and min(block.bbox[2], page.blocks[index].bbox[2])
                > max(block.bbox[0], page.blocks[index].bbox[0])
            ]
            is_labeled_caption = bool(_MINERU_FIGURE_CAPTION.match(caption))
            if (
                is_labeled_caption
                and len(candidates) == 1
                and block.bbox[1] - page.blocks[candidates[0]].bbox[3] <= 0.012
            ):
                assigned_figure_captions[candidates[0]].append(caption)
                continue
            if is_labeled_caption:
                side_by_side_candidates = []
                for index in figure_indices:
                    figure_bbox = page.blocks[index].bbox
                    if not isinstance(figure_bbox, (list, tuple)) or len(figure_bbox) != 4:
                        continue
                    vertical_overlap = min(block.bbox[3], figure_bbox[3]) - max(
                        block.bbox[1], figure_bbox[1]
                    )
                    minimum_height = min(
                        block.bbox[3] - block.bbox[1], figure_bbox[3] - figure_bbox[1]
                    )
                    horizontal_gap = max(
                        0.0,
                        block.bbox[0] - figure_bbox[2],
                        figure_bbox[0] - block.bbox[2],
                    )
                    if (
                        vertical_overlap > 0
                        and minimum_height > 0
                        and vertical_overlap / minimum_height >= 0.5
                        and horizontal_gap <= 0.05
                    ):
                        side_by_side_candidates.append(index)
                if len(side_by_side_candidates) == 1:
                    assigned_figure_captions[side_by_side_candidates[0]].append(caption)
                    continue
            is_compact_adjacent_text = (
                len(caption) <= 240
                and len(candidates) == 1
                and block.bbox[1] - page.blocks[candidates[0]].bbox[3] <= 0.012
            )
            if len(candidates) == 1 and (is_labeled_caption or is_compact_adjacent_text):
                assigned_figure_captions[candidates[0]].append(caption)
            numbered_caption = _MINERU_FIGURE_NUMBER.match(caption)
            if numbered_caption:
                figure_number = numbered_caption.group("number").casefold()
                labelled_figures = [
                    index
                    for index in figure_indices
                    if (
                        label := _MINERU_FIGURE_NUMBER.match(
                            text_value(block_data[index].get("content")).strip()
                        )
                    )
                    and label.group("number").casefold() == figure_number
                ]
                if len(labelled_figures) == 1:
                    assigned_figure_captions[labelled_figures[0]].append(caption)

        # Some scanned diagrams are emitted as fake table grids. If a nearby
        # paragraph explicitly names a diagram/chart and the next block is a
        # single horizontally aligned table candidate, retain it as a figure.
        diagram_references: dict[int, list[str]] = {}
        for block in page.blocks:
            if block.type not in {"text", "ref_text"} or not block.bbox or len(block.bbox) != 4:
                continue
            reference = re.search(
                r"\b(?:diagram|chart)\s+\d+\b[^.!?]{0,900}[.!?]?",
                text_value(block.content),
                re.I,
            )
            if not reference:
                continue
            candidates = [
                index
                for index in table_indices
                if isinstance(page.blocks[index].bbox, (list, tuple))
                and len(page.blocks[index].bbox) == 4
                and 0 <= page.blocks[index].bbox[1] - block.bbox[3] <= 0.07
                and min(block.bbox[2], page.blocks[index].bbox[2])
                > max(block.bbox[0], page.blocks[index].bbox[0])
            ]
            if len(candidates) == 1:
                diagram_references.setdefault(candidates[0], []).append(reference.group(0).strip())
        mineru_block_elements: dict[int, dict[str, Any]] = {}
        page_figure_caption_count = 0
        for block_index, block in enumerate(page.blocks):
            if len(elements) >= MAX_PDF_ELEMENTS:
                raise ValueError("MinerU output exceeds the 20,000 element limit")
            element_type = kind_map.get(block.type, "paragraph")
            text = text_value(block.content).strip()
            if block.type in {"text", "ref_text"} and _MINERU_PAGE_SELF_DESCRIPTION.match(text):
                warnings.append(
                    {"page_number": page_number, "code": "mineru_page_self_description"}
                )
                continue
            equation_text_reclassified = block.type == "equation" and _is_textual_equation(text)
            if equation_text_reclassified:
                element_type = "paragraph"
            source_content = block_data[block_index].get("content")
            if block.type == "table" and isinstance(source_content, list):
                diagram_caption = next(
                    (
                        text_value(item.get("content")).strip()
                        for item in source_content
                        if isinstance(item, dict)
                        and item.get("type") == "table_caption"
                        and _MINERU_DIAGRAM_CAPTION.match(text_value(item.get("content")).strip())
                    ),
                    None,
                )
                if diagram_caption:
                    element_type = "figure"
                    text = diagram_caption
                    assigned_captions.pop(block_index, None)
                elif block_index in diagram_references:
                    element_type = "figure"
                    text = "\n".join(dict.fromkeys(diagram_references[block_index]))
                    assigned_captions.pop(block_index, None)
            if block_index in assigned_captions and isinstance(source_content, list):
                body = [
                    item
                    for item in block_data[block_index]["content"]
                    if not isinstance(item, dict) or item.get("type") != "table_caption"
                ]
                text = "".join(assigned_captions[block_index]) + text_value(body)
            if block_index in assigned_figure_captions:
                captions = "\n".join(dict.fromkeys(assigned_figure_captions[block_index]))
                if isinstance(source_content, list):
                    body = [
                        item
                        for item in source_content
                        if not isinstance(item, dict)
                        or item.get("type") not in {"image_caption", "chart_caption"}
                    ]
                    body_text = text_value(body)
                else:
                    body_text = text
                text = f"{captions}\n{body_text}".strip() if captions else body_text.strip()
            if image_analysis_enabled and block.type in {"image", "chart"}:
                # Keep advanced-tier VLM output out of source-exact text. Preserve its
                # payload in structured data for a future typed visual-evidence path.
                text = "\n".join(dict.fromkeys(assigned_figure_captions.get(block_index, [])))
            if not text and block.type not in {"image", "chart"}:
                continue
            raw_bbox = list(block.bbox) if block.bbox is not None else [0.0, 0.0, 1.0, 1.0]
            bbox = (
                [
                    raw_bbox[0] * page_width,
                    raw_bbox[1] * page_height,
                    raw_bbox[2] * page_width,
                    raw_bbox[3] * page_height,
                ]
                if len(raw_bbox) == 4 and max(abs(float(value)) for value in raw_bbox) <= 1
                else raw_bbox
            )
            if (
                len(bbox) != 4
                or not all(math.isfinite(float(value)) for value in bbox)
                or bbox[0] < 0
                or bbox[1] < 0
                or bbox[2] > page_width
                or bbox[3] > page_height
                or bbox[0] > bbox[2]
                or bbox[1] > bbox[3]
            ):
                raise ValueError("MinerU returned invalid page geometry")
            if element_type == "heading" and text:
                section_path = (section_path + [text])[-8:]
            element_warnings = []
            if equation_text_reclassified:
                element_warnings.append("mineru_equation_text_reclassified")
                warnings.append(
                    {"page_number": page_number, "code": "mineru_equation_text_reclassified"}
                )
            if element_type == "table":
                element_warnings.append("mineru_table_cells_unverified")
            elif element_type == "figure":
                element_warnings.append("mineru_figure_caption_unverified")
                if image_analysis_enabled and block.type in {"image", "chart"}:
                    element_warnings.append("mineru_visual_analysis_unverified")
            if block.bbox is None:
                element_warnings.append("mineru_bbox_missing_page_fallback")
            if element_type in {"table", "figure"}:
                warnings.append({"page_number": page_number, "code": element_warnings[0]})
            element = {
                "element_id": _stable_element_id(page_number, element_type, text, bbox),
                "order_index": len(elements),
                "page_number": page_number,
                "page_width": round(page_width, 2),
                "page_height": round(page_height, 2),
                "bbox": [round(float(value), 2) for value in bbox],
                "element_type": element_type,
                "section_path": section_path.copy(),
                "text": text,
                "structured": {
                    **block_data[block_index],
                    **(
                        {
                            "papertrail_visual_analysis": {
                                "status": "model_generated_unverified",
                                "source": "mineru_advanced",
                            }
                        }
                        if image_analysis_enabled and block.type in {"image", "chart"}
                        else {}
                    ),
                },
                "warnings": element_warnings,
            }
            elements.append(element)
            mineru_block_elements[block_index] = element
            total_chars += len(text)
            table_count += element_type == "table"
            image_count += element_type == "figure"
            if total_chars > MAX_PDF_TEXT_CHARS:
                raise ValueError("MinerU output exceeds the 2 million character limit")
        for caption in group_figure_captions:
            raw_bbox = caption["bbox"]
            caption_box = (
                [
                    raw_bbox[0] * page_width,
                    raw_bbox[1] * page_height,
                    raw_bbox[2] * page_width,
                    raw_bbox[3] * page_height,
                ]
                if max(abs(float(value)) for value in raw_bbox) <= 1
                else raw_bbox
            )
            if (
                len(caption_box) != 4
                or not all(math.isfinite(float(value)) for value in caption_box)
                or caption_box[0] < 0
                or caption_box[1] < 0
                or caption_box[2] > page_width
                or caption_box[3] > page_height
                or caption_box[0] >= caption_box[2]
                or caption_box[1] >= caption_box[3]
            ):
                continue
            candidate_ids = [
                mineru_block_elements[index]["element_id"]
                for index in caption["candidate_indices"]
                if index in mineru_block_elements
            ]
            elements.append(
                {
                    "element_id": _stable_element_id(
                        page_number, "figure_caption", caption["text"], caption_box
                    ),
                    "order_index": len(elements),
                    "page_number": page_number,
                    "page_width": round(page_width, 2),
                    "page_height": round(page_height, 2),
                    "bbox": [round(float(value), 2) for value in caption_box],
                    "element_type": "figure_caption",
                    "section_path": section_path.copy(),
                    "text": caption["text"],
                    "structured": {
                        "image_relation": {
                            "status": "ambiguous",
                            "image_element_id": None,
                            "confidence": 0.0,
                            "candidate_image_ids": candidate_ids,
                        },
                        "source": without_image_data(caption["source"]),
                    },
                    "warnings": [],
                }
            )
            total_chars += len(caption["text"])
            page_figure_caption_count += 1
            if total_chars > MAX_PDF_TEXT_CHARS or len(elements) > MAX_PDF_ELEMENTS:
                raise ValueError("MinerU output exceeds an element or text limit")
        figure_captions += page_figure_caption_count
    # A plausible-looking table can omit a numeric column, and OCR can corrupt a
    # figure caption. Compare local source words only within each element's own
    # region. Differences remain warnings because the PDF layer has no grid.
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as source_pdf:
        for element in elements:
            if element["element_type"] not in {"table", "figure"}:
                continue
            content = element["structured"].get("content")
            if element["element_type"] == "figure":
                for item in content if isinstance(content, list) else []:
                    if not isinstance(item, dict) or item.get("type") not in {
                        "chart_caption",
                        "image_caption",
                    }:
                        continue
                    caption = text_value(item.get("content"))
                    if "\ufffd" in caption:
                        element["warnings"].append("mineru_caption_replacement_character")
                        warnings.append(
                            {
                                "page_number": element["page_number"],
                                "code": "mineru_caption_replacement_character",
                            }
                        )
                    caption_bbox = item.get("bbox")
                    if not isinstance(caption_bbox, list) or len(caption_bbox) != 4:
                        continue
                    page = source_pdf.pages[element["page_number"] - 1]
                    box = [float(value) for value in caption_bbox]
                    if max(abs(value) for value in box) <= 1:
                        box = [
                            box[0] * page.width,
                            box[1] * page.height,
                            box[2] * page.width,
                            box[3] * page.height,
                        ]
                    if not (
                        0 <= box[0] < box[2] <= page.width and 0 <= box[1] < box[3] <= page.height
                    ):
                        continue
                    source_words = page.crop(tuple(box)).extract_words(x_tolerance=1)
                    normalized_caption = re.sub(r"[^a-z0-9]", "", caption.casefold())
                    missing = [
                        word["text"]
                        for word in source_words
                        if len(re.sub(r"[^a-z0-9]", "", word["text"].casefold())) >= 5
                        and re.sub(r"[^a-z0-9]", "", word["text"].casefold())
                        not in normalized_caption
                    ]
                    if missing:
                        element["structured"].setdefault("source_audit", {})[
                            "missing_caption_words"
                        ] = missing[:8]
                        element["warnings"].append("mineru_caption_native_words_missing")
                        warnings.append(
                            {
                                "page_number": element["page_number"],
                                "code": "mineru_caption_native_words_missing",
                            }
                        )
                continue
            bodies = [
                item
                for item in (content if isinstance(content, list) else [])
                if isinstance(item, dict) and item.get("type") == "table_body"
            ]
            if not bodies:
                continue
            body = bodies[0]
            body_bbox = body.get("bbox")
            if not isinstance(body_bbox, list) or len(body_bbox) != 4:
                continue
            page = source_pdf.pages[element["page_number"] - 1]
            box = [float(value) for value in body_bbox]
            if max(abs(value) for value in box) <= 1:
                box = [
                    box[0] * page.width,
                    box[1] * page.height,
                    box[2] * page.width,
                    box[3] * page.height,
                ]
            if not (0 <= box[0] < box[2] <= page.width and 0 <= box[1] < box[3] <= page.height):
                continue
            source_words = page.crop(tuple(box)).extract_words(x_tolerance=1)
            number = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")
            native = Counter(
                word["text"] for word in source_words if number.fullmatch(word["text"])
            )
            body_text = html.unescape(re.sub(r"<[^>]+>", " ", text_value(body.get("content"))))
            parsed = Counter(number.findall(body_text))
            missing = list((native - parsed).elements())
            normalized_body = re.sub(r"[^a-z0-9]", "", body_text.casefold())
            missing_identifiers = [
                word["text"]
                for word in source_words
                if len(re.sub(r"[^a-z0-9]", "", word["text"].casefold())) >= 8
                and any(char.isdigit() for char in word["text"])
                and any(char.isalpha() for char in word["text"])
                and re.sub(r"[^a-z0-9]", "", word["text"].casefold()) not in normalized_body
            ]
            if missing or missing_identifiers:
                element["structured"]["source_audit"] = {
                    "unmatched_numeric_token_count": len(missing),
                    "unmatched_numeric_examples": missing[:8],
                    "missing_identifier_examples": missing_identifiers[:8],
                }
                element["warnings"].append("mineru_table_native_text_missing")
                warnings.append(
                    {
                        "page_number": element["page_number"],
                        "code": "mineru_table_native_text_missing",
                    }
                )
    return {
        "parser_version": f"mineru-{middle.metadata.producer.version}-{MINERU_ADAPTER_VERSION}",
        "ocr_mode": ocr_mode,
        "image_analysis_enabled": image_analysis_enabled,
        "page_count": len(middle.pages),
        "elements": elements,
        "table_regions": table_count,
        "image_regions": image_count,
        "figure_captions": figure_captions,
        "warnings": warnings,
    }


def _element_order_key(
    element: dict[str, Any], column_splits: dict[int, float]
) -> tuple[int, int, float, float, str, int]:
    page_number = element["page_number"]
    bbox = element["bbox"]
    split = column_splits.get(page_number)
    column = 0 if split is None or (bbox[0] + bbox[2]) / 2 < split else 1
    return (
        page_number,
        column,
        bbox[1],
        bbox[0],
        element["element_type"],
        element["order_index"],
    )
