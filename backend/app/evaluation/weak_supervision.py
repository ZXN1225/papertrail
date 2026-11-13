"""Weakly supervised retrieval diagnostics; generated records are never gold labels."""

from __future__ import annotations

import hashlib
import json
import re
import statistics
import time
from collections.abc import Sequence
from typing import Any

from app.evaluation.metrics import score_query

_ALLOWED_SOURCE_TYPES = {"arxiv", "openalex"}
_ALLOWED_LICENSES = {
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def generate_candidates(chunks: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Build weak masked-term queries only from approved, licensed public full text.

    The source chunk is weak provenance supervision only; it does not establish
    semantic relevance or gold. Private and unapproved material is rejected.
    """
    candidates = []
    seen_chunk_ids: set[tuple[str, str]] = set()
    seen_query_ids: set[str] = set()
    for chunk in chunks:
        source_id = chunk.get("source_id")
        source_type = chunk.get("source_type")
        license_id = chunk.get("license_id")
        content_sha256 = chunk.get("content_sha256")
        chunk_id = chunk.get("chunk_id")
        if (
            source_type not in _ALLOWED_SOURCE_TYPES
            or chunk.get("source_status") != "approved"
            or license_id not in _ALLOWED_LICENSES
            or chunk.get("license_url", _ALLOWED_LICENSES.get(license_id))
            != _ALLOWED_LICENSES.get(license_id)
            or not isinstance(source_id, str)
            or not source_id.strip()
            or not isinstance(chunk_id, str)
            or not chunk_id.strip()
            or not isinstance(content_sha256, str)
            or _SHA256.fullmatch(content_sha256) is None
        ):
            raise ValueError("candidates require approved licensed public full text lineage")
        identity = (source_id, chunk_id)
        if identity in seen_chunk_ids:
            raise ValueError("chunk identities must be unique within a source")
        seen_chunk_ids.add(identity)
        text = chunk.get("evidence_text") or chunk.get("text")
        if not isinstance(text, str):
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
        masked_index = len(terms) // 2
        answer_term = terms[masked_index]
        query_terms = terms[:masked_index] + terms[masked_index + 1 :]
        query = " ".join(query_terms[:8])
        if len(query_terms) > 8 and masked_index < 8:
            query = " ".join(query_terms[:7] + query_terms[8:9])
        if not query.strip():
            continue
        query_id = hashlib.sha256(
            f"{source_type}:{source_id}:{chunk_id}:{content_sha256}:{masked_index}".encode()
        ).hexdigest()[:20]
        if query_id in seen_query_ids:
            raise ValueError("candidate query IDs must be unique")
        seen_query_ids.add(query_id)
        candidates.append(
            {
                "query_id": query_id,
                "query": query,
                "answer_term": answer_term,
                "weak_relevant_chunk_ids": [chunk_id],
                "source_id": source_id,
                "source_type": source_type,
                "license_id": license_id,
                "source_content_sha256": content_sha256,
                "answerable": True,
                "bucket": "masked_source_chunk_lookup",
            }
        )
    return {
        "schema": "papertrail.weak-supervision-candidates.v1",
        "synthetic": False,
        "weak_supervision": True,
        "gold_standard": False,
        "quality_claim_allowed": False,
        "query_generation": "longest_sentence_single_term_mask_v1",
        "candidates": candidates,
    }


def build_dataset_from_store(store: Any, *, source_type: str | None = None) -> dict[str, Any]:
    """Generate a weak diagnostic dataset from current approved licensed index rows."""
    if getattr(store, "readonly", False) is not True:
        raise ValueError("weak-supervision dataset generation requires a read-only PaperStore")
    if source_type is not None and source_type not in _ALLOWED_SOURCE_TYPES:
        raise ValueError("source_type must be arxiv or openalex")

    sources = {
        (source["source_type"], source["source_id"]): source
        for source in store.list_current_fulltext_metadata(source_type=source_type)
        if source.get("license_id") in _ALLOWED_LICENSES
        and source.get("license_url") == _ALLOWED_LICENSES[source["license_id"]]
    }
    chunks = []
    for chunk in store.list_current_fulltext_chunks():
        source = sources.get((chunk.get("source_type"), chunk.get("source_id")))
        if source is None:
            continue
        chunks.append(
            {
                **chunk,
                "source_status": source["status"],
                "license_id": source["license_id"],
                "license_url": source["license_url"],
                "parser_version": source["parser_version"],
                "chunker_version": source.get("chunker_version"),
                "source_document_sha256": source["source_document_sha256"],
            }
        )

    generated = generate_candidates(chunks)
    partitions = partition_candidates(generated["candidates"])
    if not generated["candidates"]:
        raise ValueError("no eligible source chunks produced weak query candidates")
    source_manifest = {
        source_id: {
            key: source[key]
            for key in (
                "source_type",
                "source_id",
                "title",
                "source_url",
                "content_sha256",
                "source_document_sha256",
                "license_id",
                "license_url",
                "license_evidence_url",
                "text_source_url",
                "attribution",
                "parser_version",
                "chunker_version",
            )
        }
        for (_source_type, source_id), source in sorted(sources.items())
    }
    dataset = {
        "schema": "papertrail.weak-supervision-dataset.v1",
        "synthetic": False,
        "weak_supervision": True,
        "gold_standard": False,
        "human_reviewed": False,
        "quality_claim_allowed": False,
        "source_scope": source_type or "all_approved_licensed_fulltext",
        "query_generation": generated["query_generation"],
        "sources": source_manifest,
        "split_method": partitions["split_method"],
        "split_counts": partitions["split_counts"],
        "source_ids": partitions["source_ids"],
        "splits": partitions["splits"],
    }
    dataset["dataset_sha256"] = hashlib.sha256(
        json.dumps(dataset, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return dataset


def run_evaluation(
    store: Any,
    dataset: dict[str, Any],
    *,
    split: str = "test",
    k: int = 5,
) -> dict[str, Any]:
    """Replay weak source-chunk queries over the exact current licensed corpus."""
    if getattr(store, "readonly", False) is not True:
        raise ValueError("weak-supervision evaluation requires a read-only PaperStore")
    if (
        dataset.get("schema") != "papertrail.weak-supervision-dataset.v1"
        or dataset.get("synthetic") is not False
        or dataset.get("weak_supervision") is not True
        or dataset.get("gold_standard") is not False
        or dataset.get("human_reviewed") is not False
        or dataset.get("quality_claim_allowed") is not False
    ):
        raise ValueError("dataset provenance is not eligible for weak-supervision evaluation")
    if split not in {"all", "train", "dev", "test"}:
        raise ValueError("split must be all, train, dev or test")
    if type(k) is not int or not 1 <= k <= 100:
        raise ValueError("k must be between 1 and 100")
    fingerprint = dataset.get("dataset_sha256")
    unsigned = {key: value for key, value in dataset.items() if key != "dataset_sha256"}
    expected_fingerprint = hashlib.sha256(
        json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if fingerprint != expected_fingerprint:
        raise ValueError("dataset fingerprint does not match its contents")

    source_scope = dataset.get("source_scope")
    source_type = source_scope if source_scope in _ALLOWED_SOURCE_TYPES else None
    if source_scope not in {"arxiv", "openalex", "all_approved_licensed_fulltext"}:
        raise ValueError("unsupported weak-supervision source scope")
    current_sources = {
        (source.get("source_type"), source.get("source_id")): source
        for source in store.list_current_fulltext_metadata(source_type=source_type)
        if source.get("license_id") in _ALLOWED_LICENSES
        and source.get("license_url") == _ALLOWED_LICENSES[source["license_id"]]
    }
    manifest = dataset.get("sources")
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("dataset has no frozen source manifest")
    expected_keys = {
        (source.get("source_type"), source_id) for source_id, source in manifest.items()
    }
    if expected_keys != set(current_sources):
        raise ValueError("active approved corpus differs from the frozen dataset source scope")
    for source_id, source in manifest.items():
        active = current_sources.get((source.get("source_type"), source_id))
        if active is None or any(
            active.get(key) != source.get(key)
            for key in (
                "content_sha256",
                "source_document_sha256",
                "license_id",
                "license_url",
                "license_evidence_url",
                "text_source_url",
                "attribution",
                "parser_version",
                "chunker_version",
            )
        ):
            raise ValueError("active source lineage differs from the frozen dataset")

    chunk_lineage = {
        chunk.get("chunk_id"): (
            chunk.get("source_type"),
            chunk.get("source_id"),
            chunk.get("content_sha256"),
        )
        for chunk in store.list_current_fulltext_chunks()
        if (chunk.get("source_type"), chunk.get("source_id")) in expected_keys
    }

    all_splits = dataset.get("splits")
    candidates = all_splits.get(split) if isinstance(all_splits, dict) else None
    if split == "all" and isinstance(all_splits, dict):
        candidates = [row for name in ("train", "dev", "test") for row in all_splits.get(name, [])]
    if not isinstance(candidates, list) or not candidates:
        raise ValueError(f"dataset split {split} is empty")

    task_rows = []
    latencies: list[float] = []
    seen_query_ids: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("weak-supervision query row is malformed")
        source_id = candidate.get("source_id")
        source = manifest.get(source_id) if isinstance(source_id, str) else None
        relevant_ids = candidate.get("weak_relevant_chunk_ids")
        if (
            not isinstance(candidate.get("query_id"), str)
            or not candidate["query_id"].strip()
            or candidate["query_id"] in seen_query_ids
            or not isinstance(candidate.get("query"), str)
            or not candidate["query"].strip()
            or source is None
            or candidate.get("source_type") != source.get("source_type")
            or candidate.get("license_id") != source.get("license_id")
            or candidate.get("source_content_sha256") != source.get("content_sha256")
            or candidate.get("answerable") is not True
            or candidate.get("bucket") != "masked_source_chunk_lookup"
            or not isinstance(relevant_ids, list)
            or not relevant_ids
            or any(not isinstance(item, str) or not item for item in relevant_ids)
            or len(relevant_ids) != len(set(relevant_ids))
            or any(
                chunk_lineage.get(item)
                != (source.get("source_type"), source_id, source.get("content_sha256"))
                for item in relevant_ids
            )
        ):
            raise ValueError("weak-supervision query row is malformed")
        seen_query_ids.add(candidate["query_id"])
        started = time.perf_counter()
        result = store.search_fulltext_evidence(
            candidate["query"],
            limit=k,
            source_type=source_type,
            retrieval_method="bm25",
        )
        latency_ms = (time.perf_counter() - started) * 1000
        if result.get("status") not in {"ok", "no_results"} or result.get("truncated"):
            raise ValueError("retrieval failed or truncated while evaluating frozen corpus")
        items = result.get("items") or []
        if not isinstance(items, list) or any(
            not isinstance(item, dict)
            or item.get("source_id") not in manifest
            or item.get("content_sha256") != manifest[item["source_id"]].get("content_sha256")
            for item in items
        ):
            raise ValueError("retrieved evidence lineage differs from the frozen dataset")
        ranking = [item.get("chunk_id") for item in items]
        metrics = score_weak_retrieval(ranking, candidate["weak_relevant_chunk_ids"], k=k)
        latencies.append(latency_ms)
        task_rows.append(
            {
                "query_id": candidate["query_id"],
                "bucket": candidate["bucket"],
                "source_id": candidate["source_id"],
                "retrieved_chunk_ids": ranking,
                "retrieved_source_ids": sorted({item.get("source_id") for item in items}),
                "latency_ms": round(latency_ms, 3),
                "metrics": metrics,
            }
        )
    metric_names = sorted(task_rows[0]["metrics"])
    by_bucket: dict[str, dict[str, Any]] = {}
    for row in task_rows:
        group = by_bucket.setdefault(row["bucket"], {"query_count": 0, "metrics": {}})
        group["query_count"] += 1
        for metric in metric_names:
            group["metrics"].setdefault(metric, []).append(row["metrics"][metric])
    for group in by_bucket.values():
        group["metrics"] = {
            metric: round(statistics.fmean(values), 6)
            for metric, values in group["metrics"].items()
        }
    return {
        "report_schema": "papertrail.weak-supervision-retrieval-report.v1",
        "synthetic": False,
        "weak_supervision": True,
        "gold_standard": False,
        "human_reviewed": False,
        "quality_claim_allowed": False,
        "interpretation": (
            "source-chunk masked-term diagnostic; same-document lexical relations remain, "
            "so scores are not human relevance or general user-task quality"
        ),
        "dataset_sha256": fingerprint,
        "split": split,
        "retrieval": {"method": "bm25_fulltext_v3", "k": k, "provider_calls": 0},
        "summary": {
            "query_count": len(task_rows),
            "metrics": {
                metric: round(statistics.fmean(row["metrics"][metric] for row in task_rows), 6)
                for metric in metric_names
            },
            "latency_ms": {
                "mean": round(statistics.fmean(latencies), 3),
                "p50": round(statistics.median(latencies), 3),
                "p95": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 3),
            },
            "by_bucket": by_bucket,
        },
        "tasks": task_rows,
    }


def score_weak_retrieval(
    ranking: list[str], weak_relevant: Sequence[str], *, k: int = 5
) -> dict[str, float]:
    """Report metrics against weak source-chunk references, visibly not ground truth."""
    if type(k) is not int or k < 1:
        raise ValueError("k must be a positive integer")
    if any(not isinstance(item, str) or not item for item in ranking):
        raise ValueError("ranked chunk IDs must be non-empty strings")
    if len(ranking) != len(set(ranking)):
        raise ValueError("ranked chunk IDs must be unique")
    if any(not isinstance(item, str) or not item for item in weak_relevant):
        raise ValueError("weak relevant chunk IDs must be non-empty strings")
    relevant = set(weak_relevant)
    prefix = ranking[:k]
    hits = sum(item in relevant for item in prefix)
    scored = score_query(prefix, {item: 1 for item in relevant}, cutoffs=(k,))
    return {
        **scored,
        f"precision@{k}": hits / k,
        f"returned_precision@{k}": hits / len(prefix) if prefix else 0.0,
        f"recall@{k}": hits / len(relevant) if relevant else 0.0,
    }


def partition_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Partition by source identity so chunks from one paper cannot cross splits."""
    by_source: dict[str, list[dict[str, Any]]] = {}
    seen_query_ids: set[str] = set()
    for candidate in candidates:
        source_id = candidate.get("source_id")
        query_id = candidate.get("query_id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("each weak candidate requires a source_id")
        if not isinstance(query_id, str) or not query_id.strip() or query_id in seen_query_ids:
            raise ValueError("each weak candidate requires a unique query_id")
        seen_query_ids.add(query_id)
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
    query_counts = {split: len(rows) for split, rows in splits.items()}
    source_counts = {split: len(ids) for split, ids in source_ids.items()}
    missing = [split for split in splits if source_counts[split] == 0]
    return {
        "schema": "papertrail.weak-supervision-splits.v1",
        "synthetic": False,
        "weak_supervision": True,
        "gold_standard": False,
        "quality_claim_allowed": False,
        "split_method": "sha256_source_id_mod_10_70_10_20",
        "source_ids": source_ids,
        "splits": splits,
        "split_counts": {
            "source_count": source_counts,
            "query_count": query_counts,
            "missing": missing,
            "complete": not missing,
        },
        "sha256": hashlib.sha256(
            json.dumps(splits, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
    }
