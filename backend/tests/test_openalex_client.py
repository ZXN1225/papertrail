from __future__ import annotations

import httpx
import pytest

from app.sources.openalex import (
    OPENALEX_BASE_URL,
    OpenAlexAuthenticationError,
    OpenAlexClient,
    OpenAlexProtocolError,
    OpenAlexRateLimitError,
    OpenAlexTimeoutError,
    OpenAlexUnavailableError,
)


def _payload() -> dict[str, object]:
    return {
        "meta": {"count": 1, "page": 1, "per_page": 10},
        "results": [
            {
                "id": "https://openalex.org/W1234567890",
                "title": "A paper about reliable agents",
                "publication_year": 2025,
                "authorships": [{"author": {"display_name": "Ada Example"}}],
                "abstract_inverted_index": {"A": [0], "paper": [1]},
                "unrequested_private_field": "must be ignored",
            }
        ],
    }


def test_search_uses_fixed_host_bearer_header_and_allowlisted_projection() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=_payload(),
            headers={
                "X-RateLimit-Limit": "1000",
                "X-RateLimit-Remaining": "900",
                "X-RateLimit-Credits-Used": "1",
            },
        )

    with OpenAlexClient("private-test-key", transport=httpx.MockTransport(handler)) as client:
        page = client.search_works("  reliable   agents ", per_page=10)

    request = seen[0]
    assert request.url.scheme == "https"
    assert request.url.host == "api.openalex.org"
    assert request.url.path == "/works"
    assert "api_key" not in request.url.params
    assert request.headers["Authorization"] == "Bearer private-test-key"
    assert request.url.params["search"] == "reliable agents"
    assert request.url.params["per_page"] == "10"
    assert "abstract_inverted_index" in request.url.params["select"]
    assert page.results[0].title == "A paper about reliable agents"
    assert page.results[0].authorships[0]["author"]["display_name"] == "Ada Example"
    assert page.rate_limit_remaining == 900
    assert page.rate_limit_limit == 1000
    assert page.credits_used == 1
    assert "unrequested_private_field" not in page.results[0].model_dump()


def test_keyless_query_is_supported_and_does_not_add_auth_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers
        return httpx.Response(200, json=_payload())

    with OpenAlexClient(transport=httpx.MockTransport(handler)) as client:
        result = client.search_works("agents")

    assert result.meta.count == 1


def test_rate_limit_honors_bounded_retry_after() -> None:
    calls = 0
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "900"})
        return httpx.Response(200, json=_payload())

    with OpenAlexClient(transport=httpx.MockTransport(handler), sleep=delays.append) as client:
        client.search_works("agents")

    assert calls == 2
    assert delays == [5.0]


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [
        (401, OpenAlexAuthenticationError),
        (403, OpenAlexAuthenticationError),
        (429, OpenAlexRateLimitError),
        (503, OpenAlexUnavailableError),
    ],
)
def test_remote_errors_are_mapped_without_exposing_response_body(
    status_code: int, exception_type: type[Exception]
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="private upstream diagnostic")

    with (
        OpenAlexClient(transport=httpx.MockTransport(handler), max_retries=0) as client,
        pytest.raises(exception_type) as caught,
    ):
        client.search_works("agents")

    assert "private upstream diagnostic" not in str(caught.value)


def test_invalid_payload_and_noncanonical_ids_are_rejected() -> None:
    for payload in (
        {"not": "the expected envelope"},
        {"meta": {"count": 1, "per_page": 1}, "results": [{"id": "https://evil.test/W1"}]},
    ):
        with (
            OpenAlexClient(
                transport=httpx.MockTransport(
                    lambda _, payload=payload: httpx.Response(200, json=payload)
                )
            ) as client,
            pytest.raises(OpenAlexProtocolError),
        ):
            client.search_works("agents")


def test_timeout_is_classified_and_not_retried_past_budget() -> None:
    calls = 0
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("hidden transport detail")

    with (
        OpenAlexClient(
            transport=httpx.MockTransport(handler), max_retries=1, sleep=delays.append
        ) as client,
        pytest.raises(OpenAlexTimeoutError),
    ):
        client.search_works("agents")

    assert calls == 2
    assert delays == [0.25]


@pytest.mark.parametrize(
    ("query", "page", "per_page"),
    [
        ("", 1, 10),
        ("agents", 1, 101),
        ("agents", 1001, 10),
        ("x" * 257, 1, 10),
    ],
)
def test_queries_and_pages_are_bounded(query: str, page: int, per_page: int) -> None:
    with OpenAlexClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        with pytest.raises(ValueError):
            client.search_works(query, page=page, per_page=per_page)


def test_fixed_endpoint_constant_is_official() -> None:
    assert OPENALEX_BASE_URL == "https://api.openalex.org"


def test_work_search_accepts_official_maximum_page_size() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_payload())

    with OpenAlexClient(transport=httpx.MockTransport(handler)) as client:
        client.search_works("RAG", per_page=100)

    assert requests[0].url.params["per_page"] == "100"


def test_work_search_applies_only_explicit_bounded_research_filters() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_payload())

    with OpenAlexClient(transport=httpx.MockTransport(handler)) as client:
        client.search_works(
            "retrieval augmented generation",
            from_year=2020,
            to_year=2025,
            open_access_only=True,
        )
        client.search_works("retrieval augmented generation")
        with pytest.raises(ValueError):
            client.search_works("agents", from_year=2025, to_year=2020)

    assert requests[0].url.params["filter"] == (
        "from_publication_date:2020-01-01,to_publication_date:2025-12-31,open_access.is_oa:true"
    )
    assert "filter" not in requests[1].url.params


def test_citation_queries_use_fixed_works_filters_and_bounded_ids() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_payload())

    with OpenAlexClient(transport=httpx.MockTransport(handler)) as client:
        client.get_referenced_works(["W1234567890", "W2345678901"], per_page=2)
        client.get_citing_works("W1234567890", per_page=3)

        with pytest.raises(ValueError):
            client.get_citing_works("W123/../../evil")
        with pytest.raises(ValueError):
            client.get_referenced_works(["W1", "W1"], per_page=2)

    assert [request.url.params["filter"] for request in requests] == [
        "openalex:W1234567890|W2345678901",
        "cites:W1234567890",
    ]
    assert all(request.url.host == "api.openalex.org" for request in requests)
    assert all(request.url.params["per_page"] in {"2", "3"} for request in requests)


def test_work_detail_and_author_workflows_use_fixed_allowlisted_endpoints() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/works/W1234567890":
            return httpx.Response(200, json=_payload()["results"][0])
        if request.url.path == "/authors":
            return httpx.Response(
                200,
                json={
                    "meta": {"count": 1, "page": 1, "per_page": 1},
                    "results": [
                        {
                            "id": "https://openalex.org/A123",
                            "display_name": "Ada Example",
                            "works_count": 3,
                        }
                    ],
                },
            )
        if request.url.path == "/authors/A123":
            return httpx.Response(
                200,
                json={
                    "id": "https://openalex.org/A123",
                    "display_name": "Ada Example",
                    "works_count": 3,
                },
            )
        if request.url.path == "/works":
            return httpx.Response(200, json=_payload())
        return httpx.Response(404)

    with OpenAlexClient("test-key", transport=httpx.MockTransport(handler)) as client:
        work = client.get_work("W1234567890")
        authors = client.search_authors("Ada Example", per_page=1)
        author = client.get_author("A123")
        works = client.list_author_works("A123", per_page=1)

    assert work.title == "A paper about reliable agents"
    assert authors.results[0]["display_name"] == "Ada Example"
    assert author["id"].endswith("A123")
    assert works.results[0].id.endswith("W1234567890")
    assert [request.url.path for request in requests] == [
        "/works/W1234567890",
        "/authors",
        "/authors/A123",
        "/works",
    ]
    assert requests[-1].url.params["filter"] == "authorships.author.id:A123"
    assert all(request.url.host == "api.openalex.org" for request in requests)
    assert all(request.headers["Authorization"] == "Bearer test-key" for request in requests)


@pytest.mark.parametrize(
    ("method", "value"), [("get_work", "W1/../../evil"), ("get_author", "A1?host=evil")]
)
def test_entity_ids_cannot_change_openalex_path(method: str, value: str) -> None:
    with OpenAlexClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        with pytest.raises(ValueError):
            getattr(client, method)(value)
