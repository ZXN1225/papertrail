"""SQLite repository for immutable source snapshots and a current paper catalog."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.retrieval.bm25 import BM25Index
from app.retrieval.fulltext import (
    CHUNKER_VERSION,
    PDF_CHUNKER_VERSION,
    chunk_pdf_elements,
    chunk_plain_text,
)
from app.retrieval.vectors import dense_rank, reciprocal_rank_fusion
from app.sources.arxiv import ArxivPage, ArxivWork
from app.sources.openalex import OpenAlexPage, OpenAlexWork

PARSER_VERSION = "openalex-work-v1"
SOURCE_LICENSE = "CC0-1.0"
SOURCE_LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
SOURCE_ENDPOINT = "https://api.openalex.org/works"
ARXIV_SOURCE_ENDPOINT = "https://export.arxiv.org/api/query"
ARXIV_PARSER_VERSION = "arxiv-atom-v1"
ALLOWED_FULLTEXT_LICENSES = {
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
}
MAX_ABSTRACT_POSITIONS = 50_000
MAX_ABSTRACT_CHARS = 250_000
MAX_ACTIVE_FULLTEXT_CHUNKS = 50_000
MAX_CHUNK_ABLATION_SOURCE_BYTES = 25_000_000
RERANK_CANDIDATE_LIMIT = 128


class StoreError(RuntimeError):
    """Safe local storage error."""


class DailyAgentTokenBudgetExceeded(StoreError):
    """The owner's UTC-day token budget cannot reserve another run."""


class UnsupportedSchemaVersion(StoreError):
    pass


@dataclass(frozen=True)
class ImportSummary:
    snapshot_id: str
    total_matching_count: int
    records_received: int
    new_works: int
    new_versions: int
    unchanged_works: int
    content_sha256: str


@dataclass(frozen=True)
class ArxivImportSummary:
    snapshot_id: str
    total_matching_count: int
    records_received: int
    new_works: int
    new_versions: int
    unchanged_works: int
    linked_by_exact_doi: int
    content_sha256: str


class PaperStore:
    def __init__(self, database_path: Path, *, readonly: bool = False) -> None:
        self.database_path = database_path
        self.readonly = readonly

    def _connect(self) -> sqlite3.Connection:
        if self.readonly:
            if not self.database_path.is_file():
                raise StoreError("read-only database does not exist")
            connection = sqlite3.connect(
                f"{self.database_path.resolve().as_uri()}?mode=ro",
                uri=True,
                timeout=10,
            )
        else:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        migration_dir = Path(__file__).parent / "migrations"
        migration_paths = sorted(migration_dir.glob("[0-9][0-9][0-9][0-9]_*.sql"))
        if version > len(migration_paths):
            raise UnsupportedSchemaVersion("database schema is newer than this application")
        if self.readonly and version != len(migration_paths):
            raise UnsupportedSchemaVersion(
                "read-only database schema is not current; migrate it through PaperTrail first"
            )
        for index, migration_path in enumerate(migration_paths, start=1):
            migration_sql = migration_path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(migration_sql.encode("utf-8")).hexdigest()
            row = (
                connection.execute(
                    "SELECT checksum_sha256 FROM schema_migrations WHERE version = ?", (index,)
                ).fetchone()
                if version >= index
                else None
            )
            if version >= index:
                if row is None or row["checksum_sha256"] != checksum:
                    raise UnsupportedSchemaVersion(
                        "database migration checksum does not match code"
                    )
                continue
            rebuild_snapshot_table = migration_path.name in {
                "0005_openalex_page_size.sql",
                "0017_personal_documents.sql",
            }
            try:
                if rebuild_snapshot_table:
                    connection.execute("PRAGMA foreign_keys = OFF")
                connection.executescript("BEGIN IMMEDIATE;\n" + migration_sql)
                connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations "
                    "(version, name, checksum_sha256, applied_at) VALUES (?, ?, ?, ?)",
                    (index, migration_path.stem, checksum, _now()),
                )
                connection.execute(f"PRAGMA user_version = {index}")
                if rebuild_snapshot_table:
                    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
                    if violations:
                        raise StoreError("migration left invalid foreign keys")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                if rebuild_snapshot_table:
                    connection.execute("PRAGMA foreign_keys = ON")

    def migrate(self) -> None:
        if self.readonly:
            raise StoreError("read-only database cannot run migrations")
        with self._connection() as connection:
            self._ensure_schema(connection)

    def create_agent_run(
        self,
        run_id: str,
        question: str,
        prior_turns: Sequence[tuple[str, str]] = (),
        user_id: str | None = None,
        worker_id: str | None = None,
        token_budget: int = 0,
        harness_metadata: dict[str, Any] | None = None,
        daily_token_budget: int = 0,
    ) -> bool:
        """Persist request and history digests only; never store prompt text or answers."""
        if token_budget < 0 or daily_token_budget < 0:
            raise ValueError("token budgets must be nonnegative")
        if daily_token_budget > 0 and token_budget == 0:
            raise ValueError("daily token budgets require a positive run reservation")
        question_sha256 = hashlib.sha256(question.encode("utf-8")).hexdigest()
        history_payload = json.dumps(list(prior_turns), ensure_ascii=False, separators=(",", ":"))
        history_sha256 = hashlib.sha256(history_payload.encode("utf-8")).hexdigest()
        now = _now()
        lease_expires_at = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
        harness_metadata_json = json.dumps(
            harness_metadata or {}, ensure_ascii=False, separators=(",", ":")
        )
        with self._connection() as connection:
            self._ensure_schema(connection)
            if user_id is not None and daily_token_budget > 0:
                connection.execute("BEGIN IMMEDIATE")
                existing_run = connection.execute(
                    "SELECT 1 FROM agent_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if existing_run is not None:
                    return False
                day_start = (
                    datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                )
                row = connection.execute(
                    """SELECT COALESCE(SUM(
                        CASE
                            WHEN status = 'running' AND token_budget > 0 THEN token_budget
                            WHEN status = 'running' THEN token_actual + token_reserved
                            WHEN token_reserved > 0 THEN token_actual + token_reserved
                            ELSE token_actual
                        END
                    ), 0) AS used_tokens FROM agent_runs
                    WHERE user_id = ? AND created_at >= ?""",
                    (user_id, day_start),
                ).fetchone()
                used_tokens = int(row["used_tokens"])
                if used_tokens + token_budget > daily_token_budget:
                    raise DailyAgentTokenBudgetExceeded("daily_agent_token_budget_exceeded")
            try:
                connection.execute(
                    """INSERT INTO agent_runs (
                        run_id, question_sha256, history_sha256, status, created_at,
                        updated_at, user_id, phase, worker_id, lease_expires_at,
                        token_budget, heartbeat_at, harness_metadata_json
                    )
                    VALUES (?, ?, ?, 'running', ?, ?, ?, 'accepted', ?, ?, ?, ?, ?)""",
                    (
                        run_id,
                        question_sha256,
                        history_sha256,
                        now,
                        now,
                        user_id,
                        worker_id,
                        lease_expires_at,
                        token_budget,
                        now,
                        harness_metadata_json,
                    ),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def finish_agent_run(
        self,
        run_id: str,
        response: Any,
        *,
        model_id: str | None = None,
        pdf_parser_adapter: str | None = None,
        pdf_chunker_version: str | None = None,
    ) -> None:
        """Store redacted status/usage/trace metadata, excluding answer and evidence text."""
        failed_statuses = {
            "max_steps_exceeded",
            "tool_budget_exceeded",
            "workflow_incomplete",
            "token_budget_exceeded",
            "context_budget_exceeded",
            "deadline_exceeded",
            "model_disabled",
            "model_unavailable",
            "usage_unavailable",
            "invalid_model_output",
        }
        state = (
            "cancelled"
            if response.status == "cancelled"
            else "failed"
            if response.status in failed_statuses
            else "completed"
        )
        trace_json = json.dumps(
            [event.model_dump(mode="json") for event in response.trace],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        skill = response.skill
        harness_metadata_json = json.dumps(
            {
                "model_id": model_id,
                "runtime_version": response.context_state.get("runtime_version"),
                "semantic_plan": response.context_state.get("plan"),
                "runtime_skill": response.context_state.get("skill"),
                "pdf_parser_adapter": pdf_parser_adapter,
                "pdf_chunker_version": pdf_chunker_version,
                "task_id": skill.task_id if skill else None,
                "task_registry_version": skill.task_registry_version if skill else None,
                "task_registry_sha256": skill.task_registry_sha256 if skill else None,
                "workflow": skill.workflow if skill else None,
                "skill_id": skill.skill_id if skill else None,
                "skill_version": skill.version if skill else None,
                "skill_instructions_sha256": skill.instructions_sha256 if skill else None,
                "skill_registry_version": skill.registry_version if skill else None,
                "skill_registry_sha256": skill.registry_sha256 if skill else None,
                "prompt_sha256": skill.prompt_sha256 if skill else None,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self._connection() as connection:
            self._ensure_schema(connection)
            existing = connection.execute(
                "SELECT harness_metadata_json FROM agent_runs "
                "WHERE run_id = ? AND status = 'running'",
                (run_id,),
            ).fetchone()
            if existing is not None:
                merged_metadata = json.loads(existing["harness_metadata_json"])
                merged_metadata.update(
                    {
                        key: value
                        for key, value in json.loads(harness_metadata_json).items()
                        if value is not None
                    }
                )
                harness_metadata_json = json.dumps(
                    merged_metadata, ensure_ascii=False, separators=(",", ":")
                )
            cursor = connection.execute(
                """UPDATE agent_runs SET status = ?, phase = ?, result_status = ?, updated_at = ?,
                token_reserved = CASE WHEN ? THEN token_reserved ELSE 0 END,
                token_actual = ?, heartbeat_at = ?,
                model_input_tokens = ?, model_output_tokens = ?, total_observed_tokens = ?,
                tool_calls = ?, model_steps = ?, duration_ms = ?, trace_json = ?,
                harness_metadata_json = ?
                WHERE run_id = ? AND status = 'running'""",
                (
                    state,
                    state,
                    response.status,
                    _now(),
                    response.status in {"model_unavailable", "usage_unavailable"},
                    response.total_observed_tokens,
                    _now(),
                    response.model_input_tokens,
                    response.model_output_tokens,
                    response.total_observed_tokens,
                    response.tool_calls,
                    response.model_steps,
                    response.duration_ms,
                    trace_json,
                    harness_metadata_json,
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise StoreError("agent run is missing or no longer active")

    def update_agent_run_progress(
        self,
        run_id: str,
        worker_id: str,
        *,
        token_reserved: int,
        token_actual: int,
        trace: Sequence[Any],
    ) -> bool:
        if token_reserved < 0 or token_actual < 0 or len(trace) > 32:
            raise ValueError("invalid agent run progress")
        trace_json = json.dumps(
            [event.model_dump(mode="json") for event in trace],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        model_input = sum(event.input_tokens for event in trace if event.kind == "model")
        model_output = sum(event.output_tokens for event in trace if event.kind == "model")
        total_actual = sum(event.input_tokens + event.output_tokens for event in trace)
        if token_actual != total_actual:
            raise ValueError("agent run progress usage does not match its trace")
        tool_calls = sum(event.kind == "tool" for event in trace)
        model_steps = sum(event.kind == "model" for event in trace)
        duration_ms = sum(event.duration_ms for event in trace)
        now = _now()
        with self._connection() as connection:
            self._ensure_schema(connection)
            cursor = connection.execute(
                """UPDATE agent_runs SET token_reserved = ?, token_actual = ?,
                heartbeat_at = ?, lease_expires_at = ?, updated_at = ?,
                model_input_tokens = ?, model_output_tokens = ?, total_observed_tokens = ?,
                tool_calls = ?, model_steps = ?, duration_ms = ?, trace_json = ?
                WHERE run_id = ? AND worker_id = ? AND status = 'running'""",
                (
                    token_reserved,
                    token_actual,
                    now,
                    _lease_expiry(),
                    now,
                    model_input,
                    model_output,
                    token_actual,
                    tool_calls,
                    model_steps,
                    duration_ms,
                    trace_json,
                    run_id,
                    worker_id,
                ),
            )
            return cursor.rowcount == 1

    def get_agent_run(self, run_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        with self._connection() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "SELECT * FROM agent_runs WHERE run_id = ? AND (? IS NULL OR user_id = ?)",
                (run_id, user_id, user_id),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result.pop("user_id", None)
        result["trace"] = json.loads(result.pop("trace_json"))
        result["harness_metadata"] = json.loads(result.pop("harness_metadata_json"))
        return result

    def request_agent_run_cancel(self, run_id: str, user_id: str) -> bool:
        """Persist cancellation intent for an owned, active run."""
        with self._connection() as connection:
            self._ensure_schema(connection)
            cursor = connection.execute(
                """UPDATE agent_runs SET cancel_requested_at = COALESCE(cancel_requested_at, ?),
                phase = 'cancel_requested',
                updated_at = ? WHERE run_id = ? AND user_id = ? AND status = 'running'""",
                (_now(), _now(), run_id, user_id),
            )
            return cursor.rowcount == 1

    def set_agent_run_phase(self, run_id: str, phase: str) -> bool:
        if phase not in {"executing"}:
            raise ValueError("unsupported active agent run phase")
        with self._connection() as connection:
            self._ensure_schema(connection)
            cursor = connection.execute(
                """UPDATE agent_runs SET phase = ?, updated_at = ?, lease_expires_at = ?
                WHERE run_id = ? AND status = 'running' AND cancel_requested_at IS NULL""",
                (phase, _now(), _lease_expiry(), run_id),
            )
            return cursor.rowcount == 1

    def renew_agent_run_lease(self, run_id: str, worker_id: str) -> bool:
        with self._connection() as connection:
            self._ensure_schema(connection)
            cursor = connection.execute(
                """UPDATE agent_runs SET lease_expires_at = ?
                WHERE run_id = ? AND worker_id = ? AND status = 'running'""",
                (_lease_expiry(), run_id, worker_id),
            )
            return cursor.rowcount == 1

    def is_agent_run_lease_expired(self, run_id: str) -> bool:
        with self._connection() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "SELECT lease_expires_at FROM agent_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return bool(row and (row["lease_expires_at"] is None or row["lease_expires_at"] <= _now()))

    def is_agent_run_cancel_requested(self, run_id: str) -> bool:
        with self._connection() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "SELECT cancel_requested_at FROM agent_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return bool(row and row["cancel_requested_at"])

    def resolve_agent_run_stop(self, run_id: str, *, expired_only: bool = False) -> bool:
        """Atomically resolve an active run to cancelled or interrupted."""
        now = _now()
        with self._connection() as connection:
            self._ensure_schema(connection)
            cursor = connection.execute(
                """UPDATE agent_runs SET
                status = CASE WHEN cancel_requested_at IS NULL
                    THEN 'interrupted' ELSE 'cancelled' END,
                phase = CASE WHEN cancel_requested_at IS NULL
                    THEN 'interrupted' ELSE 'cancelled' END,
                result_status = CASE WHEN cancel_requested_at IS NULL
                    THEN 'interrupted' ELSE 'cancelled' END,
                updated_at = ?
                WHERE run_id = ? AND status = 'running'
                AND (? = 0 OR lease_expires_at IS NULL OR lease_expires_at <= ?)""",
                (now, run_id, expired_only, now),
            )
            return cursor.rowcount == 1

    def import_openalex_page(
        self, page: OpenAlexPage, *, query: str, requested_page: int, per_page: int
    ) -> ImportSummary:
        normalized_query = " ".join(query.split())
        if not normalized_query or len(normalized_query) > 256:
            raise ValueError("query must contain 1 to 256 non-whitespace characters")
        if not 1 <= per_page <= 100 or requested_page < 1:
            raise ValueError("page size must be 1 to 100 and page must be positive")
        if requested_page * per_page > 10_000:
            raise ValueError("requested page exceeds the 10,000-result paging limit")
        if len(page.results) > per_page:
            raise ValueError("source returned more records than requested")

        prepared = [_prepare_work(work) for work in page.results]
        ids = [entry["openalex_id"] for entry in prepared]
        if len(ids) != len(set(ids)):
            raise ValueError("source page contains duplicate OpenAlex IDs")
        snapshot_id = str(uuid.uuid4())
        hash_input = json.dumps(
            {
                "source": "openalex",
                "query": normalized_query,
                "page": requested_page,
                "per_page": per_page,
                "items": [
                    {"openalex_id": item["openalex_id"], "payload_sha256": item["payload_sha256"]}
                    for item in prepared
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        content_sha256 = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        imported_at = _now()

        with self._connection() as connection:
            self._ensure_schema(connection)
            new_works = new_versions = unchanged_works = 0
            with connection:
                connection.execute(
                    """INSERT INTO import_snapshots (
                        snapshot_id, source, source_endpoint, query, page, per_page,
                        total_matching_count, records_received, source_license,
                        source_license_url, fetched_at, imported_at, content_sha256
                    ) VALUES (?, 'openalex', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        snapshot_id,
                        SOURCE_ENDPOINT,
                        normalized_query,
                        requested_page,
                        per_page,
                        page.meta.count,
                        len(prepared),
                        SOURCE_LICENSE,
                        SOURCE_LICENSE_URL,
                        page.fetched_at.astimezone(UTC).isoformat(),
                        imported_at,
                        content_sha256,
                    ),
                )
                for position, item in enumerate(prepared):
                    current = connection.execute(
                        "SELECT current_version_sha256, first_seen_at "
                        "FROM works WHERE openalex_id = ?",
                        (item["openalex_id"],),
                    ).fetchone()
                    if current is None:
                        new_works += 1
                        first_seen = imported_at
                    else:
                        first_seen = current["first_seen_at"]
                        if current["current_version_sha256"] == item["payload_sha256"]:
                            unchanged_works += 1

                    connection.execute(
                        """INSERT INTO works (
                            openalex_id, source_url, title, doi, publication_year,
                            publication_date, work_type, cited_by_count, abstract,
                            abstract_status, authors_json, venue_name, open_access_json,
                            current_version_sha256, first_seen_at, last_seen_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(openalex_id) DO UPDATE SET
                            source_url=excluded.source_url, title=excluded.title, doi=excluded.doi,
                            publication_year=excluded.publication_year,
                            publication_date=excluded.publication_date,
                            work_type=excluded.work_type,
                            cited_by_count=excluded.cited_by_count, abstract=excluded.abstract,
                            abstract_status=excluded.abstract_status,
                            authors_json=excluded.authors_json,
                            venue_name=excluded.venue_name,
                            open_access_json=excluded.open_access_json,
                            current_version_sha256=excluded.current_version_sha256,
                            last_seen_at=excluded.last_seen_at""",
                        (
                            item["openalex_id"],
                            item["source_url"],
                            item["title"],
                            item["doi"],
                            item["publication_year"],
                            item["publication_date"],
                            item["work_type"],
                            item["cited_by_count"],
                            item["abstract"],
                            item["abstract_status"],
                            item["authors_json"],
                            item["venue_name"],
                            item["open_access_json"],
                            item["payload_sha256"],
                            first_seen,
                            imported_at,
                        ),
                    )
                    cursor = connection.execute(
                        """INSERT OR IGNORE INTO work_versions (
                            openalex_id, payload_sha256, source_snapshot_id, source_url,
                            fetched_at, parser_version, record_json, abstract, abstract_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            item["openalex_id"],
                            item["payload_sha256"],
                            snapshot_id,
                            item["source_url"],
                            page.fetched_at.astimezone(UTC).isoformat(),
                            PARSER_VERSION,
                            item["record_json"],
                            item["abstract"],
                            item["abstract_status"],
                        ),
                    )
                    new_versions += cursor.rowcount
                    connection.execute(
                        """INSERT INTO snapshot_items
                            (snapshot_id, openalex_id, payload_sha256, result_position)
                            VALUES (?, ?, ?, ?)""",
                        (snapshot_id, item["openalex_id"], item["payload_sha256"], position),
                    )

        return ImportSummary(
            snapshot_id=snapshot_id,
            total_matching_count=page.meta.count,
            records_received=len(prepared),
            new_works=new_works,
            new_versions=new_versions,
            unchanged_works=unchanged_works,
            content_sha256=content_sha256,
        )

    def import_arxiv_page(self, page: ArxivPage, *, query: str, start: int) -> ArxivImportSummary:
        normalized_query = " ".join(query.split())
        if not normalized_query or len(normalized_query) > 256:
            raise ValueError("query must contain 1 to 256 non-whitespace characters")
        if start < 0 or start > 9_975 or len(page.works) > 25 or page.start != start:
            raise ValueError("arXiv page is outside the bounded import contract")
        prepared = [_prepare_arxiv_work(work) for work in page.works]
        ids = [item["arxiv_id"] for item in prepared]
        if len(ids) != len(set(ids)):
            raise ValueError("arXiv source page contains duplicate IDs")
        snapshot_id = str(uuid.uuid4())
        content_sha256 = hashlib.sha256(
            _canonical_json(
                {
                    "source": "arxiv",
                    "query": normalized_query,
                    "start": start,
                    "items": [
                        {"arxiv_id": row["arxiv_id"], "payload_sha256": row["payload_sha256"]}
                        for row in prepared
                    ],
                }
            ).encode("utf-8")
        ).hexdigest()
        imported_at = _now()
        with self._connection() as connection:
            self._ensure_schema(connection)
            new_works = new_versions = unchanged = links = 0
            with connection:
                connection.execute(
                    """INSERT INTO arxiv_import_snapshots (
                        snapshot_id, source_endpoint, query, start_index, per_page,
                        total_matching_count, records_received, source_license,
                        fetched_at, imported_at, content_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'CC0-1.0', ?, ?, ?)""",
                    (
                        snapshot_id,
                        ARXIV_SOURCE_ENDPOINT,
                        normalized_query,
                        start,
                        max(1, page.items_per_page),
                        page.total_results,
                        len(prepared),
                        page.fetched_at.astimezone(UTC).isoformat(),
                        imported_at,
                        content_sha256,
                    ),
                )
                for position, row in enumerate(prepared):
                    current = connection.execute(
                        """SELECT current_version_sha256, first_seen_at
                        FROM arxiv_works WHERE arxiv_id = ?""",
                        (row["arxiv_id"],),
                    ).fetchone()
                    if current is None:
                        new_works += 1
                        first_seen = imported_at
                    else:
                        first_seen = current["first_seen_at"]
                        unchanged += current["current_version_sha256"] == row["payload_sha256"]
                    connection.execute(
                        """INSERT INTO arxiv_works (
                            arxiv_id, source_url, title, abstract, authors_json, categories_json,
                            primary_category, published_at, updated_at, doi, journal_ref,
                            current_version_sha256, first_seen_at, last_seen_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(arxiv_id) DO UPDATE SET
                            source_url=excluded.source_url, title=excluded.title,
                            abstract=excluded.abstract, authors_json=excluded.authors_json,
                            categories_json=excluded.categories_json,
                            primary_category=excluded.primary_category,
                            published_at=excluded.published_at, updated_at=excluded.updated_at,
                            doi=excluded.doi, journal_ref=excluded.journal_ref,
                            current_version_sha256=excluded.current_version_sha256,
                            last_seen_at=excluded.last_seen_at""",
                        (
                            row["arxiv_id"],
                            row["source_url"],
                            row["title"],
                            row["abstract"],
                            row["authors_json"],
                            row["categories_json"],
                            row["primary_category"],
                            row["published_at"],
                            row["updated_at"],
                            row["doi"],
                            row["journal_ref"],
                            row["payload_sha256"],
                            first_seen,
                            imported_at,
                        ),
                    )
                    cursor = connection.execute(
                        """INSERT OR IGNORE INTO arxiv_work_versions
                            (arxiv_id, payload_sha256, snapshot_id, parser_version,
                             record_json, fetched_at)
                            VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            row["arxiv_id"],
                            row["payload_sha256"],
                            snapshot_id,
                            ARXIV_PARSER_VERSION,
                            row["record_json"],
                            page.fetched_at.astimezone(UTC).isoformat(),
                        ),
                    )
                    new_versions += cursor.rowcount
                    connection.execute(
                        "INSERT INTO arxiv_snapshot_items VALUES (?, ?, ?, ?)",
                        (snapshot_id, row["arxiv_id"], row["payload_sha256"], position),
                    )
                    links += self._link_exact_doi(connection, row["arxiv_id"], row["doi"])
        return ArxivImportSummary(
            snapshot_id,
            page.total_results,
            len(prepared),
            new_works,
            new_versions,
            unchanged,
            links,
            content_sha256,
        )

    @staticmethod
    def _link_exact_doi(connection: sqlite3.Connection, arxiv_id: str, doi: str | None) -> int:
        normalized = _normalize_doi(doi)
        if normalized is None:
            return 0
        candidates = [
            row["openalex_id"]
            for row in connection.execute(
                "SELECT openalex_id, doi FROM works WHERE doi IS NOT NULL"
            )
            if _normalize_doi(row["doi"]) == normalized
        ]
        if len(candidates) != 1:
            return 0
        openalex_id = candidates[0]
        conflict = connection.execute(
            "SELECT openalex_id, arxiv_id FROM work_identifier_crosswalk "
            "WHERE openalex_id = ? OR arxiv_id = ?",
            (openalex_id, arxiv_id),
        ).fetchone()
        if conflict:
            return int(conflict["openalex_id"] == openalex_id and conflict["arxiv_id"] == arxiv_id)
        evidence = _canonical_json({"doi": normalized, "match_method": "exact_doi"})
        connection.execute(
            """INSERT INTO work_identifier_crosswalk
                (openalex_id, arxiv_id, match_method, normalized_doi, evidence_json, verified_at)
                VALUES (?, ?, 'exact_doi', ?, ?, ?)""",
            (openalex_id, arxiv_id, normalized, evidence, _now()),
        )
        return 1

    def list_arxiv_papers(self, *, query: str | None, limit: int, offset: int) -> dict[str, Any]:
        if not 1 <= limit <= 50 or not 0 <= offset <= 10_000:
            raise ValueError("limit must be 1-50 and offset must be 0-10000")
        normalized = " ".join(query.split()) if query and query.strip() else None
        if normalized and len(normalized) > 128:
            raise ValueError("query must be at most 128 characters")
        where = (
            "WHERE instr(lower(title), lower(?)) > 0 OR instr(lower(abstract), lower(?)) > 0"
            if normalized
            else ""
        )
        args: tuple[Any, ...] = (normalized, normalized) if normalized else ()
        with self._connection() as connection:
            self._ensure_schema(connection)
            total = connection.execute(
                f"SELECT COUNT(*) FROM arxiv_works {where}", args
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT * FROM arxiv_works {where}
                ORDER BY published_at DESC, arxiv_id LIMIT ? OFFSET ?""",
                (*args, limit, offset),
            ).fetchall()
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": [_arxiv_paper_view(row) for row in rows],
            }

    def get_arxiv_paper(self, arxiv_id: str) -> dict[str, Any] | None:
        from app.sources.arxiv import normalize_arxiv_id

        try:
            normalized = normalize_arxiv_id(arxiv_id)
        except ValueError:
            return None
        with self._connection() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "SELECT * FROM arxiv_works WHERE arxiv_id = ?", (normalized,)
            ).fetchone()
            if row is None:
                return None
            crosswalk = connection.execute(
                "SELECT openalex_id, match_method, normalized_doi, evidence_json, verified_at "
                "FROM work_identifier_crosswalk WHERE arxiv_id = ?",
                (normalized,),
            ).fetchone()
            result = _arxiv_paper_view(row)
            result["crosswalk"] = dict(crosswalk) if crosswalk else None
            return result

    def ingest_licensed_fulltext(
        self,
        *,
        source_type: str,
        source_id: str,
        text: str,
        text_source_url: str,
        license_id: str,
        license_url: str,
        license_evidence_url: str,
        reviewer: str,
        attribution: str,
        confirm_license_reviewed: bool,
        parsed_elements: list[dict[str, Any]] | None = None,
        parser_warnings: list[dict[str, Any]] | None = None,
        parser_version: str = "plain-text-v1",
        source_document_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Ingest locally supplied text only after an explicit human license review."""
        import hashlib
        from urllib.parse import urlparse

        if not confirm_license_reviewed:
            raise ValueError("explicit human license review confirmation is required")
        if source_type not in {"openalex", "arxiv"}:
            raise ValueError("source_type must be openalex or arxiv")
        if source_type == "openalex" and not re.fullmatch(r"W\d+", source_id):
            raise ValueError("invalid OpenAlex work ID")
        if source_type == "arxiv":
            from app.sources.arxiv import normalize_arxiv_id

            source_id = normalize_arxiv_id(source_id)
        if license_id not in ALLOWED_FULLTEXT_LICENSES:
            raise ValueError("license is not on the full-text processing allowlist")
        if license_url.rstrip("/") != ALLOWED_FULLTEXT_LICENSES[license_id].rstrip("/"):
            raise ValueError("license URL does not match the canonical license identifier")
        if not reviewer.strip() or len(reviewer.strip()) > 128:
            raise ValueError("reviewer must contain 1 to 128 characters")
        if not attribution.strip() or len(attribution.strip()) > 500:
            raise ValueError("attribution must contain 1 to 500 characters")
        for label, value in (
            ("text_source_url", text_source_url),
            ("license_evidence_url", license_evidence_url),
        ):
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.hostname or len(value) > 2_048:
                raise ValueError(f"{label} must be a bounded HTTPS URL")

        normalized_text = text.strip()
        chunker_version = PDF_CHUNKER_VERSION if parsed_elements is not None else CHUNKER_VERSION
        chunks = (
            chunk_pdf_elements(parsed_elements)
            if parsed_elements is not None
            else chunk_plain_text(normalized_text)
        )
        source_text_sha256 = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        parser_structure_sha256 = (
            hashlib.sha256(_canonical_json(parsed_elements).encode("utf-8")).hexdigest()
            if parsed_elements is not None
            else None
        )
        content_sha256 = hashlib.sha256(
            _canonical_json(
                {
                    "text_sha256": source_text_sha256,
                    "source_type": source_type,
                    "source_id": source_id,
                    "text_source_url": text_source_url,
                    "license_id": license_id,
                    "license_url": license_url,
                    "license_evidence_url": license_evidence_url,
                    "attribution": attribution.strip(),
                    "chunker_version": chunker_version,
                    "parser_version": parser_version,
                    "source_document_sha256": source_document_sha256,
                    "parser_structure_sha256": parser_structure_sha256,
                }
            ).encode("utf-8")
        ).hexdigest()
        imported_at = _now()
        with self._connection() as connection:
            self._ensure_schema(connection)
            if source_type == "openalex":
                paper = connection.execute(
                    "SELECT title, source_url FROM works WHERE openalex_id = ?", (source_id,)
                ).fetchone()
            else:
                paper = connection.execute(
                    "SELECT title, source_url FROM arxiv_works WHERE arxiv_id = ?", (source_id,)
                ).fetchone()
            if paper is None:
                raise ValueError("source paper must already exist in the metadata catalog")
            with connection:
                existing = connection.execute(
                    """SELECT d.current_sha256, v.license_id, v.license_url,
                    v.license_evidence_url, v.text_source_url, v.reviewer, v.attribution,
                    v.license_reviewed_at
                    FROM fulltext_documents d LEFT JOIN fulltext_versions v
                    ON v.source_type=d.source_type AND v.source_id=d.source_id
                    AND v.content_sha256=d.current_sha256
                    WHERE d.source_type = ? AND d.source_id = ?""",
                    (source_type, source_id),
                ).fetchone()
                unchanged = bool(existing and existing["current_sha256"] == content_sha256)
                license_review_unchanged = bool(
                    existing
                    and existing["license_reviewed_at"]
                    and existing["license_id"] == license_id
                    and existing["license_url"] == license_url
                    and existing["license_evidence_url"] == license_evidence_url
                    and existing["text_source_url"] == text_source_url
                    and existing["reviewer"] == reviewer.strip()
                    and existing["attribution"] == attribution.strip()
                )
                license_reviewed_at = (
                    existing["license_reviewed_at"] if license_review_unchanged else imported_at
                )
                connection.execute(
                    """INSERT INTO fulltext_documents
                    (source_type, source_id, title, source_url, current_sha256, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'approved', ?)
                    ON CONFLICT(source_type, source_id) DO UPDATE SET
                    title=excluded.title, source_url=excluded.source_url,
                    current_sha256=excluded.current_sha256, status='approved',
                    updated_at=excluded.updated_at""",
                    (
                        source_type,
                        source_id,
                        paper["title"],
                        paper["source_url"],
                        content_sha256,
                        imported_at,
                    ),
                )
                connection.execute(
                    """INSERT OR IGNORE INTO fulltext_versions (
                    source_type, source_id, content_sha256, source_text_sha256, text_content,
                    license_id, license_url, license_evidence_url, text_source_url,
                    license_reviewed_at, reviewer, attribution, chunker_version, imported_at,
                    parser_version, source_document_sha256, parser_warnings_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        source_type,
                        source_id,
                        content_sha256,
                        source_text_sha256,
                        normalized_text,
                        license_id,
                        license_url,
                        license_evidence_url,
                        text_source_url,
                        license_reviewed_at,
                        reviewer.strip(),
                        attribution.strip(),
                        chunker_version,
                        imported_at,
                        parser_version,
                        source_document_sha256,
                        _canonical_json(parser_warnings or []),
                    ),
                )
                if not unchanged and parsed_elements is not None:
                    for element in parsed_elements:
                        element_id = element.get("element_id")
                        order_index = element.get("order_index")
                        page_number = element.get("page_number")
                        element_type = element.get("element_type")
                        if (
                            not isinstance(element_id, str)
                            or not element_id
                            or not isinstance(order_index, int)
                            or isinstance(order_index, bool)
                            or order_index < 0
                            or not isinstance(page_number, int)
                            or isinstance(page_number, bool)
                            or page_number < 1
                            or not isinstance(element_type, str)
                        ):
                            raise ValueError("parsed PDF element is missing valid identity fields")
                        connection.execute(
                            """INSERT INTO fulltext_elements (
                            source_type, source_id, content_sha256, element_id, order_index,
                            page_number, element_type, element_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                source_type,
                                source_id,
                                content_sha256,
                                element_id,
                                order_index,
                                page_number,
                                element_type,
                                _canonical_json(element),
                            ),
                        )
                if not unchanged:
                    for chunk in chunks:
                        chunk_id = (
                            f"{source_type}:{source_id}:{content_sha256[:16]}:{chunk.ordinal}"
                        )
                        connection.execute(
                            """INSERT OR IGNORE INTO fulltext_chunks (
                            chunk_id, source_type, source_id, content_sha256, ordinal, title,
                            locator, char_start, char_end, text, page_number, element_type,
                            section_path, bbox_json, element_id, char_offset_scope,
                            retrieval_text, evidence_text, parent_element_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                chunk_id,
                                source_type,
                                source_id,
                                content_sha256,
                                chunk.ordinal,
                                paper["title"],
                                chunk.locator,
                                chunk.char_start,
                                chunk.char_end,
                                chunk.text,
                                chunk.page_number,
                                chunk.element_type,
                                chunk.section_path,
                                chunk.bbox,
                                chunk.element_id,
                                "element_text" if parsed_elements is not None else "version_text",
                                _retrieval_text(chunk.text, chunk.section_path),
                                chunk.evidence_text or chunk.text,
                                chunk.element_id,
                            ),
                        )
                count = connection.execute(
                    "SELECT COUNT(*) FROM fulltext_chunks WHERE source_type=? AND source_id=? "
                    "AND content_sha256=?",
                    (source_type, source_id, content_sha256),
                ).fetchone()[0]
        return {
            "status": "unchanged" if unchanged else "approved",
            "source_type": source_type,
            "source_id": source_id,
            "content_sha256": content_sha256,
            "parser_version": parser_version,
            "source_document_sha256": source_document_sha256,
            "source_text_sha256": source_text_sha256,
            "chunk_count": count,
            "license_id": license_id,
            "reviewer": reviewer.strip(),
            "license_reviewed_at": license_reviewed_at,
        }

    def search_fulltext_evidence(
        self,
        query: str,
        *,
        limit: int = 5,
        source_type: str | None = None,
        source_id: str | None = None,
        retrieval_method: str = "bm25",
        query_embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> dict[str, Any]:
        normalized_query = " ".join(query.split())
        if not normalized_query or len(normalized_query) > 256:
            raise ValueError("query must contain 1 to 256 non-whitespace characters")
        if not 1 <= limit <= 8:
            raise ValueError("limit must be 1-8")
        if retrieval_method not in {"bm25", "dense", "hybrid", "bm25_dense_rerank"}:
            raise ValueError("unsupported retrieval method")
        if retrieval_method != "bm25" and (query_embedding is None or not embedding_model):
            raise ValueError("dense and hybrid retrieval require an embedding and model")
        if source_type is None and source_id is not None:
            raise ValueError("source_id requires a source_type")
        if source_type is not None and source_type not in {"openalex", "arxiv"}:
            raise ValueError("source_type must be openalex or arxiv")
        if (
            source_id is not None
            and source_type == "openalex"
            and not re.fullmatch(r"W\d+", source_id)
        ):
            raise ValueError("invalid OpenAlex work ID")
        if source_type == "arxiv" and source_id is not None:
            from app.sources.arxiv import normalize_arxiv_id

            source_id = normalize_arxiv_id(source_id or "")

        clauses = ["d.status = 'approved'", "d.current_sha256 = v.content_sha256"]
        params: list[Any] = []
        if source_type is not None:
            clauses.append("d.source_type = ?")
            params.append(source_type)
        if source_id is not None:
            clauses.append("d.source_id = ?")
            params.append(source_id)
        with self._connection() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                f"""SELECT c.*, d.source_url, v.license_id, v.license_url,
                v.attribution, v.license_evidence_url, v.text_source_url,
                v.parser_warnings_json, e.vector_json, pe.element_json
                FROM fulltext_documents d JOIN fulltext_versions v
                ON v.source_type=d.source_type AND v.source_id=d.source_id
                AND v.content_sha256=d.current_sha256
                JOIN fulltext_chunks c ON c.source_type=v.source_type
                AND c.source_id=v.source_id AND c.content_sha256=v.content_sha256
                LEFT JOIN fulltext_embeddings e ON e.chunk_id=c.chunk_id
                AND e.model=? AND e.dimensions=? AND e.normalization='none'
                LEFT JOIN fulltext_elements pe ON pe.source_type=c.source_type
                AND pe.source_id=c.source_id AND pe.content_sha256=c.content_sha256
                AND pe.element_id=c.element_id
                WHERE {" AND ".join(clauses)} ORDER BY c.source_type, c.source_id,
                c.ordinal LIMIT ?""",
                [
                    embedding_model or "",
                    len(query_embedding or []),
                    *params,
                    MAX_ACTIVE_FULLTEXT_CHUNKS + 1,
                ],
            ).fetchall()
        if len(rows) > MAX_ACTIVE_FULLTEXT_CHUNKS:
            return {
                "status": "corpus_limit_exceeded",
                "items": [],
                "scanned_chunks": len(rows),
                "max_chunks": MAX_ACTIVE_FULLTEXT_CHUNKS,
                "truncated": True,
                "retrieval_method": {
                    "bm25": "bm25_fulltext_v3",
                    "dense": "dense_cosine_v1",
                    "hybrid": "hybrid_rrf_v3",
                    "bm25_dense_rerank": "bm25_dense_rerank_v1",
                }[retrieval_method],
            }
        if not rows:
            return {
                "status": "no_results",
                "items": [],
                "scanned_chunks": 0,
                "truncated": False,
                "retrieval_method": {
                    "bm25": "bm25_fulltext_v3",
                    "dense": "dense_cosine_v1",
                    "hybrid": "hybrid_rrf_v3",
                    "bm25_dense_rerank": "bm25_dense_rerank_v1",
                }[retrieval_method],
            }
        docs = [
            {
                "openalex_id": row["chunk_id"],
                "title": row["title"],
                "abstract": row["retrieval_text"] or row["text"],
            }
            for row in rows
        ]
        index = BM25Index(docs)
        by_chunk = {row["chunk_id"]: row for row in rows}
        parent_groups: dict[tuple[str, str, str, str], list[sqlite3.Row]] = {}
        section_groups: dict[tuple[str, str, str, str], list[sqlite3.Row]] = {}
        for row in rows:
            parent_id = row["parent_element_id"]
            if parent_id:
                group_key = (
                    row["source_type"],
                    row["source_id"],
                    row["content_sha256"],
                    parent_id,
                )
                parent_groups.setdefault(group_key, []).append(row)
                if row["section_path"] != "[]":
                    section_key = (
                        row["source_type"],
                        row["source_id"],
                        row["content_sha256"],
                        row["section_path"],
                    )
                    section_groups.setdefault(section_key, []).append(row)
        for group in parent_groups.values():
            group.sort(key=lambda row: row["ordinal"])
        for group in section_groups.values():
            group.sort(key=lambda row: row["ordinal"])
        lexical_hits = index.search(normalized_query, limit=min(len(rows), 2_000))
        if retrieval_method == "bm25":
            ranked_ids = [(hit.openalex_id, hit.score) for hit in lexical_hits[:limit]]
            method_name = "bm25_fulltext_v3"
        else:
            method_name = {
                "dense": "dense_cosine_v1",
                "hybrid": "hybrid_rrf_v3",
                "bm25_dense_rerank": "bm25_dense_rerank_v1",
            }[retrieval_method]
            missing_embeddings = sum(row["vector_json"] is None for row in rows)
            if not rows:
                ranked_ids = []
            elif missing_embeddings:
                return {
                    "status": "embeddings_missing",
                    "items": [],
                    "scanned_chunks": len(rows),
                    "missing_embeddings": missing_embeddings,
                    "truncated": False,
                    "retrieval_method": method_name,
                }
            else:
                vectors = {row["chunk_id"]: json.loads(row["vector_json"]) for row in rows}
                dense_hits = dense_rank(query_embedding or [], vectors)
                if retrieval_method == "dense":
                    ranked_ids = dense_hits[:limit]
                    method_name = "dense_cosine_v1"
                elif retrieval_method == "bm25_dense_rerank":
                    candidate_ids = {
                        hit.openalex_id for hit in lexical_hits[:RERANK_CANDIDATE_LIMIT]
                    }
                    candidate_vectors = {
                        chunk_id: vectors[chunk_id]
                        for chunk_id in candidate_ids
                        if chunk_id in vectors
                    }
                    ranked_ids = dense_rank(query_embedding or [], candidate_vectors)[:limit]
                else:
                    ranked_ids = reciprocal_rank_fusion(
                        [
                            [(hit.openalex_id, hit.score) for hit in lexical_hits],
                            dense_hits,
                        ],
                        k=60,
                    )[:limit]
                    method_name = "hybrid_rrf_v3"
        items: list[dict[str, Any]] = []
        remaining_expanded_children = 2
        expanded_child_ids: set[str] = set()
        for chunk_id, score in ranked_ids:
            row = by_chunk[chunk_id]
            parent_key = (
                row["source_type"],
                row["source_id"],
                row["content_sha256"],
                row["parent_element_id"],
            )
            siblings = parent_groups.get(parent_key, []) if row["parent_element_id"] else []
            sibling_index = next(
                (
                    index
                    for index, sibling in enumerate(siblings)
                    if sibling["chunk_id"] == chunk_id
                ),
                -1,
            )
            neighbor_rows = (
                siblings[max(0, sibling_index - 1) : sibling_index]
                + siblings[sibling_index + 1 : sibling_index + 2]
                if sibling_index >= 0
                else []
            )
            section_key = (
                row["source_type"],
                row["source_id"],
                row["content_sha256"],
                row["section_path"],
            )
            section_chunks = section_groups.get(section_key, [])
            section_index = next(
                (
                    index
                    for index, candidate in enumerate(section_chunks)
                    if candidate["chunk_id"] == chunk_id
                ),
                -1,
            )
            if section_index >= 0:
                neighbor_rows.extend(
                    section_chunks[max(0, section_index - 1) : section_index]
                    + section_chunks[section_index + 1 : section_index + 2]
                )
            neighbor_rows = list(
                {candidate["chunk_id"]: candidate for candidate in neighbor_rows}.values()
            )
            expanded_rows = [
                sibling
                for sibling in neighbor_rows
                if sibling["chunk_id"] not in expanded_child_ids
            ][:remaining_expanded_children]
            expanded_child_ids.update(sibling["chunk_id"] for sibling in expanded_rows)
            remaining_expanded_children -= len(expanded_rows)
            context_rows = sorted([row, *expanded_rows], key=lambda item: item["ordinal"])
            context_parts = [
                (context_row["retrieval_text"] or context_row["text"])
                for context_row in context_rows
            ]
            expanded_context = _bounded_join(context_parts, limit_bytes=5_600)
            expanded_evidence = [
                {
                    "chunk_id": sibling["chunk_id"],
                    "locator": sibling["locator"],
                    "char_start": sibling["char_start"],
                    "char_end": sibling["char_end"],
                    "element_id": sibling["element_id"],
                    "parent_element_id": sibling["parent_element_id"],
                    "page_number": sibling["page_number"],
                    "excerpt": sibling["evidence_text"] or sibling["text"],
                }
                for sibling in expanded_rows
            ]
            item: dict[str, Any] = {
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "title": row["title"],
                "source_url": row["source_url"],
                "chunk_id": row["chunk_id"],
                "locator": row["locator"],
                "char_start": row["char_start"],
                "char_end": row["char_end"],
                "char_offset_scope": row["char_offset_scope"],
                "element_id": row["element_id"],
                "parent_element_id": row["parent_element_id"],
                "page_number": row["page_number"],
                "element_type": row["element_type"],
                "section_path": json.loads(row["section_path"]),
                "bbox": json.loads(row["bbox_json"]) if row["bbox_json"] else None,
                "retrieval_context": expanded_context,
                "excerpt": row["evidence_text"] or row["text"],
                "expanded_evidence": expanded_evidence,
                "score": round(score, 6),
                "license_id": row["license_id"],
                "license_url": row["license_url"],
                "license_evidence_url": row["license_evidence_url"],
                "text_source_url": row["text_source_url"],
                "attribution": row["attribution"],
                "content_sha256": row["content_sha256"],
                "parser_warnings": json.loads(row["parser_warnings_json"]),
            }
            if row["element_json"]:
                item["element"] = _element_evidence_view(json.loads(row["element_json"]))
            if row["source_type"] == "openalex":
                item["openalex_id"] = row["source_id"]
            else:
                item["arxiv_id"] = row["source_id"]
            items.append(item)
        return {
            "status": "ok" if items else "no_results",
            "items": items,
            "scanned_chunks": len(rows),
            "truncated": False,
            "retrieval_method": method_name if retrieval_method != "bm25" else "bm25_fulltext_v3",
        }

    def list_current_fulltext_chunks(
        self, *, source_type: str | None = None, source_id: str | None = None
    ) -> list[dict[str, Any]]:
        if (source_type is None) != (source_id is None):
            raise ValueError("source_type and source_id must be provided together")
        clauses = ["d.status='approved'", "d.current_sha256=v.content_sha256"]
        params: list[Any] = []
        if source_type is not None:
            clauses.append("d.source_type=? AND d.source_id=?")
            params.extend((source_type, source_id))
        with self._connection() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                f"""SELECT c.chunk_id, c.source_type, c.source_id, c.content_sha256,
                c.ordinal, c.title, c.retrieval_text AS text, c.evidence_text,
                c.parent_element_id, c.char_start, c.char_end, c.page_number, c.element_type,
                c.element_id, c.bbox_json, c.section_path FROM fulltext_documents d
                JOIN fulltext_versions v ON v.source_type=d.source_type
                AND v.source_id=d.source_id AND v.content_sha256=d.current_sha256
                JOIN fulltext_chunks c ON c.source_type=v.source_type
                AND c.source_id=v.source_id AND c.content_sha256=v.content_sha256
                WHERE {" AND ".join(clauses)} ORDER BY c.source_type,c.source_id,c.ordinal
                LIMIT ?""",
                [*params, MAX_ACTIVE_FULLTEXT_CHUNKS + 1],
            ).fetchall()
        if len(rows) > MAX_ACTIVE_FULLTEXT_CHUNKS:
            raise ValueError(
                "approved full-text corpus exceeds the configured chunk limit; "
                "select a source or increase MAX_ACTIVE_FULLTEXT_CHUNKS"
            )
        return [dict(row) for row in rows]

    def list_current_fulltext_embeddings(
        self,
        *,
        source_type: str,
        source_ids: Sequence[str],
        model: str,
        dimensions: int | None,
    ) -> dict[str, list[float] | None]:
        """Read current approved chunk vectors for offline retrieval diagnostics."""
        import math

        if self.readonly is not True:
            raise ValueError("retrieval evaluation requires a read-only PaperStore")
        if source_type not in {"openalex", "arxiv"}:
            raise ValueError("source_type must be openalex or arxiv")
        if (
            not source_ids
            or len(source_ids) > MAX_ACTIVE_FULLTEXT_CHUNKS
            or any(not isinstance(source_id, str) or not source_id for source_id in source_ids)
        ):
            raise ValueError("source_ids must be a non-empty bounded list")
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("source_ids must be unique")
        if not isinstance(model, str) or not model.strip() or len(model) > 160:
            raise ValueError("invalid embedding model")
        if dimensions is not None and (type(dimensions) is not int or not 1 <= dimensions <= 8_192):
            raise ValueError("invalid embedding dimensions")
        if source_type == "openalex" and any(
            not isinstance(source_id, str) or not re.fullmatch(r"W\d+", source_id)
            for source_id in source_ids
        ):
            raise ValueError("invalid OpenAlex work ID")
        if source_type == "arxiv":
            from app.sources.arxiv import normalize_arxiv_id

            source_ids = [normalize_arxiv_id(source_id) for source_id in source_ids]
            if len(set(source_ids)) != len(source_ids):
                raise ValueError("source_ids must be unique after normalization")

        placeholders = ",".join("?" for _ in source_ids)
        dimension_clause = "AND e.dimensions=?" if dimensions is not None else ""
        params: list[Any] = [model]
        if dimensions is not None:
            params.append(dimensions)
        params.extend((source_type, *source_ids, MAX_ACTIVE_FULLTEXT_CHUNKS + 1))
        with self._connection() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                f"""SELECT c.chunk_id,e.vector_json FROM fulltext_documents d
                JOIN fulltext_chunks c ON c.source_type=d.source_type
                AND c.source_id=d.source_id AND c.content_sha256=d.current_sha256
                LEFT JOIN fulltext_embeddings e ON e.chunk_id=c.chunk_id
                AND e.model=? {dimension_clause} AND e.normalization='none'
                WHERE d.status='approved' AND d.source_type=?
                AND d.source_id IN ({placeholders})
                ORDER BY d.source_id,c.ordinal LIMIT ?""",
                params,
            ).fetchall()
        if len(rows) > MAX_ACTIVE_FULLTEXT_CHUNKS:
            raise ValueError("current approved corpus exceeds the embedding evaluation limit")
        vectors: dict[str, list[float] | None] = {}
        for row in rows:
            if row["vector_json"] is None:
                vectors[row["chunk_id"]] = None
                continue
            try:
                vector = json.loads(row["vector_json"])
            except (TypeError, json.JSONDecodeError) as error:
                raise ValueError("stored embedding vector is malformed") from error
            if (
                not isinstance(vector, list)
                or (dimensions is not None and len(vector) != dimensions)
                or not 1 <= len(vector) <= 8_192
                or any(
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                    for value in vector
                )
            ):
                raise ValueError("stored embedding vector is malformed")
            vectors[row["chunk_id"]] = [float(value) for value in vector]
        return vectors

    def get_approved_fulltext_chunk_by_id(
        self, *, source_type: str, source_id: str, chunk_id: str
    ) -> dict[str, Any] | None:
        """Read one current or historical chunk under an approved public source."""
        if self.readonly is not True:
            raise ValueError("historical evaluation anchors require a read-only PaperStore")
        if source_type not in {"openalex", "arxiv"}:
            raise ValueError("source_type must be openalex or arxiv")
        if source_type == "openalex" and not re.fullmatch(r"W\d+", source_id):
            raise ValueError("invalid OpenAlex work ID")
        if source_type == "arxiv":
            from app.sources.arxiv import normalize_arxiv_id

            source_id = normalize_arxiv_id(source_id)
        if not isinstance(chunk_id, str) or not chunk_id.strip() or len(chunk_id) > 500:
            raise ValueError("invalid full-text chunk ID")
        with self._connection() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                """SELECT c.*,v.source_document_sha256,v.license_id,v.license_url,
                v.parser_version FROM fulltext_documents d
                JOIN fulltext_versions v ON v.source_type=d.source_type
                AND v.source_id=d.source_id
                JOIN fulltext_chunks c ON c.source_type=v.source_type
                AND c.source_id=v.source_id AND c.content_sha256=v.content_sha256
                WHERE d.status='approved' AND d.source_type=? AND d.source_id=?
                AND c.chunk_id=? LIMIT 1""",
                (source_type, source_id, chunk_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_current_fulltext_elements(
        self, *, source_type: str, source_id: str
    ) -> list[dict[str, Any]]:
        """Load bounded parser elements from one current approved source for offline evaluation."""
        if self.readonly is not True:
            raise ValueError("chunk ablation requires a read-only PaperStore")
        if source_type not in {"openalex", "arxiv"}:
            raise ValueError("source_type must be openalex or arxiv")
        if source_type == "openalex" and not re.fullmatch(r"W\d+", source_id):
            raise ValueError("invalid OpenAlex work ID")
        if source_type == "arxiv":
            from app.sources.arxiv import normalize_arxiv_id

            source_id = normalize_arxiv_id(source_id)
        with self._connection() as connection:
            self._ensure_schema(connection)
            active_source = connection.execute(
                """SELECT d.current_sha256 FROM fulltext_documents d
                WHERE d.source_type=? AND d.source_id=? AND d.status='approved'""",
                (source_type, source_id),
            ).fetchone()
            if active_source is None:
                return []
            total_bytes = connection.execute(
                """SELECT COALESCE(SUM(length(CAST(e.element_json AS BLOB))),0)
                FROM fulltext_elements e
                WHERE e.source_type=? AND e.source_id=? AND e.content_sha256=?""",
                (source_type, source_id, active_source["current_sha256"]),
            ).fetchone()[0]
            if total_bytes > MAX_CHUNK_ABLATION_SOURCE_BYTES:
                raise ValueError("source exceeds the chunk ablation element-size limit")
            rows = connection.execute(
                """SELECT e.element_json FROM fulltext_elements e
                WHERE e.source_type=? AND e.source_id=? AND e.content_sha256=?
                ORDER BY e.order_index LIMIT ?""",
                (
                    source_type,
                    source_id,
                    active_source["current_sha256"],
                    MAX_ACTIVE_FULLTEXT_CHUNKS + 1,
                ),
            ).fetchall()
        if len(rows) > MAX_ACTIVE_FULLTEXT_CHUNKS:
            raise ValueError("source exceeds the chunk ablation element-count limit")
        elements = [json.loads(row["element_json"]) for row in rows]
        if any(not isinstance(element, dict) for element in elements):
            raise ValueError("stored parser element is malformed")
        return elements

    def list_current_fulltext_metadata(
        self, *, source_type: str | None = None
    ) -> list[dict[str, Any]]:
        """List lineage for each current approved source without loading its text."""
        if source_type not in {None, "openalex", "arxiv"}:
            raise ValueError("source_type must be openalex or arxiv")
        clauses = ["d.status='approved'", "d.current_sha256=v.content_sha256"]
        params: list[Any] = []
        if source_type is not None:
            clauses.append("d.source_type=?")
            params.append(source_type)
        with self._connection() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                f"""SELECT d.source_type, d.source_id, d.title, d.source_url, d.status,
                d.current_sha256 AS content_sha256, v.source_document_sha256,
                v.license_id, v.license_url, v.license_evidence_url, v.text_source_url,
                v.attribution, v.parser_version, v.chunker_version,
                COUNT(c.chunk_id) AS chunk_count
                FROM fulltext_documents d JOIN fulltext_versions v
                ON v.source_type=d.source_type AND v.source_id=d.source_id
                AND v.content_sha256=d.current_sha256
                LEFT JOIN fulltext_chunks c ON c.source_type=v.source_type
                AND c.source_id=v.source_id AND c.content_sha256=v.content_sha256
                WHERE {" AND ".join(clauses)}
                GROUP BY d.source_type, d.source_id, d.title, d.source_url, d.status,
                d.current_sha256, v.source_document_sha256, v.license_id, v.license_url,
                v.license_evidence_url, v.text_source_url, v.attribution, v.parser_version,
                v.chunker_version
                ORDER BY d.source_type, d.source_id""",
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_current_fulltext_metadata(
        self, *, source_type: str, source_id: str
    ) -> dict[str, Any] | None:
        """Return lineage for one currently approved full-text version."""
        if source_type not in {"openalex", "arxiv"}:
            raise ValueError("source_type must be openalex or arxiv")
        if source_type == "openalex" and not re.fullmatch(r"W\d+", source_id):
            raise ValueError("invalid OpenAlex work ID")
        if source_type == "arxiv":
            from app.sources.arxiv import normalize_arxiv_id

            source_id = normalize_arxiv_id(source_id)
        with self._connection() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                """SELECT d.source_type, d.source_id, d.title, d.status, d.current_sha256,
                d.current_sha256 AS content_sha256,
                v.source_document_sha256, v.license_id, v.license_url, v.parser_version,
                v.chunker_version, COUNT(c.chunk_id) AS chunk_count
                FROM fulltext_documents d JOIN fulltext_versions v
                ON v.source_type=d.source_type AND v.source_id=d.source_id
                AND v.content_sha256=d.current_sha256
                LEFT JOIN fulltext_chunks c ON c.source_type=v.source_type
                AND c.source_id=v.source_id AND c.content_sha256=v.content_sha256
                WHERE d.source_type=? AND d.source_id=? AND d.status='approved'
                GROUP BY d.source_type, d.source_id, d.title, d.status, d.current_sha256,
                v.source_document_sha256, v.license_id, v.license_url,
                v.parser_version, v.chunker_version""",
                (source_type, source_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def store_fulltext_embeddings(
        self,
        *,
        model: str,
        dimensions: int,
        items: list[dict[str, Any]],
    ) -> int:
        import math

        if not model.strip() or len(model) > 160 or not 1 <= dimensions <= 8_192:
            raise ValueError("invalid embedding model or dimensions")
        if len(items) > 2_000:
            raise ValueError("embedding batch exceeds the 2,000 chunk limit")
        if len({item.get("chunk_id") for item in items}) != len(items):
            raise ValueError("embedding batch contains duplicate chunk IDs")
        normalized: list[tuple[str, str, str, str, int, str]] = []
        for item in items:
            vector = item.get("vector")
            if (
                not isinstance(item.get("chunk_id"), str)
                or not isinstance(item.get("content_sha256"), str)
                or not isinstance(vector, list)
                or len(vector) != dimensions
                or any(
                    not isinstance(value, (int, float)) or not math.isfinite(value)
                    for value in vector
                )
            ):
                raise ValueError("invalid embedding vector or lineage")
            normalized.append(
                (
                    item["chunk_id"],
                    item["content_sha256"],
                    model,
                    json.dumps(vector, separators=(",", ":")),
                    dimensions,
                    _now(),
                )
            )
        with self._connection() as connection:
            self._ensure_schema(connection)
            active = {
                (row["chunk_id"], row["content_sha256"])
                for row in connection.execute(
                    """SELECT c.chunk_id,c.content_sha256 FROM fulltext_chunks c
                    JOIN fulltext_documents d ON d.source_type=c.source_type
                    AND d.source_id=c.source_id AND d.current_sha256=c.content_sha256
                    WHERE d.status='approved'"""
                ).fetchall()
            }
            if any((item[0], item[1]) not in active for item in normalized):
                raise ValueError("embedding chunk is not part of current approved full text")
            with connection:
                connection.executemany(
                    """INSERT OR REPLACE INTO fulltext_embeddings
                    (chunk_id,model,dimensions,normalization,vector_json,created_at)
                    VALUES (?,?,?,'none',?,?)""",
                    [
                        (chunk_id, model_name, dimensions, vector_json, created_at)
                        for (
                            chunk_id,
                            _,
                            model_name,
                            vector_json,
                            dimensions,
                            created_at,
                        ) in normalized
                    ],
                )
        return len(normalized)

    def delete_fulltext(self, source_type: str, source_id: str, *, reason: str) -> bool:
        if source_type not in {"openalex", "arxiv"}:
            raise ValueError("source_type must be openalex or arxiv")
        if source_type == "openalex" and not re.fullmatch(r"W\d+", source_id):
            raise ValueError("invalid OpenAlex work ID")
        if source_type == "arxiv":
            from app.sources.arxiv import normalize_arxiv_id

            source_id = normalize_arxiv_id(source_id)
        reason = " ".join(reason.split())
        if len(reason) < 3 or len(reason) > 500:
            raise ValueError("deletion reason must contain 3 to 500 characters")
        with self._connection() as connection:
            self._ensure_schema(connection)
            current = connection.execute(
                "SELECT current_sha256 FROM fulltext_documents WHERE source_type=? AND source_id=?",
                (source_type, source_id),
            ).fetchone()
            if current is None:
                return False
            with connection:
                connection.execute(
                    "INSERT INTO fulltext_deletion_events VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(uuid.uuid4()),
                        source_type,
                        source_id,
                        current["current_sha256"],
                        reason,
                        _now(),
                    ),
                )
                connection.execute(
                    "DELETE FROM fulltext_documents WHERE source_type=? AND source_id=?",
                    (source_type, source_id),
                )
        return True

    def list_papers(self, *, query: str | None, limit: int, offset: int) -> dict[str, Any]:
        if not 1 <= limit <= 50 or not 0 <= offset <= 10_000:
            raise ValueError("limit must be 1-50 and offset must be 0-10000")
        normalized_query = " ".join(query.split()) if query and query.strip() else None
        if normalized_query and len(normalized_query) > 128:
            raise ValueError("query must be at most 128 characters")
        where = "WHERE instr(lower(coalesce(title, '')), lower(?)) > 0" if normalized_query else ""
        params: tuple[Any, ...] = (normalized_query,) if normalized_query else ()
        with self._connection() as connection:
            self._ensure_schema(connection)
            total = connection.execute(f"SELECT COUNT(*) FROM works w {where}", params).fetchone()[
                0
            ]
            rows = connection.execute(
                f"""SELECT w.*,
                    (SELECT si.snapshot_id FROM snapshot_items si
                     WHERE si.openalex_id = w.openalex_id
                     ORDER BY si.rowid DESC LIMIT 1) AS snapshot_id
                    FROM works w {where}
                    ORDER BY publication_year IS NULL, publication_year DESC,
                    w.title COLLATE NOCASE, w.openalex_id LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ).fetchall()
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": [_paper_view(row) for row in rows],
            }

    def get_paper(
        self, openalex_id: str, *, snapshot_id: str | None = None
    ) -> dict[str, Any] | None:
        if not re.fullmatch(r"W\d+", openalex_id):
            return None
        with self._connection() as connection:
            self._ensure_schema(connection)
            if snapshot_id:
                row = connection.execute(
                    """SELECT w.first_seen_at, v.payload_sha256, v.fetched_at,
                        v.record_json, si.snapshot_id
                    FROM snapshot_items si JOIN works w USING (openalex_id)
                    JOIN work_versions v
                      ON v.openalex_id = si.openalex_id
                     AND v.payload_sha256 = si.payload_sha256
                    WHERE si.snapshot_id = ? AND si.openalex_id = ?""",
                    (snapshot_id, openalex_id),
                ).fetchone()
                if row is not None:
                    work = OpenAlexWork.model_validate(json.loads(row["record_json"]))
                    prepared = _prepare_work(work)
                    prepared.update(
                        {
                            "current_version_sha256": row["payload_sha256"],
                            "last_seen_at": row["fetched_at"],
                            "first_seen_at": row["first_seen_at"],
                            "snapshot_id": row["snapshot_id"],
                        }
                    )
                    return _paper_view(prepared)
            else:
                row = connection.execute(
                    """SELECT w.*, (SELECT si.snapshot_id FROM snapshot_items si
                        WHERE si.openalex_id = w.openalex_id
                        ORDER BY rowid DESC LIMIT 1) AS snapshot_id
                    FROM works w WHERE w.openalex_id = ?""",
                    (openalex_id,),
                ).fetchone()
            return _paper_view(row) if row else None

    def list_snapshots(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be 1-100")
        with self._connection() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                "SELECT * FROM import_snapshots ORDER BY imported_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "SELECT * FROM import_snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
            if row is None:
                return None
            snapshot = dict(row)
            snapshot["items"] = [
                dict(item)
                for item in connection.execute(
                    """SELECT si.openalex_id, si.payload_sha256, si.result_position,
                        w.title, w.source_url
                    FROM snapshot_items si JOIN works w USING(openalex_id)
                    WHERE si.snapshot_id = ? ORDER BY si.result_position""",
                    (snapshot_id,),
                ).fetchall()
            ]
            return snapshot


def _prepare_work(work: OpenAlexWork) -> dict[str, Any]:
    record = work.model_dump(mode="json", exclude_none=False)
    openalex_id = work.id.rsplit("/", maxsplit=1)[-1]
    record_json = _canonical_json(record)
    payload_sha256 = hashlib.sha256(record_json.encode("utf-8")).hexdigest()
    abstract, abstract_status = _reconstruct_abstract(work.abstract_inverted_index)
    authors = []
    for authorship in work.authorships:
        author = authorship.get("author")
        if isinstance(author, dict) and isinstance(author.get("display_name"), str):
            authors.append(
                {
                    "id": author.get("id") if isinstance(author.get("id"), str) else None,
                    "name": author["display_name"],
                }
            )
    primary_location = work.primary_location or {}
    source = primary_location.get("source") if isinstance(primary_location, dict) else None
    venue_name = source.get("display_name") if isinstance(source, dict) else None
    open_access_json = _canonical_json(work.open_access) if work.open_access is not None else None
    return {
        "openalex_id": openalex_id,
        "source_url": work.id,
        "title": work.title or work.display_name,
        "doi": work.doi,
        "publication_year": work.publication_year,
        "publication_date": work.publication_date,
        "work_type": work.type,
        "cited_by_count": work.cited_by_count,
        "abstract": abstract,
        "abstract_status": abstract_status,
        "authors_json": _canonical_json(authors),
        "venue_name": venue_name if isinstance(venue_name, str) else None,
        "open_access_json": open_access_json,
        "payload_sha256": payload_sha256,
        "record_json": record_json,
    }


def _prepare_arxiv_work(work: ArxivWork) -> dict[str, Any]:
    from app.sources.arxiv import normalize_arxiv_id

    record = work.model_dump(mode="json")
    normalized_id = normalize_arxiv_id(work.arxiv_id)
    record["arxiv_id"] = normalized_id
    record_json = _canonical_json(record)
    return {
        "arxiv_id": normalized_id,
        "source_url": f"https://arxiv.org/abs/{normalized_id}",
        "title": work.title,
        "abstract": work.abstract,
        "authors_json": _canonical_json(work.authors),
        "categories_json": _canonical_json(work.categories),
        "primary_category": work.primary_category,
        "published_at": work.published_at.astimezone(UTC).isoformat(),
        "updated_at": work.updated_at.astimezone(UTC).isoformat(),
        "doi": work.doi,
        "journal_ref": work.journal_ref,
        "payload_sha256": hashlib.sha256(record_json.encode("utf-8")).hexdigest(),
        "record_json": record_json,
    }


def _arxiv_paper_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "arxiv_id": row["arxiv_id"],
        "title": row["title"],
        "abstract": row["abstract"],
        "authors": json.loads(row["authors_json"]),
        "categories": json.loads(row["categories_json"]),
        "primary_category": row["primary_category"],
        "published_at": row["published_at"],
        "updated_at": row["updated_at"],
        "doi": row["doi"],
        "journal_ref": row["journal_ref"],
        "source": "arxiv",
        "source_url": row["source_url"],
        "current_version_sha256": row["current_version_sha256"],
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "metadata_license": SOURCE_LICENSE,
    }


def _reconstruct_abstract(
    inverted_index: dict[str, list[int]] | None,
) -> tuple[str | None, str]:
    if not inverted_index:
        return None, "missing"
    positions: dict[int, str] = {}
    character_count = 0
    try:
        for token, indexes in inverted_index.items():
            if len(token) > 2_000:
                return None, "oversized"
            for index in indexes:
                if index < 0 or index >= MAX_ABSTRACT_POSITIONS or index in positions:
                    return None, "invalid"
                positions[index] = token
                character_count += len(token) + 1
                if character_count > MAX_ABSTRACT_CHARS:
                    return None, "oversized"
    except (TypeError, ValueError):
        return None, "invalid"
    if not positions:
        return None, "missing"
    if max(positions) + 1 > MAX_ABSTRACT_POSITIONS:
        return None, "oversized"
    abstract = " ".join(positions.get(index, "") for index in range(max(positions) + 1)).strip()
    if len(abstract) > MAX_ABSTRACT_CHARS:
        return None, "oversized"
    return re.sub(r"\s+", " ", abstract), "available"


def _element_evidence_view(value: Any) -> dict[str, Any]:
    """Return bounded parser geometry and table/caption structure without duplicating body text."""
    if not isinstance(value, dict):
        return {}
    structured = value.get("structured")
    projected: dict[str, Any] = {}
    truncated = False
    if isinstance(structured, dict):
        rows = structured.get("rows")
        if isinstance(rows, list):
            projected_rows = []
            for row in rows[:100]:
                if not isinstance(row, dict):
                    continue
                cells = row.get("cells", [])
                projected_cells = []
                if isinstance(cells, list):
                    for cell in cells[:50]:
                        if not isinstance(cell, dict):
                            continue
                        projected_cell = {"text": str(cell.get("text", ""))[:1_000]}
                        if isinstance(cell.get("bbox"), list):
                            projected_cell["bbox"] = cell["bbox"]
                        projected_cells.append(projected_cell)
                    truncated |= len(cells) > 50
                projected_rows.append({"row_index": row.get("row_index"), "cells": projected_cells})
            projected["rows"] = projected_rows
            truncated |= len(rows) > 100
        for key in ("image_relation", "caption_relation"):
            relation = structured.get(key)
            if isinstance(relation, dict):
                projected[key] = relation
    result = {
        key: value[key]
        for key in (
            "element_id",
            "order_index",
            "page_number",
            "page_width",
            "page_height",
            "element_type",
            "bbox",
            "section_path",
            "warnings",
        )
        if key in value
    }
    if projected:
        result["structured"] = projected
    if truncated:
        result["structured_truncated"] = True
    return result


def _paper_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "openalex_id": row["openalex_id"],
        "title": row["title"],
        "doi": row["doi"],
        "publication_year": row["publication_year"],
        "publication_date": row["publication_date"],
        "type": row["work_type"],
        "cited_by_count": row["cited_by_count"],
        "abstract": row["abstract"],
        "abstract_status": row["abstract_status"],
        "authors": json.loads(row["authors_json"]),
        "venue": row["venue_name"],
        "open_access": json.loads(row["open_access_json"]) if row["open_access_json"] else None,
        "source": "openalex",
        "source_url": row["source_url"],
        "snapshot_id": row["snapshot_id"],
        "observed_at": row["last_seen_at"],
        "content_sha256": row["current_version_sha256"],
        "metadata_license": SOURCE_LICENSE,
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _retrieval_text(text: str, section_path: str) -> str:
    """Add bounded parent section context without changing the quoted evidence span."""
    try:
        sections = json.loads(section_path)
    except json.JSONDecodeError:
        sections = []
    context = " / ".join(item for item in sections if isinstance(item, str))
    if not context:
        return text
    available = max(0, 1_800 - len(text.encode("utf-8")) - 1)
    prefix = context.encode("utf-8")[:available].decode("utf-8", errors="ignore").rstrip()
    return f"{prefix}\n{text}" if prefix else text


def _bounded_join(parts: list[str], *, limit_bytes: int) -> str:
    """Join ranked/parent context while preserving UTF-8 character boundaries."""
    output: list[str] = []
    used = 0
    for part in parts:
        separator = "\n"
        separator_bytes = len(separator.encode("utf-8")) if output else 0
        available = limit_bytes - used - separator_bytes
        if available <= 0:
            break
        encoded = part.encode("utf-8")[:available]
        bounded = encoded.decode("utf-8", errors="ignore")
        if not bounded:
            break
        output.append(bounded)
        used += separator_bytes + len(bounded.encode("utf-8"))
        if len(bounded) < len(part):
            break
    return "\n".join(output)


def _normalize_doi(value: str | None) -> str | None:
    if not value or len(value) > 500:
        return None
    normalized = value.strip().lower()
    normalized = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", normalized)
    normalized = normalized.removeprefix("doi:").strip()
    return normalized if re.fullmatch(r"10\.\d{4,9}/\S+", normalized) else None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _lease_expiry() -> str:
    return (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
