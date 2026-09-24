"""Deterministic retrieval metrics for graded relevance judgments."""

from __future__ import annotations

import math


def score_query(
    ranking: list[str], relevance: dict[str, int], *, cutoffs: tuple[int, ...] = (1, 3, 5, 10)
) -> dict[str, float]:
    if any(grade < 0 for grade in relevance.values()):
        raise ValueError("relevance grades must be non-negative")
    result: dict[str, float] = {}
    first_relevant = next(
        (
            rank
            for rank, document_id in enumerate(ranking, start=1)
            if relevance.get(document_id, 0) > 0
        ),
        None,
    )
    for cutoff in cutoffs:
        if cutoff < 1:
            raise ValueError("metric cutoffs must be positive")
        prefix = ranking[:cutoff]
        result[f"hit@{cutoff}"] = float(
            any(relevance.get(document_id, 0) > 0 for document_id in prefix)
        )
        result[f"ndcg@{cutoff}"] = _ndcg(prefix, relevance, cutoff)
    result[f"mrr@{max(cutoffs)}"] = 1.0 / first_relevant if first_relevant else 0.0
    return result


def _ndcg(ranking: list[str], relevance: dict[str, int], cutoff: int) -> float:
    def gain_at(rank: int, document_id: str) -> float:
        return (2 ** relevance.get(document_id, 0) - 1) / math.log2(rank + 1)

    dcg = sum(gain_at(rank, document_id) for rank, document_id in enumerate(ranking, 1))
    ideal_grades = sorted(relevance.values(), reverse=True)[:cutoff]
    idcg = sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(ideal_grades, 1))
    return dcg / idcg if idcg else 0.0
