"""Frozen, local MinerU chart-fact review packs and deterministic scoring."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any

DATASET_SCHEMA = "papertrail.mineru-chart-tasks.v1"
REVIEW_SCHEMA = "papertrail.mineru-chart-review.v1"
FACT_TYPES = frozenset({"axis_label", "series_label", "numeric_value", "trend", "comparison"})
SPLITS = frozenset({"dev", "test"})
REFERENCE_STATUSES = frozenset({"answerable", "unanswerable", "uncertain"})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}\Z")


class MineruChartReviewError(ValueError):
    """A chart review dataset or review pack is stale, incomplete, or malformed."""


def _sha(value: Any, field: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise MineruChartReviewError(f"{field} must be a lowercase SHA-256")


def _identifier(value: Any, field: str) -> None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise MineruChartReviewError(f"{field} is invalid")


def _valid_bbox(value: Any, *, normalized: bool = False) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(type(number) in {int, float} and math.isfinite(number) for number in value)
        and value[2] > value[0]
        and value[3] > value[1]
        and (not normalized or (0 <= value[0] < value[2] <= 1 and 0 <= value[1] < value[3] <= 1))
    )


def _reviewed_content_sha256(dataset: dict[str, Any]) -> str:
    content = {
        key: value
        for key, value in dataset.items()
        if key not in {"judgment_status", "review_audit"}
    }
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_fact(fact: Any, *, reference: bool = False) -> None:
    if not isinstance(fact, dict) or fact.get("fact_type") not in FACT_TYPES:
        raise MineruChartReviewError("chart fact type is invalid")
    allowed = {"fact_type", "value", "unit", "absolute_tolerance"}
    if reference:
        allowed.add("fact_id")
    if set(fact) - allowed or (reference and "fact_id" not in fact):
        raise MineruChartReviewError("chart fact contains unsupported fields")
    value = fact.get("value")
    if fact["fact_type"] == "numeric_value":
        if type(value) not in {int, float} or not math.isfinite(value):
            raise MineruChartReviewError("numeric chart facts need a finite numeric value")
        unit = fact.get("unit", "")
        if not isinstance(unit, str) or len(unit) > 80:
            raise MineruChartReviewError("numeric chart fact unit is invalid")
        tolerance = fact.get("absolute_tolerance", 0)
        if type(tolerance) not in {int, float} or not math.isfinite(tolerance) or tolerance < 0:
            raise MineruChartReviewError(
                "numeric chart fact tolerance must be finite and non-negative"
            )
    else:
        if not isinstance(value, str) or not value.strip() or len(value) > 500:
            raise MineruChartReviewError("categorical chart fact value is invalid")
        if "unit" in fact or "absolute_tolerance" in fact:
            raise MineruChartReviewError("categorical chart facts cannot define numeric metadata")
    if not reference and "absolute_tolerance" in fact:
        raise MineruChartReviewError("only human reference facts may define numeric tolerance")


def validate_dataset(dataset: Any) -> None:
    if (
        not isinstance(dataset, dict)
        or dataset.get("schema") != DATASET_SCHEMA
        or type(dataset.get("synthetic")) is not bool
        or dataset.get("gold_standard") is not False
        or dataset.get("quality_claim_allowed") is not False
    ):
        raise MineruChartReviewError("chart dataset provenance or non-gold markers are invalid")
    if set(dataset) - {
        "schema",
        "dataset_id",
        "synthetic",
        "gold_standard",
        "quality_claim_allowed",
        "sources",
        "tasks",
        "page_audits",
        "judgment_status",
        "review_audit",
    }:
        raise MineruChartReviewError("chart dataset contains unsupported top-level fields")
    _identifier(dataset.get("dataset_id"), "dataset_id")
    sources = dataset.get("sources")
    tasks = dataset.get("tasks")
    page_audits = dataset.get("page_audits")
    if (
        not isinstance(sources, dict)
        or not sources
        or not isinstance(tasks, list)
        or not tasks
        or not isinstance(page_audits, list)
        or not page_audits
    ):
        raise MineruChartReviewError("chart dataset needs sources, QA tasks, and page audits")
    source_splits: dict[str, str] = {}
    pdf_hash_splits: dict[str, str] = {}
    for source_id, source in sources.items():
        _identifier(source_id, "source_id")
        if not isinstance(source, dict):
            raise MineruChartReviewError("chart source metadata is invalid")
        if set(source) != {
            "pdf_sha256",
            "parse_report_sha256",
            "parser_version",
            "rights_attested",
        }:
            raise MineruChartReviewError("chart source fields must be limited to provenance")
        if source.get("rights_attested") is not True:
            raise MineruChartReviewError("chart evaluation requires source rights attestation")
        for field in ("pdf_sha256", "parse_report_sha256"):
            _sha(source.get(field), field)
        if (
            not isinstance(source.get("parser_version"), str)
            or not source["parser_version"].strip()
        ):
            raise MineruChartReviewError("parser_version is required")

    task_ids: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise MineruChartReviewError("chart task must be an object")
        if set(task) - {
            "task_id",
            "source_id",
            "split",
            "page_number",
            "page_image_ref",
            "page_image_sha256",
            "element_id",
            "bbox",
            "source_pdf_sha256",
            "parse_report_sha256",
            "question",
            "predicted_facts",
            "predicted_abstained",
            "reference_status",
            "reference_facts",
            "review_note",
        }:
            raise MineruChartReviewError("chart task contains unsupported fields")
        for field in ("task_id", "source_id", "element_id"):
            _identifier(task.get(field), field)
        task_id = task["task_id"]
        source_id = task["source_id"]
        if task_id in task_ids or source_id not in sources:
            raise MineruChartReviewError("chart task ID is duplicated or source is unknown")
        task_ids.add(task_id)
        split = task.get("split")
        if split not in SPLITS:
            raise MineruChartReviewError("chart task split must be dev or test")
        if source_id in source_splits and source_splits[source_id] != split:
            raise MineruChartReviewError("pages from one source must stay in the same split")
        pdf_hash = sources[source_id]["pdf_sha256"]
        if pdf_hash in pdf_hash_splits and pdf_hash_splits[pdf_hash] != split:
            raise MineruChartReviewError("identical PDF hashes must stay in the same split")
        source_splits[source_id] = split
        pdf_hash_splits[pdf_hash] = split
        if (
            type(task.get("page_number")) is not int
            or task["page_number"] < 1
            or not isinstance(task.get("question"), str)
            or not task["question"].strip()
            or len(task["question"]) > 1000
            or not isinstance(task.get("page_image_ref"), str)
            or not task["page_image_ref"].strip()
        ):
            raise MineruChartReviewError(
                "chart task question, page, or local image reference is invalid"
            )
        image_ref = PurePosixPath(task["page_image_ref"])
        if (
            image_ref.is_absolute()
            or ".." in image_ref.parts
            or ":" in image_ref.parts[0]
            or "\\" in task["page_image_ref"]
        ):
            raise MineruChartReviewError("page image reference must stay inside the local dataset")
        _sha(task.get("page_image_sha256"), "page_image_sha256")
        if (
            task.get("source_pdf_sha256") != sources[source_id]["pdf_sha256"]
            or task.get("parse_report_sha256") != sources[source_id]["parse_report_sha256"]
        ):
            raise MineruChartReviewError(
                "chart task source lineage differs from its source manifest"
            )
        bbox = task.get("bbox")
        if not _valid_bbox(bbox):
            raise MineruChartReviewError("chart task bbox is invalid")
        facts = task.get("predicted_facts")
        if not isinstance(facts, list) or len(facts) > 100:
            raise MineruChartReviewError("predicted_facts must be a bounded list")
        for fact in facts:
            _validate_fact(fact)
        if type(task.get("predicted_abstained")) is not bool:
            raise MineruChartReviewError("predicted_abstained must be boolean")
    audit_ids: set[str] = set()
    source_page_splits: dict[tuple[str, int], str] = {}
    source_page_image_hashes: dict[tuple[str, int], str] = {}
    for audit in page_audits:
        if not isinstance(audit, dict):
            raise MineruChartReviewError("page audit must be an object")
        if set(audit) - {
            "audit_id",
            "source_id",
            "split",
            "page_number",
            "page_image_ref",
            "page_image_sha256",
            "parse_report_sha256",
            "predicted_chart_count",
            "predicted_chart_bboxes",
            "review_status",
            "reference_chart_count",
            "reference_chart_bboxes",
            "reviewed",
            "review_note",
        }:
            raise MineruChartReviewError("page audit contains unsupported fields")
        for field in ("audit_id", "source_id"):
            _identifier(audit.get(field), field)
        audit_id, source_id = audit["audit_id"], audit["source_id"]
        if audit_id in audit_ids or source_id not in sources:
            raise MineruChartReviewError("page audit ID is duplicated or source is unknown")
        audit_ids.add(audit_id)
        split = audit.get("split")
        page = audit.get("page_number")
        if split not in SPLITS or type(page) is not int or page < 1:
            raise MineruChartReviewError("page audit split or page number is invalid")
        source_page = (source_id, page)
        if source_page in source_page_splits:
            raise MineruChartReviewError("page audits must be unique per source and page")
        source_page_splits[source_page] = split
        source_page_image_hashes[source_page] = audit.get("page_image_sha256")
        if source_splits.get(source_id, split) != split:
            raise MineruChartReviewError("pages from one source must stay in the same split")
        if pdf_hash_splits.get(sources[source_id]["pdf_sha256"], split) != split:
            raise MineruChartReviewError("identical PDF hashes must stay in the same split")
        source_splits[source_id] = split
        pdf_hash_splits[sources[source_id]["pdf_sha256"]] = split
        if (
            not isinstance(audit.get("page_image_ref"), str)
            or not audit["page_image_ref"].strip()
            or audit.get("parse_report_sha256") != sources[source_id]["parse_report_sha256"]
            or type(audit.get("predicted_chart_count")) is not int
            or not 0 <= audit["predicted_chart_count"] <= 100
        ):
            raise MineruChartReviewError("page audit prediction or provenance is invalid")
        image_ref = PurePosixPath(audit["page_image_ref"])
        if (
            image_ref.is_absolute()
            or ".." in image_ref.parts
            or ":" in image_ref.parts[0]
            or "\\" in audit["page_image_ref"]
        ):
            raise MineruChartReviewError("page image reference must stay inside the local dataset")
        _sha(audit.get("page_image_sha256"), "page_image_sha256")
        predicted_boxes = audit.get("predicted_chart_bboxes")
        if "predicted_chart_bboxes" in audit and (
            not isinstance(predicted_boxes, list)
            or len(predicted_boxes) != audit["predicted_chart_count"]
            or any(not _valid_bbox(box, normalized=True) for box in predicted_boxes)
        ):
            raise MineruChartReviewError("predicted chart boxes must match the predicted count")
        if audit.get("review_status") == "reviewed":
            if (
                audit.get("reviewed") is not True
                or type(audit.get("reference_chart_count")) is not int
                or not 0 <= audit["reference_chart_count"] <= 100
            ):
                raise MineruChartReviewError("reviewed page audit needs a reference chart count")
            reference_boxes = audit.get("reference_chart_bboxes")
            if "reference_chart_bboxes" in audit and (
                not isinstance(reference_boxes, list)
                or len(reference_boxes) != audit["reference_chart_count"]
                or any(not _valid_bbox(box, normalized=True) for box in reference_boxes)
            ):
                raise MineruChartReviewError("reference chart boxes must match the reviewed count")
        elif audit.get("review_status") == "uncertain":
            if (
                audit.get("reviewed") is not True
                or audit.get("reference_chart_count") is not None
                or "reference_chart_bboxes" in audit
            ):
                raise MineruChartReviewError(
                    "uncertain page audit must not carry a reference count"
                )
        elif (
            audit.get("review_status") is not None
            or audit.get("reviewed") is not None
            or "reference_chart_bboxes" in audit
        ):
            raise MineruChartReviewError("page audit review status is invalid")
    if any((task["source_id"], task["page_number"]) not in source_page_splits for task in tasks):
        raise MineruChartReviewError("every chart QA task page must have a page-presence audit")
    if any(
        task["page_image_sha256"]
        != source_page_image_hashes[(task["source_id"], task["page_number"])]
        for task in tasks
    ):
        raise MineruChartReviewError("chart task and page audit image hashes disagree")
    if set(source_splits) != set(sources):
        raise MineruChartReviewError("every source must have at least one task or page audit")
    if "test" not in source_splits.values():
        raise MineruChartReviewError("dataset needs a document-disjoint held-out test source")
    if not any(
        audit["split"] == "test" and audit["predicted_chart_count"] == 0 for audit in page_audits
    ):
        raise MineruChartReviewError(
            "held-out page audits must sample at least one zero-prediction page"
        )
    if dataset.get("judgment_status") == "human_reviewed":
        audit = dataset.get("review_audit")
        if (
            not isinstance(audit, dict)
            or set(audit)
            != {
                "reviewer",
                "reviewed_at",
                "review_pack_sha256",
                "source_dataset_sha256",
                "reviewed_content_sha256",
                "reviewed_task_count",
                "reviewed_page_count",
            }
            or not isinstance(audit.get("reviewer"), str)
            or not audit["reviewer"].strip()
            or not isinstance(audit.get("reviewed_at"), str)
            or not audit["reviewed_at"].strip()
            or type(audit.get("reviewed_task_count")) is not int
            or audit["reviewed_task_count"] != len(tasks)
        ):
            raise MineruChartReviewError("human review audit is missing or incomplete")
        _sha(audit.get("review_pack_sha256"), "review_pack_sha256")
        _sha(audit.get("source_dataset_sha256"), "source_dataset_sha256")
        _sha(audit.get("reviewed_content_sha256"), "reviewed_content_sha256")
        if audit["reviewed_content_sha256"] != _reviewed_content_sha256(dataset):
            raise MineruChartReviewError("human-reviewed data changed after import")
        if audit.get("reviewed_page_count") != len(page_audits):
            raise MineruChartReviewError("human page-audit count does not match the dataset")
        if any(row.get("review_status") not in {"reviewed", "uncertain"} for row in page_audits):
            raise MineruChartReviewError("human-reviewed dataset has incomplete page audits")
        for task in tasks:
            facts = task.get("reference_facts")
            status = task.get("reference_status")
            if status not in REFERENCE_STATUSES or not isinstance(facts, list):
                raise MineruChartReviewError("human-reviewed chart references are incomplete")
            if (status == "answerable") != bool(facts):
                raise MineruChartReviewError("answerable status must agree with reference facts")
            seen_fact_ids: set[str] = set()
            for fact in facts:
                _validate_fact(fact, reference=True)
                _identifier(fact.get("fact_id"), "fact_id")
                if fact["fact_id"] in seen_fact_ids:
                    raise MineruChartReviewError("reference fact IDs must be unique per task")
                seen_fact_ids.add(fact["fact_id"])
    elif dataset.get("judgment_status") is not None:
        raise MineruChartReviewError("unsupported chart judgment status")


def load_dataset(path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        dataset = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MineruChartReviewError("dataset must be valid UTF-8 JSON") from error
    validate_dataset(dataset)
    return dataset, hashlib.sha256(raw).hexdigest()


def build_review_pack(dataset: dict[str, Any], dataset_sha256: str) -> dict[str, Any]:
    validate_dataset(dataset)
    if dataset.get("judgment_status") is not None:
        raise MineruChartReviewError("review packs can only be exported from an unreviewed dataset")
    _sha(dataset_sha256, "dataset_sha256")
    return {
        "schema": REVIEW_SCHEMA,
        "review_status": "awaiting_human_review",
        "source_dataset_sha256": dataset_sha256,
        "dataset_id": dataset.get("dataset_id"),
        "sources": dataset["sources"],
        "page_audits": [
            {
                "audit_id": audit["audit_id"],
                "source_id": audit["source_id"],
                "split": audit["split"],
                "page_number": audit["page_number"],
                "page_image_ref": audit["page_image_ref"],
                "page_image_sha256": audit["page_image_sha256"],
                "parse_report_sha256": audit["parse_report_sha256"],
                "predicted_chart_count": audit["predicted_chart_count"],
                **(
                    {"predicted_chart_bboxes": audit["predicted_chart_bboxes"]}
                    if "predicted_chart_bboxes" in audit
                    else {}
                ),
                "review_status": None,
                "reference_chart_count": None,
                "reviewed": False,
                "review_note": "",
            }
            for audit in dataset["page_audits"]
        ],
        "rows": [
            {
                "task_id": task["task_id"],
                "source_id": task["source_id"],
                "split": task["split"],
                "page_number": task["page_number"],
                "page_image_ref": task["page_image_ref"],
                "page_image_sha256": task["page_image_sha256"],
                "element_id": task["element_id"],
                "bbox": task["bbox"],
                "question": task["question"],
                "predicted_facts": task["predicted_facts"],
                "predicted_abstained": task["predicted_abstained"],
                "reference_status": None,
                "reference_facts": [],
                "reviewed": False,
                "review_note": "",
            }
            for task in dataset["tasks"]
        ],
    }


def apply_review_pack(
    dataset: dict[str, Any],
    dataset_sha256: str,
    pack: dict[str, Any],
    *,
    reviewer: str,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    validate_dataset(dataset)
    if dataset.get("judgment_status") is not None:
        raise MineruChartReviewError("review packs can only be imported into an unreviewed dataset")
    _sha(dataset_sha256, "dataset_sha256")
    if not reviewer.strip() or len(reviewer.strip()) > 120:
        raise MineruChartReviewError("reviewer must be a non-empty name of at most 120 characters")
    if (
        not isinstance(pack, dict)
        or pack.get("schema") != REVIEW_SCHEMA
        or pack.get("review_status") != "awaiting_human_review"
        or pack.get("source_dataset_sha256") != dataset_sha256
        or pack.get("dataset_id") != dataset.get("dataset_id")
        or pack.get("sources") != dataset["sources"]
    ):
        raise MineruChartReviewError("review pack is stale or belongs to another dataset")

    source_audits = {audit["audit_id"]: audit for audit in dataset["page_audits"]}
    pack_audits = pack.get("page_audits")
    if not isinstance(pack_audits, list) or len(pack_audits) != len(source_audits):
        raise MineruChartReviewError("review pack must contain every page audit exactly once")
    reviewed_audits: dict[str, dict[str, Any]] = {}
    for row in pack_audits:
        if not isinstance(row, dict):
            raise MineruChartReviewError("page audit review row must be an object")
        audit_id = row.get("audit_id")
        source_audit = source_audits.get(audit_id)
        if source_audit is None or audit_id in reviewed_audits:
            raise MineruChartReviewError("review pack contains an unknown or duplicate page audit")
        if any(row.get(key) != value for key, value in source_audit.items()):
            raise MineruChartReviewError("page audit provenance changed since export")
        status = row.get("review_status")
        if row.get("reviewed") is not True or status not in {"reviewed", "uncertain"}:
            raise MineruChartReviewError("each sampled page needs reviewed or uncertain status")
        expected_count = row.get("reference_chart_count")
        if status == "reviewed" and (
            type(expected_count) is not int or not 0 <= expected_count <= 100
        ):
            raise MineruChartReviewError("reviewed page needs a valid chart count")
        if status == "uncertain" and expected_count is not None:
            raise MineruChartReviewError("uncertain page must not have an expected chart count")
        note = row.get("review_note", "")
        if not isinstance(note, str) or len(note) > 1000:
            raise MineruChartReviewError("page audit notes must be text of at most 1000 characters")
        reviewed_audits[audit_id] = {
            "review_status": status,
            "reference_chart_count": expected_count,
            **(
                {"reference_chart_bboxes": row["reference_chart_bboxes"]}
                if "reference_chart_bboxes" in row
                else {}
            ),
            "reviewed": True,
            "review_note": note,
        }

    tasks = {task["task_id"]: task for task in dataset["tasks"]}
    rows = pack.get("rows")
    if not isinstance(rows, list) or len(rows) != len(tasks):
        raise MineruChartReviewError("review pack must contain every chart task exactly once")
    reviewed_by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise MineruChartReviewError("review row must be an object")
        task_id = row.get("task_id")
        task = tasks.get(task_id)
        if task is None or task_id in reviewed_by_id:
            raise MineruChartReviewError("review pack contains an unknown or duplicate chart task")
        immutable = {
            "source_id": task["source_id"],
            "split": task["split"],
            "page_number": task["page_number"],
            "page_image_ref": task["page_image_ref"],
            "page_image_sha256": task["page_image_sha256"],
            "element_id": task["element_id"],
            "bbox": task["bbox"],
            "question": task["question"],
            "predicted_facts": task["predicted_facts"],
            "predicted_abstained": task["predicted_abstained"],
        }
        if any(row.get(key) != value for key, value in immutable.items()):
            raise MineruChartReviewError("review task content or provenance changed since export")
        if row.get("reviewed") is not True or row.get("reference_status") not in REFERENCE_STATUSES:
            raise MineruChartReviewError("each chart task needs an explicit human review decision")
        reference_facts = row.get("reference_facts")
        if not isinstance(reference_facts, list) or len(reference_facts) > 100:
            raise MineruChartReviewError("reference_facts must be a bounded list")
        fact_ids: set[str] = set()
        for fact in reference_facts:
            _validate_fact(fact, reference=True)
            _identifier(fact.get("fact_id"), "fact_id")
            if fact["fact_id"] in fact_ids:
                raise MineruChartReviewError("reference fact IDs must be unique within a task")
            fact_ids.add(fact["fact_id"])
        if (row["reference_status"] == "answerable") != bool(reference_facts):
            raise MineruChartReviewError("answerable status must agree with reference facts")
        note = row.get("review_note", "")
        if not isinstance(note, str) or len(note) > 1000:
            raise MineruChartReviewError("review notes must be text of at most 1000 characters")
        reviewed_by_id[task_id] = {
            "reference_status": row["reference_status"],
            "reference_facts": reference_facts,
            "review_note": note,
        }

    result = {**dataset, "tasks": [], "page_audits": []}
    for task in dataset["tasks"]:
        result["tasks"].append({**task, **reviewed_by_id[task["task_id"]]})
    for audit in dataset["page_audits"]:
        result["page_audits"].append({**audit, **reviewed_audits[audit["audit_id"]]})
    result["judgment_status"] = "human_reviewed"
    result["review_audit"] = {
        "reviewer": reviewer.strip(),
        "reviewed_at": reviewed_at or datetime.now(UTC).isoformat(),
        "source_dataset_sha256": dataset_sha256,
        "review_pack_sha256": hashlib.sha256(
            json.dumps(pack, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "reviewed_task_count": len(tasks),
        "reviewed_page_count": len(source_audits),
    }
    result["review_audit"]["reviewed_content_sha256"] = _reviewed_content_sha256(result)
    validate_dataset(result)
    return result


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _matches(predicted: dict[str, Any], reference: dict[str, Any]) -> bool:
    if predicted["fact_type"] != reference["fact_type"]:
        return False
    if predicted["fact_type"] == "numeric_value":
        if _normalize_text(predicted.get("unit", "")) != _normalize_text(reference.get("unit", "")):
            return False
        try:
            difference = abs(Decimal(str(predicted["value"])) - Decimal(str(reference["value"])))
            tolerance = Decimal(str(reference.get("absolute_tolerance", 0)))
        except InvalidOperation:
            return False
        return difference <= tolerance
    return _normalize_text(predicted["value"]) == _normalize_text(reference["value"])


def _score_fact_lists(
    predicted: list[dict[str, Any]], reference: list[dict[str, Any]]
) -> tuple[int, int, int]:
    pairs = _match_fact_indices(predicted, reference)
    matched = len(pairs)
    return matched, len(predicted) - matched, len(reference) - matched


def _match_fact_indices(
    predicted: list[dict[str, Any]], reference: list[dict[str, Any]]
) -> list[tuple[int, int]]:
    matched_prediction: dict[int, int] = {}

    def assign(reference_index: int, visited: set[int]) -> bool:
        for predicted_index, fact in enumerate(predicted):
            if predicted_index in visited or not _matches(fact, reference[reference_index]):
                continue
            visited.add(predicted_index)
            if predicted_index not in matched_prediction or assign(
                matched_prediction[predicted_index], visited
            ):
                matched_prediction[predicted_index] = reference_index
                return True
        return False

    for reference_index in range(len(reference)):
        assign(reference_index, set())
    return sorted(
        (
            (predicted_index, reference_index)
            for predicted_index, reference_index in matched_prediction.items()
        ),
        key=lambda pair: (pair[1], pair[0]),
    )


def _box_iou(first: list[float], second: list[float]) -> float:
    width = max(0, min(first[2], second[2]) - max(first[0], second[0]))
    height = max(0, min(first[3], second[3]) - max(first[1], second[1]))
    intersection = width * height
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    return intersection / (first_area + second_area - intersection)


def _matched_chart_boxes(predicted: list[list[float]], reference: list[list[float]]) -> int:
    edges = [
        [index for index, box in enumerate(reference) if _box_iou(prediction, box) >= 0.5]
        for prediction in predicted
    ]
    matched_reference: dict[int, int] = {}

    def match(prediction_index: int, seen: set[int]) -> bool:
        for reference_index in edges[prediction_index]:
            if reference_index in seen:
                continue
            seen.add(reference_index)
            if reference_index not in matched_reference or match(
                matched_reference[reference_index], seen
            ):
                matched_reference[reference_index] = prediction_index
                return True
        return False

    for prediction_index in range(len(predicted)):
        match(prediction_index, set())
    return len(matched_reference)


def evaluate_reviewed_dataset(dataset: dict[str, Any], dataset_sha256: str) -> dict[str, Any]:
    validate_dataset(dataset)
    _sha(dataset_sha256, "dataset_sha256")
    if dataset.get("judgment_status") != "human_reviewed":
        raise MineruChartReviewError("chart metrics require an explicitly human-reviewed dataset")
    test_tasks = [task for task in dataset["tasks"] if task["split"] == "test"]
    if not test_tasks or any("reference_facts" not in task for task in test_tasks):
        raise MineruChartReviewError("held-out human-reviewed test tasks are required")
    scored_tasks = [task for task in test_tasks if task["reference_status"] != "uncertain"]
    if not scored_tasks:
        raise MineruChartReviewError("held-out test split has no adjudicated chart tasks")
    test_audits = [row for row in dataset["page_audits"] if row["split"] == "test"]
    scored_audits = [row for row in test_audits if row["review_status"] == "reviewed"]
    if not test_audits or not scored_audits:
        raise MineruChartReviewError("held-out test split has no reviewed page-presence audits")

    bucket_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    total = [0, 0, 0]
    abstention_correct = 0
    task_rows: list[dict[str, Any]] = []
    for task in scored_tasks:
        task_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        matched, false_positive, false_negative = _score_fact_lists(
            task["predicted_facts"], task["reference_facts"]
        )
        total[0] += matched
        total[1] += len(task["predicted_facts"])
        total[2] += len(task["reference_facts"])
        for fact in task["predicted_facts"]:
            kind = fact["fact_type"]
            bucket_counts[kind][1] += 1
            task_counts[kind][1] += 1
        for fact in task["reference_facts"]:
            kind = fact["fact_type"]
            bucket_counts[kind][2] += 1
            task_counts[kind][2] += 1
        for _, reference_index in _match_fact_indices(
            task["predicted_facts"], task["reference_facts"]
        ):
            kind = task["reference_facts"][reference_index]["fact_type"]
            bucket_counts[kind][0] += 1
            task_counts[kind][0] += 1
        abstention_ok = task["predicted_abstained"] == (task["reference_status"] == "unanswerable")
        abstention_correct += int(abstention_ok)
        task_rows.append(
            {
                "task_id": task["task_id"],
                "source_id": task["source_id"],
                "matched_facts": matched,
                "false_positive_facts": false_positive,
                "false_negative_facts": false_negative,
                "abstention_correct": abstention_ok,
                "fact_metrics_by_type": {
                    kind: _prf(counts) for kind, counts in sorted(task_counts.items())
                },
            }
        )
    detection_true_positive = sum(
        min(row["predicted_chart_count"], row["reference_chart_count"]) for row in scored_audits
    )
    detected_count = sum(row["predicted_chart_count"] for row in scored_audits)
    reference_count = sum(row["reference_chart_count"] for row in scored_audits)
    missed_figure_pages = sum(
        row["predicted_chart_count"] == 0 and row["reference_chart_count"] > 0
        for row in scored_audits
    )
    localized_pages = [
        row
        for row in scored_audits
        if row.get("predicted_chart_bboxes") is not None
        and row.get("reference_chart_bboxes") is not None
    ]
    localization_counts = [
        sum(
            _matched_chart_boxes(row["predicted_chart_bboxes"], row["reference_chart_bboxes"])
            for row in localized_pages
        ),
        sum(len(row["predicted_chart_bboxes"]) for row in localized_pages),
        sum(len(row["reference_chart_bboxes"]) for row in localized_pages),
    ]
    return {
        "schema": "papertrail.mineru-chart-evaluation.v1",
        "dataset_id": dataset.get("dataset_id"),
        "dataset_sha256": dataset_sha256,
        "source_dataset_sha256": dataset["review_audit"]["source_dataset_sha256"],
        "review_pack_sha256": dataset["review_audit"]["review_pack_sha256"],
        "judgment_status": dataset["judgment_status"],
        "gold_standard": False,
        "quality_claim_allowed": False,
        "split": "test",
        "test_task_count": len(test_tasks),
        "scored_task_count": len(scored_tasks),
        "uncertain_task_count": len(test_tasks) - len(scored_tasks),
        "test_source_count": len({task["source_id"] for task in test_tasks}),
        "fact_metrics": _prf(total),
        "fact_metrics_by_type": {
            kind: _prf(counts) for kind, counts in sorted(bucket_counts.items())
        },
        "abstention_accuracy": abstention_correct / len(scored_tasks),
        "chart_detection": {
            "reviewed_page_count": len(scored_audits),
            "uncertain_page_count": len(test_audits) - len(scored_audits),
            "exact_chart_count_page_accuracy": sum(
                row["predicted_chart_count"] == row["reference_chart_count"]
                for row in scored_audits
            )
            / len(scored_audits),
            "missed_figure_page_count": missed_figure_pages,
            "missed_figure_page_rate": missed_figure_pages / len(scored_audits),
            "count_metrics": _prf([detection_true_positive, detected_count, reference_count]),
            "localization": {
                "iou_threshold": 0.5,
                "evaluated_page_count": len(localized_pages),
                "not_evaluated_page_count": len(scored_audits) - len(localized_pages),
                "evaluated_page_rate": len(localized_pages) / len(scored_audits),
                "metrics": _prf(localization_counts) if localized_pages else None,
            },
        },
        "tasks": task_rows,
    }


def _prf(counts: list[int]) -> dict[str, float | int]:
    true_positive, predicted, expected = counts
    precision = true_positive / predicted if predicted else float(expected == 0)
    recall = true_positive / expected if expected else float(predicted == 0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "predicted": predicted,
        "reference": expected,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


__all__ = [
    "DATASET_SCHEMA",
    "REVIEW_SCHEMA",
    "MineruChartReviewError",
    "apply_review_pack",
    "build_review_pack",
    "evaluate_reviewed_dataset",
    "load_dataset",
    "validate_dataset",
]
