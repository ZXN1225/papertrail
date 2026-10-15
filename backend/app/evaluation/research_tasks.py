"""Lexical regression benchmark for the synthetic research-task fixture.

This module tests evaluation plumbing and deterministic token-overlap behavior only.
Its fixture labels are not a gold standard and its scores cannot support quality claims.
"""

from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
from typing import Any

from app.retrieval.tokenizer import TOKENIZER_VERSION, tokenize

DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "evaluation"
    / "TEST-research-task-lexical-v2.json"
)
EXPECTED_DOCUMENT_COUNT = 12
EXPECTED_TASK_COUNT = 40
EXPECTED_ANSWERABLE_COUNT = 24
EXPECTED_UNANSWERABLE_COUNT = 16
SCORING_VERSION = "unique-token-overlap-v4-plural-normalized-document-split"
QUALITY_CLAIM_ALLOWED = False


class ResearchTaskEvaluationError(ValueError):
    """Raised when the isolated synthetic research-task fixture is invalid."""


def _contains_fact(text: str, fact: str) -> bool:
    """Check an exact support span while tolerating case and whitespace differences."""
    normalized_text = " ".join(text.casefold().split())
    normalized_fact = " ".join(fact.casefold().split())
    return normalized_fact in normalized_text


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> tuple[dict[str, Any], str]:
    """Load fixture bytes and return parsed data plus their exact SHA-256 digest."""
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        dataset = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResearchTaskEvaluationError("dataset must be valid UTF-8 JSON") from error
    validate_dataset(dataset)
    return dataset, digest


def validate_dataset(dataset: Any) -> None:
    """Validate isolation, fixture counts, and evidence anchors before scoring."""
    if not isinstance(dataset, dict):
        raise ResearchTaskEvaluationError("dataset must be a JSON object")
    if dataset.get("synthetic") is not True:
        raise ResearchTaskEvaluationError("dataset must be synthetic=true")
    if dataset.get("quality_claim_allowed") is not False:
        raise ResearchTaskEvaluationError("quality_claim_allowed must be false")
    if dataset.get("gold_standard") is not False:
        raise ResearchTaskEvaluationError("synthetic fixture cannot be marked as a gold standard")

    documents = dataset.get("documents")
    tasks = dataset.get("tasks")
    if not isinstance(documents, list) or len(documents) != EXPECTED_DOCUMENT_COUNT:
        raise ResearchTaskEvaluationError(
            f"dataset must contain exactly {EXPECTED_DOCUMENT_COUNT} synthetic documents"
        )
    if not isinstance(tasks, list) or len(tasks) != EXPECTED_TASK_COUNT:
        raise ResearchTaskEvaluationError(
            f"dataset must contain exactly {EXPECTED_TASK_COUNT} synthetic tasks"
        )

    legacy_unsplit = (
        dataset.get("dataset_id") == "TEST-research-task-lexical-v1"
        and dataset.get("dataset_version") == 1
        and all(isinstance(document, dict) and "split" not in document for document in documents)
        and all(isinstance(task, dict) and "split" not in task for task in tasks)
    )

    document_by_id: dict[str, dict[str, Any]] = {}
    for document in documents:
        if not isinstance(document, dict):
            raise ResearchTaskEvaluationError("each document must be an object")
        document_id = document.get("id")
        if (
            not isinstance(document_id, str)
            or not document_id.startswith("TEST-")
            or document_id in document_by_id
            or document.get("synthetic") is not True
            or (not legacy_unsplit and document.get("split") not in {"dev", "test"})
            or not isinstance(document.get("title"), str)
            or not document["title"].strip()
            or not isinstance(document.get("text"), str)
            or not document["text"].strip()
        ):
            raise ResearchTaskEvaluationError(
                "each document needs a unique TEST-* ID and synthetic=true content"
            )
        document_by_id[document_id] = document

    task_ids: set[str] = set()
    answerable_count = 0
    for task in tasks:
        if not isinstance(task, dict):
            raise ResearchTaskEvaluationError("each task must be an object")
        task_id = task.get("id")
        if (
            not isinstance(task_id, str)
            or not task_id.startswith("TEST-")
            or task_id in task_ids
            or task.get("synthetic") is not True
            or not isinstance(task.get("question"), str)
            or not task["question"].strip()
            or not isinstance(task.get("challenge_type"), str)
            or not task["challenge_type"].strip()
            or type(task.get("expected_answerable")) is not bool
        ):
            raise ResearchTaskEvaluationError(
                "each task needs a unique TEST-* ID, synthetic=true, and an answerability label"
            )
        task_ids.add(task_id)
        if not legacy_unsplit and task.get("split") not in {"dev", "test"}:
            raise ResearchTaskEvaluationError("each task must declare the dev or test split")
        evidence = task.get("evidence")
        required_fact = task.get("required_fact")
        if not isinstance(required_fact, str) or not required_fact.strip():
            raise ResearchTaskEvaluationError("each task requires an exact required_fact span")
        if task["expected_answerable"]:
            answerable_count += 1
            if not isinstance(evidence, dict):
                raise ResearchTaskEvaluationError("answerable tasks require an evidence anchor")
            document_id = evidence.get("document_id")
            anchor = evidence.get("anchor")
            if (
                document_id not in document_by_id
                or not isinstance(anchor, str)
                or not anchor.strip()
                or not _contains_fact(document_by_id[document_id]["text"], anchor)
                or not _contains_fact(anchor, required_fact)
            ):
                raise ResearchTaskEvaluationError(
                    "answerable task evidence and required_fact must point to a TEST document span"
                )
            if not legacy_unsplit and task["split"] != document_by_id[document_id]["split"]:
                raise ResearchTaskEvaluationError(
                    "task split must match its evidence document split"
                )
        elif evidence is not None:
            raise ResearchTaskEvaluationError("unanswerable tasks must not have evidence anchors")
        else:
            related_document_id = task.get("related_document_id")
            if related_document_id not in document_by_id:
                raise ResearchTaskEvaluationError(
                    "unanswerable tasks require a related TEST document"
                )
            if not legacy_unsplit and task["split"] != document_by_id[related_document_id]["split"]:
                raise ResearchTaskEvaluationError(
                    "task split must match its related document split"
                )
            if any(
                _contains_fact(f"{document['title']} {document['text']}", required_fact)
                for document in documents
            ):
                raise ResearchTaskEvaluationError(
                    "unanswerable required_fact must be absent from the entire fixture corpus"
                )

    if answerable_count != EXPECTED_ANSWERABLE_COUNT:
        raise ResearchTaskEvaluationError(
            f"dataset must contain exactly {EXPECTED_ANSWERABLE_COUNT} answerable tasks"
        )
    if len(tasks) - answerable_count != EXPECTED_UNANSWERABLE_COUNT:
        raise ResearchTaskEvaluationError(
            f"dataset must contain exactly {EXPECTED_UNANSWERABLE_COUNT} unanswerable tasks"
        )


def run_evaluation(
    dataset: dict[str, Any],
    dataset_sha256: str,
    *,
    top_k: int = 3,
    min_overlap_tokens: int = 2,
    split: str = "all",
) -> dict[str, Any]:
    """Evaluate lexical recall, exact evidence support, and evidence-gated abstention."""
    validate_dataset(dataset)
    if top_k < 1:
        raise ResearchTaskEvaluationError("top_k must be positive")
    if min_overlap_tokens < 1:
        raise ResearchTaskEvaluationError("min_overlap_tokens must be positive")
    if split not in {"all", "dev", "test"}:
        raise ResearchTaskEvaluationError("split must be all, dev or test")
    if split != "all" and dataset.get("dataset_version") == 1:
        raise ResearchTaskEvaluationError("the v1 dataset does not define isolated dev/test splits")
    if len(dataset_sha256) != 64 or any(char not in "0123456789abcdef" for char in dataset_sha256):
        raise ResearchTaskEvaluationError("dataset_sha256 must be a lowercase SHA-256 digest")

    documents = [
        document
        for document in dataset["documents"]
        if split == "all" or document.get("split") == split
    ]
    tasks = [task for task in dataset["tasks"] if split == "all" or task.get("split") == split]
    token_sets = {
        document["id"]: set(tokenize(f"{document['title']} {document['text']}"))
        for document in documents
    }
    document_by_id = {document["id"]: document for document in documents}
    answerable_rows: list[dict[str, Any]] = []
    confusion = {"true_positive": 0, "false_negative": 0, "true_negative": 0, "false_positive": 0}
    per_task: list[dict[str, Any]] = []

    for task in tasks:
        query_tokens = set(tokenize(task["question"]))
        required_fact = task["required_fact"]
        scored = [
            (len(query_tokens & document_tokens), document_id)
            for document_id, document_tokens in token_sets.items()
        ]
        lexical_candidates = [
            {
                "document_id": document_id,
                "overlap_tokens": score,
                "answer_constraint_supported": _contains_fact(
                    document_by_id[document_id]["text"], required_fact
                ),
            }
            for score, document_id in sorted(scored, key=lambda pair: (-pair[0], pair[1]))
            if score >= min_overlap_tokens
        ]
        ranked = lexical_candidates[:top_k]
        supported_hits = [hit for hit in ranked if hit["answer_constraint_supported"]]
        predicted_answerable = bool(supported_hits)
        expected_answerable = task["expected_answerable"]
        if expected_answerable and predicted_answerable:
            confusion["true_positive"] += 1
        elif expected_answerable:
            confusion["false_negative"] += 1
        elif predicted_answerable:
            confusion["false_positive"] += 1
        else:
            confusion["true_negative"] += 1

        row: dict[str, Any] = {
            "task_id": task["id"],
            "split": task.get("split", "all"),
            "challenge_type": task["challenge_type"],
            "expected_answerable": expected_answerable,
            "predicted_answerable": predicted_answerable,
            "false_refusal": expected_answerable and not predicted_answerable,
            "false_answer": not expected_answerable and predicted_answerable,
            "required_fact": required_fact,
            "lexical_candidate_count": len(lexical_candidates),
            "supported_evidence_document_ids": [hit["document_id"] for hit in supported_hits],
            "retrieved_document_ids": [hit["document_id"] for hit in ranked],
            "ranked_hits": ranked,
        }
        if expected_answerable:
            evidence = task["evidence"]
            relevant_id = evidence["document_id"]
            relevant_rank = next(
                (
                    index
                    for index, hit in enumerate(ranked, start=1)
                    if hit["document_id"] == relevant_id
                    and _contains_fact(
                        document_by_id[hit["document_id"]]["text"], evidence["anchor"]
                    )
                    and hit["answer_constraint_supported"]
                ),
                None,
            )
            row["evidence_document_id"] = relevant_id
            row["evidence_rank"] = relevant_rank
            row["hit_at_1"] = relevant_rank is not None and relevant_rank <= 1
            row["hit_at_k"] = relevant_rank is not None and relevant_rank <= top_k
            answerable_rows.append(row)
        per_task.append(row)

    answerable_denominator = len(answerable_rows)
    unanswerable_denominator = len(tasks) - answerable_denominator
    false_refusal_count = confusion["false_negative"]
    false_answer_count = confusion["false_positive"]
    evidence_hit_at_1 = sum(row["hit_at_1"] for row in answerable_rows)
    evidence_hit_at_k = sum(row["hit_at_k"] for row in answerable_rows)
    unanswerable_rows = [row for row in per_task if not row["expected_answerable"]]
    unanswerable_lexical_count = sum(
        row["lexical_candidate_count"] > 0 for row in unanswerable_rows
    )
    challenge_type_counts: dict[str, dict[str, int | float]] = {}
    for task, row in zip(tasks, per_task, strict=True):
        challenge_type = task["challenge_type"]
        group = challenge_type_counts.setdefault(
            challenge_type,
            {
                "task_count": 0,
                "answerable_denominator": 0,
                "unanswerable_denominator": 0,
                "false_refusal_count": 0,
                "false_answer_count": 0,
                "unanswerable_lexical_retrieval_count": 0,
            },
        )
        group["task_count"] += 1
        group["answerable_denominator"] += int(row["expected_answerable"])
        group["unanswerable_denominator"] += int(not row["expected_answerable"])
        group["false_refusal_count"] += int(row["false_refusal"])
        group["false_answer_count"] += int(row["false_answer"])
        group["unanswerable_lexical_retrieval_count"] += int(
            not row["expected_answerable"] and row["lexical_candidate_count"] > 0
        )
    for group in challenge_type_counts.values():
        group["false_refusal_rate"] = (
            group["false_refusal_count"] / group["answerable_denominator"]
            if group["answerable_denominator"]
            else 0.0
        )
        group["false_answer_rate"] = (
            group["false_answer_count"] / group["unanswerable_denominator"]
            if group["unanswerable_denominator"]
            else 0.0
        )
        group["unanswerable_lexical_retrieval_rate"] = (
            group["unanswerable_lexical_retrieval_count"] / group["unanswerable_denominator"]
            if group["unanswerable_denominator"]
            else 0.0
        )
    false_refusal_by_task = [row["task_id"] for row in per_task if row["false_refusal"]]
    false_answer_by_task = [row["task_id"] for row in per_task if row["false_answer"]]

    return {
        "evaluation": {
            "name": "synthetic-research-task-lexical-regression",
            "purpose": "evaluation-pipeline and lexical-behavior regression only",
            "quality_claim_allowed": QUALITY_CLAIM_ALLOWED,
            "gold_standard": False,
            "synthetic": True,
            "limitations": list(dataset["limitations"]),
        },
        "dataset": {
            "id": dataset["dataset_id"],
            "version": dataset["dataset_version"],
            "sha256": dataset_sha256,
            "synthetic": True,
            "document_count": len(documents),
            "task_count": len(tasks),
            "split": split,
            "answerable_count": answerable_denominator,
            "unanswerable_count": unanswerable_denominator,
            "quality_claim_allowed": QUALITY_CLAIM_ALLOWED,
            "gold_standard": False,
        },
        "runner_config": {
            "runner_version": 2,
            "python_version": platform.python_version(),
            "tokenizer": TOKENIZER_VERSION,
            "scoring": SCORING_VERSION,
            "top_k": top_k,
            "min_overlap_tokens": min_overlap_tokens,
            "split": split,
            "answerability_rule": (
                "at least one retrieved document contains the task's exact required_fact "
                "after case and whitespace normalization"
            ),
        },
        "summary": {
            "query_count": len(per_task),
            "answerable_denominator": answerable_denominator,
            "unanswerable_denominator": unanswerable_denominator,
            "evidence_hit_at_1": {
                "count": evidence_hit_at_1,
                "denominator": answerable_denominator,
                "rate": evidence_hit_at_1 / answerable_denominator,
            },
            f"evidence_hit_at_{top_k}": {
                "count": evidence_hit_at_k,
                "denominator": answerable_denominator,
                "rate": evidence_hit_at_k / answerable_denominator,
            },
            "false_refusal": {
                "count": false_refusal_count,
                "denominator": answerable_denominator,
                "rate": false_refusal_count / answerable_denominator,
                "task_ids": false_refusal_by_task,
            },
            "false_answer": {
                "count": false_answer_count,
                "denominator": unanswerable_denominator,
                "rate": false_answer_count / unanswerable_denominator,
                "task_ids": false_answer_by_task,
            },
            "unanswerable_lexical_retrieval": {
                "count": unanswerable_lexical_count,
                "denominator": unanswerable_denominator,
                "rate": unanswerable_lexical_count / unanswerable_denominator,
                "meaning": (
                    "negative tasks with lexical candidates before exact evidence gating; "
                    "diagnostic only"
                ),
            },
            "by_challenge_type": challenge_type_counts,
            "answerability_confusion": confusion,
            "answerability_accuracy": {
                "count": confusion["true_positive"] + confusion["true_negative"],
                "denominator": len(per_task),
                "rate": (confusion["true_positive"] + confusion["true_negative"]) / len(per_task),
            },
        },
        "per_task": per_task,
    }
