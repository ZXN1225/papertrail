"""Export evenly spaced full-text chunks as candidate evidence for AI labeling.

The chunks handed to a labeling agent must be the *indexed* chunks, because an
evaluation task has to reference a real ``chunk_id`` and quote text that exists
verbatim inside it. Draft element text is not interchangeable: the chunker may split
an element, so a quote could straddle two chunks.

Read-only: the SQLite file is opened with ``mode=ro`` and nothing is written outside
``--output-dir`` (default ``data/storage/labeling``, which is git-ignored because the
export contains paper text).

Usage (from ``backend/``)::

    uv run --locked python -m tools.export_labeling_candidates --per-source 12
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from app.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "storage" / "labeling"
PREFERRED_TYPES = ("paragraph", "table", "figure_caption")
MIN_TEXT_CHARS = 240


def active_content_hashes(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        str(source_id): str(content_sha256)
        for source_id, content_sha256 in connection.execute(
            """
            SELECT d.source_id, d.current_sha256
            FROM fulltext_documents AS d
            WHERE d.source_type = 'arxiv' AND d.status = 'approved'
            ORDER BY d.source_id
            """
        )
    }


def candidate_chunks(
    connection: sqlite3.Connection, source_id: str, content_sha256: str, limit: int
) -> list[dict[str, object]]:
    rows = list(
        connection.execute(
            """
            SELECT chunk_id, page_number, element_type, locator, section_path, text
            FROM fulltext_chunks
            WHERE source_type = 'arxiv' AND source_id = ? AND content_sha256 = ?
              AND element_type IN ('paragraph', 'table', 'figure_caption')
              AND LENGTH(text) >= ?
            ORDER BY ordinal
            """,
            (source_id, content_sha256, MIN_TEXT_CHARS),
        )
    )
    if not rows:
        return []
    # Spread the picks across the document instead of taking one contiguous block.
    step = max(1, len(rows) // limit)
    selected = rows[::step][:limit]
    return [
        {
            "candidate_id": f"{source_id}#{chunk_id}",
            "source_id": source_id,
            "chunk_id": chunk_id,
            "page_number": page_number,
            "element_type": element_type,
            "locator": locator,
            "section_path": json.loads(section_path) if section_path else [],
            "text": text,
        }
        for chunk_id, page_number, element_type, locator, section_path, text in selected
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-source", type=int, default=12)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--database", type=Path, default=None)
    args = parser.parse_args()

    database = args.database or get_settings().resolved_data_storage_path
    if not database.exists():
        raise SystemExit(f"database not found: {database}")
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        hashes = active_content_hashes(connection)
        if not hashes:
            raise SystemExit("no approved full-text sources in this database")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        index: dict[str, dict[str, object]] = {"sources": {}, "candidates": []}
        for source_id, content_sha256 in hashes.items():
            chunks = candidate_chunks(connection, source_id, content_sha256, args.per_source)
            per_source = args.output_dir / f"candidates-{source_id}.json"
            per_source.write_text(
                json.dumps(
                    {"source_id": source_id, "candidates": chunks}, ensure_ascii=False, indent=2
                )
                + "\n",
                encoding="utf-8",
            )
            index["sources"][source_id] = {
                "content_sha256": content_sha256,
                "candidate_count": len(chunks),
                "file": per_source.name,
            }
            index["candidates"].extend(chunks)
            print(f"{source_id}: {len(chunks)} candidates -> {per_source.name}")
        (args.output_dir / "candidates-index.json").write_text(
            json.dumps(
                {
                    "database": str(database),
                    "sources": index["sources"],
                    "candidate_count": len(index["candidates"]),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"total candidates: {len(index['candidates'])}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
