"""Re-version a frozen full-text retrieval diagnostic dataset to a new parser version.

The dataset is deliberately pinned to one parser version and to the exact reference
chunks of that version, so a parser upgrade invalidates it. Earlier upgrades rebuilt
it with throwaway scripts; this tool makes that reproducible.

Mapping rule (unchanged from the earlier records): a reference chunk is carried over
only when exactly one chunk of the new version matches it on source, page, element
type, ``retrieval_text`` and ``evidence_text``. When no unique match exists the old
chunk id is kept and the task is reported as unmapped, which the evaluator scores as
a miss rather than silently claiming a hit.

Read-only with respect to the database: the SQLite file is opened with ``mode=ro``.

Usage (from ``backend/``)::

    uv run --locked python -m tools.reversion_retrieval_dataset \
        --dataset data/evaluation/arxiv-r01-r03-current-v21-v1.json \
        --parser-version pdfplumber-layout-v27 \
        --output data/evaluation/arxiv-r01-r03-current-v27-v1.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from app.config import get_settings

CHUNK_COLUMNS = "page_number, element_type, retrieval_text, evidence_text"


def open_readonly(database: Path) -> sqlite3.Connection:
    if not database.exists():
        raise SystemExit(f"database not found: {database}")
    return sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)


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


def chunk_row(connection: sqlite3.Connection, chunk_id: str) -> tuple | None:
    return connection.execute(
        f"SELECT {CHUNK_COLUMNS} FROM fulltext_chunks WHERE chunk_id = ?", (chunk_id,)
    ).fetchone()


def match_new_chunk(
    connection: sqlite3.Connection, source_id: str, content_sha256: str, reference: tuple
) -> str | None:
    page_number, element_type, retrieval_text, evidence_text = reference
    rows = connection.execute(
        """
        SELECT chunk_id FROM fulltext_chunks
        WHERE source_type = 'arxiv' AND source_id = ? AND content_sha256 = ?
          AND page_number = ? AND element_type = ?
          AND retrieval_text = ? AND evidence_text = ?
        """,
        (source_id, content_sha256, page_number, element_type, retrieval_text, evidence_text),
    ).fetchall()
    if len(rows) == 1:
        return str(rows[0][0])
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--parser-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to overwrite an existing dataset: {args.output}")

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    connection = open_readonly(get_settings().resolved_data_storage_path)
    try:
        sources = active_sources(connection)
        versions = {value["parser_version"] for value in sources.values()}
        if versions != {args.parser_version}:
            raise SystemExit(
                f"active parser versions are {sorted(versions)}, expected {args.parser_version}"
            )

        remapped: list[dict] = []
        unmapped: list[str] = []
        for task in dataset["tasks"]:
            source_id = task["source_id"]
            reference = chunk_row(connection, task["reference_chunk_id"])
            if reference is None:
                raise SystemExit(
                    f"reference chunk missing from database: {task['reference_chunk_id']}"
                )
            new_chunk_id = match_new_chunk(
                connection, source_id, sources[source_id]["content_sha256"], reference
            )
            if new_chunk_id is None:
                unmapped.append(task["task_id"])
                new_chunk_id = task["reference_chunk_id"]
            elif new_chunk_id != task["reference_chunk_id"]:
                pass
            remapped.append(
                {
                    **task,
                    "reference_chunk_id": new_chunk_id,
                    "reference_page": reference[0],
                    "reference_element_type": reference[1],
                }
            )
    finally:
        connection.close()

    version_label = args.parser_version.rsplit("-", 1)[-1]
    output = {
        **dataset,
        "dataset_id": f"arxiv-r01-r03-current-{version_label}-v1",
        "versioned_from_dataset": dataset["dataset_id"],
        "sources": {
            source_id: {
                "content_sha256": value["content_sha256"],
                "license_id": value["license_id"],
                "license_url": value["license_url"],
                "parser_version": value["parser_version"],
                "source_document_sha256": value["source_document_sha256"],
            }
            for source_id, value in sorted(sources.items())
        },
        "tasks": remapped,
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    print(f"remapped {len(remapped) - len(unmapped)}/{len(remapped)} references")
    if unmapped:
        print(f"unmapped (scored as miss): {', '.join(unmapped)}")


if __name__ == "__main__":
    main()
