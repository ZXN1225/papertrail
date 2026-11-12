from __future__ import annotations

import copy
import hashlib
import json

import pytest

from app.evaluation.mineru_chart_review import (
    MineruChartReviewError,
    _score_fact_lists,
    apply_review_pack,
    build_review_pack,
    evaluate_reviewed_dataset,
    validate_dataset,
)


def _hash(char: str) -> str:
    return hashlib.sha256(char.encode()).hexdigest()


def _task(
    *, task_id: str, source_id: str, split: str, page: int, predicted_facts: list[dict]
) -> dict:
    source_pdf_sha256 = _hash(source_id)
    parse_report_sha256 = _hash(f"parse:{source_id}")
    return {
        "task_id": task_id,
        "source_id": source_id,
        "split": split,
        "page_number": page,
        "page_image_ref": f"images/{task_id}.png",
        "page_image_sha256": _hash(f"image:{task_id}"),
        "element_id": f"TEST-element-{task_id}",
        "bbox": [1, 2, 30, 40],
        "source_pdf_sha256": source_pdf_sha256,
        "parse_report_sha256": parse_report_sha256,
        "question": "TEST What changes in this chart?",
        "predicted_facts": predicted_facts,
        "predicted_abstained": False,
    }


def _dataset() -> dict:
    test_id, dev_id = "TEST-source-test", "TEST-source-dev"
    test_task = _task(
        task_id="TEST-task-chart-01",
        source_id=test_id,
        split="test",
        page=1,
        predicted_facts=[
            {"fact_type": "axis_label", "value": " temperature "},
            {"fact_type": "numeric_value", "value": 10.1, "unit": "C"},
            {"fact_type": "trend", "value": "rises"},
            {"fact_type": "series_label", "value": "control"},
        ],
    )
    unanswerable = _task(
        task_id="TEST-task-chart-02",
        source_id=test_id,
        split="test",
        page=2,
        predicted_facts=[],
    )
    unanswerable["predicted_abstained"] = True
    dev_task = _task(
        task_id="TEST-task-chart-dev",
        source_id=dev_id,
        split="dev",
        page=3,
        predicted_facts=[],
    )
    page_audits = []
    for audit_id, source_id, split, page, predicted_count in (
        ("TEST-audit-test-1", test_id, "test", 1, 1),
        ("TEST-audit-test-2", test_id, "test", 2, 0),
        ("TEST-audit-dev-1", dev_id, "dev", 3, 0),
    ):
        page_audits.append(
            {
                "audit_id": audit_id,
                "source_id": source_id,
                "split": split,
                "page_number": page,
                "page_image_ref": f"images/{audit_id}.png",
                "page_image_sha256": _hash(f"image:{audit_id}"),
                "parse_report_sha256": _hash(f"parse:{source_id}"),
                "predicted_chart_count": predicted_count,
            }
        )
    for task in (test_task, unanswerable, dev_task):
        page_audit = next(
            row
            for row in page_audits
            if row["source_id"] == task["source_id"] and row["page_number"] == task["page_number"]
        )
        task["page_image_ref"] = page_audit["page_image_ref"]
        task["page_image_sha256"] = page_audit["page_image_sha256"]
    return {
        "schema": "papertrail.mineru-chart-tasks.v1",
        "dataset_id": "TEST-mineru-chart-review-v1",
        "synthetic": True,
        "gold_standard": False,
        "quality_claim_allowed": False,
        "sources": {
            source_id: {
                "pdf_sha256": _hash(source_id),
                "parse_report_sha256": _hash(f"parse:{source_id}"),
                "parser_version": "TEST-mineru-parser-v1",
                "rights_attested": True,
            }
            for source_id in (test_id, dev_id)
        },
        "tasks": [test_task, unanswerable, dev_task],
        "page_audits": page_audits,
    }


def _complete_pack(dataset: dict, dataset_sha256: str) -> dict:
    pack = build_review_pack(dataset, dataset_sha256)
    first, second = pack["rows"][:2]
    first["reviewed"] = True
    first["reference_status"] = "answerable"
    first["reference_facts"] = [
        {"fact_id": "TEST-fact-axis", "fact_type": "axis_label", "value": "Temperature"},
        {
            "fact_id": "TEST-fact-value",
            "fact_type": "numeric_value",
            "value": 10,
            "unit": "c",
            "absolute_tolerance": 0.2,
        },
        {"fact_id": "TEST-fact-trend", "fact_type": "trend", "value": "increases"},
        {"fact_id": "TEST-fact-comparison", "fact_type": "comparison", "value": "A > B"},
    ]
    second["reviewed"] = True
    second["reference_status"] = "unanswerable"
    second["reference_facts"] = []
    third = pack["rows"][2]
    third["reviewed"] = True
    third["reference_status"] = "unanswerable"
    third["reference_facts"] = []
    for row, status, reference_count in zip(
        pack["page_audits"], ("reviewed", "reviewed", "reviewed"), (1, 1, 0), strict=True
    ):
        row["review_status"] = status
        row["reference_chart_count"] = reference_count
        row["reviewed"] = True
    return pack


def test_chart_review_pack_scores_fact_types_tolerance_and_abstention() -> None:
    dataset = _dataset()
    dataset_sha256 = _hash("dataset")
    pack = _complete_pack(dataset, dataset_sha256)
    reviewed = apply_review_pack(
        dataset,
        dataset_sha256,
        pack,
        reviewer="TEST reviewer",
        reviewed_at="2026-11-12T00:00:00Z",
    )

    report = evaluate_reviewed_dataset(reviewed, _hash("reviewed-dataset"))

    assert report["judgment_status"] == "human_reviewed"
    assert report["gold_standard"] is False
    assert report["quality_claim_allowed"] is False
    assert report["test_task_count"] == 2
    assert report["test_source_count"] == 1
    assert report["scored_task_count"] == 2
    assert report["uncertain_task_count"] == 0
    assert report["fact_metrics"] == {
        "true_positive": 2,
        "predicted": 4,
        "reference": 4,
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
    }
    assert report["fact_metrics_by_type"]["numeric_value"]["f1"] == 1.0
    assert report["fact_metrics_by_type"]["trend"]["f1"] == 0.0
    assert report["abstention_accuracy"] == 1.0
    assert report["chart_detection"]["exact_chart_count_page_accuracy"] == 0.5
    assert report["chart_detection"]["missed_figure_page_count"] == 1
    assert report["chart_detection"]["count_metrics"]["recall"] == 0.5


def test_chart_review_requires_complete_reviewed_rows() -> None:
    dataset = _dataset()
    digest = _hash("dataset")
    pack = _complete_pack(dataset, digest)
    pack["rows"].pop()
    with pytest.raises(MineruChartReviewError, match="every chart task"):
        apply_review_pack(dataset, digest, pack, reviewer="TEST reviewer")

    pack = _complete_pack(dataset, digest)
    pack["rows"][0]["reviewed"] = False
    with pytest.raises(MineruChartReviewError, match="explicit human review"):
        apply_review_pack(dataset, digest, pack, reviewer="TEST reviewer")


def test_chart_review_rejects_stale_provenance_and_cross_split_documents() -> None:
    dataset = _dataset()
    digest = _hash("dataset")
    pack = _complete_pack(dataset, digest)
    pack["rows"][0]["page_image_sha256"] = _hash("different-image")
    with pytest.raises(MineruChartReviewError, match="provenance changed"):
        apply_review_pack(dataset, digest, pack, reviewer="TEST reviewer")

    invalid = copy.deepcopy(dataset)
    invalid["tasks"][0]["split"] = "dev"
    with pytest.raises(MineruChartReviewError, match="same split"):
        validate_dataset(invalid)

    aliased_pdf = copy.deepcopy(dataset)
    aliased_pdf["sources"]["TEST-source-dev"]["pdf_sha256"] = _hash("TEST-source-test")
    aliased_pdf["tasks"][2]["source_pdf_sha256"] = _hash("TEST-source-test")
    aliased_pdf["page_audits"][2]["parse_report_sha256"] = _hash("parse:TEST-source-dev")
    with pytest.raises(MineruChartReviewError, match="identical PDF hashes"):
        validate_dataset(aliased_pdf)


def test_chart_review_numeric_tolerance_matching_is_one_to_one() -> None:
    matched, false_positive, false_negative = _score_fact_lists(
        [
            {"fact_type": "numeric_value", "value": 10.4, "unit": "C"},
            {"fact_type": "numeric_value", "value": 9.6, "unit": "C"},
        ],
        [
            {
                "fact_id": "TEST-ref-1",
                "fact_type": "numeric_value",
                "value": 10,
                "unit": "C",
                "absolute_tolerance": 0.5,
            },
            {
                "fact_id": "TEST-ref-2",
                "fact_type": "numeric_value",
                "value": 10.5,
                "unit": "C",
                "absolute_tolerance": 0.1,
            },
        ],
    )
    assert (matched, false_positive, false_negative) == (2, 0, 0)


def test_uncertain_chart_tasks_are_excluded_from_scoring() -> None:
    dataset = _dataset()
    digest = _hash("dataset")
    pack = _complete_pack(dataset, digest)
    pack["rows"][1]["reference_status"] = "uncertain"
    pack["page_audits"][1]["review_status"] = "uncertain"
    pack["page_audits"][1]["reference_chart_count"] = None
    reviewed = apply_review_pack(dataset, digest, pack, reviewer="TEST reviewer")

    report = evaluate_reviewed_dataset(reviewed, _hash("reviewed-dataset"))

    assert report["test_task_count"] == 2
    assert report["scored_task_count"] == 1
    assert report["uncertain_task_count"] == 1
    assert report["chart_detection"]["uncertain_page_count"] == 1
    assert report["abstention_accuracy"] == 1.0


def test_chart_scores_reject_edits_after_human_review_import() -> None:
    dataset = _dataset()
    digest = _hash("dataset")
    reviewed = apply_review_pack(
        dataset,
        digest,
        _complete_pack(dataset, digest),
        reviewer="TEST reviewer",
    )
    reviewed["tasks"][0]["predicted_facts"][0]["value"] = "tampered prediction"

    with pytest.raises(MineruChartReviewError, match="changed after import"):
        evaluate_reviewed_dataset(reviewed, _hash("tampered-reviewed-dataset"))


def test_chart_review_rejects_non_gold_marker_changes_and_bad_numeric_facts() -> None:
    invalid = _dataset()
    invalid["gold_standard"] = True
    with pytest.raises(MineruChartReviewError, match="non-gold markers"):
        validate_dataset(invalid)

    invalid = _dataset()
    invalid["tasks"][0]["predicted_facts"][1]["value"] = float("nan")
    with pytest.raises(MineruChartReviewError, match="finite numeric"):
        validate_dataset(invalid)

    invalid = _dataset()
    invalid["page_audits"][1]["predicted_chart_count"] = 1
    with pytest.raises(MineruChartReviewError, match="zero-prediction page"):
        validate_dataset(invalid)

    invalid = _dataset()
    invalid["tasks"][0]["page_image_sha256"] = _hash("different-page")
    with pytest.raises(MineruChartReviewError, match="image hashes disagree"):
        validate_dataset(invalid)


def test_chart_review_cli_verifies_local_page_hashes_and_refuses_overwrite(
    tmp_path, capsys
) -> None:
    from app.cli.review_mineru_charts import main

    dataset = _dataset()
    for task in [*dataset["tasks"], *dataset["page_audits"]]:
        image = tmp_path / task["page_image_ref"]
        image.parent.mkdir(exist_ok=True)
        image.write_bytes(f"TEST image {task['page_image_ref']}".encode())
        task["page_image_sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
    dataset_path = tmp_path / "TEST-chart-dataset.json"
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
    pack_path = tmp_path / "TEST-chart-review-pack.json"

    assert main(["export", "--dataset", str(dataset_path), "--output", str(pack_path)]) == 0
    assert pack_path.is_file()
    assert main(["export", "--dataset", str(dataset_path), "--output", str(pack_path)]) == 2
    assert "MineruChartReviewError" in capsys.readouterr().err

    dataset_sha256 = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    pack = _complete_pack(dataset, dataset_sha256)
    pack_path.write_text(json.dumps(pack), encoding="utf-8")
    reviewed_path = tmp_path / "TEST-chart-reviewed.json"
    import_args = [
        "import",
        "--dataset",
        str(dataset_path),
        "--pack",
        str(pack_path),
        "--output",
        str(reviewed_path),
        "--reviewer",
        "TEST reviewer",
    ]
    assert main(import_args) == 2
    assert not reviewed_path.exists()
    assert main([*import_args, "--confirm-human-review"]) == 0
    report_path = tmp_path / "TEST-chart-report.json"
    assert main(["evaluate", "--dataset", str(reviewed_path), "--output", str(report_path)]) == 0
    assert json.loads(report_path.read_text(encoding="utf-8"))["quality_claim_allowed"] is False

    dataset["tasks"][0]["page_image_sha256"] = _hash("stale-image")
    stale_path = tmp_path / "TEST-chart-stale.json"
    stale_path.write_text(json.dumps(dataset), encoding="utf-8")
    assert (
        main(["export", "--dataset", str(stale_path), "--output", str(tmp_path / "never.json")])
        == 2
    )
