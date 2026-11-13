"""Evidence-grounding evaluation over an AI-labeled task set on the licensed corpus.

The labels here are authored by AI agents (``label_source: ai_agent_review``). This
module refuses any dataset that claims human review, synthetic status, or gold-standard
standing, so an AI-labeled set can never be reported as human-verified quality.

It measures retrieval deterministically, with optional precomputed query embeddings:

* **evidence grounding** — does the selected BM25, dense, hybrid or reranked retriever
  over the whole approved corpus retrieve the evidence anchors? Multi-hop tasks can declare
  all required chunks;
  older tasks without them are explicitly reported as unmeasured for complete coverage.
* **negative-task behaviour** — for a task the corpus cannot answer, how much lexical
  material does the retriever still surface? Reported as diagnostics, never as a
  quality claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import statistics
import time
from pathlib import Path
from typing import Any

from app.evaluation.metrics import score_query
from app.retrieval.parser_versions import is_supported_pdf_parser_version
from app.retrieval.tokenizer import TOKENIZER_VERSION
from app.storage.repository import RERANK_CANDIDATE_LIMIT, PaperStore

REPORT_SCHEMA = "papertrail.ai-labeled-tasks-report.v4"
DATASET_SCHEMA = "papertrail.ai-labeled-tasks.v1"
LABEL_SOURCE = "ai_agent_review"
TEST_LABEL_SOURCE = "test_fixture"
SCORING_VERSION = "fulltext-evidence-top-k-v3-multi-anchor-rerank"


class AiLabeledTaskError(ValueError):
    """Raised when an AI-labeled task set or its lineage is invalid."""


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def load_dataset(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        dataset = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AiLabeledTaskError("dataset must be valid UTF-8 JSON") from error
    validate_dataset(dataset)
    return dataset, hashlib.sha256(raw).hexdigest()


def validate_dataset(dataset: Any) -> None:
    if not isinstance(dataset, dict):
        raise AiLabeledTaskError("dataset must be a JSON object")
    if dataset.get("schema") != DATASET_SCHEMA:
        raise AiLabeledTaskError("unsupported AI-labeled dataset schema")
    if type(dataset.get("synthetic")) is not bool:
        raise AiLabeledTaskError("synthetic must be an explicit boolean")
    if (
        dataset.get("gold_standard") is not False
        or dataset.get("quality_claim_allowed") is not False
        or dataset.get("human_reviewed") is not False
    ):
        raise AiLabeledTaskError("AI labels must never claim gold-standard or human review")
    # Synthetic fixtures are allowed so tests can exercise this module without touching
    # real paper data, but they must declare themselves as such and can never carry the
    # AI-label provenance reserved for the licensed corpus.
    expected_label_source = TEST_LABEL_SOURCE if dataset["synthetic"] else LABEL_SOURCE
    if dataset.get("label_source") != expected_label_source:
        raise AiLabeledTaskError(f"label_source must be {expected_label_source}")
    if dataset.get("retrieval_method") != "bm25":
        raise AiLabeledTaskError("only the bm25 retrieval method is supported")
    top_k = dataset.get("top_k")
    if type(top_k) is not int or not 1 <= top_k <= 8:
        raise AiLabeledTaskError("top_k must be between 1 and 8")

    sources = dataset.get("sources")
    tasks = dataset.get("tasks")
    if not isinstance(sources, dict) or not sources or not isinstance(tasks, list) or not tasks:
        raise AiLabeledTaskError("dataset needs sources and tasks")
    for source_id, source in sources.items():
        if (
            not isinstance(source_id, str)
            or not isinstance(source, dict)
            or source.get("license_id") != "CC-BY-4.0"
            or source.get("license_url") != "https://creativecommons.org/licenses/by/4.0/"
            or not isinstance(source.get("parser_version"), str)
            or not is_supported_pdf_parser_version(source["parser_version"])
            or not _is_sha256(source.get("content_sha256"))
            or not _is_sha256(source.get("source_document_sha256"))
        ):
            raise AiLabeledTaskError("source lineage or license is invalid")

    seen: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise AiLabeledTaskError("each task must be an object")
        task_id = task.get("task_id")
        source_id = task.get("source_id")
        if (
            not isinstance(task_id, str)
            or not task_id
            or task_id in seen
            or source_id not in sources
            or not isinstance(task.get("question"), str)
            or not task["question"].strip()
            or type(task.get("expected_answerable")) is not bool
        ):
            raise AiLabeledTaskError("task identity or answerability label is invalid")
        seen.add(task_id)
        if task["expected_answerable"]:
            evidence = task.get("evidence")
            if not _valid_evidence_anchor(evidence, source_id):
                raise AiLabeledTaskError("answerable tasks require an evidence anchor")
            required_evidence = task.get("required_evidence")
            if required_evidence is not None:
                if (
                    not isinstance(required_evidence, list)
                    or not 2 <= len(required_evidence) <= 8
                    or any(
                        not _valid_evidence_anchor(item, source_id) for item in required_evidence
                    )
                ):
                    raise AiLabeledTaskError("required_evidence must contain 2-8 valid anchors")
                anchor_ids = [item["chunk_id"] for item in required_evidence]
                if (
                    len(anchor_ids) != len(set(anchor_ids))
                    or evidence["chunk_id"] not in anchor_ids
                ):
                    raise AiLabeledTaskError(
                        "required_evidence anchors must be unique and include the primary anchor"
                    )
        else:
            if task.get("evidence") is not None or task.get("required_evidence") is not None:
                raise AiLabeledTaskError("unanswerable tasks must not carry evidence anchors")
            if task.get("related_source_id") != source_id or not isinstance(
                task.get("absent_fact"), str
            ):
                raise AiLabeledTaskError("unanswerable tasks need a related source and absent fact")
            if task["absent_fact"].strip() == "":
                raise AiLabeledTaskError("unanswerable tasks need a non-empty absent fact")


def _valid_evidence_anchor(evidence: Any, source_id: str) -> bool:
    if not isinstance(evidence, dict):
        return False
    chunk_id = evidence.get("chunk_id")
    return (
        evidence.get("source_id") == source_id
        and isinstance(chunk_id, str)
        and chunk_id.startswith(f"arxiv:{source_id}:")
        and type(evidence.get("page_number")) is int
        and evidence["page_number"] >= 1
        and isinstance(evidence.get("element_type"), str)
        and bool(evidence["element_type"])
        and isinstance(evidence.get("quote"), str)
        and bool(evidence["quote"].strip())
    )


def run_evaluation(
    store: PaperStore,
    dataset: dict[str, Any],
    dataset_sha256: str,
    *,
    retrieval_method: str = "bm25",
    query_embeddings: dict[str, list[float]] | None = None,
    embedding_model: str | None = None,
) -> dict[str, Any]:
    if getattr(store, "readonly", False) is not True:
        raise AiLabeledTaskError("evaluation requires a read-only PaperStore")
    validate_dataset(dataset)
    if not _is_sha256(dataset_sha256):
        raise AiLabeledTaskError("dataset_sha256 must be a lowercase SHA-256 digest")
    if retrieval_method not in {"bm25", "dense", "hybrid", "bm25_dense_rerank"}:
        raise AiLabeledTaskError("unsupported retrieval method")
    if retrieval_method == "bm25":
        if query_embeddings is not None or embedding_model is not None:
            raise AiLabeledTaskError("BM25 evaluation does not accept query embeddings")
    elif (
        not isinstance(query_embeddings, dict)
        or set(query_embeddings) != {task["task_id"] for task in dataset["tasks"]}
        or not isinstance(embedding_model, str)
        or not embedding_model.strip()
    ):
        raise AiLabeledTaskError("embedding-based evaluation requires one embedding per task")
    if query_embeddings is not None and any(
        not isinstance(vector, list)
        or not vector
        or len(vector) > 8_192
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in vector
        )
        for vector in query_embeddings.values()
    ):
        raise AiLabeledTaskError("query embeddings must be finite vectors with 1-8192 dimensions")

    source_results: dict[str, dict[str, Any]] = {}
    expected_total = 0
    for source_id, expected in dataset["sources"].items():
        actual = store.get_current_fulltext_metadata(source_type="arxiv", source_id=source_id)
        if actual is None:
            raise AiLabeledTaskError(f"active approved full text is missing: {source_id}")
        checks = {
            "content_sha256": expected["content_sha256"],
            "source_document_sha256": expected["source_document_sha256"],
            "license_id": expected["license_id"],
            "license_url": expected["license_url"],
            "parser_version": expected["parser_version"],
        }
        if any(actual.get(key) != value for key, value in checks.items()):
            raise AiLabeledTaskError(f"active source lineage differs from the dataset: {source_id}")
        expected_total += int(actual["chunk_count"])
        source_results[source_id] = {**checks, "chunk_count": actual["chunk_count"]}

    top_k = dataset["top_k"]
    task_rows: list[dict[str, Any]] = []
    retrieval_latencies_ms: list[float] = []
    for task in dataset["tasks"]:
        started = time.perf_counter_ns()
        result = store.search_fulltext_evidence(
            task["question"],
            limit=top_k,
            source_type="arxiv",
            source_id=None,
            retrieval_method=retrieval_method,
            query_embedding=(query_embeddings or {}).get(task["task_id"]),
            embedding_model=embedding_model,
        )
        retrieval_latencies_ms.append((time.perf_counter_ns() - started) / 1_000_000)
        if result.get("status") not in {"ok", "no_results"}:
            raise AiLabeledTaskError(f"retrieval returned {result.get('status')}")
        if result.get("truncated") or result.get("scanned_chunks") != expected_total:
            raise AiLabeledTaskError("retrieval did not scan the complete approved corpus")
        items = result.get("items") or []
        if any(
            item.get("source_id") not in dataset["sources"]
            or item.get("content_sha256") != dataset["sources"][item["source_id"]]["content_sha256"]
            for item in items
        ):
            raise AiLabeledTaskError("retrieved evidence lineage differs from the dataset")
        scores = [float(item.get("score") or 0.0) for item in items]
        if any(not math.isfinite(score) for score in scores):
            raise AiLabeledTaskError("retrieval returned a non-finite score")
        row: dict[str, Any] = {
            "task_id": task["task_id"],
            "source_id": task["source_id"],
            "challenge_type": task["challenge_type"],
            "expected_answerable": task["expected_answerable"],
            "retrieved_chunk_ids": [item.get("chunk_id") for item in items],
            "retrieved_source_ids": [item.get("source_id") for item in items],
            "top1_score": scores[0] if scores else None,
            "retrieved_candidate_count": len(items),
            "retrieval_latency_ms": retrieval_latencies_ms[-1],
        }
        if task["expected_answerable"]:
            reference_chunk_id = task["evidence"]["chunk_id"]
            required_evidence = task.get("required_evidence")
            evidence_anchors = required_evidence or [task["evidence"]]
            anchor_ids = {anchor["chunk_id"] for anchor in evidence_anchors}
            retrieved_ids = {item.get("chunk_id") for item in items}
            ranks = {
                anchor_id: next(
                    (
                        index
                        for index, item in enumerate(items, start=1)
                        if item.get("chunk_id") == anchor_id
                    ),
                    None,
                )
                for anchor_id in anchor_ids
            }
            rank = ranks[reference_chunk_id]
            anchor_metrics = score_query(
                [item.get("chunk_id") for item in items],
                {anchor_id: 1 for anchor_id in anchor_ids},
                cutoffs=(1, top_k),
            )
            row["reference_chunk_id"] = reference_chunk_id
            row["evidence_rank"] = rank
            row["hit_at_1"] = rank == 1
            row["hit_at_k"] = rank is not None
            row["required_evidence_count"] = (
                len(anchor_ids)
                if required_evidence is not None or task["challenge_type"] != "multi_hop"
                else None
            )
            row["required_evidence_retrieved_count"] = (
                sum(anchor_id in retrieved_ids for anchor_id in anchor_ids)
                if row["required_evidence_count"] is not None
                else None
            )
            row["complete_evidence_coverage"] = (
                row["required_evidence_retrieved_count"] == row["required_evidence_count"]
                if row["required_evidence_count"] is not None
                else None
            )
            row["evidence_metrics"] = {
                "mrr_at_k": anchor_metrics[f"mrr@{top_k}"],
                "ndcg_at_k": anchor_metrics[f"ndcg@{top_k}"],
                "precision_at_k": len(anchor_ids & retrieved_ids) / top_k,
                "recall_at_k": len(anchor_ids & retrieved_ids) / len(anchor_ids),
            }
        else:
            row["absent_fact"] = task["absent_fact"]
            row["retrieval_candidate_returned"] = bool(items)
        task_rows.append(row)

    answerable = [row for row in task_rows if row["expected_answerable"]]
    negative = [row for row in task_rows if not row["expected_answerable"]]
    hit_at_1 = sum(row["hit_at_1"] for row in answerable)
    hit_at_k = sum(row["hit_at_k"] for row in answerable)
    answerable_scores = [row["top1_score"] for row in answerable if row["top1_score"] is not None]
    negative_scores = [row["top1_score"] for row in negative if row["top1_score"] is not None]
    by_type: dict[str, dict[str, Any]] = {}
    for row in task_rows:
        group = by_type.setdefault(
            row["challenge_type"],
            {
                "task_count": 0,
                "answerable_count": 0,
                "hit_at_k": 0,
                "candidate_return_count": 0,
                "mrr_at_k": [],
                "ndcg_at_k": [],
                "complete_evidence_count": 0,
                "complete_evidence_denominator": 0,
            },
        )
        group["task_count"] += 1
        if row["expected_answerable"]:
            group["answerable_count"] += 1
            group["hit_at_k"] += int(row["hit_at_k"])
            group["mrr_at_k"].append(row["evidence_metrics"]["mrr_at_k"])
            group["ndcg_at_k"].append(row["evidence_metrics"]["ndcg_at_k"])
            if row["complete_evidence_coverage"] is not None:
                group["complete_evidence_denominator"] += 1
                group["complete_evidence_count"] += int(row["complete_evidence_coverage"])
        else:
            group["candidate_return_count"] += int(row["retrieval_candidate_returned"])
    for _name, group in by_type.items():
        group["mrr_at_k_mean"] = statistics.fmean(group["mrr_at_k"]) if group["mrr_at_k"] else None
        group["ndcg_at_k_mean"] = (
            statistics.fmean(group["ndcg_at_k"]) if group["ndcg_at_k"] else None
        )
        group["complete_evidence_coverage_rate"] = (
            group["complete_evidence_count"] / group["complete_evidence_denominator"]
            if group["complete_evidence_denominator"]
            else None
        )
        del group["mrr_at_k"], group["ndcg_at_k"]
        group["evidence_hit_at_k_rate"] = (
            group["hit_at_k"] / group["answerable_count"] if group["answerable_count"] else None
        )
        group["candidate_return_rate"] = (
            group["candidate_return_count"] / (group["task_count"] - group["answerable_count"])
            if group["task_count"] - group["answerable_count"]
            else None
        )

    known_coverage = [
        row["complete_evidence_coverage"]
        for row in answerable
        if row["complete_evidence_coverage"] is not None
    ]
    ordered_latencies = sorted(retrieval_latencies_ms)

    return {
        "report_schema": REPORT_SCHEMA,
        "synthetic": dataset["synthetic"],
        "gold_standard": False,
        "quality_claim_allowed": False,
        "human_reviewed": False,
        "label_source": dataset["label_source"],
        "interpretation": (
            "AI-labeled evidence-grounding diagnostic over one licensed corpus; the questions "
            "were written from the same index being evaluated, so this is not human-verified "
            "quality evidence and not a general retrieval-quality estimate"
        ),
        "dataset": {
            "id": dataset["dataset_id"],
            "sha256": dataset_sha256,
            "task_count": len(task_rows),
            "answerable_count": len(answerable),
            "unanswerable_count": len(negative),
            "multi_hop_without_required_evidence": sum(
                row["challenge_type"] == "multi_hop" and row["required_evidence_count"] is None
                for row in answerable
            ),
            "label_source": dataset["label_source"],
            "human_reviewed": False,
        },
        "retrieval": {
            "method": result.get("retrieval_method", f"{retrieval_method}_fulltext_v1"),
            "top_k": top_k,
            "source_scope": dataset["source_scope"],
            "retrieval_provider_calls": 0,
            "scanned_chunks_per_query": expected_total,
            "query_embedding_model": embedding_model,
            "query_embedding_count": len(query_embeddings) if query_embeddings is not None else 0,
            "reranker": (
                {
                    "type": "dense_embedding_cosine",
                    "candidate_generator": "bm25",
                    "candidate_limit": RERANK_CANDIDATE_LIMIT,
                }
                if retrieval_method == "bm25_dense_rerank"
                else None
            ),
            "retrieval_latency_ms": {
                "mean": statistics.fmean(retrieval_latencies_ms),
                "p50": ordered_latencies[max(0, (len(ordered_latencies) - 1) // 2)],
                "p95": ordered_latencies[max(0, math.ceil(0.95 * len(ordered_latencies)) - 1)],
                "includes_query_embedding_provider_latency": False,
            },
        },
        "runner_config": {
            "scoring": SCORING_VERSION,
            "tokenizer": TOKENIZER_VERSION,
            "python_version": platform.python_version(),
        },
        "sources": source_results,
        "summary": {
            "evidence_hit_at_1": {
                "count": hit_at_1,
                "denominator": len(answerable),
                "rate": hit_at_1 / len(answerable) if answerable else None,
            },
            f"evidence_hit_at_{top_k}": {
                "count": hit_at_k,
                "denominator": len(answerable),
                "rate": hit_at_k / len(answerable) if answerable else None,
            },
            "unanswerable_candidate_retrieval": {
                "count": sum(1 for row in negative if row["retrieval_candidate_returned"]),
                "denominator": len(negative),
                "meaning": (
                    "negative tasks for which this retrieval method still returned candidates; "
                    "diagnostic only, since abstention is not decided by BM25 alone"
                ),
            },
            "answerable_retrieval_metrics": {
                "mrr_at_k": statistics.fmean(
                    row["evidence_metrics"]["mrr_at_k"] for row in answerable
                )
                if answerable
                else None,
                "ndcg_at_k": statistics.fmean(
                    row["evidence_metrics"]["ndcg_at_k"] for row in answerable
                )
                if answerable
                else None,
                "precision_at_k": statistics.fmean(
                    row["evidence_metrics"]["precision_at_k"] for row in answerable
                )
                if answerable
                else None,
                "recall_at_k": statistics.fmean(
                    row["evidence_metrics"]["recall_at_k"] for row in answerable
                )
                if answerable
                else None,
                "complete_evidence_coverage": (
                    statistics.fmean(known_coverage) if known_coverage else None
                ),
                "complete_evidence_denominator": len(known_coverage),
            },
            "top1_score_separability": {
                "answerable_mean": (
                    statistics.fmean(answerable_scores) if answerable_scores else None
                ),
                "unanswerable_mean": (
                    statistics.fmean(negative_scores) if negative_scores else None
                ),
                "answerable_max": max(answerable_scores) if answerable_scores else None,
                "unanswerable_max": max(negative_scores) if negative_scores else None,
                "meaning": "score overlap between answerable and negative tasks, diagnostic only",
            },
            "by_challenge_type": by_type,
        },
        "tasks": task_rows,
    }


__all__ = [
    "AiLabeledTaskError",
    "DATASET_SCHEMA",
    "LABEL_SOURCE",
    "REPORT_SCHEMA",
    "TEST_LABEL_SOURCE",
    "load_dataset",
    "run_evaluation",
    "validate_dataset",
]
