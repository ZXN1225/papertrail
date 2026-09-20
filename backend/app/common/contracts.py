from typing import Literal

from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LiveResponse(Contract):
    status: Literal["alive"] = "alive"


class DependencyChecks(Contract):
    database: Literal["ready", "unavailable", "not_configured", "migration_required"]
    redis: Literal["ready", "unavailable", "disabled"]


class ReadyResponse(Contract):
    status: Literal["ready", "not_ready"]
    checks: DependencyChecks


class ErrorDetail(Contract):
    code: str
    message: str
    details: dict[str, str]
    request_id: str


class ErrorResponse(Contract):
    error: ErrorDetail


class PlatformStatus(Contract):
    stage: Literal["foundation"] = "foundation"
    data_status: Literal["not_initialized"] = "not_initialized"
    recommendation_available: Literal[False] = False
    mode: Literal["deterministic"] = "deterministic"
    market: Literal["CN"] = "CN"
    currency: Literal["CNY"] = "CNY"
    data_version: None = None
