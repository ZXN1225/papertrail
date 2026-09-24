"""Dependency-free Okapi BM25 implementation with deterministic tie-breaking."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Protocol

from app.retrieval.tokenizer import tokenize

BM25_VERSION = "okapi-bm25-v1"
DEFAULT_K1 = 1.5
DEFAULT_B = 0.75


class SearchDocument(Protocol):
    openalex_id: str
    title: str
    abstract: str | None


@dataclass(frozen=True)
class SearchHit:
    openalex_id: str
    score: float


class BM25Index:
    def __init__(
        self,
        documents: list[SearchDocument | dict[str, Any]],
        *,
        k1: float = DEFAULT_K1,
        b: float = DEFAULT_B,
    ) -> None:
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("BM25 requires k1 > 0 and b in [0, 1]")
        identifiers = [_document_value(document, "openalex_id") for document in documents]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("document IDs must be unique")
        self.k1 = k1
        self.b = b
        self._ids = identifiers
        self._term_frequencies = [
            Counter(
                tokenize(
                    f"{_document_value(document, 'title') or ''} "
                    f"{_document_value(document, 'title') or ''} "
                    f"{_document_value(document, 'abstract') or ''}"
                )
            )
            for document in documents
        ]
        self._lengths = [sum(frequencies.values()) for frequencies in self._term_frequencies]
        self._average_length = sum(self._lengths) / len(self._lengths) if documents else 0.0
        document_frequency: Counter[str] = Counter()
        for frequencies in self._term_frequencies:
            document_frequency.update(frequencies.keys())
        count = len(documents)
        self._idf = {
            term: math.log(1 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def search(self, query: str, *, limit: int = 10) -> list[SearchHit]:
        if limit < 1:
            raise ValueError("limit must be positive")
        query_terms = tokenize(query)
        if not query_terms or not self._ids:
            return []
        query_frequency = Counter(query_terms)
        hits: list[SearchHit] = []
        for document_id, frequencies, length in zip(
            self._ids, self._term_frequencies, self._lengths, strict=True
        ):
            score = 0.0
            for term, query_count in query_frequency.items():
                term_frequency = frequencies.get(term, 0)
                if not term_frequency:
                    continue
                denominator = term_frequency + self.k1 * (
                    1 - self.b + self.b * length / self._average_length
                )
                score += (
                    self._idf[term]
                    * (term_frequency * (self.k1 + 1) / denominator)
                    * min(query_count, 2)
                )
            if score > 0:
                hits.append(SearchHit(document_id, score))
        hits.sort(key=lambda hit: (-hit.score, hit.openalex_id))
        return hits[:limit]


def _document_value(document: SearchDocument | dict[str, Any], name: str) -> Any:
    if isinstance(document, dict):
        return document.get(name)
    return getattr(document, name)
