"""Synthetic checks for the local live-answer review handoff."""

from __future__ import annotations

import json

import pytest

from app.cli import prepare_live_review as review


def _test_report(*, runs: list[dict], halt_reason: str | None = None) -> bytes:
    return json.dumps(
        {
            "schema": "papertrail.live-pilot.v1",
            "synthetic": True,
            "quality_claim_allowed": False,
            "model": review.MODEL,
            "configuration": {"mode": "post_fix_six_task"},
            "halt_reason": halt_reason,
            "runs": runs,
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _test_run(*, arm: str, outcome: dict) -> dict:
    return {
        "task_id": "TEST-R1",
        "source_id": "TEST-arxiv-paper",
        "question": "TEST-What is reported?",
        "trial": 1,
        "arm": arm,
        "outcome": outcome,
        "provider_calls": [{"final_text": "TEST-raw-model-output"}],
    }


def test_pack_preserves_answer_and_locator_without_claiming_human_review(monkeypatch) -> None:
    monkeypatch.setattr(review, "TASK_IDS", ("TEST-R1",))
    response = {
        "status": "completed",
        "answer": "TEST-supported candidate.",
        "claims": [{"text": "TEST-supported candidate.", "evidence": []}],
        "citations": [
            {
                "source": "arxiv",
                "arxiv_id": "TEST-arxiv-paper",
                "evidence": [
                    {
                        "chunk_id": "TEST-chunk-1",
                        "locator": "TEST-PDF page 3",
                        "excerpt": "TEST-exact excerpt",
                    }
                ],
            }
        ],
        "warnings": [],
    }
    raw = _test_report(
        runs=[
            _test_run(arm="skills_off", outcome={"response": response}),
            _test_run(
                arm="multi_agent",
                outcome={
                    "decision": "insufficient_workers",
                    "selected_response": None,
                    "workers": [
                        {
                            "name": "TEST-evidence-worker",
                            "status": "completed",
                            "response": response,
                        }
                    ],
                },
            ),
        ],
        halt_reason="TEST-cost_cap",
    )

    pack = review.build_review_pack(raw)

    assert pack["synthetic"] is True
    assert pack["quality_claim_allowed"] is False
    assert pack["review_state"] == "awaiting_human_review"
    assert pack["source_report_status"] == "stopped"
    assert pack["observed_entries"] == 2
    assert pack["expected_entries"] == 3
    assert (
        pack["entries"][0]["selected_response"]["citations"][0]["evidence"][0]["locator"]
        == "TEST-PDF page 3"
    )
    assert all(value is None for value in pack["entries"][0]["human_review"].values())
    assert pack["entries"][1]["machine_decision"] == "insufficient_workers"
    assert pack["entries"][1]["selected_response"] is None
    assert pack["entries"][1]["workers"][0]["response"]["answer"] == ("TEST-supported candidate.")
    assert "TEST-raw-model-output" not in json.dumps(pack)


def test_pack_rejects_duplicate_or_out_of_scope_runs(monkeypatch) -> None:
    monkeypatch.setattr(review, "TASK_IDS", ("TEST-R1",))
    run = _test_run(arm="skills_off", outcome={"response": {"status": "completed"}})
    with pytest.raises(review.ReviewPackError, match="duplicate"):
        review.build_review_pack(_test_report(runs=[run, run]))
    run["arm"] = "TEST-unknown-arm"
    with pytest.raises(review.ReviewPackError, match="outside"):
        review.build_review_pack(_test_report(runs=[run]))


def test_pack_rejects_other_mode_and_invalid_response(monkeypatch) -> None:
    monkeypatch.setattr(review, "TASK_IDS", ("TEST-R1",))
    raw = _test_report(runs=[]).replace(b"post_fix_six_task", b"r1_diagnostic")
    with pytest.raises(review.ReviewPackError, match="fixed post-fix"):
        review.build_review_pack(raw)
    run = _test_run(arm="skills_on", outcome={"response": {"answer": "TEST-answer"}})
    with pytest.raises(review.ReviewPackError, match="status is missing"):
        review.build_review_pack(_test_report(runs=[run]))


def test_missing_completion_marker_is_incomplete(monkeypatch) -> None:
    monkeypatch.setattr(review, "TASK_IDS", ("TEST-R1",))
    runs = [
        _test_run(arm=arm, outcome={"response": {"status": "completed"}}) for arm in review.ARMS[:2]
    ]
    runs.append(
        _test_run(
            arm="multi_agent",
            outcome={"decision": "insufficient_workers", "selected_response": None, "workers": []},
        )
    )
    report = json.loads(_test_report(runs=runs))
    assert review.build_review_pack(json.dumps(report).encode())["source_report_status"] == (
        "incomplete"
    )
    report["finished_at"] = "TEST-finished"
    assert review.build_review_pack(json.dumps(report).encode())["source_report_status"] == (
        "completed"
    )


def test_cli_writes_once_to_local_review_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(review, "TASK_IDS", ("TEST-R1",))
    source = tmp_path / "TEST-live-report.json"
    output = tmp_path / "TEST-live-review.json"
    source.write_bytes(_test_report(runs=[]))
    monkeypatch.setattr(review, "POST_FIX_REPORT", source)
    monkeypatch.setattr(review, "REVIEW_PACK", output)

    assert review.main() == 0
    saved = output.read_bytes()
    assert json.loads(saved)["review_state"] == "awaiting_human_review"
    assert review.main() == 2
    assert output.read_bytes() == saved
