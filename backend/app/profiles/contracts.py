from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, model_validator

from app.common.contracts import Contract

Mode = Literal["pc", "laptop", "component"]
Workload = Literal["office", "development", "gaming", "video", "rendering", "ai"]
Scope = Literal[
    "tower", "laptop", "component", "monitor", "peripherals", "os", "assembly", "shipping"
]
Category = Literal["cpu", "gpu", "motherboard", "memory", "ssd", "psu", "case", "cooler"]
Budget = Annotated[StrictInt, Field(gt=0, le=1_000_000_000)]
Brand = Annotated[StrictStr, Field(min_length=1, max_length=80, pattern=r"^\S(?:.*\S)?$")]


class PCConstraints(Contract):
    wifi_required: bool | None = Field(default=None, strict=True)


class LaptopConstraints(Contract):
    max_weight_g: Annotated[StrictInt, Field(ge=100, le=10000)] | None = None


class ProfileInput(Contract):
    mode: Mode
    budget_max_minor: Budget
    workloads: list[Workload] = Field(min_length=1, max_length=6)
    budget_scope: list[Scope] = Field(min_length=1, max_length=8)
    market: Literal["CN"] = "CN"
    currency: Literal["CNY"] = "CNY"
    excluded_brands: list[Brand] = Field(default_factory=list, max_length=20)
    pc_constraints: PCConstraints | None = None
    laptop_constraints: LaptopConstraints | None = None
    component_category: Category | None = None

    @model_validator(mode="after")
    def compatible_fields(self):
        for values in (self.workloads, self.budget_scope, self.excluded_brands):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate values are not allowed")
        required = {"pc": "tower", "laptop": "laptop", "component": "component"}[self.mode]
        other = {"tower", "laptop", "component"} - {required}
        if required not in self.budget_scope or other.intersection(self.budget_scope):
            raise ValueError("Budget scope must match the device mode")
        if self.mode != "pc" and self.pc_constraints is not None:
            raise ValueError("PC constraints only apply to PC mode")
        if self.mode != "laptop" and self.laptop_constraints is not None:
            raise ValueError("Laptop constraints only apply to laptop mode")
        if (self.mode == "component") != (self.component_category is not None):
            raise ValueError("Component category is required only in component mode")
        return self


class ProfilePatch(Contract):
    mode: Mode | None = None
    budget_max_minor: Budget | None = None
    workloads: list[Workload] | None = Field(default=None, min_length=1, max_length=6)
    budget_scope: list[Scope] | None = Field(default=None, min_length=1, max_length=8)
    excluded_brands: list[Brand] | None = Field(default=None, max_length=20)
    pc_constraints: PCConstraints | None = None
    laptop_constraints: LaptopConstraints | None = None
    component_category: Category | None = None


class PatchRequest(Contract):
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    patch: ProfilePatch


class FieldOrigin(Contract):
    origin: Literal["explicit", "default"]
    source: Literal["form", "system"]
    message_id: None = None
    confirmed_at: datetime | None = None


class ProfileSnapshot(Contract):
    id: UUID
    revision: int
    profile: ProfileInput
    origins: dict[str, FieldOrigin]
    created_at: datetime


class SessionResponse(Contract):
    expires_at: datetime
    csrf_token: str
    profile: ProfileSnapshot | None = None


class EmptyRequest(Contract):
    pass
