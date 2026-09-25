"""Typed external request, tool-argument and response contracts."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AgentTurn(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4_000)


class AgentSearchContext(StrictModel):
    source: Literal["openalex", "arxiv", "library"]
    query: str = Field(max_length=256)
    from_year: int | None = Field(default=None, ge=1400, le=2100)
    to_year: int | None = Field(default=None, ge=1400, le=2100)
    pages: int = Field(default=1, ge=1, le=3)

    @model_validator(mode="after")
    def validate_search_context(self) -> AgentSearchContext:
        if self.source != "library" and not self.query.strip():
            raise ValueError("remote search context requires a query")
        if self.source == "arxiv" and any(
            year is not None and year < 1991 for year in (self.from_year, self.to_year)
        ):
            raise ValueError("arXiv search years must be 1991 or later")
        if (
            self.from_year is not None
            and self.to_year is not None
            and self.from_year > self.to_year
        ):
            raise ValueError("from_year must not be greater than to_year")
        return self


class AgentQuestion(StrictModel):
    question: str = Field(min_length=3, max_length=1_000)
    history: list[AgentTurn] = Field(default_factory=list, max_length=8)
    search_context: AgentSearchContext | None = None


class SearchPapersArgs(StrictModel):
    query: str = Field(min_length=1, max_length=256)
    limit: int = Field(ge=1, le=10)


class GetPaperArgs(StrictModel):
    openalex_id: str = Field(pattern=r"^W\d+$")


class RelatedPapersArgs(StrictModel):
    openalex_id: str = Field(pattern=r"^W\d+$")
    limit: int = Field(ge=1, le=10)


class OpenAlexSearchArgs(StrictModel):
    query: str = Field(min_length=1, max_length=256)
    limit: int = Field(ge=1, le=10)
    from_year: int | None = Field(default=None, ge=1400, le=2100)
    to_year: int | None = Field(default=None, ge=1400, le=2100)
    open_access_only: bool | None = None

    @model_validator(mode="after")
    def validate_year_range(self) -> OpenAlexSearchArgs:
        if self.from_year and self.to_year and self.from_year > self.to_year:
            raise ValueError("from_year must not be greater than to_year")
        return self


class OpenAlexCitationArgs(StrictModel):
    openalex_id: str = Field(pattern=r"^W\d+$")
    direction: Literal["references", "cited_by", "both"]
    limit: int = Field(ge=1, le=10)
    from_year: int | None = Field(default=None, ge=1400, le=2100)
    to_year: int | None = Field(default=None, ge=1400, le=2100)
    open_access_only: bool | None = None

    @model_validator(mode="after")
    def validate_year_range(self) -> OpenAlexCitationArgs:
        if self.from_year and self.to_year and self.from_year > self.to_year:
            raise ValueError("from_year must not be greater than to_year")
        return self


class OpenAlexAuthorSearchArgs(StrictModel):
    query: str = Field(min_length=1, max_length=256)
    limit: int = Field(ge=1, le=10)


class GetAuthorArgs(StrictModel):
    openalex_author_id: str = Field(pattern=r"^A\d+$")


class AuthorWorksArgs(GetAuthorArgs):
    limit: int = Field(ge=1, le=10)


class SearchArxivArgs(StrictModel):
    query: str = Field(min_length=1, max_length=256)
    limit: int = Field(ge=1, le=10)
    from_year: int | None = Field(default=None, ge=1991, le=2100)
    to_year: int | None = Field(default=None, ge=1991, le=2100)

    @model_validator(mode="after")
    def validate_year_range(self) -> SearchArxivArgs:
        if self.from_year and self.to_year and self.from_year > self.to_year:
            raise ValueError("from_year must not be greater than to_year")
        return self


class GetArxivArgs(StrictModel):
    arxiv_id: str = Field(min_length=4, max_length=64)


class RetrieveEvidenceArgs(StrictModel):
    query: str = Field(min_length=1, max_length=256)
    limit: int = Field(ge=1, le=8)
    source_type: Literal["openalex", "arxiv"] | None = None
    source_id: str | None = Field(default=None, min_length=4, max_length=64)
    retrieval_method: Literal["bm25", "dense", "hybrid"] = "bm25"

    @model_validator(mode="after")
    def validate_optional_source(self) -> RetrieveEvidenceArgs:
        if (self.source_type is None) != (self.source_id is None):
            raise ValueError("source_type and source_id must be supplied together")
        if self.source_type == "openalex" and not re.fullmatch(r"W\d+", self.source_id or ""):
            raise ValueError("invalid OpenAlex source ID")
        if self.source_type == "arxiv":
            from app.sources.arxiv import normalize_arxiv_id

            normalize_arxiv_id(self.source_id or "")
        return self


class ComparePapersArgs(StrictModel):
    openalex_ids: list[str] = Field(min_length=2, max_length=5)

    @field_validator("openalex_ids")
    @classmethod
    def validate_ids(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(
            not re.fullmatch(r"W\d+", item) for item in values
        ):
            raise ValueError("paper IDs must be unique OpenAlex work IDs")
        return values


class FinalAnswer(StrictModel):
    answer: str = Field(max_length=4_000)
    cited_openalex_ids: list[str] = Field(max_length=10)
    cited_arxiv_ids: list[str] = Field(default_factory=list, max_length=10)
    insufficient_evidence: bool

    @field_validator("cited_openalex_ids")
    @classmethod
    def validate_citations(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values) or any(
            not re.fullmatch(r"W\d+", item) for item in values
        ):
            raise ValueError("citations must be unique OpenAlex work IDs")
        return values

    @field_validator("cited_arxiv_ids")
    @classmethod
    def validate_arxiv_citations(cls, values: list[str]) -> list[str]:
        from app.sources.arxiv import normalize_arxiv_id

        normalized = [normalize_arxiv_id(item) for item in values]
        if len(set(normalized)) != len(values):
            raise ValueError("arXiv citations must be unique canonical IDs")
        return normalized


class EvidenceSpan(StrictModel):
    chunk_id: str = Field(max_length=180)
    locator: str = Field(max_length=240)
    excerpt: str = Field(max_length=1_800)


class CitationSourceLink(StrictModel):
    source: Literal["openalex", "arxiv"]
    identifier: str = Field(min_length=4, max_length=120)
    source_url: str = Field(max_length=500)


class CitationRelationship(StrictModel):
    direction: Literal["references", "cited_by"]
    seed_openalex_id: str = Field(pattern=r"^W\d+$")


class Citation(StrictModel):
    source: Literal["openalex", "arxiv"] = "openalex"
    openalex_id: str | None = None
    arxiv_id: str | None = None
    title: str
    source_url: str
    doi: str | None = Field(default=None, max_length=500)
    publication_year: int | None = None
    citation_relationships: list[CitationRelationship] = Field(default_factory=list, max_length=8)
    alternate_sources: list[CitationSourceLink] = Field(default_factory=list, max_length=4)
    license_id: str | None = None
    license_url: str | None = None
    attribution: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def require_matching_source_identifier(self) -> Citation:
        if self.source == "openalex" and (not self.openalex_id or self.arxiv_id):
            raise ValueError("OpenAlex citation must contain only an OpenAlex ID")
        if self.source == "arxiv" and (not self.arxiv_id or self.openalex_id):
            raise ValueError("arXiv citation must contain only an arXiv ID")
        return self


class AgentTraceEvent(StrictModel):
    """Redacted run span: no prompt, paper content, credentials or raw error."""

    sequence: int = Field(ge=1)
    kind: Literal["model", "tool"]
    name: str = Field(max_length=80)
    status: Literal["ok", "error", "refusal"]
    duration_ms: int = Field(ge=0)
    error_code: str | None = Field(default=None, max_length=64)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class AgentResponse(StrictModel):
    status: Literal[
        "completed",
        "insufficient_evidence",
        "unverified_citations",
        "max_steps_exceeded",
        "tool_budget_exceeded",
        "deadline_exceeded",
        "model_disabled",
        "model_unavailable",
        "model_refusal",
        "invalid_model_output",
    ]
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tool_calls: int = 0
    model_steps: int = 0
    model_input_tokens: int = 0
    model_output_tokens: int = 0
    run_id: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    trace: list[AgentTraceEvent] = Field(default_factory=list, max_length=32)
