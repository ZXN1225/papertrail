"""Read-only, evidence-span-aware PDF chunk strategy diagnostics."""

from __future__ import annotations

import json
import math
import statistics
import time
from typing import Any

from app.evaluation.fulltext_retrieval import (
    FullTextRetrievalEvaluationError,
    validate_dataset,
)
from app.evaluation.metrics import score_query
from app.retrieval.bm25 import BM25Index
from app.retrieval.fulltext import (
    MAX_CHUNK_TOKEN_UPPER_BOUND,
    ChunkSizeInfeasibleError,
    chunk_pdf_elements,
)
from app.sources.arxiv import normalize_arxiv_id
from app.storage.repository import MAX_ACTIVE_FULLTEXT_CHUNKS, PaperStore

STRATEGIES = {
    "pdf_structure_900_bytes_v1": 900,
    "pdf_structure_1800_bytes_v1": MAX_CHUNK_TOKEN_UPPER_BOUND,
}
MAX_TOTAL_ELEMENT_BYTES = 50_000_000
REPORT_SCHEMA = "papertrail.chunk-strategy-report.v1"


class ChunkStrategyEvaluationError(ValueError):
    """A frozen corpus, source span, or chunk strategy is invalid."""


def run_evaluation(
    store: PaperStore, dataset: dict[str, Any], dataset_sha256: str
) -> dict[str, Any]:
    if getattr(store, "readonly", False) is not True:
        raise ChunkStrategyEvaluationError("evaluation requires a read-only PaperStore")
    try:
        validate_dataset(dataset)
    except FullTextRetrievalEvaluationError as error:
        raise ChunkStrategyEvaluationError(str(error)) from error
    if not _is_sha256(dataset_sha256):
        raise ChunkStrategyEvaluationError("dataset_sha256 must be lowercase SHA-256")

    source_metadata: dict[str, dict[str, Any]] = {}
    source_chunks: dict[str, dict[str, dict[str, Any]]] = {}
    source_elements: dict[str, list[dict[str, Any]]] = {}
    total_element_bytes = 0
    for source_id, expected in dataset["sources"].items():
        try:
            source_id = normalize_arxiv_id(source_id)
        except ValueError as error:
            raise ChunkStrategyEvaluationError("source arXiv ID is invalid") from error
        actual = store.get_current_fulltext_metadata(source_type="arxiv", source_id=source_id)
        if actual is None:
            raise ChunkStrategyEvaluationError(f"active approved full text is missing: {source_id}")
        for field in (
            "content_sha256",
            "source_document_sha256",
            "license_id",
            "license_url",
            "parser_version",
        ):
            if actual.get(field) != expected.get(field):
                raise ChunkStrategyEvaluationError(
                    f"active source lineage differs from manifest: {source_id}"
                )
        if actual.get("license_id") not in {"CC0-1.0", "CC-BY-4.0"}:
            raise ChunkStrategyEvaluationError("source license is not approved for processing")
        chunks = store.list_current_fulltext_chunks(source_type="arxiv", source_id=source_id)
        elements = store.list_current_fulltext_elements(source_type="arxiv", source_id=source_id)
        if not chunks or not elements or len(chunks) != actual.get("chunk_count"):
            raise ChunkStrategyEvaluationError(
                f"source parser elements are unavailable: {source_id}"
            )
        total_element_bytes += sum(
            len(json.dumps(element, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            for element in elements
        )
        if total_element_bytes > MAX_TOTAL_ELEMENT_BYTES:
            raise ChunkStrategyEvaluationError("corpus exceeds the chunk ablation size limit")
        source_metadata[source_id] = actual
        source_chunks[source_id] = {chunk["chunk_id"]: chunk for chunk in chunks}
        source_elements[source_id] = elements

    source_scope = dataset.get("source_scope", "exact_arxiv_id_per_task")
    if source_scope == "all_approved_arxiv":
        active = store.list_current_fulltext_metadata(source_type="arxiv")
        if {item["source_id"] for item in active} != set(dataset["sources"]):
            raise ChunkStrategyEvaluationError(
                "all-approved-ArXiv manifest must cover every current active source"
            )
        for item in active:
            expected = dataset["sources"][item["source_id"]]
            if any(
                item.get(field) != expected.get(field)
                for field in (
                    "content_sha256",
                    "source_document_sha256",
                    "license_id",
                    "license_url",
                    "parser_version",
                )
            ):
                raise ChunkStrategyEvaluationError(
                    f"active source lineage differs from manifest: {item['source_id']}"
                )

    candidates_by_strategy: dict[str, list[dict[str, Any]]] = {}
    build_time_ms: dict[str, float] = {}
    infeasible_strategies: set[str] = set()
    for strategy, max_chunk_bytes in STRATEGIES.items():
        started = time.perf_counter_ns()
        candidates: list[dict[str, Any]] = []
        try:
            for source_id, elements in source_elements.items():
                for chunk in chunk_pdf_elements(elements, max_chunk_bytes=max_chunk_bytes):
                    if not chunk.element_id:
                        raise ChunkStrategyEvaluationError(
                            f"candidate chunk has no element locator: {source_id}"
                        )
                    metadata = source_metadata[source_id]
                    candidates.append(
                        {
                            "chunk_id": (
                                f"{strategy}:{source_id}:{chunk.element_id}:{chunk.ordinal}"
                            ),
                            "source_id": source_id,
                            "content_sha256": metadata["content_sha256"],
                            "title": metadata["title"],
                            "text": chunk.text,
                            "evidence_text": chunk.evidence_text or chunk.text,
                            "element_id": chunk.element_id,
                            "page_number": chunk.page_number,
                            "element_type": chunk.element_type,
                            "char_start": chunk.char_start,
                            "char_end": chunk.char_end,
                            "bbox": chunk.bbox,
                            "locator": chunk.locator,
                            "section_path": chunk.section_path,
                        }
                    )
                    if len(candidates) > MAX_ACTIVE_FULLTEXT_CHUNKS:
                        raise ChunkStrategyEvaluationError(
                            "candidate corpus exceeds the chunk limit"
                        )
        except ChunkSizeInfeasibleError as error:
            if max_chunk_bytes == MAX_CHUNK_TOKEN_UPPER_BOUND:
                raise ChunkStrategyEvaluationError(
                    "current-size chunk strategy cannot represent the approved parser data"
                ) from error
            infeasible_strategies.add(strategy)
            build_time_ms[strategy] = (time.perf_counter_ns() - started) / 1_000_000
            continue
        candidates_by_strategy[strategy] = candidates
        build_time_ms[strategy] = (time.perf_counter_ns() - started) / 1_000_000

    index_by_strategy: dict[str, BM25Index] = {}
    index_by_strategy_source: dict[str, dict[str, BM25Index]] = {}
    index_build_time_ms: dict[str, float] = {}
    for strategy, candidates in candidates_by_strategy.items():
        started = time.perf_counter_ns()
        if source_scope == "all_approved_arxiv":
            index_by_strategy[strategy] = BM25Index(_bm25_documents(candidates))
        else:
            index_by_strategy_source[strategy] = {
                source_id: BM25Index(
                    _bm25_documents([item for item in candidates if item["source_id"] == source_id])
                )
                for source_id in source_metadata
            }
        index_build_time_ms[strategy] = (time.perf_counter_ns() - started) / 1_000_000

    task_results: dict[str, list[dict[str, Any]]] = {name: [] for name in STRATEGIES}
    latency_by_strategy: dict[str, list[float]] = {name: [] for name in STRATEGIES}
    top_k = dataset["top_k"]
    metric_cutoffs = tuple(sorted({1, min(3, top_k), min(5, top_k), top_k}))
    for task in dataset["tasks"]:
        source_id = task["source_id"]
        anchor = source_chunks[source_id].get(task["reference_chunk_id"])
        if (
            anchor is None
            or anchor.get("content_sha256") != dataset["sources"][source_id]["content_sha256"]
            or anchor.get("page_number") != task["reference_page"]
            or anchor.get("element_type") != task["reference_element_type"]
            or not isinstance(anchor.get("element_id"), str)
            or type(anchor.get("char_start")) is not int
            or type(anchor.get("char_end")) is not int
        ):
            raise ChunkStrategyEvaluationError(
                f"reference locator differs from manifest: {task['task_id']}"
            )
        source_element = next(
            (
                element
                for element in source_elements[source_id]
                if element.get("element_id") == anchor["element_id"]
            ),
            None,
        )
        if (
            not isinstance(source_element, dict)
            or not isinstance(source_element.get("text"), str)
            or source_element.get("page_number") != anchor["page_number"]
            or source_element.get("element_type") != anchor["element_type"]
            or (json.loads(anchor["bbox_json"]) if anchor.get("bbox_json") else None)
            != source_element.get("bbox")
        ):
            raise ChunkStrategyEvaluationError(
                f"reference parser element locator differs: {task['task_id']}"
            )
        coverage_anchor = {**anchor, "source_text": source_element["text"]}

        for strategy, candidates in candidates_by_strategy.items():
            scoped = (
                candidates
                if source_scope == "all_approved_arxiv"
                else [item for item in candidates if item["source_id"] == source_id]
            )
            index = (
                index_by_strategy[strategy]
                if source_scope == "all_approved_arxiv"
                else index_by_strategy_source[strategy][source_id]
            )
            by_id = {item["chunk_id"]: item for item in scoped}
            started = time.perf_counter_ns()
            hits = index.search(task["question"], limit=top_k)
            latency_ms = (time.perf_counter_ns() - started) / 1_000_000
            latency_by_strategy[strategy].append(latency_ms)
            ranking = [hit.openalex_id for hit in hits]
            relevant = {
                item["chunk_id"]: 1
                for item in scoped
                if item["source_id"] == source_id
                and item["element_id"] == anchor["element_id"]
                and item["char_start"] < anchor["char_end"]
                and item["char_end"] > anchor["char_start"]
            }
            if not relevant:
                raise ChunkStrategyEvaluationError(
                    f"reference span is not represented by {strategy}: {task['task_id']}"
                )
            metrics = _retrieval_metrics(ranking, relevant, metric_cutoffs)
            task_results[strategy].append(
                {
                    "task_id": task["task_id"],
                    "source_id": source_id,
                    "reference_chunk_id": task["reference_chunk_id"],
                    "reference_element_id": anchor["element_id"],
                    "reference_page": anchor["page_number"],
                    "reference_element_type": anchor["element_type"],
                    "reference_span": [anchor["char_start"], anchor["char_end"]],
                    "relevant_chunk_count": len(relevant),
                    "retrieved_chunk_ids": ranking,
                    "retrieval_latency_ms": latency_ms,
                    "evidence_span_covered": _span_is_covered(
                        [by_id[item_id] for item_id in ranking if item_id in by_id],
                        coverage_anchor,
                    ),
                    "metrics": {
                        **metrics,
                    },
                }
            )

    strategy_reports: dict[str, dict[str, Any]] = {}
    for strategy in STRATEGIES:
        if strategy in infeasible_strategies:
            strategy_reports[strategy] = {
                "status": "unavailable",
                "failure_reason": "table_structure_exceeds_candidate_chunk_size",
                "max_chunk_bytes": STRATEGIES[strategy],
                "chunk_build_latency_ms": build_time_ms[strategy],
                "tasks": [],
            }
            continue
        rows = task_results[strategy]
        latencies = latency_by_strategy[strategy]
        ordered = sorted(latencies)
        metrics = [row["metrics"] for row in rows]
        strategy_reports[strategy] = {
            "status": "completed",
            "max_chunk_bytes": STRATEGIES[strategy],
            "chunk_count": len(candidates_by_strategy[strategy]),
            "chunk_build_latency_ms": build_time_ms[strategy],
            "index_build_latency_ms": index_build_time_ms[strategy],
            "retrieval_latency_ms": {
                "mean": statistics.fmean(latencies),
                "p50": ordered[max(0, math.ceil(0.5 * len(ordered)) - 1)],
                "p95": ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)],
            },
            "metrics_macro_average": {
                metric: statistics.fmean(item[metric] for item in metrics) for metric in metrics[0]
            }
            | {
                "evidence_span_coverage": statistics.fmean(
                    float(row["evidence_span_covered"]) for row in rows
                ),
            },
            "tasks": rows,
        }

    return {
        "report_schema": REPORT_SCHEMA,
        "dataset": {
            "id": dataset["dataset_id"],
            "sha256": dataset_sha256,
            "synthetic": False,
            "gold_standard": False,
            "quality_claim_allowed": False,
            "reference_status": dataset["reference_status"],
            "task_count": len(dataset["tasks"]),
            "sources": source_metadata,
        },
        "retrieval": {
            "method": "bm25",
            "source_scope": source_scope,
            "top_k": top_k,
            "provider_calls": 0,
            "qrel_projection": (
                "candidate chunk is relevant when its exact source span overlaps the selected "
                "reference chunk span within the same parser element"
            ),
            "interpretation": (
                "small single-reviewer selected-span diagnostic; not gold relevance or general "
                "quality proof"
            ),
        },
        "strategies": strategy_reports,
    }


def _span_is_covered(retrieved: list[dict[str, Any]], anchor: dict[str, Any]) -> bool:
    spans = sorted(
        (max(item["char_start"], anchor["char_start"]), min(item["char_end"], anchor["char_end"]))
        for item in retrieved
        if item["source_id"] == anchor["source_id"]
        and item["element_id"] == anchor["element_id"]
        and item["char_start"] < anchor["char_end"]
        and item["char_end"] > anchor["char_start"]
    )
    covered_end = anchor["char_start"]
    for start, end in spans:
        if start > covered_end and not anchor["source_text"][covered_end:start].isspace():
            return False
        covered_end = max(covered_end, end)
        if covered_end >= anchor["char_end"]:
            return True
    return False


def _bm25_documents(candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "openalex_id": item["chunk_id"],
            "title": item["title"],
            "abstract": f"{item['section_path']}\n{item['text']}",
        }
        for item in candidates
    ]


def _retrieval_metrics(
    ranking: list[str], relevant: dict[str, int], cutoffs: tuple[int, ...]
) -> dict[str, float]:
    metrics = score_query(ranking, relevant, cutoffs=cutoffs)
    for cutoff in cutoffs:
        retrieved_relevant = len(set(ranking[:cutoff]) & set(relevant))
        metrics[f"precision@{cutoff}"] = retrieved_relevant / cutoff
        metrics[f"recall@{cutoff}"] = retrieved_relevant / len(relevant)
    return metrics


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )
