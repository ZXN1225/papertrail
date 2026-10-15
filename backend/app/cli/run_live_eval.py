"""Run the frozen six-question, read-only R06/R07 pilot after explicit opt-in.

Default invocation is a dry run. The live report stays in an ignored local directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.agent.harness import AgentHarness
from app.agent.model import OpenAIResponsesClient
from app.agent.multi_agent_experiment import MultiAgentExperiment, WorkerSpec
from app.agent.tools import PaperToolRegistry
from app.config import Settings
from app.evaluation.live_budget import BudgetedModelClient
from app.storage.repository import PaperStore

ROOT = Path(__file__).resolve().parents[3]
FROZEN = ROOT / "docs/research/R01-R03-real-evidence-pilot-v1.json"
REVIEW = ROOT / "docs/research/R01-R03-real-evidence-pilot-human-review-v1.json"
TASKSET = ROOT / "backend/data/evaluation/arxiv-r01-r03-human-pilot-taskset-v1.json"
REPORT = ROOT / "backend/reports/live_eval/gpt-5.6-sol-r01-r03-6x1.json"
POST_FIX_REPORT = ROOT / "backend/reports/live_eval/gpt-5.6-sol-r01-r03-postfix-6x1.json"
DIAGNOSTIC_REPORT = ROOT / "backend/reports/live_eval/gpt-5.6-sol-r1-diagnostic-1x1.json"
DIAGNOSTIC_VERIFICATION_REPORT = (
    ROOT / "backend/reports/live_eval/gpt-5.6-sol-r1-diagnostic-verify-1x1.json"
)
EXPECTED_SHA = {
    FROZEN: "9ceb30530faff7fae5a6ea085479b6755d6277077211c306e6758cd52e2ae0e3",
    REVIEW: "4b9ff6eef31968df19343c06407a01be4c5b17826b1c9dde3999696d58fd8f5d",
    TASKSET: "9122147fa003be028a74c210e36e7df23d7bf49cd02e7e98f9ae4d480e658a0b",
}
MODEL = "gpt-5.6-sol"
CAP = Decimal("2.00")
# Deliberately use the long-context tariff as a conservative local estimate.
# This is an estimate, not a provider-side spending control.
INPUT_PRICE = Decimal("8")
OUTPUT_PRICE = Decimal("30")
MAX_STEPS = 2
MAX_OUTPUT_TOKENS = 600
MAX_PROVIDER_CALLS = 48  # Six tasks, four total workers, two steps each.
ARMS = ("skills_off", "skills_on", "multi_agent")


class PilotError(RuntimeError):
    """A public, secret-free pilot preflight or execution error."""


class ScopedEvidenceTools:
    """Expose only local BM25 retrieval for one licensed arXiv source."""

    def __init__(self, store: PaperStore, source_id: str) -> None:
        self.registry = PaperToolRegistry(store)
        self.source_id = source_id
        self.observations: list[dict[str, Any]] = []
        self.calls = 0

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return self.definitions_for(None)

    def definitions_for(self, allowed_names: frozenset[str] | None) -> list[dict[str, Any]]:
        if self.calls:
            return []
        allowed = frozenset({"retrieve_paper_evidence"})
        if allowed_names is not None:
            allowed &= allowed_names
        definitions = self.registry.definitions_for(allowed)
        for definition in definitions:
            definition["description"] = (
                "Retrieve up to eight approved excerpts from this exact arXiv paper using "
                "local BM25 only. Cite observed chunk IDs and quotes."
            )
            properties = definition["parameters"]["properties"]
            properties["source_type"]["enum"] = ["arxiv"]
            properties["source_id"]["enum"] = [self.source_id]
            properties["retrieval_method"]["enum"] = ["bm25"]
        return definitions

    def execute(
        self, name: str, arguments: str, *, allowed_names: frozenset[str] | None = None
    ) -> dict[str, Any]:
        if self.calls:
            result = {"status": "error", "code": "single_retrieval_limit_reached"}
            self.observations.append({"tool": name, "arguments": None, "result": result})
            return result
        self.calls += 1
        try:
            args = json.loads(arguments)
        except (ValueError, TypeError):
            args = None
        if name != "retrieve_paper_evidence" or (
            allowed_names is not None and name not in allowed_names
        ):
            result = {"status": "error", "code": "tool_not_allowed"}
        elif not isinstance(args, dict) or (
            args.get("source_type") != "arxiv"
            or args.get("source_id") != self.source_id
            or args.get("retrieval_method") != "bm25"
        ):
            result = {"status": "error", "code": "source_scope_or_method_invalid"}
        else:
            result = self.registry.execute(name, arguments, allowed_names=allowed_names)
            items = result.get("items")
            if isinstance(items, list):
                keep = {
                    "arxiv_id",
                    "source_id",
                    "source_type",
                    "title",
                    "source_url",
                    "chunk_id",
                    "locator",
                    "page_number",
                    "element_type",
                    "excerpt",
                    "score",
                    "license_id",
                    "content_sha256",
                }
                result = {
                    **{key: value for key, value in result.items() if key != "items"},
                    "items": [
                        {key: value for key, value in item.items() if key in keep}
                        for item in items
                        if isinstance(item, dict)
                    ],
                }
        self.observations.append({"tool": name, "arguments": args, "result": result})
        return result


def _verified_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA[path]:
        raise PilotError(f"Frozen input digest changed: {path.name}")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise PilotError(f"Frozen input must be a JSON object: {path.name}")
    return payload


def _preflight(store: PaperStore) -> list[dict[str, str]]:
    frozen = _verified_json(FROZEN)
    review = _verified_json(REVIEW)
    taskset = _verified_json(TASKSET)
    if (
        frozen.get("synthetic") is not False
        or review.get("review_status") != "human_reviewed_single_reviewer"
        or taskset.get("synthetic") is not False
    ):
        raise PilotError("Frozen real-paper review status is invalid")
    tasks = frozen.get("tasks")
    if not isinstance(tasks, list) or [row.get("id") for row in tasks] != [
        "R1",
        "R2",
        "R3",
        "R4",
        "R5",
        "R6",
    ]:
        raise PilotError("Frozen six-task order changed")
    if [row.get("task_id") for row in taskset["tasks"]] != [row["id"] for row in tasks]:
        raise PilotError("Task manifest no longer matches frozen pilot")
    if [row.get("id") for row in review["labels"]] != [row["id"] for row in tasks]:
        raise PilotError("Human review IDs no longer match frozen pilot")
    for source_id, source in frozen["sources"].items():
        if source.get("license_id") != "CC-BY-4.0":
            raise PilotError(f"Source license changed: {source_id}")
        chunks = store.list_current_fulltext_chunks(source_type="arxiv", source_id=source_id)
        if not chunks or {row["content_sha256"] for row in chunks} != {
            source["indexed_content_sha256"]
        }:
            raise PilotError(f"Approved current index digest changed: {source_id}")
    return [
        {"id": row["id"], "source_id": row["source_id"], "question": row["question"]}
        for row in tasks
    ]


def _save(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _run_single(
    model: BudgetedModelClient,
    store: PaperStore,
    task: dict[str, str],
    *,
    skills_enabled: bool,
) -> dict[str, Any]:
    tools = ScopedEvidenceTools(store, task["source_id"])
    prompt = f"[paper-qa] Answer using arXiv:{task['source_id']} only. {task['question']}"
    response = AgentHarness(
        model,
        tools,  # type: ignore[arg-type]  # Same narrow registry protocol, stricter execution.
        max_steps=MAX_STEPS,
        max_tool_calls=3,
        max_total_tokens=20_000,
        max_context_chars=120_000,
        deadline_seconds=60.0,
        skills_enabled=skills_enabled,
    ).run(prompt)
    return {"response": response.model_dump(mode="json"), "observations": tools.observations}


def _run_multi(
    model: BudgetedModelClient, store: PaperStore, task: dict[str, str]
) -> dict[str, Any]:
    observations: dict[str, list[dict[str, Any]]] = {}

    def worker(name: str) -> WorkerSpec:
        def run(
            prompt: str,
            token_budget: int,
            tool_budget: int,
            deadline: float,
            cancelled: Any,
        ) -> Any:
            tools = ScopedEvidenceTools(store, task["source_id"])
            response = AgentHarness(
                model,
                tools,  # type: ignore[arg-type]
                max_steps=MAX_STEPS,
                max_tool_calls=min(3, tool_budget),
                max_total_tokens=min(20_000, token_budget),
                max_context_chars=120_000,
                deadline_seconds=deadline,
                cancellation_requested=cancelled,
                skills_enabled=True,
            ).run(prompt)
            observations[name] = tools.observations
            return response

        return WorkerSpec(name, run)

    prompt = f"[paper-qa] Answer using arXiv:{task['source_id']} only. {task['question']}"
    result = MultiAgentExperiment(
        [worker("evidence_worker"), worker("independent_checker")],
        max_workers=2,
        max_total_tokens=40_000,
        max_tool_calls=6,
        deadline_seconds=120.0,
    ).run(prompt)
    return {
        "decision": result.decision,
        "selected_response": (
            result.selected_response.model_dump(mode="json") if result.selected_response else None
        ),
        "workers": [
            {
                "name": item.name,
                "status": item.status,
                "response": item.response.model_dump(mode="json"),
            }
            for item in result.workers
        ],
        "observations": observations,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Opt in to the authorized live run")
    parser.add_argument("--confirm-licensed-excerpts", action="store_true")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--max-cost-usd", default="2.00")
    diagnostic = parser.add_mutually_exclusive_group()
    diagnostic.add_argument(
        "--diagnostic-r1",
        action="store_true",
        help="Isolated R1 skills-off diagnostic; max USD 0.50, two provider calls",
    )
    diagnostic.add_argument(
        "--verify-diagnostic-r1",
        action="store_true",
        help="One post-fix R1 check; max USD 0.45, two provider calls",
    )
    diagnostic.add_argument(
        "--post-fix-six-task",
        action="store_true",
        help="One fixed six-task comparison with a separate immutable local report",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cap = Decimal(args.max_cost_usd)
    except InvalidOperation:
        print("Invalid USD cap.", file=sys.stderr)
        return 2
    diagnostic_mode = args.diagnostic_r1 or args.verify_diagnostic_r1
    max_cap = (
        Decimal("0.45")
        if args.verify_diagnostic_r1
        else Decimal("0.50")
        if args.diagnostic_r1
        else CAP
    )
    if args.model != MODEL or cap <= 0 or cap > max_cap:
        print(f"This mode permits gpt-5.6-sol and at most USD {max_cap}.", file=sys.stderr)
        return 2
    if args.execute and not args.confirm_licensed_excerpts:
        print("Live run requires --confirm-licensed-excerpts.", file=sys.stderr)
        return 2
    report_path = (
        DIAGNOSTIC_VERIFICATION_REPORT
        if args.verify_diagnostic_r1
        else DIAGNOSTIC_REPORT
        if args.diagnostic_r1
        else POST_FIX_REPORT
        if args.post_fix_six_task
        else REPORT
    )
    if args.execute and report_path.exists():
        print("A prior local run exists; refusing a second paid execution.", file=sys.stderr)
        return 2
    try:
        # The pilot chooses its own fixed model; an unrelated product LLM_MODEL
        # setting must not alter this frozen experiment.
        settings = Settings(llm_provider="disabled", embedding_provider="disabled")
        store = PaperStore(settings.resolved_data_storage_path, readonly=True)
        tasks = _preflight(store)
        if diagnostic_mode:
            tasks = tasks[:1]
    except (OSError, ValueError, KeyError, TypeError, PilotError) as error:
        print(f"Live pilot preflight failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    arms = ("skills_off",) if diagnostic_mode else ARMS
    max_provider_calls = 2 if diagnostic_mode else MAX_PROVIDER_CALLS
    summary = {
        "model": MODEL,
        "mode": (
            "r1_diagnostic_verification"
            if args.verify_diagnostic_r1
            else "r1_diagnostic"
            if args.diagnostic_r1
            else "post_fix_six_task"
            if args.post_fix_six_task
            else "six_task_pilot"
        ),
        "tasks": len(tasks),
        "trials_per_task": 1,
        "arms": list(arms),
        "max_provider_calls": max_provider_calls,
        "max_model_steps_per_worker": MAX_STEPS,
        "max_retrieval_calls_per_worker": 1,
        "retrieval_method": "bm25",
        "retrieval_source_scope": "exact_arxiv_id_per_task",
        "max_context_chars_per_worker": 120_000,
        "max_observed_tokens_per_worker": 20_000,
        "max_output_tokens_per_request": MAX_OUTPUT_TOKENS,
        "max_cost_usd": str(cap),
        "conservative_input_price_usd_per_million": str(INPUT_PRICE),
        "conservative_output_price_usd_per_million": str(OUTPUT_PRICE),
        "report": str(report_path),
        "credential_configured": settings.llm_api_key is not None,
    }
    if not args.execute:
        print(json.dumps({"status": "dry_run_passed", **summary}, ensure_ascii=False))
        return 0
    if settings.llm_api_key is None:
        print("OpenAI API key is not configured locally; no paid calls were made.", file=sys.stderr)
        return 2
    try:
        live_settings = Settings(
            llm_provider="openai",
            llm_api_key=settings.llm_api_key,
            llm_model=MODEL,
            llm_max_output_tokens=MAX_OUTPUT_TOKENS,
            llm_timeout_seconds=60,
            embedding_provider="disabled",
        )
        provider = OpenAIResponsesClient(live_settings)
        model = BudgetedModelClient(
            provider,
            input_price_per_million_usd=INPUT_PRICE,
            output_price_per_million_usd=OUTPUT_PRICE,
            max_cost_usd=cap,
            max_provider_calls=max_provider_calls,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    except ValueError as error:
        print(f"Live pilot configuration failed: {type(error).__name__}", file=sys.stderr)
        return 2
    report: dict[str, Any] = {
        "schema": "papertrail.live-pilot.v1",
        "synthetic": False,
        "quality_claim_allowed": False,
        "model": MODEL,
        "configuration": summary,
        "frozen_sha256": {path.name: digest for path, digest in EXPECTED_SHA.items()},
        "started_at": datetime.now(UTC).isoformat(),
        "runs": [],
        "estimated_spend_usd": "0",
        "halt_reason": None,
    }
    _save(report, report_path)  # Reserve the one-shot path before any paid request.
    try:
        for task in tasks:
            for arm in arms:
                if model.halt_reason:
                    break
                call_start = len(model.call_usage)
                if arm == "multi_agent":
                    outcome = _run_multi(model, store, task)
                else:
                    outcome = _run_single(model, store, task, skills_enabled=arm == "skills_on")
                report["runs"].append(
                    {
                        "task_id": task["id"],
                        "source_id": task["source_id"],
                        "question": task["question"],
                        "trial": 1,
                        "arm": arm,
                        "outcome": outcome,
                        "provider_calls": [vars(item) for item in model.call_usage[call_start:]],
                    }
                )
                report["estimated_spend_usd"] = model.estimated_spend_usd
                report["halt_reason"] = model.halt_reason
                _save(report, report_path)
            if model.halt_reason:
                break
    finally:
        provider.close()
        report["estimated_spend_usd"] = model.estimated_spend_usd
        report["halt_reason"] = model.halt_reason
        report["finished_at"] = datetime.now(UTC).isoformat()
        _save(report, report_path)
    print(
        json.dumps(
            {
                "status": "stopped" if model.halt_reason else "completed",
                "runs": len(report["runs"]),
                "provider_calls": model.calls_attempted,
                "estimated_spend_usd": model.estimated_spend_usd,
                "halt_reason": model.halt_reason,
                "report": str(report_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if not model.halt_reason else 3


if __name__ == "__main__":
    raise SystemExit(main())
