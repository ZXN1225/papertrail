"""Assemble and validate an AI-labeled evaluation dataset from agent-labeled batches.

Labels authored by AI agents are only usable if the mechanical claims behind them
hold: every evidence quote must exist verbatim inside the chunk it names, the chunk
must belong to the named source with the stated page and element type, and every
negative task's ``absent_fact`` must genuinely be absent from the whole approved
corpus. Unverifiable tasks are dropped and reported, never silently kept.

Read-only with respect to the database (``mode=ro``).

Usage (from ``backend/``)::

    uv run --locked python -m tools.build_ai_labeled_dataset \
        --batch data/storage/labeling/labeled-batch1.json \
        --batch data/storage/labeling/labeled-batch2.json \
        --batch data/storage/labeling/labeled-batch3.json \
        --output data/evaluation/ai-labeled-licensed-v1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_SCHEMA = "papertrail.ai-labeled-tasks.v1"
LABEL_SOURCE = "ai_agent_review"
ALLOWED_CHALLENGE_TYPES = ("single_fact", "multi_hop", "table_lookup", "figure_caption")
ALLOWED_ELEMENT_TYPES = ("paragraph", "table", "figure_caption", "heading", "list_item")


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def active_sources(connection: sqlite3.Connection) -> dict[str, dict[str, str]]:
    rows = connection.execute(
        """
        SELECT d.source_id, v.parser_version, v.content_sha256, v.source_document_sha256,
               v.license_id, v.license_url
        FROM fulltext_documents AS d
        JOIN fulltext_versions AS v
          ON v.source_type = d.source_type AND v.source_id = d.source_id
         AND v.content_sha256 = d.current_sha256
        WHERE d.source_type = 'arxiv' AND d.status = 'approved'
        ORDER BY d.source_id
        """
    )
    return {
        str(source_id): {
            "parser_version": parser_version,
            "content_sha256": content_sha256,
            "source_document_sha256": document_sha256,
            "license_id": license_id,
            "license_url": license_url,
        }
        for (
            source_id,
            parser_version,
            content_sha256,
            document_sha256,
            license_id,
            license_url,
        ) in rows
    }


def chunk_row(
    connection: sqlite3.Connection, chunk_id: str
) -> tuple[str, int, str, str, str] | None:
    row = connection.execute(
        """
        SELECT source_id, page_number, element_type, content_sha256, text
        FROM fulltext_chunks WHERE chunk_id = ?
        """,
        (chunk_id,),
    ).fetchone()
    return None if row is None else (row[0], row[1], row[2], row[3], row[4])


def validate_evidence_anchors(
    connection: sqlite3.Connection,
    source_id: str,
    source: dict[str, str],
    task: dict[str, Any],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    primary = task.get("evidence")
    raw_required = task.get("required_evidence")
    if not isinstance(primary, dict):
        return None, "invalid_evidence_anchor"
    if raw_required is None:
        raw_anchors = [primary]
    elif (
        not isinstance(raw_required, list)
        or not 2 <= len(raw_required) <= 8
        or any(not isinstance(anchor, dict) for anchor in raw_required)
    ):
        return None, "invalid_required_evidence"
    else:
        raw_anchors = raw_required
        anchor_ids = [anchor.get("chunk_id") for anchor in raw_anchors]
        if (
            any(not isinstance(anchor_id, str) or not anchor_id for anchor_id in anchor_ids)
            or len(anchor_ids) != len(set(anchor_ids))
            or primary.get("chunk_id") not in anchor_ids
        ):
            return None, "invalid_required_evidence"

    validated: list[dict[str, Any]] = []
    for anchor in raw_anchors:
        chunk_id = anchor.get("chunk_id")
        quote = anchor.get("quote")
        page = anchor.get("page_number")
        element_type = anchor.get("element_type")
        if (
            anchor.get("source_id") != source_id
            or not isinstance(chunk_id, str)
            or type(page) is not int
            or page < 1
            or not isinstance(element_type, str)
            or not isinstance(quote, str)
            or not quote.strip()
        ):
            return None, "invalid_evidence_anchor"
        chunk = chunk_row(connection, chunk_id)
        if chunk is None:
            return None, "unknown_chunk_id"
        chunk_source, actual_page, actual_type, content_hash, text = chunk
        if chunk_source != source_id or content_hash != source["content_sha256"]:
            return None, "source_mismatch"
        if actual_page != page or actual_type != element_type:
            return None, "locator_mismatch"
        if normalize(quote) not in normalize(text):
            return None, "quote_not_verbatim"
        validated.append(
            {
                "source_id": source_id,
                "chunk_id": chunk_id,
                "page_number": actual_page,
                "element_type": actual_type,
                "quote": quote,
            }
        )
    return validated, None


def full_corpus_text(connection: sqlite3.Connection, hashes: list[str]) -> str:
    placeholders = ",".join("?" for _ in hashes)
    parts = [
        row[0]
        for row in connection.execute(
            f"SELECT text FROM fulltext_chunks WHERE content_sha256 IN ({placeholders})",
            hashes,
        )
    ]
    return normalize(" ".join(parts))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()

    database = args.database or get_settings().resolved_data_storage_path
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    rejected: list[dict[str, str]] = []
    try:
        sources = active_sources(connection)
        if not sources:
            raise SystemExit("no approved full-text sources in this database")
        corpus = full_corpus_text(
            connection, [value["content_sha256"] for value in sources.values()]
        )

        tasks: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for batch_path in args.batch:
            batch = json.loads(batch_path.read_text(encoding="utf-8"))
            if (
                batch.get("label_source") != LABEL_SOURCE
                or batch.get("human_reviewed") is not False
            ):
                raise SystemExit(
                    f"{batch_path.name}: batch must be {LABEL_SOURCE}, not human reviewed"
                )
            for group in batch["batches"]:
                source_id = group["source_id"]
                for task in group["answerable_tasks"]:
                    if task["challenge_type"] not in ALLOWED_CHALLENGE_TYPES:
                        rejected.append(
                            {"task_id": task["task_id"], "reason": "bad_challenge_type"}
                        )
                        continue
                    source = sources.get(source_id)
                    anchors, reason = (
                        validate_evidence_anchors(connection, source_id, source, task)
                        if source is not None
                        else (None, "unknown_source")
                    )
                    if reason is not None or not anchors:
                        rejected.append(
                            {
                                "task_id": task["task_id"],
                                "reason": reason or "invalid_evidence_anchor",
                            }
                        )
                        continue
                    primary_chunk_id = task["evidence"]["chunk_id"]
                    primary = next(
                        anchor for anchor in anchors if anchor["chunk_id"] == primary_chunk_id
                    )
                    if task["challenge_type"] != "multi_hop":
                        if (
                            primary["element_type"] == "table"
                            and task["challenge_type"] != "table_lookup"
                        ):
                            rejected.append(
                                {"task_id": task["task_id"], "reason": "table_type_mismatch"}
                            )
                            continue
                        if (
                            primary["element_type"] == "figure_caption"
                            and task["challenge_type"] != "figure_caption"
                        ):
                            rejected.append(
                                {"task_id": task["task_id"], "reason": "caption_type_mismatch"}
                            )
                            continue
                    if task["task_id"] in seen_ids:
                        rejected.append({"task_id": task["task_id"], "reason": "duplicate_task_id"})
                        continue
                    seen_ids.add(task["task_id"])
                    tasks.append(
                        {
                            "task_id": task["task_id"],
                            "source_id": source_id,
                            "challenge_type": task["challenge_type"],
                            "question": task["question"].strip(),
                            "answer": task["answer"].strip(),
                            "expected_answerable": True,
                            "evidence": primary,
                            **(
                                {"required_evidence": anchors}
                                if task.get("required_evidence") is not None
                                else {}
                            ),
                        }
                    )
            for task in batch["unanswerable_tasks"]:
                fact = normalize(task["absent_fact"])
                if task["related_source_id"] not in sources:
                    rejected.append(
                        {"task_id": task["task_id"], "reason": "unknown_related_source"}
                    )
                    continue
                if fact and fact in corpus:
                    rejected.append({"task_id": task["task_id"], "reason": "absent_fact_present"})
                    continue
                if task["task_id"] in seen_ids:
                    rejected.append({"task_id": task["task_id"], "reason": "duplicate_task_id"})
                    continue
                seen_ids.add(task["task_id"])
                tasks.append(
                    {
                        "task_id": task["task_id"],
                        "source_id": task["related_source_id"],
                        "challenge_type": "unanswerable",
                        "question": task["question"].strip(),
                        "expected_answerable": False,
                        "absent_fact": task["absent_fact"].strip(),
                        "related_source_id": task["related_source_id"],
                    }
                )
    finally:
        connection.close()

    tasks.sort(key=lambda item: item["task_id"])
    dataset = {
        "schema": DATASET_SCHEMA,
        "dataset_id": "ai-labeled-licensed-v1",
        "created_by": "tools.build_ai_labeled_dataset",
        "synthetic": False,
        "gold_standard": False,
        "quality_claim_allowed": False,
        "human_reviewed": False,
        "label_source": LABEL_SOURCE,
        "label_method": (
            "AI agents authored each question from an indexed chunk of the licensed corpus; "
            "quote-to-chunk verbatim containment and corpus-wide absence of negative facts "
            "are verified mechanically by the build tool"
        ),
        "retrieval_method": "bm25",
        "top_k": args.top_k,
        "source_scope": "all_approved_arxiv",
        "sources": sources,
        "limitations": [
            "labels are AI-authored, not human-reviewed and not a gold standard",
            "questions were written from the same index that is being evaluated",
            "single licensed corpus of nine papers; not a general retrieval-quality estimate",
        ],
        "tasks": tasks,
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(dataset, ensure_ascii=False, indent=2) + "\n"
    target.write_text(raw, encoding="utf-8")
    answerable = sum(task["expected_answerable"] for task in tasks)
    print(f"wrote {target}")
    print(
        f"answerable={answerable} unanswerable={len(tasks) - answerable} rejected={len(rejected)}"
    )
    print(f"dataset sha256 = {hashlib.sha256(raw.encode('utf-8')).hexdigest()}")
    for item in rejected:
        print(f"  rejected {item['task_id']}: {item['reason']}")


if __name__ == "__main__":
    main()
