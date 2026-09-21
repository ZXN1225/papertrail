# ruff: noqa: E501
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr

from app.common.contracts import Contract


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
