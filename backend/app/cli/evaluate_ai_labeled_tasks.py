"""Run the read-only AI-labeled evidence-grounding diagnostic over the licensed corpus."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.embeddings.client import (
    MAX_BATCH_SIZE,
    MAX_INPUT_CHARS,
    EmbeddingError,
    OpenAIEmbeddingClient,
)
from app.evaluation.ai_labeled_tasks import (
    AiLabeledTaskError,
    load_dataset,
    run_evaluation,
)
from app.storage.repository import PaperStore

DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "evaluation" / "ai-labeled-licensed-v1.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--retrieval-method",
        choices=("bm25", "dense", "hybrid", "bm25_dense_rerank"),
        action="append",
        help="repeat to compare methods; BM25 alone is the zero-provider default",
    )
    parser.add_argument("--max-query-embeddings", type=int)
    parser.add_argument("--max-cost-usd")
    parser.add_argument("--confirm-data-transfer", action="store_true")
    return parser


def _decimal_cost(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("max cost must be a positive decimal") from error
    if not result.is_finite() or result <= 0:
        raise ValueError("max cost must be a positive decimal")
    return result


def embed_task_queries(
    dataset: dict[str, Any],
    settings: Any,
    *,
    max_query_embeddings: int | None,
    max_cost_usd: str | None,
    confirm_data_transfer: bool,
    client_factory=OpenAIEmbeddingClient,
) -> tuple[dict[str, list[float]], dict[str, Any]]:
    if not confirm_data_transfer:
        raise ValueError("embedding-based retrieval requires --confirm-data-transfer")
    tasks = dataset["tasks"]
    if max_query_embeddings is None or max_query_embeddings < len(tasks):
        raise ValueError("--max-query-embeddings must cover the complete task set")
    if settings.embedding_provider != "openai" or settings.embedding_price_per_million_usd is None:
        raise ValueError(
            "priced OpenAI embeddings must be configured for embedding-based retrieval"
        )
    if max_cost_usd is None:
        raise ValueError("embedding-based retrieval requires --max-cost-usd")
    cost_limit = _decimal_cost(max_cost_usd)
    queries = [task["question"] for task in tasks]
    if any(not query.strip() or len(query) > MAX_INPUT_CHARS for query in queries):
        raise ValueError("task questions exceed the embedding input limit")
    token_upper_bound = sum(len(query.encode("utf-8")) for query in queries)
    price = Decimal(str(settings.embedding_price_per_million_usd))
    upper_cost = price * token_upper_bound / Decimal(1_000_000)
    if upper_cost > cost_limit:
        raise ValueError("UTF-8 byte upper-bound estimate exceeds --max-cost-usd")

    vectors: dict[str, list[float]] = {}
    input_tokens = 0
    calls = 0
    client = client_factory(settings)
    try:
        for offset in range(0, len(tasks), MAX_BATCH_SIZE):
            batch_tasks = tasks[offset : offset + MAX_BATCH_SIZE]
            batch = client.embed([task["question"] for task in batch_tasks])
            calls += 1
            input_tokens += batch.input_tokens
            vectors.update(
                {
                    task["task_id"]: vector
                    for task, vector in zip(batch_tasks, batch.vectors, strict=True)
                }
            )
    finally:
        client.close()
    actual_cost = price * input_tokens / Decimal(1_000_000)
    if actual_cost > cost_limit:
        raise ValueError("provider-reported query embedding cost exceeds --max-cost-usd")
    return vectors, {
        "model": client.model,
        "query_count": len(vectors),
        "provider_calls": calls,
        "input_tokens": input_tokens,
        "input_token_upper_bound": token_upper_bound,
        "estimated_upper_bound_cost_usd": str(upper_cost),
        "calculated_cost_usd": str(actual_cost),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset, digest = load_dataset(args.dataset)
        methods = args.retrieval_method or ["bm25"]
        if len(methods) != len(set(methods)):
            raise ValueError("retrieval methods must be unique")
        settings = get_settings()
        embeddings = None
        embedding_usage = {
            "model": None,
            "query_count": 0,
            "provider_calls": 0,
            "input_tokens": 0,
            "input_token_upper_bound": 0,
            "estimated_upper_bound_cost_usd": "0",
            "calculated_cost_usd": "0",
        }
        if any(method != "bm25" for method in methods):
            embeddings, embedding_usage = embed_task_queries(
                dataset,
                settings,
                max_query_embeddings=args.max_query_embeddings,
                max_cost_usd=args.max_cost_usd,
                confirm_data_transfer=args.confirm_data_transfer,
            )
        store = PaperStore(get_settings().resolved_data_storage_path, readonly=True)
        reports = {
            method: run_evaluation(
                store,
                dataset,
                digest,
                retrieval_method=method,
                query_embeddings=embeddings if method != "bm25" else None,
                embedding_model=embedding_usage["model"] if method != "bm25" else None,
            )
            for method in methods
        }
        report = reports[methods[0]]
        if len(reports) > 1:
            report = {
                "report_schema": "papertrail.ai-labeled-method-comparison.v1",
                "synthetic": dataset["synthetic"],
                "gold_standard": False,
                "quality_claim_allowed": False,
                "human_reviewed": False,
                "label_source": dataset["label_source"],
                "dataset_sha256": digest,
                "dataset": {
                    "id": dataset["dataset_id"],
                    "task_count": len(dataset["tasks"]),
                },
                "embedding_usage": embedding_usage,
                "methods": reports,
            }
        elif embedding_usage["provider_calls"]:
            report["embedding_usage"] = embedding_usage
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError:
        print(
            "Refusing to overwrite an existing report; choose a new --output path.",
            file=sys.stderr,
        )
        return 2
    except (EmbeddingError, OSError, ValueError, KeyError, TypeError) as error:
        message = str(error) if isinstance(error, AiLabeledTaskError) else type(error).__name__
        print(f"AI-labeled task evaluation failed: {message}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(output),
                "dataset_sha256": digest,
                "embedding_provider_calls": embedding_usage["provider_calls"],
                "methods": methods,
                "quality_claim_allowed": report["quality_claim_allowed"],
                "label_source": report["label_source"],
                "embedding_usage": embedding_usage,
                "summary": {
                    method: {
                        "answerable_retrieval_metrics": method_report["summary"][
                            "answerable_retrieval_metrics"
                        ],
                        "by_challenge_type": method_report["summary"]["by_challenge_type"],
                        "multi_hop_without_required_evidence": method_report["dataset"][
                            "multi_hop_without_required_evidence"
                        ],
                    }
                    for method, method_report in reports.items()
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
