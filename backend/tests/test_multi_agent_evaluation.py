from __future__ import annotations

from pathlib import Path

import pytest

from app.cli.evaluate_multi_agent import _load_input
from app.evaluation.multi_agent import (
    MultiAgentEvaluationError,
    TrialObservation,
    evaluate_paired_runs,
)

DATASET_HASH = "a" * 64


def _rows() -> list[TrialObservation]:
    rows: list[TrialObservation] = []
    # Task 1 wins only one multi-agent trial; task 2 wins both. Aggregation is
    # per question, so these contribute 0.5 and 1.0, not three independent tasks.
    for task_id, outcomes in (("TEST-1", (False, True)), ("TEST-2", (True, True))):
        for trial, multi_success in enumerate(outcomes, start=1):
            rows.extend(
                [
                    TrialObservation(
                        task_id=task_id,
                        trial=trial,
                        arm="single_agent",
                        task_success=False,
                        evidence_valid=True,
                        safety_violation=False,
                        observed_tokens=100,
                        cost_usd=0.01,
                        latency_ms=500,
                    ),
                    TrialObservation(
                        task_id=task_id,
                        trial=trial,
                        arm="multi_agent",
                        task_success=multi_success,
                        evidence_valid=True,
                        safety_violation=False,
                        observed_tokens=140,
                        cost_usd=0.014,
                        latency_ms=800,
                    ),
                ]
            )
    return rows


def test_paired_eval_aggregates_trials_by_question_and_reports_cost_safety_evidence() -> None:
    report = evaluate_paired_runs(
        _rows(),
        dataset_sha256=DATASET_HASH,
        synthetic=True,
        label_source="synthetic_fixture",
    )

    summary = report["summary"]
    assert report["quality_claim_allowed"] is False
    assert summary["task_count"] == 2
    assert summary["trial_count_per_arm"] == 4
    assert summary["single_agent"]["task_success_fraction"] == 0.0
    assert summary["multi_agent"]["task_success_fraction"] == 0.75
    assert summary["task_success_delta_multi_minus_single"] == 0.75
    assert summary["cost_ratio_multi_over_single"] == 1.4
    assert summary["safety_violation_delta_multi_minus_single"] == 0
    assert summary["evidence_valid_delta_multi_minus_single"] == 0.0
    assert report["per_task"][0]["multi_agent_success_fraction"] == 0.5
    assert report["interpretation"] == "synthetic contract data; no quality claim"


def test_paired_eval_is_reproducible_for_same_seed() -> None:
    kwargs = {
        "dataset_sha256": DATASET_HASH,
        "synthetic": True,
        "label_source": "synthetic_fixture",
        "bootstrap_seed": 17,
    }
    left = evaluate_paired_runs(_rows(), **kwargs)  # type: ignore[arg-type]
    right = evaluate_paired_runs(_rows(), **kwargs)  # type: ignore[arg-type]
    assert left["summary"] == right["summary"]


def test_paired_eval_rejects_unpaired_trials() -> None:
    rows = _rows()[:-1]
    with pytest.raises(MultiAgentEvaluationError, match="matching trials"):
        evaluate_paired_runs(
            rows,
            dataset_sha256=DATASET_HASH,
            synthetic=True,
            label_source="synthetic_fixture",
        )


def test_paired_eval_rejects_human_labels_on_synthetic_test_data() -> None:
    with pytest.raises(MultiAgentEvaluationError, match="human-reviewed"):
        evaluate_paired_runs(
            _rows(),
            dataset_sha256=DATASET_HASH,
            synthetic=True,
            label_source="human_reviewed",
            review_record_sha256="b" * 64,
        )


def test_paired_eval_requires_synthetic_labels_for_synthetic_inputs() -> None:
    with pytest.raises(MultiAgentEvaluationError, match="synthetic data"):
        evaluate_paired_runs(
            _rows(),
            dataset_sha256=DATASET_HASH,
            synthetic=True,
            label_source="ai_generated",
        )


def test_cli_binds_input_to_exact_synthetic_manifest_tasks() -> None:
    backend = Path(__file__).parents[1]
    data_dir = backend / "data" / "evaluation"
    report, input_hash = _load_input(
        data_dir / "TEST-multi-agent-paired-v1.json",
        data_dir / "TEST-multi-agent-taskset-v1.json",
    )

    assert report["dataset"]["manifest_sha256_verified"] == report["dataset"]["sha256"]
    assert report["dataset"]["dataset_id"] == "TEST-multi-agent-taskset-v1"
    assert len(input_hash) == 64
    assert report["quality_claim_allowed"] is False


def test_cli_rejects_manifest_digest_mismatch(tmp_path: Path) -> None:
    backend = Path(__file__).parents[1]
    data_dir = backend / "data" / "evaluation"
    input_path = tmp_path / "input.json"
    payload = (data_dir / "TEST-multi-agent-paired-v1.json").read_text(encoding="utf-8")
    input_path.write_text(payload.replace("5cd905", "0cd905", 1), encoding="utf-8")

    with pytest.raises(MultiAgentEvaluationError, match="does not match"):
        _load_input(input_path, data_dir / "TEST-multi-agent-taskset-v1.json")


def test_cli_rejects_observations_outside_frozen_manifest(tmp_path: Path) -> None:
    backend = Path(__file__).parents[1]
    data_dir = backend / "data" / "evaluation"
    input_path = tmp_path / "input.json"
    payload = (data_dir / "TEST-multi-agent-paired-v1.json").read_text(encoding="utf-8")
    input_path.write_text(payload.replace('"TEST-2"', '"TEST-3"'), encoding="utf-8")

    with pytest.raises(MultiAgentEvaluationError, match="exactly"):
        _load_input(input_path, data_dir / "TEST-multi-agent-taskset-v1.json")
