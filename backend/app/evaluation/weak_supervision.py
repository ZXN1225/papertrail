"""Weakly supervised retrieval diagnostics; generated records are never gold labels."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from typing import Any

from app.evaluation.metrics import score_query


def generate_candidates(chunks: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Build deterministic query candidates from parsed text and lineage metadata.

    Each query is made by masking a phrase from a source chunk. The source chunk is
    weak provenance supervision only: it does not establish semantic relevance or gold.
    """
    candidates = []
    for index, chunk in enumerate(chunks):
        text = chunk.get("evidence_text") or chunk.get("text")
        chunk_id = chunk.get("chunk_id")
        if not isinstance(text, str) or not isinstance(chunk_id, str):
            continue
        sentences = [
            part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", text) if part.strip()
        ]
        if not sentences:
            sentences = [text.strip()]
        sentence = max(sentences, key=len)
        terms = re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}|[\u4e00-\u9fff]{2,}", sentence)
        if len(terms) < 3:
            continue
        query = " ".join(terms[: min(8, len(terms))])
        query_id = hashlib.sha256(f"{chunk_id}:{index}:{query}".encode()).hexdigest()[:16]
        candidates.append(
            {
                "query_id": query_id,
                "query": query,
                "weak_relevant_chunk_ids": [chunk_id],
                "source_id": chunk.get("source_id"),
                "answerable": True,
                "bucket": "weak_source_chunk_query",
            }
        )
    return {
        "schema": "papertrail.weak-supervision-candidates.v1",
        "synthetic": False,
        "weak_supervision": True,
        "gold_standard": False,
        "quality_claim_allowed": False,
        "candidates": candidates,
    }


def score_weak_retrieval(
    ranking: list[str], weak_relevant: Sequence[str], *, k: int = 5
) -> dict[str, float]:
    """Report metrics against weak source-chunk references, visibly not ground truth."""
    relevant = set(weak_relevant)
    prefix = ranking[:k]
    hits = sum(item in relevant for item in prefix)
    scored = score_query(ranking, {item: 1 for item in relevant}, cutoffs=(k,))
    return {
        **scored,
        f"precision@{k}": hits / k,
        f"recall@{k}": hits / len(relevant) if relevant else 0.0,
    }


def partition_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Partition by source identity so chunks from one paper cannot cross splits."""
    by_source: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        source_id = candidate.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("each weak candidate requires a source_id")
        by_source.setdefault(source_id, []).append(candidate)
    splits: dict[str, list[dict[str, Any]]] = {"train": [], "dev": [], "test": []}
    for source_id, source_candidates in by_source.items():
        bucket = int(hashlib.sha256(source_id.encode()).hexdigest()[:8], 16) % 10
        split = "train" if bucket < 7 else "dev" if bucket < 8 else "test"
        splits[split].extend(source_candidates)
    source_ids = {
        split: sorted({candidate["source_id"] for candidate in rows})
        for split, rows in splits.items()
    }
    return {
        "schema": "papertrail.weak-supervision-splits.v1",
        "synthetic": False,
        "weak_supervision": True,
        "gold_standard": False,
        "quality_claim_allowed": False,
        "split_method": "sha256_source_id_mod_10_70_10_20",
        "source_ids": source_ids,
        "splits": splits,
        "sha256": hashlib.sha256(
            json.dumps(splits, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
    }
