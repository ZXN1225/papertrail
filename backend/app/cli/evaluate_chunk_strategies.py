"""Compare versioned PDF chunk size and overlap strategies on a frozen read-only corpus."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.cli.evaluate_ai_labeled_tasks import (
    embed_task_queries,
    estimate_task_query_embedding_budget,
)
from app.config import get_settings
from app.embeddings.client import EmbeddingError
from app.evaluation.chunking import ChunkStrategyEvaluationError, run_evaluation
from app.evaluation.fulltext_retrieval import DEFAULT_DATASET_PATH, load_dataset
from app.storage.repository import PaperStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument(
        "--output", type=Path, default=Path("reports/current-chunk-strategy-v1.json")
    )
    parser.add_argument(
        "--parent-embedding-rerank",
        action="store_true",
        help="compare parent-vector proxy reranking; sends task questions for query embeddings",
    )
    parser.add_argument("--max-query-embeddings", type=int)
    parser.add_argument("--max-cost-usd")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "validate the local rerank index and estimate query-only transfer cost without "
            "a provider call"
        ),
    )
    parser.add_argument("--confirm-data-transfer", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset, digest = load_dataset(args.dataset)
        settings = get_settings()
        output = args.output.resolve()
        if args.dry_run and not args.parent_embedding_rerank:
            raise ValueError("--dry-run is available only with --parent-embedding-rerank")
        if not args.dry_run and output.exists():
            raise FileExistsError
        if not args.dry_run:
            output.parent.mkdir(parents=True, exist_ok=True)
        store = PaperStore(settings.resolved_data_storage_path, readonly=True)
        query_embeddings = None
        embedding_usage = None
        if args.parent_embedding_rerank:
            if not args.dry_run and not args.confirm_data_transfer:
                raise ValueError("embedding-based reranking requires --confirm-data-transfer")
            if (
                not isinstance(settings.embedding_model, str)
                or not settings.embedding_model.strip()
            ):
                raise ValueError("embedding-based reranking requires a configured embedding model")
            index_status = _rerank_index_status(store, dataset, digest, settings)
            if args.dry_run:
                embedding_usage = estimate_task_query_embedding_budget(
                    dataset,
                    settings,
                    max_query_embeddings=args.max_query_embeddings,
                    max_cost_usd=args.max_cost_usd,
                )
                print(
                    json.dumps(
                        {
                            "status": "dry_run_passed",
                            "dataset_sha256": digest,
                            "query_embedding_model": settings.embedding_model,
                            "embedding_provider_enabled": settings.embedding_provider == "openai",
                            **index_status,
                            "source_count": len(dataset["sources"]),
                            **embedding_usage,
                            "provider_calls": 0,
                            "data_transfer_approved": False,
                            "confirm_data_transfer_required_for_execute": True,
                            "report_written": False,
                            "quality_claim_allowed": False,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
                return 0
            if not index_status["rerank_index_complete"]:
                raise ValueError(
                    "parent embedding rerank requires a complete current corpus embedding index"
                )
            embedding_started = time.perf_counter()
            query_embeddings, embedding_usage = embed_task_queries(
                dataset,
                settings,
                max_query_embeddings=args.max_query_embeddings,
                max_cost_usd=args.max_cost_usd,
                confirm_data_transfer=args.confirm_data_transfer,
            )
            embedding_usage["provider_elapsed_ms"] = round(
                (time.perf_counter() - embedding_started) * 1000, 3
            )
        report = run_evaluation(
            store,
            dataset,
            digest,
            query_embeddings=query_embeddings,
            embedding_model=embedding_usage["model"] if embedding_usage else None,
        )
        if embedding_usage is not None:
            report["query_embedding_usage"] = embedding_usage
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError:
        print(
            "Refusing to overwrite an existing report; choose a new --output path.", file=sys.stderr
        )
        return 2
    except (EmbeddingError, OSError, ValueError, KeyError, TypeError) as error:
        message = type(error).__name__
        if isinstance(error, EmbeddingError):
            message = error.code
        elif isinstance(error, ChunkStrategyEvaluationError) or (
            args.dry_run and isinstance(error, ValueError)
        ):
            message = str(error)
        print(f"Chunk strategy evaluation failed: {message}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(output),
                "dataset_sha256": digest,
                "query_embedding_provider_calls": (
                    embedding_usage["provider_calls"] if embedding_usage else 0
                ),
                "quality_claim_allowed": report["dataset"]["quality_claim_allowed"],
                "strategies": {
                    name: {
                        "bm25": strategy.get("metrics_macro_average", strategy["status"]),
                        "parent_embedding_proxy_rerank": strategy.get("retrieval_methods", {})
                        .get("bm25_parent_embedding_proxy_rerank", {})
                        .get("status"),
                    }
                    for name, strategy in report["strategies"].items()
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _rerank_index_status(store, dataset, digest: str, settings) -> dict[str, Any]:
    run_evaluation(store, dataset, digest)
    active_chunks = [
        chunk
        for source_id in dataset["sources"]
        for chunk in store.list_current_fulltext_chunks(source_type="arxiv", source_id=source_id)
    ]
    stored_vectors = store.list_current_fulltext_embeddings(
        source_type="arxiv",
        source_ids=list(dataset["sources"]),
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    active_chunk_ids = {
        chunk["chunk_id"] for chunk in active_chunks if chunk["source_id"] in dataset["sources"]
    }
    stored_dimensions = {len(vector) for vector in stored_vectors.values() if vector is not None}
    missing_vector_count = len(active_chunk_ids - set(stored_vectors)) + sum(
        vector is None for vector in stored_vectors.values()
    )
    extra_vector_count = len(set(stored_vectors) - active_chunk_ids)
    dimensions_configured = isinstance(settings.embedding_dimensions, int)
    dimensions_match = (
        stored_dimensions == {settings.embedding_dimensions} if dimensions_configured else None
    )
    missing_chunks = [
        chunk
        for chunk in active_chunks
        if chunk["chunk_id"] not in stored_vectors or stored_vectors[chunk["chunk_id"]] is None
    ]
    missing_text_bytes = sum(
        len(chunk["text"].encode("utf-8"))
        for chunk in missing_chunks
        if isinstance(chunk.get("text"), str)
    )
    missing_text_count = sum(not isinstance(chunk.get("text"), str) for chunk in missing_chunks)
    index_cost_estimate = None
    price_per_million = getattr(settings, "embedding_price_per_million_usd", None)
    if price_per_million is not None and missing_text_count == 0:
        index_cost_estimate = str(
            Decimal(str(price_per_million)) * missing_text_bytes / Decimal(1_000_000)
        )
    return {
        "rerank_index_complete": (
            missing_vector_count == 0
            and extra_vector_count == 0
            and dimensions_match is True
            and len(stored_dimensions) == 1
        ),
        "active_chunk_count": len(active_chunk_ids),
        "indexed_chunk_count": sum(vector is not None for vector in stored_vectors.values()),
        "missing_vector_count": missing_vector_count,
        "missing_vector_text_bytes_upper_bound": missing_text_bytes,
        "missing_vector_text_count_unavailable": missing_text_count,
        "estimated_missing_fulltext_embedding_cost_usd": index_cost_estimate,
        "extra_vector_count": extra_vector_count,
        "embedding_dimensions_configured": dimensions_configured,
        "embedding_dimensions_match": dimensions_match,
    }


if __name__ == "__main__":
    raise SystemExit(main())
