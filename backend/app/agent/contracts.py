"""Public and internal contracts for the bounded agent harness."""

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
]
RunStatus = Literal[
    "completed",
    "clarifying",
    "partial",
    "failed",
    "timed_out",
    "provider_disabled",
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
