"""Rate-limited client for the official arXiv Atom metadata API."""

from __future__ import annotations

import platform
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import quote, urlencode, urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

ARXIV_BASE_URL = "https://export.arxiv.org"
ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"
OPENSEARCH_NS = "http://a9.com/-/spec/opensearch/1.1/"
MAX_RESPONSE_BYTES = 2_000_000
_NEW_ID = re.compile(r"^\d{4}\.\d{4,5}$")
_OLD_ID = re.compile(r"^[a-z-]+(?:\.[A-Z]{2})?/\d{7}$", re.IGNORECASE)
_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_AT: float | None = None


class ArxivError(Exception):
    code = "arxiv_error"
    status_code = 502
    safe_message = "arXiv API 请求失败。"


class ArxivRateLimitError(ArxivError):
    code = "arxiv_rate_limited"
    status_code = 503
    safe_message = "arXiv API 暂时不可用，请稍后重试。"


class ArxivUnavailableError(ArxivError):
    code = "arxiv_unavailable"
    safe_message = "arXiv API 暂时不可用，请稍后重试。"


class ArxivTimeoutError(ArxivUnavailableError):
    code = "arxiv_timeout"
    safe_message = "arXiv API 请求超时，请稍后重试。"


class ArxivProtocolError(ArxivError):
    code = "arxiv_invalid_response"
    safe_message = "arXiv API 返回了无法识别的数据格式。"


class ArxivWork(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arxiv_id: str
    title: str = Field(max_length=2_000)
    abstract: str = Field(max_length=100_000)
    authors: list[str] = Field(max_length=200)
    categories: list[str] = Field(max_length=100)
    primary_category: str | None = None
    published_at: datetime
    updated_at: datetime
    doi: str | None = Field(default=None, max_length=500)
    journal_ref: str | None = Field(default=None, max_length=2_000)
    source_url: str


class ArxivPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_results: int = Field(ge=0)
    start: int = Field(ge=0)
    items_per_page: int = Field(ge=0, le=25)
    works: list[ArxivWork]
    fetched_at: datetime


def normalize_arxiv_id(value: str) -> str:
    raw = value.strip()
    parsed = urlparse(raw)
    if parsed.scheme:
        if parsed.scheme not in {"http", "https"} or parsed.netloc not in {
            "arxiv.org",
            "export.arxiv.org",
        }:
            raise ValueError("arXiv ID URL must use the canonical arxiv.org host")
        raw = parsed.path.removeprefix("/abs/").removeprefix("/pdf/").strip("/")
    raw = raw.removesuffix(".pdf")
    base = re.sub(r"v\d+$", "", raw)
    if not (_NEW_ID.fullmatch(base) or _OLD_ID.fullmatch(base)):
        raise ValueError("arxiv_id is not a supported canonical identifier")
    return base.lower() if "/" in base else base


class ArxivClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 15,
        min_interval_seconds: float = 3,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not 0.1 <= timeout_seconds <= 60 or min_interval_seconds < 3:
            raise ValueError(
                "timeout must be bounded and arXiv interval must be at least 3 seconds"
            )
        self._clock = clock
        self._sleep = sleep
        self._min_interval = min_interval_seconds
        self._http = httpx.Client(
            base_url=ARXIV_BASE_URL,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            # arXiv's API gateway returns HTTP 406 for the generic project UA.
            # Keep request negotiation conservative: urllib (which succeeds
            # against this gateway) advertises identity encoding by default.
            headers={
                "Accept": "application/atom+xml",
                "Accept-Encoding": "identity",
                # arXiv's gateway rejects httpx's default `python-httpx/...` UA
                # with HTTP 406 for normal result pages. Identify the actual
                # runtime truthfully; don't impersonate a browser or urllib.
                "User-Agent": f"Python/{platform.python_version()}",
            },
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ArxivClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def search(
        self,
        query: str,
        *,
        start: int = 0,
        max_results: int = 10,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> ArxivPage:
        normalized = " ".join(query.split()) if isinstance(query, str) else ""
        if not normalized or len(normalized) > 256:
            raise ValueError("query must contain 1 to 256 non-whitespace characters")
        if (
            (from_year is not None and not 1991 <= from_year <= 2100)
            or (to_year is not None and not 1991 <= to_year <= 2100)
            or (from_year is not None and to_year is not None and from_year > to_year)
        ):
            raise ValueError("arXiv year range must be within 1991-2100 and ordered")
        if start < 0 or start + max_results > 10_000 or not 1 <= max_results <= 25:
            raise ValueError("arXiv page must be within the bounded 10,000 result range")
        search_query = f'all:"{_escape_query(normalized)}"'
        if from_year is not None or to_year is not None:
            start_year = from_year or 1991
            end_year = to_year or datetime.now(UTC).year
            date_filter = f"submittedDate:[{start_year}01010000 TO {end_year}12312359]"
            search_query += f" AND {date_filter}"
        id_match = re.fullmatch(r"id:\s*(\S+)", normalized, flags=re.IGNORECASE)
        if id_match and from_year is None and to_year is None:
            arxiv_id = normalize_arxiv_id(id_match.group(1))
            return self._query(search_query=f"id:{arxiv_id}", start=0, max_results=1)
        return self._query(
            search_query=search_query,
            start=start,
            max_results=max_results,
        )

    def get_work(self, arxiv_id: str) -> ArxivWork | None:
        normalized = normalize_arxiv_id(arxiv_id)
        page = self._query(id_list=normalized, start=0, max_results=1)
        return page.works[0] if page.works else None

    def _query(self, *, start: int, max_results: int, **params: str | int) -> ArxivPage:
        global _LAST_REQUEST_AT
        with _REQUEST_LOCK:
            now = self._clock()
            if _LAST_REQUEST_AT is not None:
                delay = self._min_interval - (now - _LAST_REQUEST_AT)
                if delay > 0:
                    self._sleep(delay)
            _LAST_REQUEST_AT = self._clock()
            try:
                request_params = {
                    **params,
                    "start": start,
                    "max_results": max_results,
                }
                # arXiv's export gateway rejects form-style '+' spaces (HTTP 406).
                # Encode spaces as %20 while preserving the fixed endpoint and params.
                query = urlencode(request_params, quote_via=quote)
                response = self._http.get(f"/api/query?{query}")
            except httpx.TimeoutException:
                raise ArxivTimeoutError from None
            except httpx.TransportError:
                raise ArxivUnavailableError from None
        if response.status_code == 429:
            raise ArxivRateLimitError
        if response.status_code < 200 or response.status_code >= 300:
            raise ArxivUnavailableError
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ArxivProtocolError
        if b"<!DOCTYPE" in response.content.upper() or b"<!ENTITY" in response.content.upper():
            raise ArxivProtocolError
        return _parse_atom(response.content, start=start)


def _parse_atom(content: bytes, *, start: int) -> ArxivPage:
    try:
        root = ET.fromstring(content)
        if root.tag != f"{{{ATOM_NS}}}feed":
            raise ValueError
        total = int(root.findtext(f"{{{OPENSEARCH_NS}}}totalResults", "0"))
        response_start = int(root.findtext(f"{{{OPENSEARCH_NS}}}startIndex", str(start)))
        page_size = int(root.findtext(f"{{{OPENSEARCH_NS}}}itemsPerPage", "0"))
        entries: list[ArxivWork] = []
        for entry in root.findall(f"{{{ATOM_NS}}}entry"):
            entry_id = entry.findtext(f"{{{ATOM_NS}}}id", "")
            work_id = normalize_arxiv_id(entry_id)
            primary = entry.find(f"{{{ARXIV_NS}}}primary_category")
            authors = [
                node.findtext(f"{{{ATOM_NS}}}name", "")
                for node in entry.findall(f"{{{ATOM_NS}}}author")
            ]
            categories = [
                node.attrib["term"]
                for node in entry.findall(f"{{{ATOM_NS}}}category")
                if "term" in node.attrib
            ]
            doi_node = entry.find(f"{{{ARXIV_NS}}}doi")
            journal_node = entry.find(f"{{{ARXIV_NS}}}journal_ref")
            source_url = f"https://arxiv.org/abs/{work_id}"
            entries.append(
                ArxivWork(
                    arxiv_id=work_id,
                    title=" ".join(entry.findtext(f"{{{ATOM_NS}}}title", "").split()),
                    abstract=" ".join(entry.findtext(f"{{{ATOM_NS}}}summary", "").split()),
                    authors=[name for name in authors if name],
                    categories=categories,
                    primary_category=primary.attrib.get("term") if primary is not None else None,
                    published_at=_parse_datetime(entry.findtext(f"{{{ATOM_NS}}}published", "")),
                    updated_at=_parse_datetime(entry.findtext(f"{{{ATOM_NS}}}updated", "")),
                    doi=(doi_node.text or "").strip() if doi_node is not None else None,
                    journal_ref=(journal_node.text or "").strip()
                    if journal_node is not None
                    else None,
                    source_url=source_url,
                )
            )
        if page_size != len(entries) or len(entries) > 25:
            raise ValueError
        return ArxivPage(
            total_results=total,
            start=response_start,
            items_per_page=page_size,
            works=entries,
            fetched_at=datetime.now(UTC),
        )
    except (ET.ParseError, ValueError, KeyError, ValidationError, TypeError):
        raise ArxivProtocolError from None


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _escape_query(query: str) -> str:
    return query.replace("\\", " ").replace('"', " ")
