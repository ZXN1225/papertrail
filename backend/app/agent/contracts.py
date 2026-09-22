"""Public and internal contracts for the bounded agent harness."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, JsonValue, StrictInt, StrictStr

from app.common.contracts import Contract

ToolName = Literal[
    "search_catalog",
    "get_product_facts",
    "get_offers",
    "rank_laptops",
    "solve_pc_builds",
    "check_compatibility",
    "retrieve_knowledge",
]
RunStatus = Literal[
    "completed",
    "clarifying",
    "partial",
    "failed",
    "timed_out",
    "provider_disabled",
]
PersistentRunStatus = Literal[
    "queued",
    "running",
    "completed",
    "clarifying",
    "partial",
    "failed",
    "timed_out",
    "provider_disabled",
    "cancelled",
]


class AgentPreviewRequest(Contract):
    profile_id: UUID
    profile_revision: Annotated[StrictInt, Field(ge=1)]
    message: Annotated[StrictStr, Field(min_length=1, max_length=2000)]


class ToolCall(Contract):
    name: ToolName
    arguments: dict[str, JsonValue]


class AgentDecision(Contract):
    kind: Literal["tool", "final", "clarify"]
    tool_call: ToolCall | None = None
    question: Annotated[StrictStr, Field(min_length=1, max_length=500)] | None = None
    reason: Annotated[StrictStr, Field(min_length=1, max_length=200)] | None = None
    final_text: Annotated[StrictStr, Field(min_length=1, max_length=2000)] | None = None


class ToolObservation(Contract):
    name: ToolName
    status: Literal["ok", "partial", "error"]
    data: dict[str, JsonValue]
    evidence_ids: list[UUID]
    missing_fields: list[str]
    data_version: UUID | None = None
    error_code: str | None = None
    deduplicated: bool = False


class AgentPreviewResponse(Contract):
    status: RunStatus
    profile_id: UUID
    profile_revision: StrictInt
    tool_calls_used: StrictInt
    decision_rounds_used: StrictInt
    observations: list[ToolObservation]
    pending_question: str | None = None
    reason: str | None = None


class AgentSession(Contract):
    id: UUID
    revision: StrictInt
    created_at: datetime


class AgentRunCreate(Contract):
    profile_id: UUID
    profile_revision: Annotated[StrictInt, Field(ge=1)]
    message: Annotated[StrictStr, Field(min_length=1, max_length=2000)]
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    client_request_id: Annotated[StrictStr, Field(min_length=1, max_length=200)]


class AgentCandidate(Contract):
    source_tool: Literal["rank_laptops", "solve_pc_builds"]
    data: dict[str, JsonValue]


class AgentCitation(Contract):
    document_id: UUID
    chunk_id: UUID
    title: str
    canonical_url: str
    locator: str


class AgentAnswer(Contract):
    summary: str
    profile_revision: StrictInt
    candidates: list[AgentCandidate]
    tradeoffs: list[str]
    warnings: list[str]
    citations: list[AgentCitation]
    missing_fields: list[str]
    data_version: UUID | None


class AgentRun(Contract):
    id: UUID
    agent_session_id: UUID
    profile_id: UUID
    profile_revision: StrictInt
    revision: StrictInt
    status: PersistentRunStatus
    answer: AgentAnswer | None = None
    pending_question: str | None = None
    reason: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class AgentEvent(Contract):
    event_id: StrictInt
    run_id: UUID
    revision: StrictInt
    type: Literal[
        "run.started",
        "profile.updated",
        "question.required",
        "tool.started",
        "tool.completed",
        "result.validated",
        "run.completed",
        "run.failed",
        "run.cancelled",
    ]
    data: dict[str, JsonValue]
