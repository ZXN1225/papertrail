"""Bounded, read-only client for the official OpenAlex Works endpoint."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

OPENALEX_BASE_URL = "https://api.openalex.org"
WORKS_SELECT = ",".join(
    (
        "id",
        "title",
        "display_name",
        "doi",
        "publication_year",
        "publication_date",
        "type",
        "cited_by_count",
        "authorships",
        "primary_location",
        "open_access",
        "abstract_inverted_index",
        "referenced_works",
    )
)
_WORK_ID = re.compile(r"^/W\d+$")
_AUTHOR_ID = re.compile(r"^/A\d+$")
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class OpenAlexError(Exception):
    """Base exception whose message is safe to show without upstream bodies."""

    code = "openalex_error"
    status_code = 502
    safe_message = "OpenAlex 请求失败。"


class OpenAlexAuthenticationError(OpenAlexError):
    code = "openalex_authentication_failed"
    safe_message = "OpenAlex 拒绝了认证信息，请检查服务端 API Key。"


class OpenAlexRateLimitError(OpenAlexError):
    code = "openalex_rate_limited"
    status_code = 503
    safe_message = "OpenAlex 当前限流或额度不足，请稍后重试并检查额度。"


class OpenAlexUnavailableError(OpenAlexError):
    code = "openalex_unavailable"
    safe_message = "OpenAlex 暂时不可用，请稍后重试。"


class OpenAlexTimeoutError(OpenAlexUnavailableError):
    code = "openalex_timeout"
    safe_message = "OpenAlex 请求超时，请稍后重试。"


class OpenAlexProtocolError(OpenAlexError):
    code = "openalex_invalid_response"
    safe_message = "OpenAlex 返回了无法识别的数据格式。"


class OpenAlexWork(BaseModel):
    """Small, version-tolerant projection of the Works response."""

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str | None = None
    display_name: str | None = None
    doi: str | None = None
    publication_year: int | None = None
    publication_date: str | None = None
    type: str | None = None
    cited_by_count: int | None = None
    authorships: list[dict[str, Any]] = Field(default_factory=list)
    primary_location: dict[str, Any] | None = None
    open_access: dict[str, Any] | None = None
    abstract_inverted_index: dict[str, list[int]] | None = None
    referenced_works: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_openalex_work_id(cls, value: str) -> str:
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "openalex.org"
            or not _WORK_ID.fullmatch(parsed.path)
        ):
            raise ValueError("expected a canonical OpenAlex Works ID")
        return value


class OpenAlexMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    count: int = Field(ge=0)
    page: int | None = Field(default=None, ge=1)
    per_page: int = Field(ge=1, le=100)
    next_cursor: str | None = None
    cost_usd: float | None = Field(default=None, ge=0)


class OpenAlexPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    meta: OpenAlexMeta
    results: list[OpenAlexWork]
    fetched_at: datetime
    rate_limit_limit: int | None = None
    rate_limit_remaining: int | None = None
    credits_used: int | None = None
    rate_limit_reset_seconds: int | None = None


class OpenAlexEntityPage(BaseModel):
    """Validated envelope for allowlisted non-Work entities."""

    model_config = ConfigDict(extra="ignore")

    meta: OpenAlexMeta
    results: list[dict[str, Any]]
    fetched_at: datetime
    rate_limit_limit: int | None = None
    rate_limit_remaining: int | None = None
    credits_used: int | None = None
    rate_limit_reset_seconds: int | None = None


class OpenAlexClient:
    """OpenAlex API client; endpoint is intentionally not caller-configurable."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout_seconds: float = 12.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 0.1 <= timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be between 0.1 and 60")
        if not 0 <= max_retries <= 3:
            raise ValueError("max_retries must be between 0 and 3")
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self._max_retries = max_retries
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=OPENALEX_BASE_URL,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "PaperTrail/0.1"},
            follow_redirects=False,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> OpenAlexClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def search_works(
        self,
        query: str,
        *,
        page: int = 1,
        per_page: int = 10,
        from_year: int | None = None,
        to_year: int | None = None,
        open_access_only: bool = False,
    ) -> OpenAlexPage:
        normalized_query = " ".join(query.split()) if isinstance(query, str) else ""
        if not normalized_query:
            raise ValueError("query must not be empty")
        if len(normalized_query) > 256:
            raise ValueError("query must be at most 256 characters")
        if not 1 <= per_page <= 100:
            raise ValueError("per_page must be between 1 and 100")
        if page < 1 or page * per_page > 10_000:
            raise ValueError("page must be positive and within OpenAlex's 10,000-result page limit")

        filters = _research_filters(from_year, to_year, open_access_only)
        params = {
            "search": normalized_query,
            "page": page,
            "per_page": per_page,
            "select": WORKS_SELECT,
        }
        if filters:
            params["filter"] = ",".join(filters)
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        response = self._get_with_retry(path="/works", params=params, headers=headers)
        return _parse_response(response, OpenAlexPage)

    def get_work(self, work_id: str) -> OpenAlexWork:
        normalized = work_id.strip().removeprefix("https://openalex.org/")
        if not re.fullmatch(r"W\d+", normalized):
            raise ValueError("work_id must be a canonical OpenAlex Work ID")
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        response = self._get_with_retry(
            path=f"/works/{normalized}", params={"select": WORKS_SELECT}, headers=headers
        )
        try:
            payload = response.json()
            return OpenAlexWork.model_validate(payload)
        except (ValueError, ValidationError):
            raise OpenAlexProtocolError from None

    def get_referenced_works(
        self,
        work_ids: list[str],
        *,
        per_page: int = 10,
        from_year: int | None = None,
        to_year: int | None = None,
        open_access_only: bool = False,
    ) -> OpenAlexPage:
        """Fetch a bounded batch of works referenced by a seed work."""
        normalized = _normalize_work_ids(work_ids)
        if not 1 <= per_page <= 10 or len(normalized) > per_page:
            raise ValueError("reference lookup accepts at most 10 unique work IDs")
        return self._works_filter_page(
            "openalex:" + "|".join(normalized),
            per_page=per_page,
            extra_filters=_research_filters(from_year, to_year, open_access_only),
        )

    def get_citing_works(
        self,
        work_id: str,
        *,
        per_page: int = 10,
        from_year: int | None = None,
        to_year: int | None = None,
        open_access_only: bool = False,
    ) -> OpenAlexPage:
        """Fetch a bounded page of works that cite one seed work."""
        normalized = _normalize_work_ids([work_id])[0]
        if not 1 <= per_page <= 10:
            raise ValueError("citation lookup page size must be between 1 and 10")
        return self._works_filter_page(
            f"cites:{normalized}",
            per_page=per_page,
            extra_filters=_research_filters(from_year, to_year, open_access_only),
        )

    def _works_filter_page(
        self, filter_value: str, *, per_page: int, extra_filters: list[str] | None = None
    ) -> OpenAlexPage:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        filters = [filter_value, *(extra_filters or [])]
        response = self._get_with_retry(
            path="/works",
            params={"filter": ",".join(filters), "per_page": per_page, "select": WORKS_SELECT},
            headers=headers,
        )
        return _parse_response(response, OpenAlexPage)

    def search_authors(
        self, query: str, *, page: int = 1, per_page: int = 10
    ) -> OpenAlexEntityPage:
        normalized = " ".join(query.split()) if isinstance(query, str) else ""
        if not normalized or len(normalized) > 256:
            raise ValueError("query must contain 1 to 256 non-whitespace characters")
        if not 1 <= per_page <= 25 or page < 1 or page * per_page > 10_000:
            raise ValueError("author page must be within the bounded API paging range")
        return self._entity_page(
            "/authors",
            {
                "search": normalized,
                "page": page,
                "per_page": per_page,
                "select": "id,display_name,works_count,cited_by_count,orcid",
            },
        )

    def get_author(self, author_id: str) -> dict[str, Any]:
        normalized = author_id.strip().removeprefix("https://openalex.org/")
        if not re.fullmatch(r"A\d+", normalized):
            raise ValueError("author_id must be a canonical OpenAlex Author ID")
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        response = self._get_with_retry(
            path=f"/authors/{normalized}",
            params={"select": "id,display_name,works_count,cited_by_count,orcid,ids,affiliations"},
            headers=headers,
        )
        try:
            value = response.json()
            if not isinstance(value, dict) or not _AUTHOR_ID.fullmatch(
                value.get("id", "").removeprefix("https://openalex.org")
            ):
                raise ValueError
            return value
        except (ValueError, AttributeError):
            raise OpenAlexProtocolError from None

    def list_author_works(
        self, author_id: str, *, page: int = 1, per_page: int = 10
    ) -> OpenAlexPage:
        normalized = author_id.strip().removeprefix("https://openalex.org/")
        if not re.fullmatch(r"A\d+", normalized):
            raise ValueError("author_id must be a canonical OpenAlex Author ID")
        if not 1 <= per_page <= 25 or page < 1 or page * per_page > 10_000:
            raise ValueError("author work page must be within the bounded API paging range")
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        response = self._get_with_retry(
            path="/works",
            params={
                "filter": f"authorships.author.id:{normalized}",
                "page": page,
                "per_page": per_page,
                "select": WORKS_SELECT,
            },
            headers=headers,
        )
        return _parse_response(response, OpenAlexPage)

    def _entity_page(self, path: str, params: dict[str, object]) -> OpenAlexEntityPage:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        response = self._get_with_retry(path=path, params=params, headers=headers)
        return _parse_response(response, OpenAlexEntityPage)

    def _get_with_retry(
        self, *, path: str, params: dict[str, object], headers: dict[str, str]
    ) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
                response = self._http.get(path, params=params, headers=headers)
            except httpx.TimeoutException:
                if attempt < self._max_retries:
                    self._sleep(_backoff(attempt))
                    continue
                raise OpenAlexTimeoutError from None
            except httpx.TransportError:
                if attempt < self._max_retries:
                    self._sleep(_backoff(attempt))
                    continue
                raise OpenAlexUnavailableError from None

            if response.status_code in _RETRYABLE_STATUS:
                if attempt < self._max_retries:
                    self._sleep(_retry_after(response, attempt))
                    continue
                if response.status_code == 429:
                    raise OpenAlexRateLimitError
                raise OpenAlexUnavailableError
            if response.status_code in (401, 403):
                raise OpenAlexAuthenticationError
            if response.is_error:
                raise OpenAlexError
            return response
        raise OpenAlexUnavailableError


def _parse_response(response: httpx.Response, model: type[BaseModel]) -> Any:
    try:
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("response root must be an object")
        payload["fetched_at"] = datetime.now(UTC)
        payload["rate_limit_limit"] = _optional_int_header(response, "X-RateLimit-Limit")
        payload["rate_limit_remaining"] = _optional_int_header(response, "X-RateLimit-Remaining")
        payload["credits_used"] = _optional_int_header(response, "X-RateLimit-Credits-Used")
        payload["rate_limit_reset_seconds"] = _optional_int_header(response, "X-RateLimit-Reset")
        return model.model_validate(payload)
    except (ValueError, ValidationError):
        raise OpenAlexProtocolError from None


def _backoff(attempt: int) -> float:
    return min(0.25 * (2**attempt), 2.0)


def _retry_after(response: httpx.Response, attempt: int) -> float:
    value = response.headers.get("Retry-After", "")
    try:
        return min(max(float(value), 0.0), 5.0)
    except ValueError:
        return _backoff(attempt)


def _optional_int_header(response: httpx.Response, name: str) -> int | None:
    try:
        return int(response.headers[name])
    except (KeyError, TypeError, ValueError):
        return None


def _normalize_work_ids(work_ids: list[str]) -> list[str]:
    if not 1 <= len(work_ids) <= 10:
        raise ValueError("between 1 and 10 OpenAlex Work IDs are required")
    normalized = [item.strip().removeprefix("https://openalex.org/") for item in work_ids]
    if any(not re.fullmatch(r"W\d+", item) for item in normalized):
        raise ValueError("work_ids must contain canonical OpenAlex Work IDs")
    if len(set(normalized)) != len(normalized):
        raise ValueError("work_ids must be unique")
    return normalized


def _research_filters(
    from_year: int | None, to_year: int | None, open_access_only: bool
) -> list[str]:
    filters = []
    if from_year is not None:
        if not 1400 <= from_year <= 2100:
            raise ValueError("from_year must be between 1400 and 2100")
        filters.append(f"from_publication_date:{from_year}-01-01")
    if to_year is not None:
        if not 1400 <= to_year <= 2100:
            raise ValueError("to_year must be between 1400 and 2100")
        filters.append(f"to_publication_date:{to_year}-12-31")
    if from_year is not None and to_year is not None and from_year > to_year:
        raise ValueError("from_year must not be greater than to_year")
    if open_access_only:
        filters.append("open_access.is_oa:true")
    return filters
