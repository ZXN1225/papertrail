"""Create a paired single-agent versus multi-agent evaluation report from JSON trials."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.evaluation.multi_agent import (
    MultiAgentEvaluationError,
    TrialObservation,
    evaluate_paired_runs,
    sha256_bytes,
)


def _read_json_object(path: Path, *, description: str) -> tuple[dict[str, Any], bytes]:
    content = path.read_bytes()
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MultiAgentEvaluationError(f"{description} must be valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise MultiAgentEvaluationError(f"{description} must be a JSON object")
    return payload, content


def _load_dataset(path: Path) -> tuple[dict[str, Any], str]:
    manifest, content = _read_json_object(path, description="dataset manifest")
    if set(manifest) != {"schema_version", "dataset_id", "synthetic", "tasks"}:
        raise MultiAgentEvaluationError("dataset manifest contains unsupported or missing fields")
    if manifest["schema_version"] != "papertrail.multi-agent-taskset.v1":
        raise MultiAgentEvaluationError("dataset manifest schema_version is unsupported")
    if not isinstance(manifest["dataset_id"], str) or not manifest["dataset_id"].strip():
        raise MultiAgentEvaluationError("dataset_id must be a non-empty string")
    if type(manifest["synthetic"]) is not bool or not isinstance(manifest["tasks"], list):
        raise MultiAgentEvaluationError("dataset synthetic and tasks fields are invalid")
    if manifest["synthetic"] and not manifest["dataset_id"].startswith("TEST-"):
        raise MultiAgentEvaluationError("synthetic dataset IDs must use the TEST- prefix")
    if not manifest["synthetic"] and manifest["dataset_id"].startswith("TEST-"):
        raise MultiAgentEvaluationError("real dataset IDs cannot use the TEST- prefix")
    task_ids: set[str] = set()
    task_fields = {"task_id", "synthetic", "challenge_type", "source_refs"}
    for task in manifest["tasks"]:
        if not isinstance(task, dict) or set(task) != task_fields:
            raise MultiAgentEvaluationError(
                "each dataset task must contain exactly documented fields"
            )
        task_id = task["task_id"]
        if not isinstance(task_id, str) or not task_id.strip() or task_id in task_ids:
            raise MultiAgentEvaluationError("dataset task IDs must be non-empty and unique")
        if (
            type(task["synthetic"]) is not bool
            or not isinstance(task["challenge_type"], str)
            or not task["challenge_type"].strip()
            or not isinstance(task["source_refs"], list)
            or any(not isinstance(ref, str) or not ref.strip() for ref in task["source_refs"])
        ):
            raise MultiAgentEvaluationError("dataset task metadata is invalid")
        if not manifest["synthetic"] and not task["source_refs"]:
            raise MultiAgentEvaluationError("real tasks must reference at least one source")
        if task["synthetic"] is not manifest["synthetic"]:
            raise MultiAgentEvaluationError("task synthetic flags must match the dataset")
        if manifest["synthetic"] and not task_id.startswith("TEST-"):
            raise MultiAgentEvaluationError("synthetic task IDs must use the TEST- prefix")
        if not manifest["synthetic"] and task_id.startswith("TEST-"):
            raise MultiAgentEvaluationError("real task IDs cannot use the TEST- prefix")
        task_ids.add(task_id)
    if not task_ids:
        raise MultiAgentEvaluationError("dataset manifest must contain at least one task")
    return manifest, sha256_bytes(content)


def _load_input(path: Path, dataset_path: Path) -> tuple[dict[str, Any], str]:
    payload, content = _read_json_object(path, description="input")
    manifest, manifest_sha256 = _load_dataset(dataset_path)
    allowed = {
        "dataset_sha256",
        "synthetic",
        "label_source",
        "review_record_sha256",
        "bootstrap_seed",
        "observations",
    }
    if set(payload) - allowed:
        raise MultiAgentEvaluationError("input contains unsupported top-level fields")
    raw_observations = payload.get("observations")
    if not isinstance(raw_observations, list):
        raise MultiAgentEvaluationError("observations must be a JSON array")
    observations: list[TrialObservation] = []
    fields = {
        "task_id",
        "trial",
        "arm",
        "task_success",
        "evidence_valid",
        "safety_violation",
        "observed_tokens",
        "cost_usd",
        "latency_ms",
    }
    for row in raw_observations:
        if not isinstance(row, dict) or set(row) != fields:
            raise MultiAgentEvaluationError(
                "each observation must contain exactly the documented fields"
            )
        try:
            observations.append(TrialObservation(**row))
        except TypeError as error:
            raise MultiAgentEvaluationError("observation fields have invalid types") from error

    observed_task_ids = {item.task_id for item in observations}
    manifest_task_ids = {task["task_id"] for task in manifest["tasks"]}
    if observed_task_ids != manifest_task_ids:
        raise MultiAgentEvaluationError("dataset tasks must match observed task IDs exactly")
    if payload.get("dataset_sha256") != manifest_sha256:
        raise MultiAgentEvaluationError("dataset_sha256 does not match the supplied manifest")
    if payload.get("synthetic") is not manifest["synthetic"]:
        raise MultiAgentEvaluationError("input synthetic flag does not match the dataset manifest")

    report = evaluate_paired_runs(
        observations,
        dataset_sha256=payload.get("dataset_sha256", ""),
        synthetic=payload.get("synthetic"),
        label_source=payload.get("label_source"),
        review_record_sha256=payload.get("review_record_sha256"),
        bootstrap_seed=payload.get("bootstrap_seed", 20261011),
    )
    report["dataset"]["dataset_id"] = manifest["dataset_id"]
    report["dataset"]["manifest_sha256_verified"] = manifest_sha256
    report["input_sha256"] = sha256_bytes(content)
    return report, sha256_bytes(content)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report, input_sha256 = _load_input(args.input, args.dataset)
    except (OSError, MultiAgentEvaluationError) as error:
        print(f"Paired evaluation failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "input_sha256": input_sha256,
                "output": str(args.output.resolve()),
                "synthetic": report["dataset"]["synthetic"],
                "quality_claim_allowed": report["quality_claim_allowed"],
                "summary": report["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
