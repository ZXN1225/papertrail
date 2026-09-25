"""Agreement diagnostics between prior assistant qrels and human grades."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.evaluation.p36_pool import PoolReviewError


def evaluate_grade_agreement(
    assistant_grades: dict[tuple[str, str], int],
    human_grades: dict[tuple[str, str], int],
    *,
    query_buckets: dict[str, str],
) -> dict[str, Any]:
    """Compare paired 0-3 grades without treating either source as universal gold."""
    if not assistant_grades or not human_grades:
        raise PoolReviewError("agreement evaluation requires non-empty paired grades")
    if set(assistant_grades) != set(human_grades):
        raise PoolReviewError("assistant and human grades must cover exactly the same pairs")
    pairs = sorted(human_grades)
    for pair in pairs:
        if (
            not isinstance(pair, tuple)
            or len(pair) != 2
            or not all(isinstance(value, str) and value for value in pair)
            or type(assistant_grades[pair]) is not int
            or type(human_grades[pair]) is not int
            or not 0 <= assistant_grades[pair] <= 3
            or not 0 <= human_grades[pair] <= 3
        ):
            raise PoolReviewError("paired grades must be valid integer 0-3 query-paper judgments")
        if pair[0] not in query_buckets:
            raise PoolReviewError("a reviewed query has no intent bucket")

    count = len(pairs)
    assistant_counts = Counter(assistant_grades[pair] for pair in pairs)
    human_counts = Counter(human_grades[pair] for pair in pairs)
    confusion = Counter((assistant_grades[pair], human_grades[pair]) for pair in pairs)
    absolute_errors = [abs(assistant_grades[pair] - human_grades[pair]) for pair in pairs]
    exact = sum(error == 0 for error in absolute_errors)
    within_one = sum(error <= 1 for error in absolute_errors)
    quadratic_denominator = 9
    observed_disagreement = sum(
        confusion[(assistant, human)] * (assistant - human) ** 2
        for assistant in range(4)
        for human in range(4)
    ) / (count * quadratic_denominator)
    expected_disagreement = sum(
        assistant_counts[assistant] * human_counts[human] * (assistant - human) ** 2
        for assistant in range(4)
        for human in range(4)
    ) / (count * count * quadratic_denominator)

    by_query: dict[str, list[int]] = {}
    for pair, error in zip(pairs, absolute_errors, strict=True):
        by_query.setdefault(pair[0], []).append(error)

    return {
        "pair_count": count,
        "query_count": len(by_query),
        "exact_agreement": round(exact / count, 6),
        "within_one_grade": round(within_one / count, 6),
        "mean_absolute_error": round(sum(absolute_errors) / count, 6),
        "quadratic_weighted_kappa": (
            round(1 - observed_disagreement / expected_disagreement, 6)
            if expected_disagreement
            else None
        ),
        "assistant_grade_counts": {str(grade): assistant_counts[grade] for grade in range(4)},
        "human_grade_counts": {str(grade): human_counts[grade] for grade in range(4)},
        "confusion_matrix_rows_assistant_columns_human": [
            [confusion[(assistant, human)] for human in range(4)] for assistant in range(4)
        ],
        "per_query": {
            query_id: {
                "bucket": query_buckets[query_id],
                "pair_count": len(errors),
                "exact_agreement": round(sum(error == 0 for error in errors) / len(errors), 6),
                "mean_absolute_error": round(sum(errors) / len(errors), 6),
            }
            for query_id, errors in sorted(by_query.items())
        },
        "interpretation": {
            "purpose": (
                "diagnose agreement of prior assistant suggestions with this human-reviewed pool"
            ),
            "not_a_calibration_claim": True,
            "not_a_retrieval_quality_claim": True,
        },
    }
