from __future__ import annotations

import pytest

from app.evaluation.grade_agreement import evaluate_grade_agreement
from app.evaluation.p36_pool import PoolReviewError


def test_grade_agreement_reports_pairwise_and_weighted_metrics():
    assistant = {("q1", "w1"): 0, ("q1", "w2"): 2, ("q2", "w3"): 3}
    human = {("q1", "w1"): 0, ("q1", "w2"): 1, ("q2", "w3"): 3}

    result = evaluate_grade_agreement(assistant, human, query_buckets={"q1": "a", "q2": "b"})

    assert result["pair_count"] == 3
    assert result["exact_agreement"] == pytest.approx(2 / 3)
    assert result["within_one_grade"] == 1.0
    assert result["mean_absolute_error"] == pytest.approx(1 / 3)
    assert result["quadratic_weighted_kappa"] == pytest.approx(0.896552)
    assert result["confusion_matrix_rows_assistant_columns_human"] == [
        [1, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 1],
    ]
    assert result["interpretation"]["not_a_calibration_claim"] is True


def test_grade_agreement_rejects_mismatched_or_invalid_pairs():
    with pytest.raises(PoolReviewError, match="exactly the same pairs"):
        evaluate_grade_agreement({("q", "w"): 2}, {("q", "other"): 2}, query_buckets={"q": "x"})
    with pytest.raises(PoolReviewError, match="valid integer 0-3"):
        evaluate_grade_agreement({("q", "w"): 4}, {("q", "w"): 2}, query_buckets={"q": "x"})


def test_grade_agreement_rejects_missing_query_bucket():
    with pytest.raises(PoolReviewError, match="no intent bucket"):
        evaluate_grade_agreement({("q", "w"): 1}, {("q", "w"): 1}, query_buckets={})
