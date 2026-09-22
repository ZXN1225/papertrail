"""Persistence and validation boundary for bounded agent runs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, insert, select, update

from app.agent.contracts import (
    AgentAnswer,
    AgentCandidate,
    AgentCitation,
    AgentEvent,
    AgentRun,
    AgentSession,
)
from app.agent.models import agent_events, agent_runs, agent_sessions
from app.profiles.service import DomainError, invisible


class AgentRunService:
    """Stores public-safe events; model output never bypasses deterministic validation."""

    def __init__(self, engine, profiles, harness):
        self.engine, self.profiles, self.harness = engine, profiles, harness

    @staticmethod
    def _hash(body):
        value = body.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _session(conn, session, agent_session_id, lock=False):
        query = select(agent_sessions).where(
            agent_sessions.c.id == agent_session_id, agent_sessions.c.session_id == session["id"]
        )
        if lock:
            query = query.with_for_update()
        row = conn.execute(query).mappings().first()
        if row is None:
            raise invisible()
        return row

    @staticmethod
    def _run(conn, session, run_id, lock=False):
        query = select(agent_runs).where(
            agent_runs.c.id == run_id, agent_runs.c.session_id == session["id"]
        )
        if lock:
            query = query.with_for_update()
        row = conn.execute(query).mappings().first()
        if row is None:
            raise invisible()
        return row

    @staticmethod
    def _event(conn, run_id, revision, type, data):
        event_id = conn.scalar(
            select(agent_events.c.event_id)
            .where(agent_events.c.run_id == run_id)
            .order_by(agent_events.c.event_id.desc())
            .limit(1)
        )
        conn.execute(
            insert(agent_events).values(
                run_id=run_id,
                event_id=(event_id or 0) + 1,
                revision=revision,
                type=type,
                data=data,
                created_at=datetime.now(UTC),
            )
        )

    def create_session(self, cookie):
        with self.engine.begin() as conn:
            session = self.profiles.authenticate(conn, cookie, lock=True)
            now, agent_session_id = datetime.now(UTC), uuid4()
            conn.execute(
                insert(agent_sessions).values(
                    id=agent_session_id, session_id=session["id"], revision=1, created_at=now
                )
            )
            return AgentSession(id=agent_session_id, revision=1, created_at=now)

    def create_run(self, cookie, agent_session_id, body):
        body_hash = self._hash(body)
        with self.engine.begin() as conn:
            session = self.profiles.authenticate(conn, cookie, lock=True)
            agent_session = self._session(conn, session, agent_session_id, lock=True)
            existing = (
                conn.execute(
                    select(agent_runs).where(
                        agent_runs.c.agent_session_id == agent_session_id,
                        agent_runs.c.client_request_id == body.client_request_id,
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                if existing["body_hash"] != body_hash:
                    raise DomainError(409, "IDEMPOTENCY_CONFLICT", "同一请求标识对应的内容不同。")
                return self._serialize_run(existing)
            if agent_session["revision"] != body.expected_revision:
                raise DomainError(
                    409,
                    "REVISION_CONFLICT",
                    "对话已在另一页面更新，请先读取最新版本。",
                    {"current_revision": str(agent_session["revision"])},
                )
            # Reading the claimed profile revision validates ownership before a run is accepted.
            self.profiles.owned(conn, session, body.profile_id)
            self.profiles.snapshot(conn, body.profile_id, body.profile_revision)
            run_id, now, revision = uuid4(), datetime.now(UTC), agent_session["revision"] + 1
            conn.execute(
                update(agent_sessions)
                .where(
                    agent_sessions.c.id == agent_session_id,
                    agent_sessions.c.revision == body.expected_revision,
                )
                .values(revision=revision)
            )
            conn.execute(
                insert(agent_runs).values(
                    id=run_id,
                    agent_session_id=agent_session_id,
                    session_id=session["id"],
                    profile_id=body.profile_id,
                    profile_revision=body.profile_revision,
                    revision=revision,
                    message=body.message,
                    client_request_id=body.client_request_id,
                    body_hash=body_hash,
                    status="queued",
                    created_at=now,
                )
            )
            self._event(conn, run_id, revision, "run.started", {"status": "queued"})
        # The current provider is bounded and synchronous. A future worker can call execute_run
        # using this durable queued row without changing the HTTP/SSE contract.
        self.execute_run(cookie, run_id)
        return self.read_run(cookie, run_id)

    def execute_run(self, cookie, run_id):
        with self.engine.begin() as conn:
            session = self.profiles.authenticate(conn, cookie, lock=True)
            run = self._run(conn, session, run_id, lock=True)
            if run["cancel_requested"] or run["status"] == "cancelled":
                return
            conn.execute(
                update(agent_runs).where(agent_runs.c.id == run_id).values(status="running")
            )
        request = type(
            "RunRequest",
            (),
            {
                "profile_id": run["profile_id"],
                "profile_revision": run["profile_revision"],
                "message": run["message"],
            },
        )()
        result = self.harness.run(cookie, request)
        answer = self._answer(result)
        with self.engine.begin() as conn:
            session = self.profiles.authenticate(conn, cookie, lock=True)
            current = self._run(conn, session, run_id, lock=True)
            if current["cancel_requested"] or current["status"] == "cancelled":
                return
            for observation in result["observations"]:
                self._event(
                    conn,
                    run_id,
                    current["revision"],
                    "tool.started",
                    {"tool": observation.name},
                )
                self._event(
                    conn,
                    run_id,
                    current["revision"],
                    "tool.completed",
                    {
                        "tool": observation.name,
                        "status": observation.status,
                        "missing_fields": observation.missing_fields,
                    },
                )
            if result["status"] == "clarifying":
                self._event(
                    conn,
                    run_id,
                    current["revision"],
                    "question.required",
                    {"question": result["pending_question"]},
                )
            self._event(
                conn,
                run_id,
                current["revision"],
                "result.validated",
                {
                    "candidate_count": len(answer.candidates),
                    "missing_fields": answer.missing_fields,
                },
            )
            completed = datetime.now(UTC)
            conn.execute(
                update(agent_runs)
                .where(agent_runs.c.id == run_id)
                .values(
                    status=result["status"],
                    answer=answer.model_dump(mode="json"),
                    pending_question=result["pending_question"],
                    reason=result["reason"],
                    completed_at=completed,
                )
            )
            event_type = (
                "run.completed"
                if result["status"] in {"completed", "partial", "clarifying", "provider_disabled"}
                else "run.failed"
            )
            self._event(conn, run_id, current["revision"], event_type, {"status": result["status"]})

    @staticmethod
    def _answer(result):
        candidates, citations, missing, versions = [], [], set(), set()
        for observation in result["observations"]:
            missing.update(observation.missing_fields)
            if observation.data_version:
                versions.add(observation.data_version)
            if observation.name in {"rank_laptops", "solve_pc_builds"}:
                for item in observation.data.get("candidates", []):
                    if isinstance(item, dict):
                        candidates.append(AgentCandidate(source_tool=observation.name, data=item))
                missing.update(observation.data.get("missing_data", []))
            if observation.name == "retrieve_knowledge":
                for item in observation.data.get("citations", []):
                    try:
                        citations.append(AgentCitation.model_validate(item))
                    except (TypeError, ValueError):
                        missing.add("invalid_knowledge_citation")
        warnings = []
        if result["reason"]:
            warnings.append(result["reason"])
        if result["status"] == "provider_disabled":
            warnings.append("模型服务尚未配置，未生成推荐结论。")
        summary = result.get("final_text") or (
            "已验证工具结果并生成结构化回答。" if candidates else "当前没有可展示的已验证候选。"
        )
        return AgentAnswer(
            summary=summary,
            profile_revision=result["profile_revision"],
            candidates=candidates[:3],
            tradeoffs=[],
            warnings=warnings,
            citations=citations,
            missing_fields=sorted(missing),
            data_version=next(iter(versions)) if len(versions) == 1 else None,
        )

    def read_run(self, cookie, run_id):
        with self.engine.begin() as conn:
            session = self.profiles.authenticate(conn, cookie)
            return self._serialize_run(self._run(conn, session, run_id))

    @staticmethod
    def _serialize_run(row):
        return AgentRun(
            id=row["id"],
            agent_session_id=row["agent_session_id"],
            profile_id=row["profile_id"],
            profile_revision=row["profile_revision"],
            revision=row["revision"],
            status=row["status"],
            answer=AgentAnswer.model_validate(row["answer"]) if row["answer"] else None,
            pending_question=row["pending_question"],
            reason=row["reason"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )

    def events(self, cookie, run_id, after_event_id=0):
        with self.engine.begin() as conn:
            session = self.profiles.authenticate(conn, cookie)
            self._run(conn, session, run_id)
            rows = (
                conn.execute(
                    select(agent_events)
                    .where(
                        agent_events.c.run_id == run_id, agent_events.c.event_id > after_event_id
                    )
                    .order_by(agent_events.c.event_id)
                )
                .mappings()
                .all()
            )
            return [
                AgentEvent(
                    event_id=row["event_id"],
                    run_id=run_id,
                    revision=row["revision"],
                    type=row["type"],
                    data=row["data"],
                )
                for row in rows
            ]

    def cancel(self, cookie, run_id):
        with self.engine.begin() as conn:
            session = self.profiles.authenticate(conn, cookie, lock=True)
            run = self._run(conn, session, run_id, lock=True)
            if run["status"] in {
                "completed",
                "clarifying",
                "partial",
                "failed",
                "timed_out",
                "provider_disabled",
                "cancelled",
            }:
                raise DomainError(409, "RUN_NOT_CANCELLABLE", "该运行已经结束，不能取消。")
            conn.execute(
                update(agent_runs)
                .where(agent_runs.c.id == run_id)
                .values(status="cancelled", cancel_requested=True, completed_at=datetime.now(UTC))
            )
            self._event(conn, run_id, run["revision"], "run.cancelled", {"status": "cancelled"})
        return self.read_run(cookie, run_id)

    def delete_session(self, cookie, agent_session_id):
        with self.engine.begin() as conn:
            session = self.profiles.authenticate(conn, cookie, lock=True)
            self._session(conn, session, agent_session_id, lock=True)
            conn.execute(delete(agent_sessions).where(agent_sessions.c.id == agent_session_id))
