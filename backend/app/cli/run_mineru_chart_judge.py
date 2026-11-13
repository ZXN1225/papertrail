"""Run an explicitly authorized, budgeted MinerU chart-task LLM judge."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.agent.model import OpenAIResponsesClient
from app.config import Settings
from app.evaluation.live_budget import BudgetedModelClient
from app.evaluation.mineru_chart_judge import (
    MineruChartJudgeError,
    estimate_mineru_chart_judge_cost,
    run_mineru_chart_judge,
)
from app.evaluation.mineru_chart_review import load_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-model", required=True)
    parser.add_argument("--judge-model", required=True)
    parser.add_argument("--max-tasks", type=int, default=20)
    parser.add_argument("--max-provider-calls", type=int, default=20)
    parser.add_argument("--max-cost-usd", required=True)
    parser.add_argument("--input-price-per-million-usd", required=True)
    parser.add_argument("--output-price-per-million-usd", required=True)
    parser.add_argument("--max-output-tokens", type=int, default=800)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--confirm-data-transfer",
        action="store_true",
        help="confirm chart questions, candidate facts, and human references may be sent to judge",
    )
    return parser


def _decimal(value: str, field: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{field} must be a positive decimal") from error
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{field} must be a positive finite decimal")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    provider: OpenAIResponsesClient | None = None
    try:
        max_cost = _decimal(args.max_cost_usd, "max-cost-usd")
        input_price = _decimal(args.input_price_per_million_usd, "input-price-per-million-usd")
        output_price = _decimal(args.output_price_per_million_usd, "output-price-per-million-usd")
        if (
            args.max_tasks < 1
            or args.max_provider_calls < 1
            or args.max_output_tokens < 1
            or args.seed < 0
        ):
            raise ValueError("task, provider-call, token and seed limits are invalid")
        dataset, dataset_sha256 = load_dataset(args.dataset)
        if dataset.get("judgment_status") != "human_reviewed":
            raise MineruChartJudgeError("chart judge requires a human-reviewed dataset")
        task_count = sum(
            row["split"] == "test" and row["reference_status"] != "uncertain"
            for row in dataset["tasks"]
        )
        if task_count > args.max_tasks or task_count > args.max_provider_calls:
            raise MineruChartJudgeError("held-out tasks exceed the configured call budget")
        if args.candidate_model.strip().casefold() == args.judge_model.strip().casefold():
            raise MineruChartJudgeError("judge model must differ from candidate model")
        budget_estimate = estimate_mineru_chart_judge_cost(
            dataset,
            max_output_tokens=args.max_output_tokens,
            input_price_per_million_usd=input_price,
            output_price_per_million_usd=output_price,
        )
        budget_estimate["max_cost_usd"] = str(max_cost)
        budget_estimate["full_run_fits_estimated_cost_cap"] = (
            Decimal(budget_estimate["estimated_max_cost_usd"]) <= max_cost
        )
        if args.execute and not budget_estimate["full_run_fits_estimated_cost_cap"]:
            raise MineruChartJudgeError(
                "full-run conservative estimate exceeds max-cost-usd; no provider calls made"
            )
    except (OSError, ValueError, TypeError, KeyError) as error:
        detail = str(error) if isinstance(error, MineruChartJudgeError) else type(error).__name__
        print(f"MinerU chart judge preflight failed: {detail}", file=sys.stderr)
        return 2

    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "dry_run_passed",
                    "provider_calls": 0,
                    "dataset_sha256": dataset_sha256,
                    "task_count": task_count,
                    "candidate_model": args.candidate_model,
                    "judge_model": args.judge_model,
                    "max_provider_calls": args.max_provider_calls,
                    "max_cost_usd": str(max_cost),
                    "budget_estimate": budget_estimate,
                    "quality_claim_allowed": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if not args.confirm_data_transfer:
        print("Live judging requires --confirm-data-transfer.", file=sys.stderr)
        return 2
    if dataset["synthetic"]:
        print("Live judging is disabled for synthetic chart datasets.", file=sys.stderr)
        return 2

    settings = Settings(
        llm_provider="openai",
        llm_model=args.judge_model,
        embedding_provider="disabled",
        llm_max_output_tokens=max(64, min(args.max_output_tokens, 4_096)),
    )
    if settings.llm_api_key is None:
        print("LLM_API_KEY is not configured; no provider calls were made.", file=sys.stderr)
        return 2
    if args.max_output_tokens > settings.llm_max_output_tokens:
        print("max-output-tokens exceeds configured LLM_MAX_OUTPUT_TOKENS.", file=sys.stderr)
        return 2

    output = args.output.resolve()
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(
                {"schema": "papertrail.mineru-chart-llm-judge.v1", "status": "running"}, stream
            )
            stream.write("\n")
    except (OSError, FileExistsError) as error:
        print(f"Could not reserve chart judge output: {type(error).__name__}", file=sys.stderr)
        return 2

    budgeted: BudgetedModelClient | None = None
    try:
        provider = OpenAIResponsesClient(settings)
        guarded = BudgetedModelClient(
            provider,
            input_price_per_million_usd=input_price,
            output_price_per_million_usd=output_price,
            max_cost_usd=max_cost,
            max_provider_calls=args.max_provider_calls,
            max_output_tokens=args.max_output_tokens,
        )
        budgeted = guarded
        report = run_mineru_chart_judge(
            dataset,
            dataset_sha256,
            guarded,
            candidate_model=args.candidate_model,
            judge_model=args.judge_model,
            seed=args.seed,
            max_tasks=args.max_tasks,
        )
        report["budget"].update(
            {
                "max_cost_usd": str(max_cost),
                "input_price_per_million_usd": str(input_price),
                "output_price_per_million_usd": str(output_price),
            }
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {
            "schema": "papertrail.mineru-chart-llm-judge.v1",
            "status": "preflight_failed",
            "error_type": type(error).__name__,
            "provider_calls": budgeted.calls_attempted if budgeted is not None else 0,
            "estimated_cost_usd": budgeted.estimated_spend_usd if budgeted is not None else "0",
            "gold_standard": False,
            "quality_claim_allowed": False,
        }
        print(f"MinerU chart judge failed: {type(error).__name__}", file=sys.stderr)
    finally:
        if provider is not None:
            provider.close()
    try:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        print(f"Could not save chart judge report: {type(error).__name__}", file=sys.stderr)
        return 3
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "report": str(output),
                "provider_calls": report.get("budget", {}).get("provider_calls", 0),
                "quality_claim_allowed": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
