import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, JsonValue, StrictBool, StrictInt, StrictStr, model_validator

from app.catalog.contracts import Digest, Nonempty
from app.common.contracts import Contract

Kind = Literal[
    "brands",
    "product_families",
    "product_skus",
    "product_aliases",
    "sources",
    "source_documents",
    "evidence",
    "evidence_skus",
    "attribute_definitions",
    "spec_facts",
    "merchants",
    "merchant_listings",
    "offer_snapshots",
]


class ImportRow(Contract):
    kind: Kind
    data: dict[str, JsonValue]


class ImportInput(Contract):
    format_version: Literal["manual-v1"] = "manual-v1"
    source_id: UUID
    external_batch_id: Annotated[Nonempty, Field(max_length=120)]
    synthetic: StrictBool = False
    rows: Annotated[list[ImportRow], Field(min_length=1, max_length=500)]
    configurations: dict[str, dict[str, StrictStr]] = Field(default_factory=dict, max_length=100)

    @model_validator(mode="after")
    def finite_json(self):
        json.dumps(self.model_dump(mode="json"), allow_nan=False)
        return self


class Issue(Contract):
    row: int | None = None
    code: str
    field: str = ""
    message: str
    blocking: bool = True


class RowPreview(Contract):
    row: int
    kind: Kind
    key: str
    action: Literal["add", "unchanged", "invalid"]


class Preview(Contract):
    content_hash: Digest
    base_version: UUID | None
    rows: list[RowPreview]
    issues: list[Issue]
    valid: bool
    publishable: bool
    normalized: list[ImportRow]
    conflict_groups: list[list[UUID]]


class ImportJob(Contract):
    id: UUID
    source_id: UUID
    external_batch_id: str
    synthetic: bool
    content_hash: Digest
    status: Literal["invalid", "staged", "approved", "rejected", "published"]
    checkpoint: Literal["validated", "reviewed", "published"]
    preview: Preview
    reviewer: str | None
    review_note: str | None
    version_id: UUID | None


class ReviewInput(Contract):
    content_hash: Digest
    base_version: UUID | None
    decision: Literal["approve", "reject"]
    note: Annotated[Nonempty, Field(max_length=1000)]
    selected_fact_ids: list[UUID] = Field(default_factory=list, max_length=5000)


class PublishInput(Contract):
    content_hash: Digest
    base_version: UUID | None


class Published(Contract):
    version_id: UUID
    synthetic: bool
    record_count: StrictInt


class DispatchResult(Contract):
    delivered: int
    failed: int
