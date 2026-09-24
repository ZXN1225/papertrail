from __future__ import annotations

import platform

import httpx
import pytest

import app.sources.arxiv as arxiv_module
from app.sources.arxiv import (
    ARXIV_BASE_URL,
    ArxivClient,
    ArxivProtocolError,
    normalize_arxiv_id,
)

ATOM = "http://www.w3.org/2005/Atom"
OPEN = "http://a9.com/-/spec/opensearch/1.1/"
ARXIV = "http://arxiv.org/schemas/atom"


def _feed(work_id: str = "2401.12345v2", doi: str = "10.1000/example") -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="{ATOM}" xmlns:opensearch="{OPEN}" xmlns:arxiv="{ARXIV}">
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <entry>
        <id>http://arxiv.org/abs/{work_id}</id>
        <title>  A Research Paper  </title>
        <summary> An abstract for testing. </summary>
        <published>2024-01-02T00:00:00Z</published>
        <updated>2024-02-03T00:00:00Z</updated>
        <author><name>Ada Example</name></author>
        <category term="cs.AI" scheme="http://arxiv.org/schemas/atom" />
        <arxiv:primary_category term="cs.AI" />
        <arxiv:doi>{doi}</arxiv:doi>
      </entry>
    </feed>'''.encode()


def test_arxiv_search_parses_atom_and_uses_fixed_host_and_bounded_query() -> None:
    arxiv_module._LAST_REQUEST_AT = None
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_feed())

    with ArxivClient(transport=httpx.MockTransport(handler)) as client:
        page = client.search("  research   paper ", max_results=1)

    assert ARXIV_BASE_URL == "https://export.arxiv.org"
    assert seen[0].url.host == "export.arxiv.org"
    assert seen[0].url.path == "/api/query"
    assert b"research%20paper" in seen[0].url.query
    assert b"+" not in seen[0].url.query
    assert seen[0].url.params["max_results"] == "1"
    assert seen[0].headers["user-agent"].startswith("Python/")
    assert page.total_results == 1
    assert page.works[0].arxiv_id == "2401.12345"
    assert page.works[0].source_url == "https://arxiv.org/abs/2401.12345"
    assert page.works[0].abstract == "An abstract for testing."
    assert page.works[0].categories == ["cs.AI"]
    assert page.works[0].doi == "10.1000/example"


def test_arxiv_client_identifies_python_runtime_for_export_gateway() -> None:
    arxiv_module._LAST_REQUEST_AT = None
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_feed())

    with ArxivClient(transport=httpx.MockTransport(handler)) as client:
        client.search("retrieval augmented generation", max_results=10)

    assert seen[0].headers["user-agent"].startswith(f"Python/{platform.python_version()}")
    assert b"retrieval%20augmented%20generation" in seen[0].url.query


def test_id_normalization_handles_version_and_rejects_untrusted_hosts() -> None:
    assert normalize_arxiv_id("https://arxiv.org/abs/2401.12345v3") == "2401.12345"
    assert normalize_arxiv_id("hep-ex/0307015v2") == "hep-ex/0307015"
    with pytest.raises(ValueError):
        normalize_arxiv_id("https://evil.test/abs/2401.12345")
    with pytest.raises(ValueError):
        normalize_arxiv_id("2401.12345/../../etc")


def test_search_accepts_exact_arxiv_id_query_without_treating_it_as_keywords() -> None:
    arxiv_module._LAST_REQUEST_AT = None
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_feed("2609.25991v1"))

    with ArxivClient(transport=httpx.MockTransport(handler)) as client:
        page = client.search("id:2609.25991v1", max_results=5)

    assert seen[0].url.params["search_query"] == "id:2609.25991"
    assert seen[0].url.params["max_results"] == "1"
    assert page.works[0].arxiv_id == "2609.25991"


def test_dtd_entity_payload_and_malformed_atom_are_rejected() -> None:
    arxiv_module._LAST_REQUEST_AT = None
    responses = [
        b'<!DOCTYPE feed [<!ENTITY x "boom">]><feed/>',
        b"<html>not atom</html>",
    ]
    for payload in responses:
        arxiv_module._LAST_REQUEST_AT = None
        with (
            ArxivClient(
                transport=httpx.MockTransport(
                    lambda _, body=payload: httpx.Response(200, content=body)
                )
            ) as client,
            pytest.raises(ArxivProtocolError),
        ):
            client.search("test")


def test_arxiv_client_enforces_three_second_minimum_between_requests() -> None:
    arxiv_module._LAST_REQUEST_AT = None
    now = [100.0]
    sleeps: list[float] = []

    def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_feed())

    with ArxivClient(
        transport=httpx.MockTransport(handler), clock=lambda: now[0], sleep=fake_sleep
    ) as client:
        client.search("one")
        client.search("two")

    assert sleeps == [3.0]
