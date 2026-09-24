from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.hybrid import HybridEvaluationError, run_synthetic_hybrid_evaluation


def test_synthetic_hybrid_evaluation_is_isolated_and_repeatable() -> None:
    path = Path(__file__).parents[1] / "data/evaluation/p10_synthetic_v1.json"
    dataset = json.loads(path.read_text(encoding="utf-8"))
    first = run_synthetic_hybrid_evaluation(dataset, "fixture-hash")
    second = run_synthetic_hybrid_evaluation(dataset, "fixture-hash")

    assert first["dataset"]["synthetic"] is True
    assert first["dataset"]["quality_claim_allowed"] is False
    assert first["dataset"]["embedding_calls"] == 0
    assert first["dataset"]["document_count"] == 6
    assert first["dataset"]["query_count"] == 4
    assert first["methods"].keys() == {"bm25", "dense", "hybrid_rrf_k60"}
    assert [query["rankings"] for query in first["queries"]] == [
        query["rankings"] for query in second["queries"]
    ]
    assert all("ndcg@10" in method["metrics_macro_average"] for method in first["methods"].values())


def test_synthetic_hybrid_evaluation_rejects_unmarked_or_non_test_documents() -> None:
    with pytest.raises(HybridEvaluationError, match="synthetic=true"):
        run_synthetic_hybrid_evaluation({"synthetic": False}, "hash")
    dataset = {
        "synthetic": True,
        "documents": [
            {
                "id": "W123",
                "synthetic": True,
                "title": "real",
                "text": "real text",
                "fixture_vector": [1.0],
            }
        ],
        "queries": [
            {
                "id": "TEST-P10-Q-001",
                "text": "test query",
                "fixture_vector": [1.0],
                "relevance": {"W123": 0},
            }
        ],
    }
    with pytest.raises(HybridEvaluationError, match=r"TEST-\*"):
        run_synthetic_hybrid_evaluation(dataset, "hash")
