"""Read-only, version-pinned retrieval diagnostics for licensed full text.

The selected reference chunks are review aids, not an independently sampled gold
standard. Metrics from this runner must never be presented as general retrieval quality.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.sources.arxiv import normalize_arxiv_id
from app.storage.repository import PaperStore

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET_PATH = ROOT / "backend/data/evaluation/arxiv-r01-r03-current-v21-v1.json"
SCHEMA = "papertrail.fulltext-retrieval-diagnostic.v1"
REPORT_SCHEMA = "papertrail.fulltext-retrieval-report.v1"


class FullTextRetrievalEvaluationError(ValueError):
    """A diagnostic manifest is invalid or no longer matches the active index."""


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        dataset = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FullTextRetrievalEvaluationError("dataset must be valid UTF-8 JSON") from error
    validate_dataset(dataset)
    return dataset, hashlib.sha256(raw).hexdigest()


def validate_dataset(dataset: Any) -> None:
    if not isinstance(dataset, dict) or dataset.get("schema") != SCHEMA:
        raise FullTextRetrievalEvaluationError("unsupported diagnostic dataset schema")
    if (
        dataset.get("synthetic") is not False
        or dataset.get("gold_standard") is not False
        or dataset.get("quality_claim_allowed") is not False
        or dataset.get("reference_status") != "single_reviewer_selected_reference"
        or dataset.get("retrieval_method") != "bm25"
    ):
        raise FullTextRetrievalEvaluationError("dataset provenance or retrieval scope is invalid")
    if dataset.get("source_scope", "exact_arxiv_id_per_task") not in {
        "exact_arxiv_id_per_task",
        "all_approved_arxiv",
    }:
        raise FullTextRetrievalEvaluationError("unsupported source scope")
    top_k = dataset.get("top_k")
    if type(top_k) is not int or not 1 <= top_k <= 8:
        raise FullTextRetrievalEvaluationError("top_k must be between 1 and 8")
    sources = dataset.get("sources")
    tasks = dataset.get("tasks")
    if not isinstance(sources, dict) or not sources or not isinstance(tasks, list) or not tasks:
        raise FullTextRetrievalEvaluationError("dataset needs sources and tasks")
    for source_id, source in sources.items():
        try:
            canonical_source_id = (
                normalize_arxiv_id(source_id) if isinstance(source_id, str) else None
            )
        except ValueError as error:
            raise FullTextRetrievalEvaluationError("source arXiv ID is invalid") from error
        if (
            not isinstance(source_id, str)
            or canonical_source_id != source_id
            or not isinstance(source, dict)
            or source.get("license_id") != "CC-BY-4.0"
            or source.get("license_url") != "https://creativecommons.org/licenses/by/4.0/"
            or not isinstance(source.get("parser_version"), str)
            or re.fullmatch(r"pdfplumber-layout-v\d+", source["parser_version"]) is None
            or not _is_sha256(source.get("source_document_sha256"))
            or not _is_sha256(source.get("content_sha256"))
        ):
            raise FullTextRetrievalEvaluationError("source lineage or license is invalid")
    seen_task_ids: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise FullTextRetrievalEvaluationError("each task must be an object")
        task_id = task.get("task_id")
        source_id = task.get("source_id")
        chunk_id = task.get("reference_chunk_id")
        if (
            not isinstance(task_id, str)
            or not re.fullmatch(r"R\d+", task_id)
            or task_id in seen_task_ids
            or not isinstance(source_id, str)
            or source_id not in sources
            or not isinstance(task.get("question"), str)
            or not task["question"].strip()
            or not isinstance(chunk_id, str)
            or not chunk_id.startswith(f"arxiv:{source_id}:")
            or type(task.get("reference_page")) is not int
            or task["reference_page"] < 1
            or not isinstance(task.get("reference_element_type"), str)
            or not task["reference_element_type"]
        ):
            raise FullTextRetrievalEvaluationError("task identity or reference is invalid")
        seen_task_ids.add(task_id)


def run_evaluation(
    store: PaperStore, dataset: dict[str, Any], dataset_sha256: str
) -> dict[str, Any]:
    if getattr(store, "readonly", False) is not True:
        raise FullTextRetrievalEvaluationError("evaluation requires a read-only PaperStore")
    validate_dataset(dataset)
    if not _is_sha256(dataset_sha256):
        raise FullTextRetrievalEvaluationError("dataset_sha256 must be lowercase SHA-256")
    source_results: dict[str, dict[str, Any]] = {}
    source_scope = dataset.get("source_scope", "exact_arxiv_id_per_task")
    for source_id, expected in dataset["sources"].items():
        actual = store.get_current_fulltext_metadata(source_type="arxiv", source_id=source_id)
        if actual is None:
            raise FullTextRetrievalEvaluationError(
                f"active approved full text is missing: {source_id}"
            )
        checks = {
            "content_sha256": expected["content_sha256"],
            "source_document_sha256": expected["source_document_sha256"],
            "license_id": expected["license_id"],
            "license_url": expected["license_url"],
            "parser_version": expected["parser_version"],
        }
        if any(actual.get(key) != value for key, value in checks.items()):
            raise FullTextRetrievalEvaluationError(
                f"active source lineage/license differs from frozen manifest: {source_id}"
            )
        source_results[source_id] = {
            **checks,
            "chunk_count": actual["chunk_count"],
            "status": actual["status"],
        }
    if source_scope == "all_approved_arxiv":
        active_sources = store.list_current_fulltext_metadata(source_type="arxiv")
        active_ids = {source["source_id"] for source in active_sources}
        if active_ids != set(dataset["sources"]):
            raise FullTextRetrievalEvaluationError(
                "all-approved-ArXiv manifest must cover every current active source"
            )
        for source in active_sources:
            expected = dataset["sources"][source["source_id"]]
            if any(
                source.get(key) != expected.get(key)
                for key in (
                    "content_sha256",
                    "source_document_sha256",
                    "license_id",
                    "license_url",
                    "parser_version",
                )
            ):
                raise FullTextRetrievalEvaluationError(
                    f"active corpus lineage differs from manifest: {source['source_id']}"
                )

    task_results: list[dict[str, Any]] = []
    hit_count = 0
    top_k = dataset["top_k"]
    for task in dataset["tasks"]:
        source_id = task["source_id"]
        result = store.search_fulltext_evidence(
            task["question"],
            limit=top_k,
            source_type="arxiv",
            source_id=source_id if source_scope == "exact_arxiv_id_per_task" else None,
            retrieval_method="bm25",
        )
        if result.get("status") != "ok":
            raise FullTextRetrievalEvaluationError(
                f"retrieval returned {result.get('status')} for {task['task_id']}"
            )
        if result.get("truncated") or (
            source_scope == "all_approved_arxiv"
            and result.get("scanned_chunks")
            != sum(source["chunk_count"] for source in source_results.values())
        ):
            raise FullTextRetrievalEvaluationError(
                f"retrieval did not scan the complete frozen scope: {task['task_id']}"
            )
        items = result.get("items")
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise FullTextRetrievalEvaluationError(
                f"retrieval returned malformed items for {task['task_id']}"
            )
        if any(
            item.get("source_type") != "arxiv"
            or (source_scope == "exact_arxiv_id_per_task" and item.get("source_id") != source_id)
            or item.get("source_id") not in dataset["sources"]
            or item.get("content_sha256") != dataset["sources"][item["source_id"]]["content_sha256"]
            for item in items
        ):
            raise FullTextRetrievalEvaluationError(
                f"retrieved evidence lineage differs from manifest: {task['task_id']}"
            )
        reference_rank = next(
            (
                rank
                for rank, item in enumerate(items, start=1)
                if item.get("chunk_id") == task["reference_chunk_id"]
            ),
            None,
        )
        reference = next(
            (item for item in items if item.get("chunk_id") == task["reference_chunk_id"]), None
        )
        reference_location_matches = bool(
            reference
            and reference.get("source_type") == "arxiv"
            and reference.get("source_id") == source_id
            and reference.get("page_number") == task["reference_page"]
            and reference.get("element_type") == task["reference_element_type"]
        )
        if reference_rank is not None and not reference_location_matches:
            raise FullTextRetrievalEvaluationError(
                f"reference locator differs from manifest: {task['task_id']}"
            )
        selected_reference_in_top_k = reference_rank is not None
        hit_count += int(selected_reference_in_top_k)
        task_results.append(
            {
                "task_id": task["task_id"],
                "source_id": source_id,
                "question": task["question"],
                "reference_chunk_id": task["reference_chunk_id"],
                "reference_rank": reference_rank,
                "selected_reference_in_top_k": selected_reference_in_top_k,
                "reference_location_matches": reference_location_matches,
                "retrieved_chunk_ids": [item["chunk_id"] for item in items],
                "scanned_chunks": result.get("scanned_chunks"),
                "truncated": result.get("truncated", False),
            }
        )
    return {
        "report_schema": REPORT_SCHEMA,
        "synthetic": False,
        "gold_standard": False,
        "quality_claim_allowed": False,
        "interpretation": (
            "selected-reference rank diagnostic on a small, single-reviewer set; "
            "not gold evidence recall or a general retrieval-quality estimate"
        ),
        "dataset": {
            "id": dataset["dataset_id"],
            "sha256": dataset_sha256,
            "task_count": len(task_results),
            "reference_status": dataset["reference_status"],
        },
        "retrieval": {
            "method": "bm25_fulltext_v3",
            "top_k": top_k,
            "source_scope": source_scope,
            "provider_calls": 0,
        },
        "sources": source_results,
        "summary": {
            "selected_reference_hits": hit_count,
            "task_count": len(task_results),
            "selected_reference_hit_rate": hit_count / len(task_results),
        },
        "tasks": task_results,
    }


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
