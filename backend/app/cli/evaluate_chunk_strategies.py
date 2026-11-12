"""Compare versioned PDF chunk sizes on one frozen, approved read-only corpus."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from app.cli.evaluate_ai_labeled_tasks import embed_task_queries
from app.config import get_settings
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
    parser.add_argument("--confirm-data-transfer", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset, digest = load_dataset(args.dataset)
        settings = get_settings()
        output = args.output.resolve()
        if output.exists():
            raise FileExistsError
        output.parent.mkdir(parents=True, exist_ok=True)
        store = PaperStore(settings.resolved_data_storage_path, readonly=True)
        query_embeddings = None
        embedding_usage = None
        if args.parent_embedding_rerank:
            if not args.confirm_data_transfer:
                raise ValueError("embedding-based reranking requires --confirm-data-transfer")
            if not settings.embedding_model:
                raise ValueError("embedding-based reranking requires a configured embedding model")
            run_evaluation(store, dataset, digest)
            active_chunks = store.list_current_fulltext_chunks(source_type="arxiv")
            stored_vectors = store.list_current_fulltext_embeddings(
                source_type="arxiv",
                source_ids=list(dataset["sources"]),
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
            )
            active_chunk_ids = {
                chunk["chunk_id"]
                for chunk in active_chunks
                if chunk["source_id"] in dataset["sources"]
            }
            stored_dimensions = {
                len(vector) for vector in stored_vectors.values() if vector is not None
            }
            if (
                set(stored_vectors) != active_chunk_ids
                or any(vector is None for vector in stored_vectors.values())
                or len(stored_dimensions) != 1
            ):
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
    except (OSError, ValueError, KeyError, TypeError) as error:
        message = (
            str(error) if isinstance(error, ChunkStrategyEvaluationError) else type(error).__name__
        )
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


if __name__ == "__main__":
    raise SystemExit(main())
