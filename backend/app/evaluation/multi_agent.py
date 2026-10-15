"""Paired, question-level evaluation for single-agent and multi-agent runs.

The evaluator never infers semantic quality from model output. Callers must supply
human-reviewed task outcomes and bind them to a frozen dataset and review record.
Synthetic reports are always marked as unsuitable for quality claims.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Arm = Literal["single_agent", "multi_agent"]


class MultiAgentEvaluationError(ValueError):
    """Raised when paired multi-agent evaluation inputs are incomplete or unsafe."""


@dataclass(frozen=True)
class TrialObservation:
    task_id: str
    trial: int
    arm: Arm
    task_success: bool
    evidence_valid: bool
    safety_violation: bool
    observed_tokens: int
    cost_usd: float
    latency_ms: int


def _rate(values: Sequence[float | int | bool]) -> float | None:
    return sum(values) / len(values) if values else None


def _bootstrap_interval(
    values: Sequence[float], *, seed: int, samples: int = 5_000
) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(samples))
    return [means[int(0.025 * (samples - 1))], means[int(0.975 * (samples - 1))]]


def evaluate_paired_runs(
    observations: Sequence[TrialObservation],
    *,
    dataset_sha256: str,
    synthetic: bool,
    label_source: Literal["human_reviewed", "ai_generated", "synthetic_fixture"],
    review_record_sha256: str | None = None,
    bootstrap_seed: int = 20261011,
) -> dict[str, object]:
    """Compare paired arms, averaging repeated trials within each question first."""
    if not observations:
        raise MultiAgentEvaluationError("at least one paired observation is required")
    if (
        not isinstance(dataset_sha256, str)
        or len(dataset_sha256) != 64
        or any(c not in "0123456789abcdef" for c in dataset_sha256)
    ):
        raise MultiAgentEvaluationError("dataset_sha256 must be a lowercase SHA-256 digest")
    if type(synthetic) is not bool:
        raise MultiAgentEvaluationError("synthetic must be a boolean")
    if type(bootstrap_seed) is not int or bootstrap_seed < 0:
        raise MultiAgentEvaluationError("bootstrap_seed must be non-negative")
    if not isinstance(label_source, str) or label_source not in {
        "human_reviewed",
        "ai_generated",
        "synthetic_fixture",
    }:
        raise MultiAgentEvaluationError("label_source is unsupported")
    if review_record_sha256 is not None and (
        not isinstance(review_record_sha256, str)
        or len(review_record_sha256) != 64
        or any(c not in "0123456789abcdef" for c in review_record_sha256)
    ):
        raise MultiAgentEvaluationError("review_record_sha256 must be a lowercase SHA-256 digest")
    if label_source == "human_reviewed" and (
        synthetic
        or review_record_sha256 is None
        or len(review_record_sha256) != 64
        or any(c not in "0123456789abcdef" for c in review_record_sha256)
    ):
        raise MultiAgentEvaluationError(
            "human-reviewed quality evaluation requires real data and a review-record SHA-256"
        )
    if synthetic and label_source != "synthetic_fixture":
        raise MultiAgentEvaluationError("synthetic data must use synthetic_fixture labels")
    if not synthetic and label_source == "synthetic_fixture":
        raise MultiAgentEvaluationError("real data cannot use synthetic_fixture labels")

    grouped: dict[tuple[str, Arm], dict[int, TrialObservation]] = defaultdict(dict)
    for item in observations:
        if (
            not isinstance(item.task_id, str)
            or not item.task_id.strip()
            or type(item.trial) is not int
            or item.trial < 1
            or not isinstance(item.arm, str)
            or item.arm not in {"single_agent", "multi_agent"}
            or type(item.task_success) is not bool
            or type(item.evidence_valid) is not bool
            or type(item.safety_violation) is not bool
            or type(item.observed_tokens) is not int
            or item.observed_tokens < 0
            or isinstance(item.cost_usd, bool)
            or not isinstance(item.cost_usd, (int, float))
            or not math.isfinite(item.cost_usd)
            or item.cost_usd < 0
            or type(item.latency_ms) is not int
            or item.latency_ms < 0
        ):
            raise MultiAgentEvaluationError("trial observations contain invalid values")
        trials = grouped[(item.task_id, item.arm)]
        if item.trial in trials:
            raise MultiAgentEvaluationError("duplicate task/arm/trial observation")
        trials[item.trial] = item

    task_ids = sorted({task_id for task_id, _ in grouped})
    per_task: list[dict[str, object]] = []
    deltas: list[float] = []
    arm_trials: dict[str, list[TrialObservation]] = {"single_agent": [], "multi_agent": []}
    for task_id in task_ids:
        single = grouped.get((task_id, "single_agent"), {})
        multi = grouped.get((task_id, "multi_agent"), {})
        if not single or set(single) != set(multi):
            raise MultiAgentEvaluationError(
                "each task must have matching trials for both evaluation arms"
            )
        single_rows = [single[index] for index in sorted(single)]
        multi_rows = [multi[index] for index in sorted(multi)]
        arm_trials["single_agent"].extend(single_rows)
        arm_trials["multi_agent"].extend(multi_rows)
        single_success = float(_rate([row.task_success for row in single_rows]) or 0.0)
        multi_success = float(_rate([row.task_success for row in multi_rows]) or 0.0)
        delta = multi_success - single_success
        deltas.append(delta)
        per_task.append(
            {
                "task_id": task_id,
                "trial_count": len(single_rows),
                "single_agent_success_fraction": single_success,
                "multi_agent_success_fraction": multi_success,
                "success_delta": delta,
                "single_agent_cost_usd_mean": float(
                    _rate([row.cost_usd for row in single_rows]) or 0.0
                ),
                "multi_agent_cost_usd_mean": float(
                    _rate([row.cost_usd for row in multi_rows]) or 0.0
                ),
            }
        )

    metrics: dict[str, dict[str, float | int | None]] = {}
    for arm, rows in arm_trials.items():
        metrics[arm] = {
            "trial_count": len(rows),
            "task_count": len(task_ids),
            "task_success_fraction": float(
                _rate([float(task[f"{arm}_success_fraction"]) for task in per_task]) or 0.0
            ),
            "evidence_valid_fraction": float(_rate([row.evidence_valid for row in rows]) or 0.0),
            "safety_violation_count": sum(row.safety_violation for row in rows),
            "observed_tokens_total": sum(row.observed_tokens for row in rows),
            "cost_usd_total": round(sum(row.cost_usd for row in rows), 8),
            "latency_ms_mean": float(_rate([row.latency_ms for row in rows]) or 0.0),
        }
    single_cost = float(metrics["single_agent"]["cost_usd_total"] or 0.0)
    multi_cost = float(metrics["multi_agent"]["cost_usd_total"] or 0.0)
    mean_delta = float(_rate(deltas) or 0.0)
    return {
        "schema_version": "papertrail.multi-agent-paired-evaluation.v2",
        "dataset": {
            "sha256": dataset_sha256,
            "synthetic": synthetic,
            "label_source_declared": label_source,
            "review_record_sha256_declared": review_record_sha256,
        },
        # Digests and labels are caller-provided declarations. This evaluator
        # cannot authenticate review identity, source licenses, or label content.
        "quality_claim_allowed": False,
        "quality_claim_reason": (
            "evaluator does not authenticate dataset licensing or human review; "
            "results are descriptive until independently verified"
        ),
        "aggregation": {
            "unit": "task_id",
            "repeated_trials_averaged_within_task": True,
            "bootstrap": {"method": "paired_task_percentile", "seed": bootstrap_seed},
        },
        "summary": {
            "task_count": len(task_ids),
            "trial_count_per_arm": len(arm_trials["single_agent"]),
            "single_agent": metrics["single_agent"],
            "multi_agent": metrics["multi_agent"],
            "task_success_delta_multi_minus_single": mean_delta,
            "task_success_delta_95pct_bootstrap_interval": _bootstrap_interval(
                deltas, seed=bootstrap_seed
            ),
            "cost_ratio_multi_over_single": round(multi_cost / single_cost, 6)
            if single_cost > 0
            else None,
            "safety_violation_delta_multi_minus_single": int(
                metrics["multi_agent"]["safety_violation_count"] or 0
            )
            - int(metrics["single_agent"]["safety_violation_count"] or 0),
            "evidence_valid_delta_multi_minus_single": round(
                float(metrics["multi_agent"]["evidence_valid_fraction"] or 0.0)
                - float(metrics["single_agent"]["evidence_valid_fraction"] or 0.0),
                6,
            ),
        },
        "per_task": per_task,
        "interpretation": (
            "synthetic contract data; no quality claim"
            if synthetic
            else (
                "paired descriptive comparison; inspect interval, safety, evidence, cost, "
                "and latency"
            )
        ),
    }


def sha256_bytes(content: bytes) -> str:
    """Expose one canonical digest helper for frozen task and review files."""
    return hashlib.sha256(content).hexdigest()
