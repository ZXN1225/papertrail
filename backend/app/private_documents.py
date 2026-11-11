"""Private, user-owned PDF storage and MinerU indexing."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.embeddings.client import EmbeddingError, EmbeddingProvider
from app.retrieval.fulltext import PDF_CHUNKER_VERSION, chunk_pdf_elements
from app.retrieval.pdf_parser import (
    MAX_PDF_BYTES,
    MINERU_ADAPTER_VERSION,
    read_pdf_bytes,
)
from app.retrieval.vectors import dense_rank, reciprocal_rank_fusion
from app.storage.repository import PaperStore

MAX_USER_DOCUMENTS = 20
MAX_USER_DOCUMENT_BYTES = 500 * 1024 * 1024
MAX_PRIVATE_USER_CHUNKS = 25_000
MAX_FILENAME_LENGTH = 180
PRIVATE_PARSE_TIMEOUT_SECONDS = 1800
MAX_PRIVATE_PARSE_OUTPUT_BYTES = 32 * 1024 * 1024


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_filename(value: str) -> str:
    name = Path(value.replace("\\", "/")).name
    name = "".join(character for character in name if character.isprintable())
    name = name[:MAX_FILENAME_LENGTH].strip()
    if not name or not name.lower().endswith(".pdf"):
        raise ValueError("invalid_pdf_filename")
    return name


def _parse_pdf_in_worker(path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="papertrail-private-parse-") as directory:
        output = Path(directory) / "parsed.json"
        environment = os.environ.copy()
        environment["MINERU_MODEL_SOURCE"] = "local"
        environment["MINERU_TELEMETRY_DISABLED"] = "1"
        for key in ("OPENAI_API_KEY", "LLM_API_KEY", "EMBEDDING_API_KEY", "OPENALEX_API_KEY"):
            environment.pop(key, None)
        subprocess.run(
            [sys.executable, "-m", "app.cli.parse_private_pdf", str(path), str(output)],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=PRIVATE_PARSE_TIMEOUT_SECONDS,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if not output.is_file() or output.stat().st_size > MAX_PRIVATE_PARSE_OUTPUT_BYTES:
            raise ValueError("MinerU worker returned invalid output")
        return json.loads(output.read_text(encoding="utf-8"))


class PrivateDocumentService:
    def __init__(self, store: PaperStore) -> None:
        self.store = store
        self.root = (store.database_path.parent / "private-papers").resolve()

    def _path(self, owner: str, storage_key: str) -> Path:
        if re.fullmatch(r"[0-9a-f-]{36}\.pdf", storage_key) is None:
            raise ValueError("invalid_storage_key")
        owner_dir = (self.root / owner).resolve()
        path = (owner_dir / storage_key).resolve()
        if not path.is_relative_to(owner_dir) or not owner_dir.is_relative_to(self.root):
            raise ValueError("invalid_storage_path")
        return path

    def store_upload(
        self,
        *,
        user_id: str,
        library_entry_id: str | None = None,
        title: str | None = None,
        filename: str,
        pdf_bytes: bytes,
        rights_attested: bool,
    ) -> dict[str, Any]:
        if rights_attested is not True:
            raise ValueError("private_rights_attestation_required")
        if (library_entry_id is None) == (title is None):
            raise ValueError("exactly_one_document_source_required")
        if title is not None:
            title = title.strip()
            if not title or len(title) > 500:
                raise ValueError("invalid_personal_title")
        if not pdf_bytes.startswith(b"%PDF-") or len(pdf_bytes) > MAX_PDF_BYTES:
            raise ValueError("invalid_or_oversized_pdf")
        clean_name = _safe_filename(filename)
        now = _now()
        digest = hashlib.sha256(pdf_bytes).hexdigest()
        document_id = str(uuid.uuid4())
        storage_key = f"{document_id}.pdf"
        path = self._path(user_id, storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.store._connection() as db:
            self.store._ensure_schema(db)
            db.execute("BEGIN IMMEDIATE")
            library_entry = None
            if library_entry_id is not None:
                library_entry = db.execute(
                    "SELECT source,source_id,metadata_json,metadata_sha256 "
                    "FROM user_library_entries "
                    "WHERE id=? AND user_id=?",
                    (library_entry_id, user_id),
                ).fetchone()
                if library_entry is None:
                    raise LookupError("library_entry_not_found")
            usage = db.execute(
                "SELECT COUNT(*) AS documents, COALESCE(SUM(size_bytes),0) AS bytes "
                "FROM user_documents WHERE user_id=?",
                (user_id,),
            ).fetchone()
            if usage["documents"] >= MAX_USER_DOCUMENTS:
                raise OverflowError("user_document_count_limit")
            if usage["bytes"] + len(pdf_bytes) > MAX_USER_DOCUMENT_BYTES:
                raise OverflowError("user_document_storage_limit")
            if library_entry is not None:
                if (
                    hashlib.sha256(library_entry["metadata_json"].encode("utf-8")).hexdigest()
                    != library_entry["metadata_sha256"]
                ):
                    raise ValueError("library_metadata_integrity_error")
                try:
                    metadata = json.loads(library_entry["metadata_json"])
                except json.JSONDecodeError as error:
                    raise ValueError("library_metadata_integrity_error") from error
                title = metadata.get("title")
                source_url = metadata.get("sourceUrl")
                expected_url = (
                    f"https://openalex.org/{library_entry['source_id']}"
                    if library_entry["source"] == "openalex"
                    else f"https://arxiv.org/abs/{library_entry['source_id']}"
                )
                if not isinstance(title, str) or source_url != expected_url:
                    raise ValueError("library_metadata_missing_canonical_source")
            with path.open("xb") as handle:
                handle.write(pdf_bytes)
            try:
                db.execute(
                    "INSERT INTO user_documents "
                    "(id,user_id,library_entry_id,source_type,source_id,title,source_url,"
                    "original_filename,storage_key,document_sha256,size_bytes,state,"
                    "rights_attested_at,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,'queued',?,?,?)",
                    (
                        document_id,
                        user_id,
                        library_entry_id,
                        library_entry["source"] if library_entry is not None else "personal",
                        library_entry["source_id"] if library_entry is not None else document_id,
                        title[:500],
                        expected_url if library_entry is not None else "",
                        clean_name,
                        storage_key,
                        digest,
                        len(pdf_bytes),
                        now,
                        now,
                        now,
                    ),
                )
            except Exception:
                path.unlink(missing_ok=True)
                raise
        return self.get_document(user_id, document_id) or {}

    def get_document(self, user_id: str, document_id: str) -> dict[str, Any] | None:
        with self.store._connection() as db:
            self.store._ensure_schema(db)
            row = db.execute(
                "SELECT d.id,d.library_entry_id,d.source_type,d.source_id,d.title,d.source_url,"
                "d.original_filename,d.document_sha256,d.size_bytes,d.state,"
                "d.rights_attested_at,d.parser_version,d.chunker_version,d.error_code,d.chunk_count,"
                "d.created_at,d.updated_at,d.indexed_at,"
                "(SELECT COUNT(*) FROM user_document_chunks c WHERE c.document_id=d.id "
                "AND c.user_id=d.user_id) AS stored_chunk_count "
                "FROM user_documents d WHERE d.id=? AND d.user_id=?",
                (document_id, user_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_documents(
        self, user_id: str, library_entry_id: str | None = None
    ) -> list[dict[str, Any]]:
        with self.store._connection() as db:
            self.store._ensure_schema(db)
            rows = db.execute(
                "SELECT id,library_entry_id,source_type,source_id,title,source_url,"
                "original_filename,"
                "document_sha256,size_bytes,state,rights_attested_at,parser_version,chunker_version,error_code,"
                "chunk_count,created_at,updated_at,indexed_at FROM user_documents "
                "WHERE user_id=? AND (? IS NULL OR library_entry_id=?) "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, library_entry_id, library_entry_id, MAX_USER_DOCUMENTS),
            ).fetchall()
        return [dict(row) for row in rows]

    def pending_documents(self) -> list[tuple[str, str]]:
        with self.store._connection() as db:
            self.store._ensure_schema(db)
            db.execute("BEGIN IMMEDIATE")
            self._recover_delete_tombstones(db)
            db.execute(
                "UPDATE user_documents SET state='failed',error_code='reindex_required',"
                "updated_at=? WHERE state='indexed' AND "
                "(parser_version IS NULL OR parser_version NOT LIKE ? "
                "OR COALESCE(chunker_version,'')!=?)",
                (_now(), f"%-{MINERU_ADAPTER_VERSION}", PDF_CHUNKER_VERSION),
            )
            db.execute(
                "UPDATE user_documents SET state='failed',error_code='worker_interrupted',"
                "updated_at=? WHERE state='processing'",
                (_now(),),
            )
            rows = db.execute(
                "SELECT id,user_id FROM user_documents WHERE state='queued' ORDER BY created_at"
            ).fetchall()
        return [(row["id"], row["user_id"]) for row in rows]

    def _recover_delete_tombstones(self, db: Any) -> None:
        if not self.root.is_dir():
            return
        for owner_dir in self.root.iterdir():
            if not owner_dir.is_dir() or owner_dir.is_symlink():
                continue
            for tombstone in owner_dir.glob("*.pdf.deleting"):
                if tombstone.is_symlink():
                    tombstone.unlink(missing_ok=True)
                    continue
                storage_key = tombstone.name.removesuffix(".deleting")
                try:
                    original = self._path(owner_dir.name, storage_key)
                except ValueError:
                    continue
                row = db.execute(
                    "SELECT 1 FROM user_documents WHERE user_id=? AND storage_key=?",
                    (owner_dir.name, storage_key),
                ).fetchone()
                if row is not None and not original.exists():
                    tombstone.replace(original)
                else:
                    tombstone.unlink(missing_ok=True)

    def retry_document(self, user_id: str, document_id: str) -> bool:
        with self.store._connection() as db:
            cursor = db.execute(
                "UPDATE user_documents SET state='queued',error_code=NULL,updated_at=? "
                "WHERE id=? AND user_id=? AND state='failed'",
                (_now(), document_id, user_id),
            )
        return cursor.rowcount == 1

    def delete_document(self, user_id: str, document_id: str) -> str:
        path: Path | None = None
        tombstone: Path | None = None
        try:
            with self.store._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT storage_key,state FROM user_documents WHERE id=? AND user_id=?",
                    (document_id, user_id),
                ).fetchone()
                if row is None:
                    raise LookupError("document_not_found")
                if row["state"] in {"queued", "processing"}:
                    raise RuntimeError("document_processing")
                path = self._path(user_id, row["storage_key"])
                tombstone = path.with_name(f"{path.name}.deleting")
                if path.exists():
                    path.replace(tombstone)
                db.execute(
                    "DELETE FROM user_documents WHERE id=? AND user_id=?",
                    (document_id, user_id),
                )
        except Exception:
            if tombstone is not None and tombstone.exists() and path is not None:
                if not path.exists():
                    tombstone.replace(path)
            raise
        if tombstone is not None:
            try:
                tombstone.unlink(missing_ok=True)
            except OSError as error:
                raise OSError("document_file_cleanup_failed") from error
        return document_id

    def process_document(self, user_id: str, document_id: str) -> None:
        with self.store._connection() as db:
            row = db.execute(
                "SELECT * FROM user_documents WHERE id=? AND user_id=? AND state='queued'",
                (document_id, user_id),
            ).fetchone()
            if row is None:
                return
            storage_key = row["storage_key"]
            expected_sha256 = row["document_sha256"]
            cursor = db.execute(
                "UPDATE user_documents SET state='processing',error_code=NULL,updated_at=? "
                "WHERE id=? AND user_id=? AND state='queued'",
                (_now(), document_id, user_id),
            )
            if cursor.rowcount != 1:
                return
        try:
            pdf_bytes = read_pdf_bytes(self._path(user_id, storage_key))
            if hashlib.sha256(pdf_bytes).hexdigest() != expected_sha256:
                raise ValueError("private_document_hash_mismatch")
            parsed = _parse_pdf_in_worker(self._path(user_id, storage_key))
            chunks = chunk_pdf_elements(parsed["elements"])
            with self.store._connection() as db:
                existing_chunk_count = db.execute(
                    "SELECT COALESCE(SUM(chunk_count),0) FROM user_documents "
                    "WHERE user_id=? AND id<>? AND state='indexed'",
                    (user_id, document_id),
                ).fetchone()[0]
                if existing_chunk_count + len(chunks) > MAX_PRIVATE_USER_CHUNKS:
                    raise OverflowError("private_index_chunk_limit")
                current = db.execute(
                    "SELECT 1 FROM user_documents WHERE id=? AND user_id=? AND state='processing' "
                    "AND document_sha256=?",
                    (document_id, user_id, expected_sha256),
                ).fetchone()
                if current is None:
                    return
                db.execute("DELETE FROM user_document_chunks WHERE document_id=?", (document_id,))
                db.executemany(
                    "INSERT INTO user_document_chunks "
                    "(chunk_id,document_id,user_id,ordinal,retrieval_text,evidence_text,locator,"
                    "char_start,char_end,page_number,element_type,section_path,bbox_json,element_id,"
                    "content_sha256) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        (
                            f"private:{document_id}:{chunk.ordinal}",
                            document_id,
                            user_id,
                            chunk.ordinal,
                            chunk.text,
                            chunk.evidence_text or chunk.text,
                            chunk.locator,
                            chunk.char_start,
                            chunk.char_end,
                            chunk.page_number or 1,
                            chunk.element_type,
                            chunk.section_path,
                            chunk.bbox,
                            chunk.element_id,
                            expected_sha256,
                        )
                        for chunk in chunks
                    ],
                )
                db.execute(
                    "UPDATE user_documents SET state='indexed',parser_version=?,"
                    "chunker_version=?,error_code=NULL,"
                    "chunk_count=?,updated_at=?,indexed_at=? WHERE id=? AND user_id=?",
                    (
                        parsed["parser_version"],
                        PDF_CHUNKER_VERSION,
                        len(chunks),
                        _now(),
                        _now(),
                        document_id,
                        user_id,
                    ),
                )
        except Exception as error:
            with self.store._connection() as db:
                db.execute(
                    "UPDATE user_documents SET state='failed',error_code=?,updated_at=? "
                    "WHERE id=? AND user_id=? AND state='processing'",
                    (
                        "document_integrity_error"
                        if isinstance(locals().get("pdf_bytes"), bytes)
                        and hashlib.sha256(locals()["pdf_bytes"]).hexdigest() != expected_sha256
                        else "private_index_chunk_limit"
                        if isinstance(error, OverflowError)
                        else "mineru_timeout"
                        if isinstance(error, subprocess.TimeoutExpired)
                        else "mineru_remote_config_forbidden"
                        if isinstance(error, subprocess.CalledProcessError)
                        and error.returncode == 3
                        else "mineru_parse_failed",
                        _now(),
                        document_id,
                        user_id,
                    ),
                )

    def build_embeddings(self, user_id: str, provider: EmbeddingProvider) -> dict[str, int]:
        """Explicit indexing operation; never invoked by the read-only Agent tool."""
        self.store.migrate()
        with self.store._connection() as db:
            rows = db.execute(
                "SELECT c.chunk_id,c.retrieval_text FROM user_document_chunks c "
                "JOIN user_documents d ON d.id=c.document_id AND d.user_id=c.user_id "
                "WHERE c.user_id=? AND d.state='indexed' "
                "AND c.element_type NOT IN ('table','figure') ORDER BY c.chunk_id",
                (user_id,),
            ).fetchall()
            existing = {
                row["chunk_id"]: row["content_sha256"]
                for row in db.execute(
                    "SELECT e.chunk_id,e.content_sha256 FROM user_chunk_embeddings e "
                    "JOIN user_document_chunks c ON c.chunk_id=e.chunk_id "
                    "WHERE c.user_id=? AND e.model=?",
                    (user_id, provider.model),
                )
            }
        rows = [
            row
            for row in rows
            if existing.get(row["chunk_id"])
            != hashlib.sha256(row["retrieval_text"][:8000].encode()).hexdigest()
        ]
        tokens = 0
        for start in range(0, len(rows), 32):
            batch_rows = rows[start : start + 32]
            texts = [row["retrieval_text"][:8000] for row in batch_rows]
            batch = provider.embed(texts)
            if batch.model != provider.model or len(batch.vectors) != len(batch_rows):
                raise EmbeddingError("invalid_response")
            tokens += batch.input_tokens
            with self.store._connection() as db:
                for row, text, vector in zip(batch_rows, texts, batch.vectors, strict=True):
                    current = db.execute(
                        "SELECT retrieval_text FROM user_document_chunks "
                        "WHERE chunk_id=? AND user_id=?",
                        (row["chunk_id"], user_id),
                    ).fetchone()
                    if current is None or current["retrieval_text"][:8000] != text:
                        continue
                    db.execute(
                        "INSERT OR REPLACE INTO user_chunk_embeddings "
                        "(chunk_id,model,content_sha256,dimensions,vector_json) VALUES(?,?,?,?,?)",
                        (
                            row["chunk_id"],
                            batch.model,
                            hashlib.sha256(text.encode()).hexdigest(),
                            len(vector),
                            json.dumps(vector),
                        ),
                    )
        return {"chunks": len(rows), "input_tokens": tokens}

    def search_evidence(
        self,
        query: str,
        *,
        user_id: str,
        source_type: str | None,
        source_id: str | None,
        limit: int,
        query_vector: list[float] | None = None,
        embedding_model: str | None = None,
        library_only: bool = False,
    ) -> dict[str, Any]:
        normalized = " ".join(query.split())
        if not normalized or len(normalized) > 256:
            raise ValueError("query must contain 1 to 256 non-whitespace characters")
        clauses = [
            "c.user_id=?",
            "d.user_id=c.user_id",
            "d.state='indexed'",
            "c.element_type NOT IN ('table','figure')",
        ]
        params: list[Any] = [user_id]
        if library_only:
            clauses.append("d.library_entry_id IS NOT NULL")
        if source_type is not None:
            clauses.append("d.source_type=?")
            params.append(source_type)
        if source_id is not None:
            clauses.append("d.source_id=?")
            params.append(source_id)
        with self.store._connection() as db:
            rows = db.execute(
                f"SELECT c.*,d.source_type,d.source_id,d.title,d.source_url,d.document_sha256,"
                f"d.rights_attested_at FROM user_document_chunks c JOIN user_documents d "
                f"ON d.id=c.document_id WHERE {' AND '.join(clauses)} "
                "ORDER BY c.document_id,c.ordinal LIMIT ?",
                [*params, MAX_PRIVATE_USER_CHUNKS + 1],
            ).fetchall()
        if len(rows) > MAX_PRIVATE_USER_CHUNKS:
            return {
                "status": "corpus_limit_exceeded",
                "items": [],
                "scanned_chunks": len(rows),
            }
        if not rows:
            return {"status": "no_results", "items": [], "scanned_chunks": 0}
        from app.retrieval.bm25 import BM25Index

        documents = [
            {
                "openalex_id": row["chunk_id"],
                "title": row["title"],
                "abstract": row["retrieval_text"],
            }
            for row in rows
        ]
        by_id = {row["chunk_id"]: row for row in rows}
        hits = BM25Index(documents).search(normalized, limit=max(limit, 32))
        ranked = [(hit.openalex_id, hit.score) for hit in hits]
        method = "private_bm25"
        if query_vector is not None and embedding_model is not None:
            with self.store._connection() as db:
                vectors = db.execute(
                    "SELECT e.* FROM user_chunk_embeddings e JOIN user_document_chunks c "
                    "ON c.chunk_id=e.chunk_id WHERE c.user_id=? AND e.model=? "
                    "AND e.dimensions=?",
                    (user_id, embedding_model, len(query_vector)),
                ).fetchall()
            valid = {
                row["chunk_id"]: json.loads(row["vector_json"])
                for row in vectors
                if row["chunk_id"] in by_id
                and row["content_sha256"]
                == hashlib.sha256(
                    by_id[row["chunk_id"]]["retrieval_text"][:8000].encode()
                ).hexdigest()
            }
            if valid:
                dense = dense_rank(query_vector, valid)[:32]
                ranked = reciprocal_rank_fusion([ranked, dense])
                method = "private_hybrid_rrf"
        items = []
        for chunk_id, score in ranked[:limit]:
            row = by_id[chunk_id]
            item: dict[str, Any] = {
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "title": row["title"],
                "source_url": row["source_url"],
                "chunk_id": row["chunk_id"],
                "locator": row["locator"][:240],
                "char_start": row["char_start"],
                "char_end": row["char_end"],
                "element_id": row["element_id"],
                "page_number": row["page_number"],
                "element_type": row["element_type"],
                "section_path": json.loads(row["section_path"]),
                "bbox": json.loads(row["bbox_json"]) if row["bbox_json"] else None,
                "retrieval_context": row["retrieval_text"],
                "excerpt": row["evidence_text"],
                "expanded_evidence": [],
                "score": round(score, 6),
                "private_processing": True,
                "rights_attested_at": row["rights_attested_at"],
                "content_sha256": row["document_sha256"],
                "parser_warnings": [],
            }
            identifier_key = {
                "openalex": "openalex_id",
                "arxiv": "arxiv_id",
                "personal": "personal_id",
            }[row["source_type"]]
            item[identifier_key] = row["source_id"]
            items.append(item)
        return {
            "status": "ok" if items else "no_results",
            "items": items,
            "scanned_chunks": len(rows),
            "retrieval_method": method,
        }
