from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    Field,
    JsonValue,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from app.common.contracts import Contract

Slot = Literal["cpu", "motherboard", "gpu", "memory", "storage", "psu", "case", "cooler"]
RuleStatus = Literal["pass", "fail", "unknown", "warning"]
RequirementName = Literal["wifi", "usb_ports", "pcie_slots"]


class CompatibilityItem(Contract):
    slot: Slot
    sku_id: UUID
    quantity: Annotated[StrictInt, Field(ge=1, le=4)] = 1


class CompatibilityRequest(Contract):
    items: Annotated[list[CompatibilityItem], Field(min_length=1, max_length=8)]
    bios_version: Annotated[StrictStr, Field(min_length=1, max_length=50)] | None = None
    hard_requirements: dict[RequirementName, StrictInt | StrictBool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def slots_are_unique(self):
        slots = [item.slot for item in self.items]
        if len(slots) != len(set(slots)):
            raise ValueError("Each compatibility slot may appear only once")
        if any(item.quantity != 1 for item in self.items if item.slot != "memory"):
            raise ValueError("CPU and motherboard quantities must be one")
        return self


class RuleResult(Contract):
    rule_id: Literal[
        "C001",
        "C002",
        "C003",
        "C004",
        "C005",
        "C006",
        "C007",
        "C008",
        "C009",
        "C010",
        "C011",
        "C012",
    ]
    rule_version: Literal["compat-v1"] = "compat-v1"
    status: RuleStatus
    blocking: StrictBool = True
    message: str
    fact_ids: list[UUID]
    details: dict[str, JsonValue]


class CompatibilityReport(Contract):
    rule_version: Literal["compat-v1"] = "compat-v1"
    status: Literal["validated", "incompatible", "needs_verification"]
    results: list[RuleResult]
    unexecuted_rule_ids: list[str] = []
    data_version: UUID
    generated_at: AwareDatetime
