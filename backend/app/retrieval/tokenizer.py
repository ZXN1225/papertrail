"""Versioned lightweight tokenizer for English and CJK metadata."""

from __future__ import annotations

import re

TOKENIZER_VERSION = "unicode-latin-cjk-bigram-v1"
_LATIN_TOKEN = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Lowercase Latin/numeric terms and emit overlapping CJK character bigrams."""
    tokens: list[str] = []
    latin_buffer: list[str] = []
    cjk_buffer: list[str] = []

    def flush_latin() -> None:
        if latin_buffer:
            tokens.extend(_LATIN_TOKEN.findall("".join(latin_buffer).casefold()))
            latin_buffer.clear()

    def flush_cjk() -> None:
        if cjk_buffer:
            if len(cjk_buffer) == 1:
                tokens.append(cjk_buffer[0])
            else:
                tokens.extend(
                    "".join(cjk_buffer[index : index + 2]) for index in range(len(cjk_buffer) - 1)
                )
            cjk_buffer.clear()

    for character in text:
        codepoint = ord(character)
        if _is_cjk(codepoint):
            flush_latin()
            cjk_buffer.append(character)
        else:
            flush_cjk()
            latin_buffer.append(character)
    flush_cjk()
    flush_latin()
    return tokens


def _is_cjk(codepoint: int) -> bool:
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x3134F
    )
