"""Prepare an unscored, local human-review pack from the one-shot live trial."""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any

from app.cli.run_live_eval import ARMS, MODEL, POST_FIX_REPORT, ROOT

REVIEW_PACK = ROOT / "backend/reports/live_eval/gpt-5.6-sol-r01-r03-postfix-review.json"
TASK_IDS = ("R1", "R2", "R3", "R4", "R5", "R6")


class ReviewPackError(ValueError):
    """The local trial report cannot be turned into a trustworthy review pack."""


def _response_view(response: Any) -> dict[str, Any] | None:
    if response is None:
        return None
    if not isinstance(response, dict):
        raise ReviewPackError("response must be a JSON object")
    status = response.get("status")
    if not isinstance(status, str):
        raise ReviewPackError("response status is missing")
    return {
        "status": status,
        "answer": response.get("answer"),
        "claims": response.get("claims", []),
        "citations": response.get("citations", []),
        "warnings": response.get("warnings", []),
    }


def build_review_pack(raw: bytes) -> dict[str, Any]:
    """Preserve model output and locators without assigning human quality labels."""
    try:
        report = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReviewPackError("trial report must be valid UTF-8 JSON") from error
    if not isinstance(report, dict) or report.get("schema") != "papertrail.live-pilot.v1":
        raise ReviewPackError("trial report schema is invalid")
    if type(report.get("synthetic")) is not bool:
        raise ReviewPackError("trial synthetic marker is invalid")
    config = report.get("configuration")
    if (
        not isinstance(config, dict)
        or config.get("mode") != "post_fix_six_task"
        or report.get("model") != MODEL
    ):
        raise ReviewPackError("this review pack requires the fixed post-fix trial")
    runs = report.get("runs")
    if not isinstance(runs, list) or len(runs) > len(TASK_IDS) * len(ARMS):
        raise ReviewPackError("trial runs are missing or exceed the frozen scope")
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for run in runs:
        if not isinstance(run, dict):
            raise ReviewPackError("trial run must be a JSON object")
        task_id, arm, trial = run.get("task_id"), run.get("arm"), run.get("trial")
        if task_id not in TASK_IDS or arm not in ARMS or type(trial) is not int or trial != 1:
            raise ReviewPackError("trial run is outside the frozen six-task scope")
        key = (task_id, trial, arm)
        if key in seen:
            raise ReviewPackError("trial report contains a duplicate task/arm")
        seen.add(key)
        outcome = run.get("outcome")
        calls = run.get("provider_calls")
        if not isinstance(outcome, dict) or not isinstance(calls, list):
            raise ReviewPackError("trial outcome or provider calls are invalid")
        if (
            not isinstance(run.get("source_id"), str)
            or not run["source_id"]
            or not isinstance(run.get("question"), str)
            or not run["question"]
        ):
            raise ReviewPackError("trial source or question is missing")
        if arm == "multi_agent":
            if not isinstance(outcome.get("decision"), str) or not isinstance(
                outcome.get("workers"), list
            ):
                raise ReviewPackError("multi-agent decision or workers are missing")
        elif not isinstance(outcome.get("response"), dict):
            raise ReviewPackError("single-agent response is missing")
        workers = outcome.get("workers", [])
        if not isinstance(workers, list):
            raise ReviewPackError("multi-agent workers must be an array")
        worker_views: list[dict[str, Any]] = []
        for worker in workers:
            if not isinstance(worker, dict) or not isinstance(worker.get("name"), str):
                raise ReviewPackError("worker record is invalid")
            worker_views.append(
                {
                    "name": worker["name"],
                    "status": worker.get("status"),
                    "response": _response_view(worker.get("response")),
                }
            )
        response = _response_view(
            outcome.get("selected_response") if arm == "multi_agent" else outcome.get("response")
        )
        entries.append(
            {
                "task_id": task_id,
                "source_id": run.get("source_id"),
                "question": run.get("question"),
                "trial": trial,
                "arm": arm,
                "machine_decision": outcome.get("decision") if arm == "multi_agent" else None,
                "selected_response": response,
                "workers": worker_views,
                "provider_call_count": len(calls),
                "human_review": {
                    "task_success": None,
                    "answer_support": None,
                    "evidence_locator_valid": None,
                    "safety_violation": None,
                    "notes": None,
                },
            }
        )
    expected_entries = len(TASK_IDS) * len(ARMS)
    report_status = (
        "stopped"
        if report.get("halt_reason")
        else "completed"
        if len(entries) == expected_entries and isinstance(report.get("finished_at"), str)
        else "incomplete"
    )
    return {
        "schema": "papertrail.live-human-review-pack.v1",
        "synthetic": report.get("synthetic"),
        "quality_claim_allowed": False,
        "review_state": "awaiting_human_review",
        "source_report_sha256": hashlib.sha256(raw).hexdigest(),
        "source_report_status": report_status,
        "source_halt_reason": report.get("halt_reason"),
        "expected_entries": expected_entries,
        "observed_entries": len(entries),
        "entries": entries,
    }


def main() -> int:
    if REVIEW_PACK.exists():
        print("Local human-review pack already exists; refusing overwrite.", file=sys.stderr)
        return 2
    try:
        pack = build_review_pack(POST_FIX_REPORT.read_bytes())
    except (OSError, ReviewPackError) as error:
        print(f"Human-review preparation failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    REVIEW_PACK.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "prepared",
                "observed_entries": pack["observed_entries"],
                "expected_entries": pack["expected_entries"],
                "source_report_sha256": pack["source_report_sha256"],
                "output": str(REVIEW_PACK),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
