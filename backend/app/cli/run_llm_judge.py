"""Run a blinded, budgeted LLM judge; default invocation performs no provider calls."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.agent.model import OpenAIResponsesClient
from app.config import Settings
from app.evaluation.ai_labeled_tasks import load_dataset
from app.evaluation.live_budget import BudgetedModelClient
from app.evaluation.llm_judge import (
    LLMJudgeError,
    load_answer_bundle,
    run_llm_judge,
)
from app.storage.repository import PaperStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--judge-model", required=True)
    parser.add_argument("--max-provider-calls", type=int, default=20)
    parser.add_argument("--max-cost-usd", required=True)
    parser.add_argument("--input-price-per-million-usd", required=True)
    parser.add_argument("--output-price-per-million-usd", required=True)
    parser.add_argument("--max-output-tokens", type=int, default=600)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--confirm-data-transfer",
        action="store_true",
        help=(
            "confirm benchmark answers and cited licensed excerpts may be sent "
            "to the judge provider"
        ),
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
    try:
        max_cost = _decimal(args.max_cost_usd, "max-cost-usd")
        input_price = _decimal(args.input_price_per_million_usd, "input-price-per-million-usd")
        output_price = _decimal(args.output_price_per_million_usd, "output-price-per-million-usd")
        if args.max_provider_calls < 1 or args.max_output_tokens < 1 or args.seed < 0:
            raise ValueError("provider, output-token and seed limits must be positive")
        dataset, dataset_sha256 = load_dataset(args.dataset)
        answer_bundle, answer_bundle_sha256 = load_answer_bundle(args.answers)
        if answer_bundle["dataset_sha256"] != dataset_sha256:
            raise LLMJudgeError("answer bundle dataset hash does not match --dataset")
        if args.judge_model.casefold() == answer_bundle["candidate_model"].casefold():
            raise LLMJudgeError("judge model must differ from candidate model")
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"LLM judge preflight failed: {type(error).__name__}", file=sys.stderr)
        return 2

    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "dry_run_passed",
                    "provider_calls": 0,
                    "dataset_sha256": dataset_sha256,
                    "answer_bundle_sha256": answer_bundle_sha256,
                    "answer_count": len(answer_bundle["answers"]),
                    "judge_model": args.judge_model,
                    "candidate_model": answer_bundle["candidate_model"],
                    "max_provider_calls": args.max_provider_calls,
                    "max_cost_usd": str(max_cost),
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
        print("Live judging is disabled for synthetic task datasets.", file=sys.stderr)
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
            json.dump({"schema": "papertrail.llm-judge-report.v1", "status": "running"}, stream)
            stream.write("\n")
    except (OSError, FileExistsError) as error:
        print(f"Could not reserve report output: {type(error).__name__}", file=sys.stderr)
        return 2

    store = PaperStore(settings.resolved_data_storage_path, readonly=True)
    provider: OpenAIResponsesClient | None = None
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
        report = run_llm_judge(
            store,
            dataset,
            dataset_sha256,
            answer_bundle,
            answer_bundle_sha256,
            guarded,
            judge_model=args.judge_model,
            seed=args.seed,
        )
        report["seed"] = args.seed
        report["budget"].update(
            {
                "max_provider_calls": args.max_provider_calls,
                "max_cost_usd": str(max_cost),
                "input_price_per_million_usd": str(input_price),
                "output_price_per_million_usd": str(output_price),
            }
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {
            "schema": "papertrail.llm-judge-report.v1",
            "status": "preflight_failed",
            "error_type": type(error).__name__,
            "provider_calls": 0,
            "gold_standard": False,
            "quality_claim_allowed": False,
        }
        print(f"LLM judge execution failed: {type(error).__name__}", file=sys.stderr)
    finally:
        if provider is not None:
            provider.close()
    try:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        print(f"Could not save judge report: {type(error).__name__}", file=sys.stderr)
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
    return 0 if report.get("schema") == "papertrail.llm-judge-report.v1" else 3


if __name__ == "__main__":
    raise SystemExit(main())
