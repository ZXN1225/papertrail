# ruff: noqa: E501
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from app.common.contracts import Contract
from app.compatibility.contracts import CompatibilityReport, RequirementName, Slot


class LaptopRankRequest(Contract):
    region: Annotated[StrictStr, Field(pattern=r"^[A-Z]{2}$")] = "CN"
    budget_minor: Annotated[StrictInt, Field(ge=1, le=1_000_000_000)]
    max_weight_g: Annotated[StrictInt, Field(ge=100, le=10000)] | None = None
    min_memory_gib: Annotated[StrictInt, Field(ge=1, le=1024)] | None = None
    excluded_brands: list[Annotated[StrictStr, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=20
    )


class LaptopCandidate(Contract):
    sku_id: UUID
    brand: str
    family: str
    manufacturer_part_number: str | None
    offer_id: UUID
    total_minor: StrictInt
    score_lower: float
    score_upper: float
    evidence_coverage: float
    missing_score_fields: list[
        Literal["battery_life_hours", "screen_quality", "application_performance"]
    ]
    data_version: UUID


class LaptopRankResponse(Contract):
    score_version: Literal["laptop-score-v1"] = "laptop-score-v1"
    status: Literal["ok", "no_candidates"]
    candidates: list[LaptopCandidate]
    blocking_constraints: list[str]
    missing_data: list[str]
    data_version: UUID | None


class PcFixedItem(Contract):
    """A confirmed exact SKU which the solver must retain."""

    slot: Slot
    sku_id: UUID


class PcSolveRequest(Contract):
    region: Annotated[StrictStr, Field(pattern=r"^[A-Z]{2}$")] = "CN"
    budget_minor: Annotated[StrictInt, Field(ge=1, le=1_000_000_000)]
    require_gpu: StrictBool = False
    bios_version: Annotated[StrictStr, Field(min_length=1, max_length=50)] | None = None
    excluded_brands: list[Annotated[StrictStr, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=20
    )
    locked_items: list[PcFixedItem] = Field(default_factory=list, max_length=8)
    existing_items: list[PcFixedItem] = Field(default_factory=list, max_length=8)
    hard_requirements: dict[RequirementName, StrictInt | StrictBool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fixed_slots_are_unique(self):
        slots = [item.slot for item in self.locked_items + self.existing_items]
        if len(slots) != len(set(slots)):
            raise ValueError("A PC slot may be locked or existing only once")
        return self


class PcCandidateItem(Contract):
    slot: Slot
    sku_id: UUID
    offer_id: UUID | None
    owned: bool
    total_minor: StrictInt | None


class PcCandidate(Contract):
    items: list[PcCandidateItem]
    total_minor: StrictInt
    score: float
    evidence_coverage: float
    compatibility: CompatibilityReport
    data_version: UUID


class PcSolveResponse(Contract):
    score_version: Literal["pc-score-v1"] = "pc-score-v1"
    status: Literal["ok", "no_candidates", "incomplete_search"]
    search_status: Literal["complete", "time_limit", "no_published_catalog"]
    candidates: list[PcCandidate]
    explored_count: StrictInt
    pruned_count: StrictInt
    candidate_pool_version: UUID | None
    optimality_proven: Literal[False] = False
    blocking_constraints: list[str]
    missing_data: list[str]
    relaxation_options: list[str]
