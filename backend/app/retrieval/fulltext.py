"""Deterministic bounded plain-text chunking for explicitly licensed papers."""

from __future__ import annotations

import re
from dataclasses import dataclass

CHUNKER_VERSION = "paragraph-char-v1"
MAX_CHUNK_CHARS = 1_800
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
            stop = min(start + MAX_CHUNK_CHARS, end)
            if stop < end:
                boundary = normalized.rfind(" ", start + MAX_CHUNK_CHARS // 2, stop)
                if boundary > start:
                    stop = boundary
            body = normalized[start:stop].strip()
            if body:
                chunks.append(
                    TextChunk(
                        ordinal=len(chunks),
                        locator=f"{active_section} · 字符 {start}-{stop}",
                        char_start=start,
                        char_end=stop,
                        text=body,
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
