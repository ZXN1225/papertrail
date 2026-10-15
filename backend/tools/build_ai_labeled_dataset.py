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
                    evidence = dict(task["evidence"])
                    chunk = chunk_row(connection, evidence["chunk_id"])
                    if chunk is None:
                        rejected.append({"task_id": task["task_id"], "reason": "unknown_chunk_id"})
                        continue
                    chunk_source, page, element_type, content_hash, text = chunk
                    if chunk_source != source_id or content_hash != sources.get(source_id, {}).get(
                        "content_sha256"
                    ):
                        rejected.append({"task_id": task["task_id"], "reason": "source_mismatch"})
                        continue
                    if page != evidence["page_number"] or element_type != evidence["element_type"]:
                        rejected.append({"task_id": task["task_id"], "reason": "locator_mismatch"})
                        continue
                    if task["challenge_type"] not in ALLOWED_CHALLENGE_TYPES:
                        rejected.append(
                            {"task_id": task["task_id"], "reason": "bad_challenge_type"}
                        )
                        continue
                    if element_type == "table" and task["challenge_type"] != "table_lookup":
                        rejected.append(
                            {"task_id": task["task_id"], "reason": "table_type_mismatch"}
                        )
                        continue
                    if (
                        element_type == "figure_caption"
                        and task["challenge_type"] != "figure_caption"
                    ):
                        rejected.append(
                            {"task_id": task["task_id"], "reason": "caption_type_mismatch"}
                        )
                        continue
                    if normalize(evidence["quote"]) not in normalize(text):
                        rejected.append(
                            {"task_id": task["task_id"], "reason": "quote_not_verbatim"}
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
                            "evidence": {
                                "source_id": source_id,
                                "chunk_id": evidence["chunk_id"],
                                "page_number": page,
                                "element_type": element_type,
                                "quote": evidence["quote"],
                            },
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
