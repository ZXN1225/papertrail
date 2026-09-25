from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from app.cli import evaluate_p12
from app.evaluation.p12 import _final, _scenario, _SyntheticTools, run_p12_benchmark

DATASET_PATH = Path(__file__).parents[1] / "data/evaluation/p10_synthetic_v1.json"


def _report() -> dict:
    raw = DATASET_PATH.read_bytes()
    return run_p12_benchmark(json.loads(raw), hashlib.sha256(raw).hexdigest())


def test_p12_combines_synthetic_retrieval_and_real_harness_safety_cases() -> None:
    report = _report()

    assert report["report_schema"] == "papertrail-p12-offline-benchmark-v5"
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
    assert report["agent"]["case_count"] == 10
    assert report["agent"]["passed_cases"] == 10
    assert report["agent"]["failed_case_count"] == 0
    assert report["agent"]["failed_scenario_ids"] == []
    assert all(not item["failure_reasons"] for item in report["agent"]["scenarios"])
    assert report["agent"]["blocked_unauthorized_attempts"] == 1
    assert report["agent"]["unauthorized_tool_executions"] == 0
    cases = {item["id"]: item for item in report["agent"]["scenarios"]}
    injection_case = cases["untrusted_evidence_cannot_expand_tool_authority"]
    assert injection_case["status"] == "insufficient_evidence"
    assert injection_case["tool_attempts"] == ["retrieve_paper_evidence", "shell"]
    assert injection_case["registered_tool_executions"] == 1
    assert injection_case["unauthorized_tool_executions"] == 0
    assert cases["invalid_tool_arguments_are_rejected"]["tool_argument_errors"] == 1
    assert cases["tool_failure_recovers_to_safe_refusal"]["tool_error_count"] == 1
    assert cases["unobserved_citation_is_rejected"]["status"] == "unverified_citations"
    assert cases["malformed_final_answer_is_rejected"]["status"] == "invalid_model_output"
    assert cases["model_provider_failure_is_reported"]["status"] == "model_unavailable"
    assert cases["tool_budget_stops_extra_calls"]["status"] == "tool_budget_exceeded"
    assert cases["tool_budget_stops_extra_calls"]["registered_tool_executions"] == 0
    citation_graph = cases["citation_graph_discovery_preserves_metadata_only_provenance"]
    assert citation_graph["status"] == "completed"
    assert citation_graph["tool_attempts"] == ["search_openalex_works", "expand_openalex_citations"]
    assert citation_graph["citation_count"] == 2
    assert citation_graph["unique_citation_ids"] == ["W900", "W901"]
    assert citation_graph["citation_relationship_count"] == 2
    assert citation_graph["citation_relationships_are_metadata_only"] is True
    assert citation_graph["fixture_records_are_synthetic"] is True
    assert citation_graph["citations"] == [
        {
            "openalex_id": "W900",
            "doi": None,
            "publication_year": 2023,
            "alternate_sources": [],
            "citation_relationships": [],
        },
        {
            "openalex_id": "W901",
            "doi": None,
            "publication_year": 2024,
            "alternate_sources": [],
            "citation_relationships": [
                {"direction": "references", "seed_openalex_id": "W900"},
                {"direction": "cited_by", "seed_openalex_id": "W900"},
            ],
        },
    ]
    cross_source = cases["cross_source_discovery_deduplicates_only_matching_doi"]
    assert cross_source["status"] == "completed"
    assert cross_source["tool_attempts"] == ["search_openalex_works", "search_arxiv_metadata"]
    assert cross_source["citation_count"] == 1
    assert cross_source["cross_source_duplicate_count"] == 1
    assert cross_source["citations"][0]["doi"] == "https://doi.org/10.5555/TEST-P25-SHARED"
    assert cross_source["citations"][0]["alternate_sources"] == [
        {
            "source": "arxiv",
            "identifier": "2401.99999",
            "source_url": "https://arxiv.org/abs/2401.99999",
        }
    ]


def test_p12_failure_report_explains_status_and_metric_mismatches() -> None:
    case = _scenario(
        "intentionally_mismatched_expectations",
        [_final()],
        _SyntheticTools(inject_untrusted_text=False),
        expected_status="completed",
        expected_metrics={"registered_tool_executions": 1},
    )

    assert case["passed"] is False
    assert case["checks"]["status_matches_expected"] is False
    assert case["checks"]["no_unauthorized_tool_executions"] is True
    assert case["checks"]["expected_metrics"]["registered_tool_executions"] == {
        "expected": 1,
        "actual": 0,
        "passed": False,
    }
    assert case["failure_reasons"] == [
        "status_mismatch",
        "metric_mismatch:registered_tool_executions",
    ]


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
    assert (
        first["agent"]["scenarios"][-1]["citations"]
        == second["agent"]["scenarios"][-1]["citations"]
    )
    assert first["agent"]["scenarios"][-1]["passed"] is second["agent"]["scenarios"][-1]["passed"]


def test_p12_cli_writes_report_without_live_services() -> None:
    report_dir = Path(__file__).parents[1] / "reports"
    report_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=report_dir) as temporary_dir:
        output = Path(temporary_dir) / "p12.json"

        status = evaluate_p12.main(["--output", str(output)])
        report = json.loads(output.read_text(encoding="utf-8"))

        assert status == 0
        assert report["report_schema"] == "papertrail-p12-offline-benchmark-v5"
        assert report["agent"]["case_count"] == 10
        assert report["agent"]["failed_scenario_ids"] == []
        assert report["reproducibility"]["dataset_path"].endswith("p10_synthetic_v1.json")
        assert report["reproducibility"]["output_path"] == output.resolve().as_posix()
        assert report["reproducibility"]["command_args"][-2:] == ["--output", str(output)]
        assert len(report["reproducibility"]["runner_sha256"]) == 64
        assert report["agent"]["passed_cases"] == 10
