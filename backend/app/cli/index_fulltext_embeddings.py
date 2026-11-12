"""Index embeddings for the current approved local full-text corpus."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from decimal import Decimal, InvalidOperation
from typing import Any

from app.config import get_settings
from app.embeddings.client import (
    MAX_BATCH_SIZE,
    MAX_INPUT_CHARS,
    EmbeddingError,
    OpenAIEmbeddingClient,
)
from app.storage.repository import PaperStore


def _parse_cost(value: str) -> Decimal:
    try:
        cost = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("--max-cost-usd must be a positive decimal") from error
    if not cost.is_finite() or cost <= 0:
        raise ValueError("--max-cost-usd must be a positive decimal")
    return cost


def _missing_chunks(
    store: PaperStore, args: argparse.Namespace, settings: Any
) -> list[dict[str, Any]]:
    chunks = store.list_current_fulltext_chunks(
        source_type=args.source_type, source_id=args.source_id
    )
    missing: list[dict[str, Any]] = []
    source_groups: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        source_groups.setdefault(chunk["source_type"], []).append(chunk)
    for source_type, source_chunks in source_groups.items():
        vectors = store.list_current_fulltext_embeddings(
            source_type=source_type,
            source_ids=list(dict.fromkeys(chunk["source_id"] for chunk in source_chunks)),
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        missing.extend(
            chunk
            for chunk in source_chunks
            if chunk["chunk_id"] not in vectors or vectors[chunk["chunk_id"]] is None
        )
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-type", choices=("openalex", "arxiv"))
    parser.add_argument("--source-id")
    parser.add_argument("--dry-run", action="store_true", help="preview without provider calls")
    parser.add_argument("--confirm-data-transfer", action="store_true")
    parser.add_argument("--max-chunks", type=int)
    parser.add_argument("--max-cost-usd")
    args = parser.parse_args(argv)
    if (args.source_type is None) != (args.source_id is None):
        parser.error("--source-type and --source-id must be provided together")

    settings = get_settings()
    if settings.embedding_provider not in {"openai", "disabled"}:
        print("Embedding index failed: unsupported_provider", file=sys.stderr)
        return 2
    if not isinstance(settings.embedding_model, str) or not settings.embedding_model.strip():
        print("Embedding index failed: embedding_model_not_configured", file=sys.stderr)
        return 2
    if settings.embedding_price_per_million_usd is None:
        print("Embedding index failed: embedding_price_not_configured", file=sys.stderr)
        return 2
    if args.max_chunks is None or args.max_chunks < 1:
        print("Embedding index failed: --max-chunks must be positive", file=sys.stderr)
        return 2
    if args.max_cost_usd is None:
        print("Embedding index failed: --max-cost-usd is required", file=sys.stderr)
        return 2
    try:
        cost_limit = _parse_cost(args.max_cost_usd)
        readonly_store = PaperStore(settings.resolved_data_storage_path, readonly=True)
        missing = _missing_chunks(readonly_store, args, settings)
        if len(missing) > args.max_chunks:
            raise ValueError("missing chunk count exceeds --max-chunks")
        if any(
            not isinstance(chunk.get("text"), str)
            or not chunk["text"].strip()
            or len(chunk["text"]) > MAX_INPUT_CHARS
            for chunk in missing
        ):
            raise ValueError("a missing chunk is empty or exceeds the embedding input limit")
        input_bytes_upper_bound = sum(len(chunk["text"].encode("utf-8")) for chunk in missing)
        price = Decimal(str(settings.embedding_price_per_million_usd))
        estimated_upper_bound_cost = price * input_bytes_upper_bound / Decimal(1_000_000)
        if estimated_upper_bound_cost > cost_limit:
            raise ValueError("UTF-8 byte upper-bound estimate exceeds --max-cost-usd")
        budget = {
            "missing_chunks": len(missing),
            "input_utf8_bytes_upper_bound": input_bytes_upper_bound,
            "provider_call_upper_bound": (len(missing) + MAX_BATCH_SIZE - 1) // MAX_BATCH_SIZE,
            "estimated_upper_bound_cost_usd": str(estimated_upper_bound_cost),
            "max_cost_usd": str(cost_limit),
            "model": settings.embedding_model,
        }
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "status": "dry_run_passed",
                        **budget,
                        "provider_calls": 0,
                        "data_transfer_approved": False,
                        "confirm_data_transfer_required_for_execute": True,
                        "index_written": False,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if not args.confirm_data_transfer:
            raise ValueError("embedding indexing requires --confirm-data-transfer")
        if settings.embedding_provider != "openai":
            raise ValueError("live embedding indexing requires embedding provider=openai")
        if not missing:
            print(json.dumps({"status": "already_indexed", "indexed_chunks": 0}, sort_keys=True))
            return 0

        store = PaperStore(settings.resolved_data_storage_path)
        client = OpenAIEmbeddingClient(settings)
        token_count = 0
        dimension_count = settings.embedding_dimensions
        try:
            for start in range(0, len(missing), MAX_BATCH_SIZE):
                batch_chunks = missing[start : start + MAX_BATCH_SIZE]
                batch = client.embed([chunk["text"] for chunk in batch_chunks])
                dimension_count = len(batch.vectors[0])
                token_count += batch.input_tokens
                store.store_fulltext_embeddings(
                    model=batch.model,
                    dimensions=dimension_count,
                    items=[
                        {
                            "chunk_id": chunk["chunk_id"],
                            "content_sha256": chunk["content_sha256"],
                            "vector": vector,
                        }
                        for chunk, vector in zip(batch_chunks, batch.vectors, strict=True)
                    ],
                )
        finally:
            client.close()
    except (EmbeddingError, OSError, ValueError, sqlite3.Error) as error:
        code = (
            error.code
            if isinstance(error, EmbeddingError)
            else str(error)
            if isinstance(error, ValueError)
            else type(error).__name__
        )
        print(f"Embedding index failed: {code}", file=sys.stderr)
        return 3
    print(
        json.dumps(
            {
                "status": "indexed",
                "source_type": args.source_type or "all",
                "source_id": args.source_id,
                "indexed_chunks": len(missing),
                "model": settings.embedding_model,
                "dimensions": dimension_count,
                "input_tokens": token_count,
                "estimated_cost_usd": round(
                    settings.embedding_price_per_million_usd * token_count / 1_000_000, 10
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
