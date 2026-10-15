"""Versioned lightweight tokenizer for English and CJK retrieval text."""

from __future__ import annotations

import re

TOKENIZER_VERSION = "unicode-latin-cjk-bigram-plural-v3"
_LATIN_TOKEN = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
_IRREGULAR_PLURALS = {
    "analyses": "analysis",
    "aliases": "alias",
    "atlases": "atlas",
    "axes": "axis",
    "biases": "bias",
    "bases": "basis",
    "canvases": "canvas",
    "crises": "crisis",
    "diagnoses": "diagnosis",
    "hypotheses": "hypothesis",
    "indices": "index",
    "lenses": "lens",
    "matrices": "matrix",
    "parentheses": "parenthesis",
    "theses": "thesis",
    "gases": "gas",
    "statuses": "status",
    "vertices": "vertex",
}
_UNCHANGED_LATIN_TERMS = {
    "atlas",
    "alias",
    "bias",
    "canvas",
    "gas",
    "lens",
    "mathematics",
    "news",
    "physics",
    "series",
    "species",
    "statistics",
    "status",
}
_IE_PLURAL_EXCEPTIONS = {
    "brownies",
    "cookies",
    "groupies",
    "movies",
    "rookies",
    "selfies",
    "zombies",
}


def tokenize(text: str) -> list[str]:
    """Lowercase Latin/numeric terms and emit overlapping CJK character bigrams."""
    tokens: list[str] = []
    latin_buffer: list[str] = []
    cjk_buffer: list[str] = []

    def flush_latin() -> None:
        if latin_buffer:
            tokens.extend(
                _normalize_english_plural(token)
                for token in _LATIN_TOKEN.findall("".join(latin_buffer).casefold())
            )
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


def _normalize_english_plural(token: str) -> str:
    """Fold common English plurals to singulars for sparse retrieval matching.

    This is a deliberately small, versioned rule set rather than a general stemmer.
    Preserve common singular terms and map frequent irregular or ambiguous forms before
    applying regular ``-ies``, sibilant ``-es`` and terminal ``-s`` rules.
    """
    if token in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[token]
    if token in _UNCHANGED_LATIN_TERMS:
        return token
    if token in _IE_PLURAL_EXCEPTIONS:
        return token[:-1]
    if token == "ties":
        return "tie"
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 4 and token.endswith(("ches", "shes", "sses", "xes", "zes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is", "ics")):
        return token[:-1]
    return token


def _is_cjk(codepoint: int) -> bool:
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x3134F
    )
