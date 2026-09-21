from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictStr

from app.catalog.contracts import Region
from app.common.contracts import Contract


class KnowledgeDocumentInput(Contract):
    source_document_id: UUID
    content: Annotated[StrictStr, Field(min_length=1, max_length=800000)]
    language: Annotated[StrictStr, Field(min_length=2, max_length=20)] = "zh-CN"
    region: Region | None = None
    sku_ids: list[UUID] = Field(default_factory=list, max_length=20)


class KnowledgeReviewInput(Contract):
    decision: str = Field(pattern="^(approve|reject)$")
    note: Annotated[StrictStr, Field(min_length=1, max_length=1000)]


class KnowledgeDocument(Contract):
    id: UUID
    source_document_id: UUID
    data_version: UUID
    title: str
    canonical_url: str
    language: str
    region: str | None
    sku_ids: list[UUID]
    content_sha256: str
    review_status: str
    reviewer: str | None
    reviewed_at: AwareDatetime | None
    created_at: AwareDatetime


class KnowledgeSearchRequest(Contract):
    query: Annotated[StrictStr, Field(min_length=1, max_length=500)]
    region: Region | None = None
    sku_ids: list[UUID] = Field(default_factory=list, max_length=10)
    top_k: int = Field(default=5, ge=1, le=8)


class KnowledgeCitation(Contract):
    document_id: UUID
    source_document_id: UUID
    chunk_id: UUID
    title: str
    canonical_url: str
    locator: str
    excerpt: str
    score: float
    data_version: UUID


class KnowledgeSearchResponse(Contract):
    status: str
    citations: list[KnowledgeCitation]
    missing_fields: list[str]
    data_version: UUID | None
