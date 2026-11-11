"""HTTP entry point for the PaperTrail API."""

import asyncio
import hashlib
import json
import logging
import re
import sqlite3
import threading
import time
import traceback
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi import Path as PathParameter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.agent.contracts import AgentQuestion, AgentResponse, AgentTaskStatus, AgentTraceEvent
from app.agent.service import AgentService
from app.auth import SESSION_COOKIE, create_account, login, session_user, token_digest
from app.config import Settings, get_settings
from app.embeddings.client import EmbeddingError, OpenAIEmbeddingClient
from app.private_documents import (
    MAX_USER_DOCUMENT_BYTES,
    MAX_USER_DOCUMENTS,
    PrivateDocumentService,
)
from app.retrieval.fulltext import PDF_CHUNKER_VERSION
from app.retrieval.pdf_parser import MINERU_ADAPTER_VERSION
from app.sources.arxiv import ArxivClient, ArxivError
from app.sources.openalex import OpenAlexClient, OpenAlexError
from app.storage.repository import DailyAgentTokenBudgetExceeded, PaperStore, StoreError

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _require_user(request: Request, settings: Settings) -> str:
    user_id = session_user(
        PaperStore(settings.resolved_data_storage_path), request.cookies.get(SESSION_COOKIE)
    )
    if user_id is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    return user_id


def _agent_run_harness_metadata(
    question: str,
    settings: Settings,
    *,
    prior_user_questions: list[str] | None = None,
    library_ids: list[tuple[str, str]] | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "model_id": settings.llm_model,
        "model_reasoning_effort": settings.llm_reasoning_effort,
        "model_max_output_tokens": settings.llm_max_output_tokens,
        "pdf_parser_adapter": MINERU_ADAPTER_VERSION,
        "pdf_chunker_version": PDF_CHUNKER_VERSION,
    }
    metadata.update(
        {
            "runtime_version": "research-runtime-2",
            "workflow": ["semantic-plan", "scoped-retrieval", "draft", "semantic-review"],
        }
    )
    return metadata


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    application = FastAPI(
        title="PaperTrail API",
        version="0.1.0",
        description="Academic paper discovery and research assistant API.",
    )
    application.state.active_agent_runs = {}
    application.state.agent_worker_id = str(uuid4())
    application.state.private_document_tasks = {}
    application.state.private_document_semaphore = asyncio.Semaphore(1)

    def schedule_private_document(document_id: str, owner: str) -> None:
        tasks: dict[str, asyncio.Task] = application.state.private_document_tasks
        active = tasks.get(document_id)
        if active is not None and not active.done():

            async def schedule_after_active() -> None:
                try:
                    await active
                finally:
                    if tasks.get(document_id) is asyncio.current_task():
                        tasks.pop(document_id, None)
                document = PrivateDocumentService(
                    PaperStore(app_settings.resolved_data_storage_path)
                ).get_document(owner, document_id)
                if document is not None and document["state"] == "queued":
                    schedule_private_document(document_id, owner)

            tasks[document_id] = asyncio.create_task(schedule_after_active())
            return

        async def process() -> None:
            try:
                async with application.state.private_document_semaphore:
                    store = PaperStore(app_settings.resolved_data_storage_path)
                    await run_in_threadpool(
                        PrivateDocumentService(store).process_document, owner, document_id
                    )
            finally:
                if tasks.get(document_id) is asyncio.current_task():
                    tasks.pop(document_id, None)

        tasks[document_id] = asyncio.create_task(process())

    async def resume_private_document_tasks() -> None:
        store = PaperStore(app_settings.resolved_data_storage_path)
        store.migrate()
        for document_id, owner in PrivateDocumentService(store).pending_documents():
            schedule_private_document(document_id, owner)

    async def stop_private_document_tasks() -> None:
        tasks = list(application.state.private_document_tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    application.router.add_event_handler("startup", resume_private_document_tasks)
    application.router.add_event_handler("shutdown", stop_private_document_tasks)

    def check_auth_limit(request: Request, username: str) -> None:
        now = time.time()
        client_key = request.client.host if request.client else "unknown"
        store = PaperStore(app_settings.resolved_data_storage_path)
        store.migrate()
        with store._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM auth_attempts WHERE attempted_at <= ?", (now - 900,))
            recent = db.execute(
                "SELECT COUNT(*) FROM auth_attempts WHERE client_key=? AND username_key=? "
                "AND attempted_at>?",
                (client_key, username.casefold(), now - 900),
            ).fetchone()[0]
            if recent >= 8:
                raise HTTPException(status_code=429, detail="too_many_attempts")
            db.execute(
                "INSERT INTO auth_attempts(client_key,username_key,attempted_at) VALUES(?,?,?)",
                (client_key, username.casefold(), now),
            )

    class Credentials(BaseModel):
        username: str = Field(min_length=3, max_length=40)
        password: str = Field(min_length=12, max_length=256)

    class LibraryEntry(BaseModel):
        source: str
        source_id: str = Field(min_length=1, max_length=200)
        metadata: dict[str, object] = Field(default_factory=dict)

    class ConversationInput(BaseModel):
        title: str = Field(min_length=1, max_length=120)

    @application.post("/api/v1/auth/register", tags=["auth"], status_code=201)
    def register(body: Credentials, request: Request) -> dict[str, str]:
        check_auth_limit(request, body.username)
        try:
            user_id = create_account(
                PaperStore(app_settings.resolved_data_storage_path), body.username, body.password
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid_credentials") from exc
        if user_id is None:
            raise HTTPException(status_code=409, detail="username_unavailable")
        return {"id": user_id, "username": body.username.strip()}

    @application.post("/api/v1/auth/login", tags=["auth"])
    def auth_login(body: Credentials, request: Request, response: Response) -> dict[str, str]:
        check_auth_limit(request, body.username)
        result = login(
            PaperStore(app_settings.resolved_data_storage_path), body.username, body.password
        )
        if result is None:
            raise HTTPException(status_code=401, detail="invalid_credentials")
        user_id, token = result
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            secure=app_settings.app_env == "production",
            samesite="lax",
            max_age=14 * 24 * 60 * 60,
            path="/",
        )
        return {"id": user_id}

    @application.post("/api/v1/auth/logout", tags=["auth"])
    def auth_logout(request: Request, response: Response) -> dict[str, str]:
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            store = PaperStore(app_settings.resolved_data_storage_path)
            store.migrate()
            with store._connection() as db:
                db.execute(
                    "UPDATE user_sessions SET revoked_at=? WHERE token_sha256=?",
                    (_now_iso(), token_digest(token)),
                )
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"status": "ok"}

    @application.get("/api/v1/auth/me", tags=["auth"])
    def auth_me(request: Request) -> dict[str, str]:
        user_id = session_user(
            PaperStore(app_settings.resolved_data_storage_path),
            request.cookies.get(SESSION_COOKIE),
        )
        if user_id is None:
            raise HTTPException(status_code=401, detail="authentication_required")
        return {"id": user_id}

    @application.get("/api/v1/library", tags=["library"])
    def list_library(
        request: Request,
        query: str | None = Query(default=None, max_length=128),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> list[dict[str, object]]:
        user_id = _require_user(request, app_settings)
        store = PaperStore(app_settings.resolved_data_storage_path)
        store.migrate()
        terms = re.findall(r"\w+", query.casefold()) if query and query.strip() else []
        if query and query.strip() and not terms:
            terms = [query.strip().casefold()]
        match_clauses = [
            "(instr(lower(source),lower(?))>0 OR "
            "instr(lower(source_id),lower(?))>0 OR "
            "instr(lower(metadata_json),lower(?))>0)"
            for _ in terms
        ]
        where_clause = " AND ".join(["user_id=?", *match_clauses])
        query_params: list[object] = [user_id]
        for term in terms:
            query_params.extend((term, term, term))
        query_params.append(limit)
        with store._connection() as db:
            rows = db.execute(
                "SELECT id,source,source_id,added_at,metadata_json,metadata_sha256 "
                f"FROM user_library_entries WHERE {where_clause} "
                "ORDER BY added_at DESC LIMIT ?",
                query_params,
            ).fetchall()
        entries = []
        for row in rows:
            metadata_json = row["metadata_json"]
            digest = hashlib.sha256(metadata_json.encode("utf-8")).hexdigest()
            try:
                metadata = json.loads(metadata_json) if digest == row["metadata_sha256"] else {}
            except json.JSONDecodeError:
                metadata = {}
            entries.append(
                {
                    "id": row["id"],
                    "source": row["source"],
                    "source_id": row["source_id"],
                    "added_at": row["added_at"],
                    "metadata": metadata,
                    "metadata_sha256": row["metadata_sha256"],
                }
            )
        return entries

    @application.post("/api/v1/library", tags=["library"], status_code=201)
    def add_library(body: LibraryEntry, request: Request) -> dict[str, object]:
        user_id = _require_user(request, app_settings)
        if body.source not in {"openalex", "arxiv"}:
            raise HTTPException(status_code=422, detail="unsupported_source")
        source_id = body.source_id.strip()
        if body.source == "openalex" and not re.fullmatch(r"W\d+", source_id):
            raise HTTPException(status_code=422, detail="invalid_source_id")
        if body.source == "arxiv":
            from app.sources.arxiv import normalize_arxiv_id

            try:
                source_id = normalize_arxiv_id(source_id)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="invalid_source_id") from exc
        metadata = body.metadata
        if len(json.dumps(metadata, ensure_ascii=False)) > 20_000:
            raise HTTPException(status_code=413, detail="metadata_too_large")
        if metadata:
            expected_url = (
                f"https://openalex.org/{source_id}"
                if body.source == "openalex"
                else f"https://arxiv.org/abs/{source_id}"
            )
            if metadata.get("id") != source_id or metadata.get("sourceUrl") != expected_url:
                raise HTTPException(status_code=422, detail="metadata_source_mismatch")
        metadata_json = json.dumps(
            metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        metadata_sha256 = hashlib.sha256(metadata_json.encode("utf-8")).hexdigest()
        from uuid import uuid4

        store = PaperStore(app_settings.resolved_data_storage_path)
        store.migrate()
        entry_id = str(uuid4())
        try:
            with store._connection() as db:
                db.execute(
                    "INSERT INTO user_library_entries "
                    "(id,user_id,source,source_id,added_at,metadata_json,metadata_sha256) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (
                        entry_id,
                        user_id,
                        body.source,
                        source_id,
                        _now_iso(),
                        metadata_json,
                        metadata_sha256,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="paper_already_in_library") from exc
        return {
            "id": entry_id,
            "source": body.source,
            "source_id": source_id,
            "metadata": metadata,
            "metadata_sha256": metadata_sha256,
        }

    @application.delete("/api/v1/library/{entry_id}", tags=["library"], status_code=204)
    def remove_library(entry_id: str, request: Request) -> Response:
        user_id = _require_user(request, app_settings)
        store = PaperStore(app_settings.resolved_data_storage_path)
        store.migrate()
        try:
            with store._connection() as db:
                cursor = db.execute(
                    "DELETE FROM user_library_entries WHERE id=? AND user_id=?",
                    (entry_id, user_id),
                )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="paper_has_private_documents") from exc
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="library_entry_not_found")
        return Response(status_code=204)

    @application.get("/api/v1/documents", tags=["documents"])
    def list_private_documents(
        request: Request,
        library_entry_id: str | None = Query(default=None, max_length=64),
    ) -> list[dict[str, object]]:
        owner = _require_user(request, app_settings)
        store = PaperStore(app_settings.resolved_data_storage_path)
        store.migrate()
        return PrivateDocumentService(store).list_documents(owner, library_entry_id)

    @application.post("/api/v1/documents", tags=["documents"], status_code=202)
    async def upload_private_document(
        request: Request,
        file: Annotated[UploadFile, File()],
        rights_attested: Annotated[bool, Form()],
        library_entry_id: Annotated[str | None, Form(min_length=1, max_length=64)] = None,
        title: Annotated[str | None, Form(min_length=1, max_length=500)] = None,
    ) -> dict[str, object]:
        owner = _require_user(request, app_settings)
        if not rights_attested:
            raise HTTPException(status_code=422, detail="private_rights_attestation_required")
        if (library_entry_id is None) == (title is None):
            raise HTTPException(status_code=422, detail="exactly_one_document_source_required")
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=422, detail="invalid_pdf_filename")
        if file.content_type not in {"application/pdf", "application/octet-stream"}:
            raise HTTPException(status_code=415, detail="unsupported_document_media_type")
        store = PaperStore(app_settings.resolved_data_storage_path)
        store.migrate()
        service = PrivateDocumentService(store)
        existing = service.list_documents(owner)
        current_usage = sum(int(item["size_bytes"]) for item in existing)
        if len(existing) >= MAX_USER_DOCUMENTS:
            raise HTTPException(status_code=413, detail="user_document_count_limit")
        if current_usage >= MAX_USER_DOCUMENT_BYTES:
            raise HTTPException(status_code=413, detail="user_document_storage_limit")
        chunks: list[bytes] = []
        size = 0
        while data := await file.read(1 << 20):
            size += len(data)
            if size > 40 * 1024 * 1024 or current_usage + size > MAX_USER_DOCUMENT_BYTES:
                raise HTTPException(status_code=413, detail="document_size_limit")
            chunks.append(data)
        pdf_bytes = b"".join(chunks)
        try:
            document = service.store_upload(
                user_id=owner,
                library_entry_id=library_entry_id,
                title=title,
                filename=file.filename,
                pdf_bytes=pdf_bytes,
                rights_attested=True,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OverflowError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        schedule_private_document(str(document["id"]), owner)
        return document

    @application.get("/api/v1/documents/{document_id}", tags=["documents"])
    def get_private_document(document_id: str, request: Request) -> dict[str, object]:
        owner = _require_user(request, app_settings)
        document = PrivateDocumentService(
            PaperStore(app_settings.resolved_data_storage_path)
        ).get_document(owner, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="document_not_found")
        return document

    @application.post("/api/v1/documents/{document_id}/retry", tags=["documents"], status_code=202)
    def retry_private_document(document_id: str, request: Request) -> dict[str, object]:
        owner = _require_user(request, app_settings)
        service = PrivateDocumentService(PaperStore(app_settings.resolved_data_storage_path))
        service.store.migrate()
        if not service.retry_document(owner, document_id):
            if service.get_document(owner, document_id) is None:
                raise HTTPException(status_code=404, detail="document_not_found")
            raise HTTPException(status_code=409, detail="document_not_retryable")
        schedule_private_document(document_id, owner)
        return {"id": document_id, "state": "queued"}

    @application.delete("/api/v1/documents/{document_id}", tags=["documents"], status_code=204)
    def delete_private_document(document_id: str, request: Request) -> Response:
        owner = _require_user(request, app_settings)
        service = PrivateDocumentService(PaperStore(app_settings.resolved_data_storage_path))
        service.store.migrate()
        try:
            service.delete_document(owner, document_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return Response(status_code=204)

    @application.get("/api/v1/conversations", tags=["conversations"])
    def list_conversations(request: Request) -> list[dict[str, str]]:
        owner = _require_user(request, app_settings)
        store = PaperStore(app_settings.resolved_data_storage_path)
        store.migrate()
        with store._connection() as db:
            rows = db.execute(
                "SELECT id,title,created_at,updated_at FROM conversations "
                "WHERE user_id=? ORDER BY updated_at DESC LIMIT 100",
                (owner,),
            ).fetchall()
        return [dict(row) for row in rows]

    @application.post("/api/v1/conversations", tags=["conversations"], status_code=201)
    def create_conversation(body: ConversationInput, request: Request) -> dict[str, str]:
        owner = _require_user(request, app_settings)
        from uuid import uuid4

        conversation_id = str(uuid4())
        now = _now_iso()
        store = PaperStore(app_settings.resolved_data_storage_path)
        store.migrate()
        with store._connection() as db:
            db.execute(
                "INSERT INTO conversations "
                "(id,user_id,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                (conversation_id, owner, body.title.strip(), now, now),
            )
        return {"id": conversation_id, "title": body.title.strip(), "created_at": now}

    @application.patch("/api/v1/conversations/{conversation_id}", tags=["conversations"])
    def rename_conversation(
        conversation_id: str, body: ConversationInput, request: Request
    ) -> dict[str, str]:
        owner = _require_user(request, app_settings)
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="invalid_conversation_title")
        now = _now_iso()
        store = PaperStore(app_settings.resolved_data_storage_path)
        store.migrate()
        with store._connection() as db:
            cursor = db.execute(
                "UPDATE conversations SET title=?,updated_at=? WHERE id=? AND user_id=?",
                (title, now, conversation_id, owner),
            )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        return {"id": conversation_id, "title": title, "updated_at": now}

    @application.get("/api/v1/conversations/{conversation_id}/messages", tags=["conversations"])
    def get_conversation_messages(conversation_id: str, request: Request) -> list[dict[str, str]]:
        owner = _require_user(request, app_settings)
        store = PaperStore(app_settings.resolved_data_storage_path)
        store.migrate()
        with store._connection() as db:
            rows = db.execute(
                "SELECT m.id,m.role,m.content,m.created_at FROM conversation_messages m "
                "JOIN conversations c ON c.id=m.conversation_id "
                "WHERE c.id=? AND c.user_id=? ORDER BY m.created_at, m.rowid LIMIT 500",
                (conversation_id, owner),
            ).fetchall()
            exists = db.execute(
                "SELECT 1 FROM conversations WHERE id=? AND user_id=?", (conversation_id, owner)
            ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        return [dict(row) for row in rows]

    @application.delete(
        "/api/v1/conversations/{conversation_id}/messages",
        tags=["conversations"],
        status_code=204,
    )
    def clear_conversation_messages(conversation_id: str, request: Request) -> Response:
        owner = _require_user(request, app_settings)
        store = PaperStore(app_settings.resolved_data_storage_path)
        store.migrate()
        with store._connection() as db:
            exists = db.execute(
                "SELECT 1 FROM conversations WHERE id=? AND user_id=?", (conversation_id, owner)
            ).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail="conversation_not_found")
            db.execute(
                "DELETE FROM conversation_messages WHERE conversation_id=?", (conversation_id,)
            )
            db.execute(
                "INSERT INTO conversation_state(conversation_id,revision,state_json) "
                "VALUES(?,1,'{}') ON CONFLICT(conversation_id) DO UPDATE SET "
                "revision=revision+1,state_json='{}'",
                (conversation_id,),
            )
            db.execute(
                "UPDATE conversations SET updated_at=? WHERE id=? AND user_id=?",
                (_now_iso(), conversation_id, owner),
            )
        return Response(status_code=204)

    @application.delete(
        "/api/v1/conversations/{conversation_id}", tags=["conversations"], status_code=204
    )
    def delete_conversation(conversation_id: str, request: Request) -> Response:
        owner = _require_user(request, app_settings)
        store = PaperStore(app_settings.resolved_data_storage_path)
        store.migrate()
        with store._connection() as db:
            cursor = db.execute(
                "DELETE FROM conversations WHERE id=? AND user_id=?", (conversation_id, owner)
            )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        return Response(status_code=204)

    @application.get("/api/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @application.post(
        "/api/v1/agent/ask",
        response_model=AgentResponse,
        responses={429: {"description": "Per-user daily agent token budget exhausted."}},
        tags=["agent"],
    )
    async def ask_agent(body: AgentQuestion, request: Request, response: Response) -> AgentResponse:
        request_user = _require_user(request, app_settings)
        run_id = str(body.run_id or uuid4())
        store = PaperStore(app_settings.resolved_data_storage_path)
        conversation_owner = None
        history = body.history
        context_questions = None
        conversation_memory = {}
        memory_revision = 0
        if body.conversation_id is not None:
            conversation_owner = _require_user(request, app_settings)
            with store._connection() as db:
                conversation = db.execute(
                    "SELECT id FROM conversations WHERE id=? AND user_id=?",
                    (str(body.conversation_id), conversation_owner),
                ).fetchone()
                if conversation is None:
                    raise HTTPException(status_code=404, detail="conversation_not_found")
                state_row = db.execute(
                    "SELECT revision,state_json FROM conversation_state WHERE conversation_id=?",
                    (str(body.conversation_id),),
                ).fetchone()
                if state_row:
                    memory_revision = state_row["revision"]
                    conversation_memory = json.loads(state_row["state_json"])
                turns = db.execute(
                    "SELECT role,content FROM conversation_messages WHERE conversation_id=? "
                    "ORDER BY created_at DESC, rowid DESC LIMIT 24",
                    (str(body.conversation_id),),
                ).fetchall()
                question_rows = db.execute(
                    "SELECT content FROM conversation_messages WHERE conversation_id=? "
                    "AND role='user' ORDER BY created_at DESC,rowid DESC LIMIT 40",
                    (str(body.conversation_id),),
                ).fetchall()
                context_questions = [row["content"] for row in reversed(question_rows)]
            from app.agent.contracts import AgentTurn

            history = [
                AgentTurn(role=row["role"], content=row["content"]) for row in reversed(turns)
            ]
            if len(history) % 2:
                history = history[1:]
            while len(history) > 2 and sum(len(turn.content) for turn in history) > 16000:
                history = history[2:]
        with store._connection() as db:
            saved_papers = db.execute(
                "SELECT source,source_id FROM user_library_entries "
                "WHERE user_id=? ORDER BY added_at DESC LIMIT 50",
                (request_user,),
            ).fetchall()
        user_library = [(row["source"], row["source_id"]) for row in saved_papers]
        harness_metadata = _agent_run_harness_metadata(
            body.question,
            app_settings,
            prior_user_questions=[turn.content for turn in history if turn.role == "user"],
            library_ids=user_library,
        )
        try:
            created = store.create_agent_run(
                run_id,
                body.question,
                [(turn.role, turn.content) for turn in history],
                user_id=request_user,
                worker_id=application.state.agent_worker_id,
                token_budget=app_settings.agent_max_total_tokens,
                harness_metadata=harness_metadata,
                daily_token_budget=app_settings.agent_daily_user_token_budget,
            )
        except DailyAgentTokenBudgetExceeded:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "daily_agent_token_budget_exceeded",
                    "daily_token_budget": app_settings.agent_daily_user_token_budget,
                },
            ) from None
        if not created:
            raise HTTPException(
                status_code=409,
                detail={"code": "duplicate_run_id", "run_id": run_id},
            )
        cancellation = threading.Event()
        application.state.active_agent_runs[run_id] = cancellation
        store.set_agent_run_phase(run_id, "executing")

        def persist_agent_progress(
            token_reserved: int, token_actual: int, trace: list[AgentTraceEvent]
        ) -> None:
            store.update_agent_run_progress(
                run_id,
                application.state.agent_worker_id,
                token_reserved=token_reserved,
                token_actual=token_actual,
                trace=trace,
            )

        execution = asyncio.create_task(
            run_in_threadpool(
                AgentService(
                    app_settings,
                    store,
                ).ask,
                body.question,
                history=history,
                prior_user_questions=context_questions,
                memory=conversation_memory,
                user_library=user_library,
                user_id=request_user,
                cancellation_requested=lambda: (
                    cancellation.is_set() or store.is_agent_run_cancel_requested(run_id)
                ),
                progress_callback=persist_agent_progress,
            )
        )
        disconnect_cancel_requested = False
        last_lease_renewal = time.monotonic()
        while not execution.done():
            if time.monotonic() - last_lease_renewal >= 5:
                store.renew_agent_run_lease(run_id, application.state.agent_worker_id)
                last_lease_renewal = time.monotonic()
            if await request.is_disconnected() and not disconnect_cancel_requested:
                store.request_agent_run_cancel(run_id, request_user)
                cancellation.set()
                disconnect_cancel_requested = True
            await asyncio.sleep(0.05)
        try:
            result = await execution
        except Exception as exc:
            cancellation.set()
            logger.error(
                "Agent run %s interrupted (%s.%s); traceback=%s",
                run_id,
                type(exc).__module__,
                type(exc).__name__,
                [
                    {"file": frame.filename, "line": frame.lineno, "function": frame.name}
                    for frame in traceback.extract_tb(exc.__traceback__)
                ],
            )
            store.resolve_agent_run_stop(run_id)
            raise HTTPException(
                status_code=503,
                detail={"code": "agent_run_interrupted", "run_id": run_id},
            ) from None
        finally:
            application.state.active_agent_runs.pop(run_id, None)
        result = result.model_copy(update={"run_id": run_id})
        store.finish_agent_run(
            run_id,
            result,
            model_id=app_settings.llm_model,
            pdf_parser_adapter=MINERU_ADAPTER_VERSION,
            pdf_chunker_version=PDF_CHUNKER_VERSION,
        )
        if conversation_owner and result.status in {"completed", "insufficient_evidence"}:
            now = _now_iso()
            with store._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    "SELECT COALESCE(s.revision,0) revision FROM conversations c "
                    "LEFT JOIN conversation_state s ON s.conversation_id=c.id "
                    "WHERE c.id=? AND c.user_id=?",
                    (str(body.conversation_id), conversation_owner),
                ).fetchone()
                if current is None or current["revision"] != memory_revision:
                    return result.model_copy(
                        update={"warnings": [*result.warnings, "conversation_changed_not_saved"]}
                    )
                if result.context_state:
                    db.execute(
                        "INSERT INTO conversation_state(conversation_id,revision,state_json) "
                        "VALUES(?,1,?) ON CONFLICT(conversation_id) DO UPDATE SET "
                        "revision=revision+1,state_json=excluded.state_json WHERE revision=?",
                        (
                            str(body.conversation_id),
                            json.dumps(result.context_state, ensure_ascii=False),
                            memory_revision,
                        ),
                    )
                db.executemany(
                    "INSERT INTO conversation_messages(id,conversation_id,role,content,created_at) "
                    "VALUES(?,?,?,?,?)",
                    [
                        (str(uuid4()), str(body.conversation_id), "user", body.question, now),
                        (str(uuid4()), str(body.conversation_id), "assistant", result.answer, now),
                    ],
                )
                title = " ".join(body.question.split())[:60]
                db.execute(
                    "UPDATE conversations SET title=CASE "
                    "WHEN title='新对话' THEN ? ELSE title END, "
                    "updated_at=? WHERE id=? AND user_id=?",
                    (title, now, str(body.conversation_id), conversation_owner),
                )
        if result.status in {"model_disabled", "model_unavailable", "usage_unavailable"}:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return result

    @application.get(
        "/api/v1/agent/runs/{run_id}",
        response_model=AgentTaskStatus,
        tags=["agent"],
    )
    def get_agent_run(run_id: UUID, request: Request) -> AgentTaskStatus:
        store = PaperStore(app_settings.resolved_data_storage_path)
        owner = _require_user(request, app_settings)
        run = store.get_agent_run(str(run_id), owner)
        if run is None:
            raise HTTPException(status_code=404, detail="agent run not found")
        if run["status"] == "running" and store.is_agent_run_lease_expired(str(run_id)):
            store.resolve_agent_run_stop(str(run_id), expired_only=True)
            run = store.get_agent_run(str(run_id), owner)
            assert run is not None
        return AgentTaskStatus.model_validate(
            {field: run[field] for field in AgentTaskStatus.model_fields if field in run}
        )

    @application.post("/api/v1/agent/runs/{run_id}/cancel", tags=["agent"])
    def cancel_agent_run(run_id: UUID, request: Request) -> dict[str, object]:
        identifier = str(run_id)
        owner = _require_user(request, app_settings)
        store = PaperStore(app_settings.resolved_data_storage_path)
        run = store.get_agent_run(identifier, owner)
        if run is None:
            raise HTTPException(status_code=404, detail="agent run not found")
        cancellation = application.state.active_agent_runs.get(identifier)
        if run["status"] == "running":
            requested = store.request_agent_run_cancel(identifier, owner)
            if cancellation is not None and requested:
                cancellation.set()
            elif cancellation is None and store.is_agent_run_lease_expired(identifier):
                store.resolve_agent_run_stop(identifier, expired_only=True)
            run = store.get_agent_run(identifier, owner) or run
        else:
            return {
                "run_id": identifier,
                "status": run["status"],
                "cancellation_requested": bool(run.get("cancel_requested_at")),
            }
        return {
            "run_id": identifier,
            "status": run["status"],
            "cancellation_requested": bool(run.get("cancel_requested_at")),
        }

    @application.get("/api/health/ready", tags=["health"])
    def ready(response: Response) -> dict[str, object]:
        try:
            PaperStore(app_settings.resolved_data_storage_path).migrate()
        except (sqlite3.Error, StoreError):
            response.status_code = 503
            return {
                "status": "not_ready",
                "checks": {
                    "application": "available",
                    "database": "unavailable",
                    "openalex": "not_connected",
                    "llm": "disabled" if app_settings.llm_provider == "disabled" else "configured",
                    "embedding": (
                        "disabled"
                        if app_settings.embedding_provider == "disabled"
                        else "configured"
                    ),
                },
            }
        return {
            "status": "ready",
            "checks": {
                "application": "available",
                "database": "sqlite_available",
                "openalex": "not_connected",
                "llm": "disabled" if app_settings.llm_provider == "disabled" else "configured",
                "embedding": (
                    "disabled" if app_settings.embedding_provider == "disabled" else "configured"
                ),
            },
        }

    @application.get("/api/v1/papers/search", tags=["papers"])
    def search_papers(
        q: str = Query(min_length=1, max_length=256),
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=10, ge=1, le=100),
    ) -> dict[str, object]:
        if not q.strip():
            raise HTTPException(status_code=422, detail="q must contain non-whitespace characters")
        api_key = app_settings.openalex_api_key
        secret = api_key.get_secret_value() if api_key else None
        try:
            with OpenAlexClient(api_key=secret) as client:
                result = client.search_works(q, page=page, per_page=per_page)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except OpenAlexError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None
        return result.model_dump(mode="json")

    @application.get("/api/v1/openalex/works/{work_id}", tags=["openalex"])
    def get_openalex_work(work_id: str = PathParameter(pattern=r"^W\d+$")) -> dict[str, object]:
        try:
            with _openalex_client(app_settings) as client:
                work = client.get_work(work_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except OpenAlexError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None
        return work.model_dump(mode="json")

    @application.get("/api/v1/openalex/authors/search", tags=["openalex"])
    def search_openalex_authors(
        q: str = Query(min_length=1, max_length=256),
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=10, ge=1, le=25),
    ) -> dict[str, object]:
        try:
            with _openalex_client(app_settings) as client:
                result = client.search_authors(q, page=page, per_page=per_page)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except OpenAlexError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None
        return result.model_dump(mode="json")

    @application.get("/api/v1/openalex/authors/{author_id}", tags=["openalex"])
    def get_openalex_author(author_id: str = PathParameter(pattern=r"^A\d+$")) -> dict[str, object]:
        try:
            with _openalex_client(app_settings) as client:
                return client.get_author(author_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except OpenAlexError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None

    @application.get("/api/v1/openalex/authors/{author_id}/works", tags=["openalex"])
    def list_openalex_author_works(
        author_id: str = PathParameter(pattern=r"^A\d+$"),
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=10, ge=1, le=25),
    ) -> dict[str, object]:
        try:
            with _openalex_client(app_settings) as client:
                result = client.list_author_works(author_id, page=page, per_page=per_page)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except OpenAlexError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None
        return result.model_dump(mode="json")

    @application.get("/api/v1/arxiv/search", tags=["arxiv"])
    def search_arxiv(
        q: str = Query(min_length=1, max_length=256),
        start: int = Query(default=0, ge=0, le=9_975),
        max_results: int = Query(default=10, ge=1, le=25),
    ) -> dict[str, object]:
        try:
            with ArxivClient(timeout_seconds=15) as client:
                result = client.search(q, start=start, max_results=max_results)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except ArxivError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None
        return result.model_dump(mode="json")

    @application.get("/api/v1/arxiv/works/{arxiv_id}", tags=["arxiv"])
    def get_arxiv_work(
        arxiv_id: str = PathParameter(min_length=4, max_length=64),
    ) -> dict[str, object]:
        try:
            with ArxivClient(timeout_seconds=15) as client:
                work = client.get_work(arxiv_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except ArxivError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.safe_message},
            ) from None
        if work is None:
            raise HTTPException(status_code=404, detail="arXiv work not found")
        return work.model_dump(mode="json")

    @application.get("/api/v1/catalog/arxiv", tags=["catalog"])
    def list_catalog_arxiv(
        q: str | None = Query(default=None, max_length=128),
        limit: int = Query(default=20, ge=1, le=50),
        offset: int = Query(default=0, ge=0, le=10_000),
    ) -> dict[str, object]:
        try:
            return PaperStore(app_settings.resolved_data_storage_path).list_arxiv_papers(
                query=q, limit=limit, offset=offset
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "catalog_unavailable", "message": "本地论文目录暂时不可用。"},
            ) from None

    @application.get("/api/v1/catalog/arxiv/{arxiv_id}", tags=["catalog"])
    def get_catalog_arxiv(
        arxiv_id: str = PathParameter(min_length=4, max_length=64),
    ) -> dict[str, object]:
        try:
            work = PaperStore(app_settings.resolved_data_storage_path).get_arxiv_paper(arxiv_id)
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "catalog_unavailable", "message": "本地论文目录暂时不可用。"},
            ) from None
        if work is None:
            raise HTTPException(status_code=404, detail="arXiv paper not found")
        return work

    @application.get("/api/v1/evidence/search", tags=["evidence"])
    def search_licensed_evidence(
        q: str = Query(min_length=1, max_length=256),
        limit: int = Query(default=5, ge=1, le=8),
        source_type: str | None = Query(default=None, pattern=r"^(openalex|arxiv)$"),
        source_id: str | None = Query(default=None, min_length=4, max_length=64),
        retrieval_method: str = Query(default="bm25", pattern=r"^(bm25|dense|hybrid)$"),
    ) -> dict[str, object]:
        try:
            if (source_type is None) != (source_id is None):
                raise ValueError("source_type and source_id must be provided together")
            query_embedding = None
            embedding_model = None
            if retrieval_method != "bm25":
                if app_settings.embedding_provider == "disabled":
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": "embedding_disabled",
                            "message": "Embedding provider 未启用。",
                        },
                    )
                embeddings = OpenAIEmbeddingClient(app_settings)
                try:
                    batch = embeddings.embed([q])
                finally:
                    embeddings.close()
                query_embedding = batch.vectors[0]
                embedding_model = batch.model
            result = PaperStore(app_settings.resolved_data_storage_path).search_fulltext_evidence(
                q,
                limit=limit,
                source_type=source_type,
                source_id=source_id,
                retrieval_method=retrieval_method,
                query_embedding=query_embedding,
                embedding_model=embedding_model,
            )
            if retrieval_method != "bm25":
                result["embedding_usage"] = {
                    "model": embedding_model,
                    "input_tokens": batch.input_tokens,
                    "estimated_cost_usd": _embedding_cost_estimate(
                        app_settings.embedding_price_per_million_usd, batch.input_tokens
                    ),
                }
            return result
        except EmbeddingError as error:
            raise HTTPException(
                status_code=502,
                detail={"code": error.code, "message": "Embedding 服务暂不可用。"},
            ) from None
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "evidence_unavailable", "message": "许可全文检索暂不可用。"},
            ) from None

    @application.get("/api/v1/catalog/papers", tags=["catalog"])
    def list_catalog_papers(
        q: str | None = Query(default=None, max_length=128),
        limit: int = Query(default=20, ge=1, le=50),
        offset: int = Query(default=0, ge=0, le=10_000),
    ) -> dict[str, object]:
        try:
            return PaperStore(app_settings.resolved_data_storage_path).list_papers(
                query=q, limit=limit, offset=offset
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "catalog_unavailable", "message": "本地论文目录暂时不可用。"},
            ) from None

    @application.get("/api/v1/catalog/papers/{openalex_id}", tags=["catalog"])
    def get_catalog_paper(
        openalex_id: str = PathParameter(pattern=r"^W\d+$"),
        snapshot_id: str | None = Query(default=None, max_length=36),
    ) -> dict[str, object]:
        try:
            paper = PaperStore(app_settings.resolved_data_storage_path).get_paper(
                openalex_id, snapshot_id=snapshot_id
            )
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "catalog_unavailable", "message": "本地论文目录暂时不可用。"},
            ) from None
        if paper is None:
            raise HTTPException(status_code=404, detail="paper not found in requested snapshot")
        return paper

    @application.get("/api/v1/catalog/snapshots", tags=["catalog"])
    def list_catalog_snapshots(
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[dict[str, object]]:
        try:
            return PaperStore(app_settings.resolved_data_storage_path).list_snapshots(limit=limit)
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "catalog_unavailable", "message": "本地快照记录暂时不可用。"},
            ) from None

    @application.get("/api/v1/catalog/snapshots/{snapshot_id}", tags=["catalog"])
    def get_catalog_snapshot(
        snapshot_id: str = PathParameter(min_length=36, max_length=36),
    ) -> dict[str, object]:
        try:
            snapshot = PaperStore(app_settings.resolved_data_storage_path).get_snapshot(snapshot_id)
        except (sqlite3.Error, StoreError):
            raise HTTPException(
                status_code=503,
                detail={"code": "catalog_unavailable", "message": "本地快照记录暂时不可用。"},
            ) from None
        if snapshot is None:
            raise HTTPException(status_code=404, detail="snapshot not found")
        return snapshot

    return application


def _embedding_cost_estimate(
    price_per_million_usd: float | None, input_tokens: int
) -> float | None:
    if price_per_million_usd is None:
        return None
    return round(price_per_million_usd * input_tokens / 1_000_000, 10)


def _openalex_client(settings: Settings) -> OpenAlexClient:
    secret = settings.openalex_api_key.get_secret_value() if settings.openalex_api_key else None
    return OpenAlexClient(api_key=secret)


app = create_app()
