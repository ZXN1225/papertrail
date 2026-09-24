"""Index embeddings for the current approved local full-text corpus."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from app.config import get_settings
from app.embeddings.client import MAX_BATCH_SIZE, EmbeddingError, OpenAIEmbeddingClient
from app.storage.repository import PaperStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-type", choices=("openalex", "arxiv"))
    parser.add_argument("--source-id")
    args = parser.parse_args(argv)
    if (args.source_type is None) != (args.source_id is None):
        parser.error("--source-type and --source-id must be provided together")

    settings = get_settings()
    if settings.embedding_provider != "openai":
        print("Embedding index failed: provider_disabled", file=sys.stderr)
        return 2
    store = PaperStore(settings.resolved_data_storage_path)
    try:
        chunks = store.list_current_fulltext_chunks(
            source_type=args.source_type, source_id=args.source_id
        )
        if not chunks:
            print(json.dumps({"status": "no_approved_chunks", "indexed_chunks": 0}))
            return 0
        client = OpenAIEmbeddingClient(settings)
        token_count = 0
        dimension_count = settings.embedding_dimensions
        try:
            for start in range(0, len(chunks), MAX_BATCH_SIZE):
                batch_chunks = chunks[start : start + MAX_BATCH_SIZE]
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
        code = error.code if isinstance(error, EmbeddingError) else type(error).__name__
        print(f"Embedding index failed: {code}", file=sys.stderr)
        return 3
    print(
        json.dumps(
            {
                "status": "indexed",
                "source_type": args.source_type or "all",
                "source_id": args.source_id,
                "indexed_chunks": len(chunks),
                "model": settings.embedding_model,
                "dimensions": dimension_count,
                "input_tokens": token_count,
                "estimated_cost_usd": (
                    round(settings.embedding_price_per_million_usd * token_count / 1_000_000, 10)
                    if settings.embedding_price_per_million_usd is not None
                    else None
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
