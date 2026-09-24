"""Validated cosine ranking and reciprocal-rank fusion helpers."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or len(left) != len(right):
        raise ValueError("vectors must have the same positive dimension")
    if any(not math.isfinite(value) for value in (*left, *right)):
        raise ValueError("vectors must contain finite values")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def dense_rank(
    query_vector: Sequence[float], vectors_by_id: Mapping[str, Sequence[float]]
) -> list[tuple[str, float]]:
    ranked = [
        (item_id, cosine_similarity(query_vector, vector))
        for item_id, vector in vectors_by_id.items()
    ]
    return sorted(ranked, key=lambda item: (-item[1], item[0]))


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[Any]], *, k: int = 60
) -> list[tuple[str, float]]:
    if k < 1:
        raise ValueError("RRF k must be positive")
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, hit in enumerate(ranked, start=1):
            item_id = (
                hit[0]
                if isinstance(hit, tuple)
                else hit
                if isinstance(hit, str)
                else hit.openalex_id
            )
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
