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
from app.retrieval.vectors import cosine_similarity
from app.sources.arxiv import normalize_arxiv_id
from app.storage.repository import (
    MAX_ACTIVE_FULLTEXT_CHUNKS,
    RERANK_CANDIDATE_LIMIT,
    PaperStore,
)

STRATEGIES = {
    "pdf_structure_900_bytes_v1": (900, 0),
    "pdf_structure_900_bytes_10pct_overlap_v1": (900, 90),
    "pdf_structure_1200_bytes_v1": (1_200, 0),
    "pdf_structure_1200_bytes_10pct_overlap_v1": (1_200, 120),
    "pdf_structure_1800_bytes_v1": (MAX_CHUNK_TOKEN_UPPER_BOUND, 0),
    "pdf_structure_1800_bytes_10pct_overlap_v1": (MAX_CHUNK_TOKEN_UPPER_BOUND, 180),
}
MAX_TOTAL_ELEMENT_BYTES = 50_000_000
REPORT_SCHEMA = "papertrail.chunk-strategy-report.v3"
PARENT_RERANK_METHOD = "bm25_parent_embedding_proxy_rerank"


class ChunkStrategyEvaluationError(ValueError):
    """A frozen corpus, source span, or chunk strategy is invalid."""


def run_evaluation(
    store: PaperStore,
    dataset: dict[str, Any],
    dataset_sha256: str,
    *,
    query_embeddings: dict[str, list[float]] | None = None,
    embedding_model: str | None = None,
) -> dict[str, Any]:
    if getattr(store, "readonly", False) is not True:
        raise ChunkStrategyEvaluationError("evaluation requires a read-only PaperStore")
    try:
        validate_dataset(dataset)
    except FullTextRetrievalEvaluationError as error:
        raise ChunkStrategyEvaluationError(str(error)) from error
    if not _is_sha256(dataset_sha256):
        raise ChunkStrategyEvaluationError("dataset_sha256 must be lowercase SHA-256")
    if (query_embeddings is None) != (embedding_model is None):
        raise ChunkStrategyEvaluationError("query embeddings and model must be provided together")
    if query_embeddings is not None and (
        set(query_embeddings) != {task["task_id"] for task in dataset["tasks"]}
        or any(
            not isinstance(vector, list)
            or not 1 <= len(vector) <= 8_192
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                for value in vector
            )
            for vector in query_embeddings.values()
        )
    ):
        raise ChunkStrategyEvaluationError(
            "query embeddings must cover each task with finite vectors"
        )

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

    parent_vectors: dict[str, list[float]] = {}
    rerank_unavailable_reason: str | None = None
    if query_embeddings is not None:
        dimensions = len(next(iter(query_embeddings.values())))
        if any(len(vector) != dimensions for vector in query_embeddings.values()):
            raise ChunkStrategyEvaluationError("query embedding dimensions are inconsistent")
        try:
            stored_vectors = store.list_current_fulltext_embeddings(
                source_type="arxiv",
                source_ids=list(source_metadata),
                model=embedding_model or "",
                dimensions=dimensions,
            )
        except (AttributeError, ValueError) as error:
            raise ChunkStrategyEvaluationError(
                "current chunk embeddings are unavailable"
            ) from error
        indexed_chunk_ids = {chunk_id for chunks in source_chunks.values() for chunk_id in chunks}
        if set(stored_vectors) != indexed_chunk_ids or any(
            vector is None for vector in stored_vectors.values()
        ):
            rerank_unavailable_reason = "current_chunk_embedding_index_incomplete"
        else:
            parent_vectors = {
                chunk_id: vector
                for chunk_id, vector in stored_vectors.items()
                if vector is not None
            }

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
    for strategy, (max_chunk_bytes, max_overlap_bytes) in STRATEGIES.items():
        started = time.perf_counter_ns()
        candidates: list[dict[str, Any]] = []
        try:
            for source_id, elements in source_elements.items():
                for chunk in chunk_pdf_elements(
                    elements,
                    max_chunk_bytes=max_chunk_bytes,
                    max_overlap_bytes=max_overlap_bytes,
                ):
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

    candidate_parent_ids: dict[str, dict[str, str]] = {}
    rerank_reason_by_strategy: dict[str, str] = {}
    if query_embeddings is None:
        rerank_reason_by_strategy = {
            name: "query_embeddings_not_provided" for name in candidates_by_strategy
        }
    elif rerank_unavailable_reason:
        rerank_reason_by_strategy = {
            name: rerank_unavailable_reason for name in candidates_by_strategy
        }
    else:
        for strategy, candidates in candidates_by_strategy.items():
            try:
                candidate_parent_ids[strategy] = _map_candidates_to_current_chunks(
                    candidates, source_chunks
                )
            except ChunkStrategyEvaluationError:
                rerank_reason_by_strategy[strategy] = "candidate_to_parent_embedding_mapping_failed"

    task_results: dict[str, dict[str, list[dict[str, Any]]]] = {
        name: {"bm25": [], PARENT_RERANK_METHOD: []} for name in STRATEGIES
    }
    latency_by_method: dict[str, dict[str, list[float]]] = {
        name: {"bm25": [], PARENT_RERANK_METHOD: []} for name in STRATEGIES
    }
    rerank_candidate_counts: dict[str, list[int]] = {name: [] for name in STRATEGIES}
    top_k = dataset["top_k"]
    metric_cutoffs = tuple(sorted({1, min(3, top_k), min(5, top_k), top_k}))
    for task in dataset["tasks"]:
        source_id = task["source_id"]
        anchor, source_element, anchor_resolution = _resolve_reference_anchor(
            store,
            task,
            dataset["sources"][source_id],
            source_chunks[source_id],
            source_elements[source_id],
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
            hits = index.search(task["question"], limit=len(scoped))
            bm25_latency_ms = (time.perf_counter_ns() - started) / 1_000_000
            latency_by_method[strategy]["bm25"].append(bm25_latency_ms)
            bm25_ranking = [hit.openalex_id for hit in hits[:top_k]]
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
            task_results[strategy]["bm25"].append(
                _task_method_result(
                    task,
                    anchor,
                    anchor_resolution,
                    relevant,
                    bm25_ranking,
                    by_id,
                    coverage_anchor,
                    bm25_latency_ms,
                    metric_cutoffs,
                )
            )
            if strategy in rerank_reason_by_strategy:
                continue
            parent_map = candidate_parent_ids[strategy]
            query_vector = query_embeddings[task["task_id"]]
            started = time.perf_counter_ns()
            reranked_ids, parent_candidate_count = _parent_embedding_proxy_rerank(
                hits,
                scoped,
                parent_map,
                parent_vectors,
                query_vector,
                limit=top_k,
            )
            rerank_latency_ms = (time.perf_counter_ns() - started) / 1_000_000
            latency_by_method[strategy][PARENT_RERANK_METHOD].append(
                bm25_latency_ms + rerank_latency_ms
            )
            rerank_candidate_counts[strategy].append(parent_candidate_count)
            task_results[strategy][PARENT_RERANK_METHOD].append(
                _task_method_result(
                    task,
                    anchor,
                    anchor_resolution,
                    relevant,
                    reranked_ids,
                    by_id,
                    coverage_anchor,
                    bm25_latency_ms + rerank_latency_ms,
                    metric_cutoffs,
                )
                | {
                    "unique_parent_candidates": parent_candidate_count,
                    "bm25_candidate_retrieval_latency_ms": bm25_latency_ms,
                    "rerank_latency_ms": rerank_latency_ms,
                }
            )

    strategy_reports: dict[str, dict[str, Any]] = {}
    for strategy in STRATEGIES:
        if strategy in infeasible_strategies:
            strategy_reports[strategy] = {
                "status": "unavailable",
                "failure_reason": "table_structure_exceeds_candidate_chunk_size",
                "max_chunk_bytes": STRATEGIES[strategy][0],
                "max_overlap_bytes": STRATEGIES[strategy][1],
                "chunk_build_latency_ms": build_time_ms[strategy],
                "tasks": [],
            }
            continue
        rows = task_results[strategy]["bm25"]
        strategy_report = {
            "status": "completed",
            "max_chunk_bytes": STRATEGIES[strategy][0],
            "max_overlap_bytes": STRATEGIES[strategy][1],
            "chunk_count": len(candidates_by_strategy[strategy]),
            "chunk_build_latency_ms": build_time_ms[strategy],
            "index_build_latency_ms": index_build_time_ms[strategy],
            **_summarize_method(rows, latency_by_method[strategy]["bm25"]),
            "tasks": rows,
        }
        if strategy in rerank_reason_by_strategy:
            strategy_report["retrieval_methods"] = {
                "bm25": {"status": "completed", "tasks": rows},
                PARENT_RERANK_METHOD: {
                    "status": "unavailable",
                    "failure_reason": rerank_reason_by_strategy[strategy],
                    "tasks": [],
                },
            }
        else:
            rerank_rows = task_results[strategy][PARENT_RERANK_METHOD]
            rerank_method = {
                "status": "completed",
                "reranker": "existing_1800_byte_parent_embedding_proxy",
                "candidate_parent_limit": RERANK_CANDIDATE_LIMIT,
                "parent_candidate_count_mean": statistics.fmean(rerank_candidate_counts[strategy]),
                "unique_parent_count": len(set(candidate_parent_ids[strategy].values())),
                "candidate_chunks_per_parent_mean": len(candidates_by_strategy[strategy])
                / len(set(candidate_parent_ids[strategy].values())),
                **_summarize_method(rerank_rows, latency_by_method[strategy][PARENT_RERANK_METHOD]),
                "tasks": rerank_rows,
            }
            strategy_report["retrieval_methods"] = {
                "bm25": {"status": "completed", "tasks": rows},
                PARENT_RERANK_METHOD: rerank_method,
            }
        strategy_reports[strategy] = strategy_report

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
            "method": "paired_bm25_and_parent_embedding_proxy_rerank",
            "source_scope": source_scope,
            "top_k": top_k,
            "retrieval_provider_calls": 0,
            "query_embedding_model": embedding_model,
            "query_embedding_count": len(query_embeddings) if query_embeddings else 0,
            "reranker_type": "parent_chunk_embedding_proxy_not_child_dense_or_cross_encoder",
            "query_embedding_provider_latency_included": False,
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


def _map_candidates_to_current_chunks(
    candidates: list[dict[str, Any]],
    source_chunks: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for candidate in candidates:
        matches = [
            chunk_id
            for chunk_id, parent in source_chunks[candidate["source_id"]].items()
            if parent.get("content_sha256") == candidate["content_sha256"]
            and parent.get("element_id") == candidate["element_id"]
            and parent.get("element_type") == candidate["element_type"]
            and parent.get("page_number") == candidate["page_number"]
            and type(parent.get("char_start")) is int
            and type(parent.get("char_end")) is int
            and parent["char_start"] <= candidate["char_start"]
            and parent["char_end"] >= candidate["char_end"]
        ]
        if len(matches) != 1:
            raise ChunkStrategyEvaluationError(
                "candidate chunk does not map to one current parent chunk"
            )
        mapped[candidate["chunk_id"]] = matches[0]
    return mapped


def _parent_embedding_proxy_rerank(
    bm25_hits: list[Any],
    candidates: list[dict[str, Any]],
    parent_by_candidate: dict[str, str],
    parent_vectors: dict[str, list[float]],
    query_vector: list[float],
    *,
    limit: int,
) -> tuple[list[str], int]:
    by_id = {item["chunk_id"]: item for item in candidates}
    bm25_rank = {hit.openalex_id: rank for rank, hit in enumerate(bm25_hits)}
    candidate_ids_by_parent: dict[str, list[str]] = {}
    parent_first_rank: dict[str, int] = {}
    for hit in bm25_hits:
        chunk_id = hit.openalex_id
        if chunk_id not in by_id:
            continue
        parent_id = parent_by_candidate[chunk_id]
        candidate_ids_by_parent.setdefault(parent_id, []).append(chunk_id)
        parent_first_rank.setdefault(parent_id, bm25_rank[chunk_id])

    selected_parent_ids = sorted(
        candidate_ids_by_parent,
        key=lambda parent_id: parent_first_rank[parent_id],
    )[:RERANK_CANDIDATE_LIMIT]
    scored_parents = [
        (parent_id, cosine_similarity(query_vector, parent_vectors[parent_id]))
        for parent_id in selected_parent_ids
    ]
    scored_parents.sort(key=lambda item: (-item[1], parent_first_rank[item[0]], item[0]))
    ranking = [
        chunk_id
        for parent_id, _score in scored_parents
        for chunk_id in sorted(
            candidate_ids_by_parent[parent_id], key=lambda item_id: bm25_rank[item_id]
        )
    ]
    return ranking[:limit], len(selected_parent_ids)


def _task_method_result(
    task: dict[str, Any],
    anchor: dict[str, Any],
    anchor_resolution: str,
    relevant: dict[str, int],
    ranking: list[str],
    by_id: dict[str, dict[str, Any]],
    coverage_anchor: dict[str, Any],
    latency_ms: float,
    metric_cutoffs: tuple[int, ...],
) -> dict[str, Any]:
    return {
        "task_id": task["task_id"],
        "source_id": task["source_id"],
        "reference_chunk_id": task["reference_chunk_id"],
        "reference_element_id": anchor["element_id"],
        "reference_page": anchor["page_number"],
        "reference_element_type": anchor["element_type"],
        "reference_span": [anchor["char_start"], anchor["char_end"]],
        "reference_anchor_resolution": anchor_resolution,
        "relevant_chunk_count": len(relevant),
        "retrieved_chunk_ids": ranking,
        "retrieval_latency_ms": latency_ms,
        "evidence_span_covered": _span_is_covered(
            [by_id[item_id] for item_id in ranking if item_id in by_id], coverage_anchor
        ),
        "metrics": _retrieval_metrics(ranking, relevant, metric_cutoffs),
    }


def _summarize_method(rows: list[dict[str, Any]], latencies: list[float]) -> dict[str, Any]:
    ordered = sorted(latencies)
    metrics = [row["metrics"] for row in rows]
    return {
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
    }


def _resolve_reference_anchor(
    store: PaperStore,
    task: dict[str, Any],
    expected_source: dict[str, Any],
    current_chunks: dict[str, dict[str, Any]],
    current_elements: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    task_id = task["task_id"]
    source_id = task["source_id"]
    anchor = current_chunks.get(task["reference_chunk_id"])
    if anchor is not None:
        if (
            anchor.get("content_sha256") != expected_source["content_sha256"]
            or anchor.get("page_number") != task["reference_page"]
            or anchor.get("element_type") != task["reference_element_type"]
            or not isinstance(anchor.get("element_id"), str)
            or type(anchor.get("char_start")) is not int
            or type(anchor.get("char_end")) is not int
        ):
            raise ChunkStrategyEvaluationError(
                f"reference locator differs from manifest: {task_id}"
            )
        source_element = next(
            (item for item in current_elements if item.get("element_id") == anchor["element_id"]),
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
            raise ChunkStrategyEvaluationError(f"reference parser locator differs: {task_id}")
        return anchor, source_element, "current_chunk"

    historical = store.get_approved_fulltext_chunk_by_id(
        source_type="arxiv", source_id=source_id, chunk_id=task["reference_chunk_id"]
    )
    evidence_text = (
        (historical.get("evidence_text") or historical.get("text"))
        if isinstance(historical, dict)
        else None
    )
    if (
        historical is None
        or historical.get("source_document_sha256") != expected_source["source_document_sha256"]
        or historical.get("license_id") != expected_source["license_id"]
        or historical.get("license_url") != expected_source["license_url"]
        or historical.get("page_number") != task["reference_page"]
        or historical.get("element_type") != task["reference_element_type"]
        or not isinstance(evidence_text, str)
        or not evidence_text
    ):
        raise ChunkStrategyEvaluationError(
            f"historical reference anchor is not verified against the current PDF: {task_id}"
        )

    matches: list[tuple[dict[str, Any], int]] = []
    for element in current_elements:
        text = element.get("text")
        if (
            element.get("page_number") != task["reference_page"]
            or element.get("element_type") != task["reference_element_type"]
            or not isinstance(text, str)
        ):
            continue
        start = text.find(evidence_text)
        if start >= 0 and text.find(evidence_text, start + 1) < 0:
            matches.append((element, start))
    if len(matches) != 1:
        raise ChunkStrategyEvaluationError(
            f"historical reference text does not map uniquely to the current PDF: {task_id}"
        )
    source_element, char_start = matches[0]
    return (
        {
            "chunk_id": task["reference_chunk_id"],
            "content_sha256": expected_source["content_sha256"],
            "source_id": source_id,
            "element_id": source_element["element_id"],
            "page_number": source_element["page_number"],
            "element_type": source_element["element_type"],
            "char_start": char_start,
            "char_end": char_start + len(evidence_text),
            "bbox_json": json.dumps(source_element.get("bbox"), separators=(",", ":")),
        },
        source_element,
        "exact_text_remap_same_pdf",
    )


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
