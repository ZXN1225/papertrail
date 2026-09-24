from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from app.cli import evaluate_p12
from app.evaluation.p12 import run_p12_benchmark

DATASET_PATH = Path(__file__).parents[1] / "data/evaluation/p10_synthetic_v1.json"


def _report() -> dict:
    raw = DATASET_PATH.read_bytes()
    return run_p12_benchmark(json.loads(raw), hashlib.sha256(raw).hexdigest())


def test_p12_combines_synthetic_retrieval_and_real_harness_safety_cases() -> None:
    report = _report()

    assert report["report_schema"] == "papertrail-p12-offline-benchmark-v1"
    assert report["benchmark"]["network_calls"] == 0
    assert report["benchmark"]["real_database_used"] is False
    assert report["benchmark"]["real_model_used"] is False
    assert report["benchmark"]["quality_claim_allowed"] is False
    assert report["benchmark"]["estimated_cost_usd"] is None
    assert set(report["retrieval"]["methods"]) == {"bm25", "dense", "hybrid_rrf_k60"}
    assert report["rag_fixture"]["locator_exact"] is True
    assert report["rag_fixture"]["supporting_claim_exactly_present"] is True
    assert report["rag_fixture"]["evidence_precision"] == 1.0
    assert report["rag_fixture"]["evidence_recall"] == 1.0
    assert report["agent"]["case_count"] == 3
    assert report["agent"]["passed_cases"] == 3
    assert report["agent"]["blocked_unauthorized_attempts"] == 1
    assert report["agent"]["unauthorized_tool_executions"] == 0
    injection_case = report["agent"]["scenarios"][1]
    assert injection_case["status"] == "insufficient_evidence"
    assert injection_case["tool_attempts"] == ["retrieve_paper_evidence", "shell"]
    assert injection_case["tool_side_effect_executions"] == 1


def test_p12_quality_outputs_are_repeatable_while_runtime_fields_are_observations() -> None:
    first = _report()
    second = _report()

    assert first["retrieval"]["dataset"] == second["retrieval"]["dataset"]
    assert {
        name: method["metrics_macro_average"]
        for name, method in first["retrieval"]["methods"].items()
    } == {
        name: method["metrics_macro_average"]
        for name, method in second["retrieval"]["methods"].items()
    }
    assert [item["rankings"] for item in first["retrieval"]["queries"]] == [
        item["rankings"] for item in second["retrieval"]["queries"]
    ]
    assert [item["status"] for item in first["agent"]["scenarios"]] == [
        item["status"] for item in second["agent"]["scenarios"]
    ]


def test_p12_cli_writes_report_without_live_services() -> None:
    report_dir = Path(__file__).parents[1] / "reports"
    report_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=report_dir) as temporary_dir:
        output = Path(temporary_dir) / "p12.json"

        status = evaluate_p12.main(["--output", str(output)])
        report = json.loads(output.read_text(encoding="utf-8"))

        assert status == 0
        assert report["reproducibility"]["dataset_path"].endswith("p10_synthetic_v1.json")
        assert len(report["reproducibility"]["runner_sha256"]) == 64
        assert report["agent"]["passed_cases"] == 3
