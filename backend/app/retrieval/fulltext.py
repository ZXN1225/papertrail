"""Deterministic bounded chunking for explicitly licensed paper text."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

CHUNKER_VERSION = "paragraph-utf8-token-upper-bound-v3"
PDF_CHUNKER_VERSION = "pdf-element-structure-token-upper-bound-v4"
MAX_CHUNK_TOKEN_UPPER_BOUND = 1_800
# Backward-compatible name for callers/tests; this limit is now UTF-8 bytes, not characters.
MAX_CHUNK_CHARS = MAX_CHUNK_TOKEN_UPPER_BOUND
MAX_CHUNKS = 10_000
MAX_TEXT_CHARS = 2_000_000
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class TextChunk:
    ordinal: int
    locator: str
    char_start: int
    char_end: int
    text: str
    page_number: int | None = None
    element_type: str = "paragraph"
    section_path: str = "[]"
    bbox: str | None = None
    element_id: str | None = None
    evidence_text: str | None = None


def _trimmed_span(text: str, start: int, stop: int) -> tuple[int, int, str]:
    left = len(text[start:stop]) - len(text[start:stop].lstrip())
    right = len(text[start:stop].rstrip())
    actual_start = start + left
    actual_end = start + right
    return actual_start, actual_end, text[actual_start:actual_end]


def _choose_stop(text: str, start: int, byte_limit: int) -> int:
    """Return a character boundary whose UTF-8 byte span stays within ``byte_limit``.

    For byte-level BPE tokenizers, UTF-8 bytes are a conservative token-count upper bound:
    a token cannot represent fewer than one input byte. It intentionally avoids downloading
    provider vocabulary files during offline licensed-document ingestion.
    """
    stop = start
    byte_count = 0
    while stop < len(text):
        next_size = len(text[stop].encode("utf-8"))
        if byte_count + next_size > byte_limit:
            break
        byte_count += next_size
        stop += 1
    if stop < len(text):
        midpoint = start + max(1, (stop - start) // 2)
        boundary = max(text.rfind(" ", midpoint, stop), text.rfind("\n", midpoint, stop))
        if boundary > start:
            stop = boundary
    return stop


def chunk_plain_text(text: str) -> list[TextChunk]:
    if not isinstance(text, str):
        raise ValueError("full text must be a string")
    normalized = text.strip()
    if not normalized:
        raise ValueError("full text must not be empty")
    if len(normalized) > MAX_TEXT_CHARS:
        raise ValueError("full text exceeds the 2,000,000 character limit")

    chunks: list[TextChunk] = []
    active_section = "未标注章节"
    paragraphs = re.finditer(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*", normalized)
    for match in paragraphs:
        paragraph = match.group(0)
        heading = _HEADING.match(paragraph)
        if heading:
            active_section = heading.group(1)[:120]
            continue
        if not paragraph.strip():
            continue
        start = match.start()
        end = match.end()
        while start < end:
            stop = start + _choose_stop(normalized[start:end], 0, MAX_CHUNK_TOKEN_UPPER_BOUND)
            actual_start, actual_end, body = _trimmed_span(normalized, start, stop)
            if body:
                chunks.append(
                    TextChunk(
                        ordinal=len(chunks),
                        locator=f"{active_section} · 字符 {actual_start}-{actual_end}",
                        char_start=actual_start,
                        char_end=actual_end,
                        text=body,
                        evidence_text=body,
                    )
                )
                if len(chunks) > MAX_CHUNKS:
                    raise ValueError("full text creates too many chunks")
            start = stop
            while start < end and normalized[start].isspace():
                start += 1
    if not chunks:
        raise ValueError("full text contains no indexable paragraphs")
    return chunks


def _section_path(element: dict[str, Any]) -> list[str]:
    value = element.get("section_path")
    if isinstance(value, list):
        return [str(part) for part in value]
    if isinstance(value, str):
        # Preserve compatibility with the old single-section shape and serialized JSON.
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = [value]
        if isinstance(parsed, list):
            return [str(part) for part in parsed]
        if isinstance(parsed, str):
            return [parsed]
    legacy = str(element.get("section", "未标注章节"))
    return [legacy]


def _line_positions(text: str) -> list[tuple[str, int, int]]:
    return [(match.group(0), match.start(), match.end()) for match in re.finditer(r"[^\n]+", text)]


def _cell_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text", "")).strip()
    return str(value or "").strip()


def _table_column_groups(header_cells: list[Any]) -> list[list[int]]:
    """Collapse blank header columns into the preceding visible header column."""
    groups: list[list[int]] = []
    for index, cell in enumerate(header_cells):
        if not _cell_text(cell) and groups:
            groups[-1].append(index)
        else:
            groups.append([index])
    return groups


def _logical_table_cells(cells: list[Any], groups: list[list[int]]) -> list[str]:
    logical: list[str] = []
    for group in groups:
        value = ""
        for index in group:
            cell = _cell_text(cells[index]) if index < len(cells) else ""
            if not cell:
                continue
            if not value:
                value = cell
            elif value.endswith("-") and cell[:1].islower():
                prefix = value.rsplit(None, 1)[-1].rsplit("/", 1)[-1][:-1]
                separator = "" if len(prefix) >= 5 else " "
                value = value[:-1] + separator + cell
            elif re.search(r"(?:^|\s)[A-Za-z]$", value) and cell[:1].islower():
                value += cell
            else:
                value += " " + cell
        logical.append(value)
    return logical


def _table_chunk_text(title: str, header: str, rows: list[str]) -> str:
    return "\n".join(part for part in (title, header, *rows) if part)


def _format_source_rows(rows: list[int]) -> str:
    if not rows:
        return ""
    parts: list[str] = []
    start = prior = rows[0]
    for value in rows[1:]:
        if value == prior + 1:
            prior = value
            continue
        parts.append(str(start) if start == prior else f"{start}-{prior}")
        start = prior = value
    parts.append(str(start) if start == prior else f"{start}-{prior}")
    return ",".join(parts)


def _chunk_table(
    element: dict[str, Any],
    text: str,
    page: int,
    section_path: list[str],
    bbox: str | None,
    element_id: str | None,
    ordinal_start: int,
) -> list[TextChunk]:
    lines = _line_positions(text)
    structured = element.get("structured")
    structured = structured if isinstance(structured, dict) else {}
    rows_value = structured.get("rows")
    title = lines[0][0] if lines else ""
    header = ""
    data_rows: list[tuple[str, int, int, list[int]]] = []

    if isinstance(rows_value, list) and rows_value:
        header_row_count = structured.get("header_row_count", 1)
        if (
            not isinstance(header_row_count, int)
            or isinstance(header_row_count, bool)
            or not 1 <= header_row_count <= len(rows_value)
        ):
            header_row_count = 1
        header_rows = [
            row.get("cells", []) if isinstance(row, dict) else []
            for row in rows_value[:header_row_count]
        ]
        column_count = max((len(row) for row in header_rows), default=0)
        header_cells: list[dict[str, str]] = []
        for column in range(column_count):
            values: list[str] = []
            for row in header_rows:
                value = _cell_text(row[column]) if column < len(row) else ""
                if value and value not in values:
                    values.append(value)
            # A small top-level symbol may be repeated inside its detailed unit
            # label; keep the more informative header once.
            values = [
                value
                for value in values
                if not any(value != other and value in other for other in values)
            ]
            header_cells.append({"text": " / ".join(values)})
        final_header_cells = (
            header_rows[-1]
            if header_rows
            else (rows_value[0].get("cells", []) if isinstance(rows_value[0], dict) else [])
        )
        column_groups = _table_column_groups(final_header_cells)
        header = " | ".join(_logical_table_cells(header_cells, column_groups))
        if len(lines) > header_row_count:
            header_start, header_end = lines[1][1], lines[header_row_count][2]
        else:
            header_start = 0
            header_end = len(text)
        search_from = header_end
        for compact_index, row in enumerate(rows_value[header_row_count:], start=header_row_count):
            cells = row.get("cells", []) if isinstance(row, dict) else []
            raw_row_text = " | ".join(_cell_text(cell) for cell in cells)
            row_text = " | ".join(_logical_table_cells(cells, column_groups))
            if not any(_cell_text(cell) for cell in cells):
                continue
            source_row_index = (
                row.get("row_index", compact_index) if isinstance(row, dict) else compact_index
            )
            try:
                source_row_number = int(source_row_index) + 1
            except (TypeError, ValueError):
                source_row_number = compact_index + 1
            match = re.search(re.escape(raw_row_text), text[search_from:])
            if match:
                row_start = search_from + match.start()
                row_end = search_from + match.end()
                search_from = row_end
            else:
                row_start = search_from
                row_end = min(len(text), row_start + len(raw_row_text))
            data_rows.append((row_text, row_start, row_end, [source_row_number]))
    elif len(lines) >= 2:
        header, header_start, header_end = lines[1]
        data_rows = [
            (line, start, end, [index + 2]) for index, (line, start, end) in enumerate(lines[2:])
        ]
    else:
        header_start, header_end = 0, len(text)

    if not header and len(lines) > 1:
        header, header_start, header_end = lines[1]
    if len(header.encode("utf-8")) > MAX_CHUNK_TOKEN_UPPER_BOUND:
        raise ValueError("PDF table header exceeds the 1,800 UTF-8 byte chunk limit")

    # Some PDF table extractors split a hyphenated word across two physical rows,
    # leaving the continuation in an otherwise empty row. Join only that unambiguous
    # same-column case for retrieval; evidence_text and offsets still cover the exact
    # original source span, and the locator retains both physical row numbers.
    joined_rows: list[tuple[str, int, int, list[int]]] = []
    for row_text, row_start, row_end, source_rows in data_rows:
        cells = row_text.split(" | ")
        nonempty_cells = [(index, cell.strip()) for index, cell in enumerate(cells) if cell.strip()]
        if joined_rows and len(nonempty_cells) == 1:
            column, continuation = nonempty_cells[0]
            prior_text, prior_start, _prior_end, prior_source_rows = joined_rows[-1]
            prior_cells = prior_text.split(" | ")
            prior_cell = prior_cells[column].strip() if column < len(prior_cells) else ""
            if (
                prior_cell.endswith("-")
                and continuation[:1].islower()
                and all(not cell.strip() for index, cell in enumerate(cells) if index != column)
                and column < len(prior_cells)
            ):
                prefix = prior_cell.rsplit(None, 1)[-1].rsplit("/", 1)[-1][:-1]
                separator = "" if len(prefix) >= 5 else "-"
                prior_cells[column] = prior_cell[:-1] + separator + continuation
                joined_rows[-1] = (
                    " | ".join(prior_cells),
                    prior_start,
                    row_end,
                    prior_source_rows + source_rows,
                )
                continue
        joined_rows.append((row_text, row_start, row_end, source_rows))
    data_rows = joined_rows

    chunks: list[TextChunk] = []
    pending: list[tuple[str, int, int, list[int]]] = []

    def flush() -> None:
        if not pending:
            return
        content = _table_chunk_text(title, header, [row[0] for row in pending])
        if len(content.encode("utf-8")) > MAX_CHUNK_TOKEN_UPPER_BOUND:
            raise ValueError("PDF table row exceeds the 1,800 UTF-8 byte chunk limit")
        source_start = pending[0][1] if pending else header_start
        source_end = pending[-1][2] if pending else header_end
        source_row_label = _format_source_rows(
            [source_row for row in pending for source_row in row[3]]
        )
        chunks.append(
            TextChunk(
                ordinal=ordinal_start + len(chunks),
                locator=(
                    f"第 {page} 页 · {' / '.join(section_path)} · table · "
                    f"解析器物理行 {source_row_label}"
                    if section_path
                    else f"第 {page} 页 · table · 解析器物理行 {source_row_label}"
                ),
                char_start=source_start,
                char_end=source_end,
                text=content,
                evidence_text=text[source_start:source_end],
                page_number=page,
                element_type="table",
                section_path=json.dumps(section_path, ensure_ascii=False, separators=(",", ":")),
                bbox=bbox,
                element_id=element_id,
            )
        )
        pending.clear()

    for row in data_rows:
        candidate = _table_chunk_text(title, header, [item[0] for item in pending] + [row[0]])
        if pending and len(candidate.encode("utf-8")) > MAX_CHUNK_TOKEN_UPPER_BOUND:
            flush()
            candidate = _table_chunk_text(title, header, [row[0]])
        if len(candidate.encode("utf-8")) > MAX_CHUNK_TOKEN_UPPER_BOUND:
            prefix = _table_chunk_text(title, header, []) + "\n"
            available = MAX_CHUNK_TOKEN_UPPER_BOUND - len(prefix.encode("utf-8"))
            if available < 1:
                raise ValueError(
                    "PDF table title and header exceed the 1,800 UTF-8 byte chunk limit"
                )
            part_start = 0
            part_index = 1
            while part_start < len(row[0]):
                part_stop = _choose_stop(row[0], part_start, available)
                if part_stop <= part_start:
                    raise ValueError(
                        "PDF table row contains a character that cannot fit "
                        "with its repeated header"
                    )
                source_start = row[1] + part_start
                source_end = row[1] + part_stop
                fragment = row[0][part_start:part_stop].strip()
                if fragment:
                    chunks.append(
                        TextChunk(
                            ordinal=ordinal_start + len(chunks),
                            locator=(
                                f"第 {page} 页 · {' / '.join(section_path)} · table · "
                                f"解析器物理行 {_format_source_rows(row[3])} · 分段 {part_index}"
                            ),
                            char_start=source_start,
                            char_end=source_end,
                            text=_table_chunk_text(title, header, [fragment]),
                            evidence_text=text[source_start:source_end],
                            page_number=page,
                            element_type="table",
                            section_path=json.dumps(
                                section_path, ensure_ascii=False, separators=(",", ":")
                            ),
                            bbox=bbox,
                            element_id=element_id,
                        )
                    )
                part_start = part_stop
                while part_start < len(row[0]) and row[0][part_start].isspace():
                    part_start += 1
                part_index += 1
            continue
        pending.append(row)
    flush()

    if not chunks:
        # Header-only tables remain searchable and retain their source span.
        content = _table_chunk_text(title, header, [])
        chunks.append(
            TextChunk(
                ordinal=ordinal_start,
                locator=f"第 {page} 页 · {' / '.join(section_path)} · table · 表头",
                char_start=0,
                char_end=min(len(text), header_end),
                text=content,
                evidence_text=text[: min(len(text), header_end)],
                page_number=page,
                element_type="table",
                section_path=json.dumps(section_path, ensure_ascii=False, separators=(",", ":")),
                bbox=bbox,
                element_id=element_id,
            )
        )
    return chunks


def chunk_pdf_elements(elements: list[dict[str, object]]) -> list[TextChunk]:
    """Chunk PDF elements while retaining element lineage, local offsets and table headers.

    ``char_start`` and ``char_end`` are half-open offsets into the source element's
    ``text``. For paragraphs/headings/captions, the chunk text is that source slice.
    Table chunks repeat the title/header as retrieval context; their offsets identify
    the contiguous source data-row span named in ``locator`` (the repeated header is
    contextual text and is not included in that span).
    """
    chunks: list[TextChunk] = []
    for element in elements:
        if not isinstance(element, dict):
            raise ValueError("PDF elements must be objects")
        source_text = str(element.get("text", ""))
        text = source_text
        if not text.strip():
            continue
        if len(text) > MAX_TEXT_CHARS:
            raise ValueError("PDF element exceeds the 2,000,000 character limit")
        try:
            page = int(element["page_number"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("PDF elements must include an integer page_number") from error
        path = _section_path(element)
        section = " / ".join(path) or "未标注章节"
        element_type = str(element.get("element_type", "paragraph"))
        bbox_value = element.get("bbox")
        bbox = json.dumps(bbox_value, separators=(",", ":")) if bbox_value else None
        element_id_value = element.get("element_id")
        element_id = str(element_id_value) if element_id_value else None

        if element_type == "table":
            table_chunks = _chunk_table(
                element,
                text,
                page,
                path,
                bbox,
                element_id,
                len(chunks),
            )
            chunks.extend(table_chunks)
            if len(chunks) > MAX_CHUNKS:
                raise ValueError("PDF creates too many chunks")
            continue

        start = 0
        while start < len(text):
            stop = _choose_stop(text, start, MAX_CHUNK_TOKEN_UPPER_BOUND)
            actual_start, actual_end, body = _trimmed_span(text, start, stop)
            if body:
                chunks.append(
                    TextChunk(
                        ordinal=len(chunks),
                        locator=(
                            f"第 {page} 页 · {section} · {element_type} · "
                            f"字符 {actual_start}-{actual_end}"
                        ),
                        char_start=actual_start,
                        char_end=actual_end,
                        text=body,
                        evidence_text=body,
                        page_number=page,
                        element_type=element_type,
                        section_path=json.dumps(path, ensure_ascii=False, separators=(",", ":")),
                        bbox=bbox,
                        element_id=element_id,
                    )
                )
            start = stop
            while start < len(text) and text[start].isspace():
                start += 1
            if len(chunks) > MAX_CHUNKS:
                raise ValueError("PDF creates too many chunks")
    if not chunks:
        raise ValueError("PDF contains no indexable text, table, or figure captions")
    return chunks
