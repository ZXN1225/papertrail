from __future__ import annotations

import copy
import hashlib
import tempfile
from pathlib import Path

import pytest

from app.evaluation.research_tasks import (
    DEFAULT_DATASET_PATH,
    ResearchTaskEvaluationError,
    load_dataset,
    run_evaluation,
    validate_dataset,
)


def test_benchmark_fixture_is_isolated_and_has_expected_counts() -> None:
    dataset, digest = load_dataset()

    assert len(digest) == 64
    assert all(document["id"].startswith("TEST-") for document in dataset["documents"])
    assert all(task["id"].startswith("TEST-") for task in dataset["tasks"])
    assert all(document["synthetic"] is True for document in dataset["documents"])
    assert all(task["synthetic"] is True for task in dataset["tasks"])
    assert {document["split"] for document in dataset["documents"]} == {"dev", "test"}
    assert all(
        task["split"]
        == next(
            document["split"]
            for document in dataset["documents"]
            if document["id"]
            == (task.get("evidence") or {}).get("document_id", task.get("related_document_id"))
        )
        for task in dataset["tasks"]
    )
    assert sum(task["expected_answerable"] for task in dataset["tasks"]) == 24
    assert sum(not task["expected_answerable"] for task in dataset["tasks"]) == 16


def test_evaluation_reports_per_task_metrics_denominators_and_non_claim_flags() -> None:
    dataset, digest = load_dataset()

    report = run_evaluation(dataset, digest)

    assert report["evaluation"]["quality_claim_allowed"] is False
    assert report["evaluation"]["gold_standard"] is False
    assert report["dataset"]["quality_claim_allowed"] is False
    assert report["dataset"]["sha256"] == digest
    assert report["dataset"]["task_count"] == 40
    assert report["summary"]["query_count"] == 40
    assert report["summary"]["answerable_denominator"] == 24
    assert report["summary"]["unanswerable_denominator"] == 16
    assert report["summary"]["false_refusal"]["denominator"] == 24
    assert report["summary"]["false_answer"]["denominator"] == 16
    assert report["summary"]["false_answer"]["count"] == 0
    assert report["summary"]["unanswerable_lexical_retrieval"] == {
        "count": 16,
        "denominator": 16,
        "rate": 1.0,
        "meaning": (
            "negative tasks with lexical candidates before exact evidence gating; diagnostic only"
        ),
    }
    assert (
        report["summary"]["by_challenge_type"]["measurement_value_mismatch"][
            "unanswerable_denominator"
        ]
        == 11
    )
    assert len(report["per_task"]) == 40
    assert all("retrieved_document_ids" in task for task in report["per_task"])
    assert all(
        task["hit_at_1"] in (True, False)
        for task in report["per_task"]
        if task["expected_answerable"]
    )


def test_loader_digest_is_over_exact_dataset_bytes() -> None:
    raw = DEFAULT_DATASET_PATH.read_bytes()
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        path = Path(temp_dir) / "fixture.json"
        path.write_bytes(raw)
        dataset, digest = load_dataset(path)

    assert digest == hashlib.sha256(raw).hexdigest()
    assert dataset["dataset_id"] == "TEST-research-task-lexical-v2"


def test_v1_legacy_fixture_still_runs_all_but_rejects_split_selection() -> None:
    legacy_path = Path(__file__).parents[1] / "data/evaluation/TEST-research-task-lexical-v1.json"
    dataset, digest = load_dataset(legacy_path)

    report = run_evaluation(dataset, digest)

    assert report["dataset"]["split"] == "all"
    assert report["dataset"]["task_count"] == 40
    with pytest.raises(ResearchTaskEvaluationError, match="v1 dataset does not define"):
        run_evaluation(dataset, digest, split="test")


@pytest.mark.parametrize(
    ("split", "task_count", "document_count", "answerable", "unanswerable"),
    [("dev", 21, 6, 12, 9), ("test", 19, 6, 12, 7)],
)
def test_split_evaluation_is_document_disjoint_and_keeps_denominators(
    split: str,
    task_count: int,
    document_count: int,
    answerable: int,
    unanswerable: int,
) -> None:
    dataset, digest = load_dataset()

    report = run_evaluation(dataset, digest, split=split)

    assert report["dataset"]["split"] == split
    assert report["dataset"]["task_count"] == task_count
    assert report["dataset"]["document_count"] == document_count
    assert report["summary"]["answerable_denominator"] == answerable
    assert report["summary"]["unanswerable_denominator"] == unanswerable
    assert all(task["split"] == split for task in report["per_task"])
    allowed_documents = {
        document["id"] for document in dataset["documents"] if document["split"] == split
    }
    assert all(
        set(task["retrieved_document_ids"]).issubset(allowed_documents)
        for task in report["per_task"]
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.update(quality_claim_allowed=True), "quality_claim_allowed"),
        (lambda data: data.update(gold_standard=True), "gold standard"),
        (lambda data: data["documents"][0].update(id="DOC-001"), "TEST-*"),
        (
            lambda data: data["tasks"][0]["evidence"].update(anchor="not in source"),
            "document span",
        ),
        (
            lambda data: data["tasks"][0].update(split="test"),
            "task split must match",
        ),
        (
            lambda data: data["tasks"][24].update(required_fact="copper alloy sample"),
            "absent from the entire fixture corpus",
        ),
        (
            lambda data: data["tasks"][24].update(evidence={"document_id": "TEST-DOC-001"}),
            "must not have evidence",
        ),
        (lambda data: data["tasks"].pop(), "exactly 40"),
    ],
)
def test_dataset_validation_rejects_unsafe_or_incomplete_fixtures(mutation, message: str) -> None:
    dataset, _ = load_dataset()
    altered = copy.deepcopy(dataset)
    mutation(altered)

    with pytest.raises(ResearchTaskEvaluationError, match=message):
        validate_dataset(altered)


def test_runner_rejects_invalid_parameters_and_digest() -> None:
    dataset, digest = load_dataset()

    with pytest.raises(ResearchTaskEvaluationError, match="top_k"):
        run_evaluation(dataset, digest, top_k=0)
    with pytest.raises(ResearchTaskEvaluationError, match="min_overlap_tokens"):
        run_evaluation(dataset, digest, min_overlap_tokens=0)
    with pytest.raises(ResearchTaskEvaluationError, match="split must be"):
        run_evaluation(dataset, digest, split="validation")
    with pytest.raises(ResearchTaskEvaluationError, match="SHA-256"):
        run_evaluation(dataset, "not-a-digest")
