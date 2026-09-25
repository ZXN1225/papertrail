from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent.contracts import (
    AgentResponse,
    AgentSearchContext,
    AgentTurn,
    ComparePapersArgs,
)
from app.agent.harness import AgentHarness, _collect_citations, _output_diagnostic_warnings
from app.agent.model import (
    ModelToolCall,
    ModelTurn,
    ModelUnavailable,
    OpenAIResponsesClient,
)
from app.agent.tools import PaperToolRegistry
from app.config import Settings
from app.main import create_app
from app.sources.arxiv import ArxivClient
from app.sources.openalex import OpenAlexClient, OpenAlexMeta, OpenAlexPage, OpenAlexWork
from app.storage.repository import PaperStore


def _store_in_tempdir() -> tuple[tempfile.TemporaryDirectory[str], PaperStore]:
    temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
    store = PaperStore(Path(temporary.name) / "catalog.sqlite3")
    page = OpenAlexPage(
        meta=OpenAlexMeta(count=2, page=1, per_page=2),
        results=[
            OpenAlexWork(
                id="https://openalex.org/W100",
                title="Retrieval systems for research assistants",
                publication_year=2025,
                abstract_inverted_index={
                    "Retrieval": [0],
                    "systems": [1],
                    "support": [2],
                    "research": [3],
                    "assistants": [4],
                },
            ),
            OpenAlexWork(
                id="https://openalex.org/W200",
                title="Graph retrieval methods for language models",
                publication_year=2024,
            ),
        ],
        fetched_at=datetime(2026, 9, 23, tzinfo=UTC),
    )
    store.import_openalex_page(page, query="research assistant", requested_page=1, per_page=2)
    return temporary, store


class FakeModel:
    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = turns
        self.inputs: list[list[dict]] = []
        self.instructions: list[str] = []
        self.tool_sets: list[list[dict]] = []

    def complete(
        self, *, instructions: str, input_items: list[dict], tools: list[dict]
    ) -> ModelTurn:
        self.instructions.append(instructions)
        self.inputs.append(input_items.copy())
        self.tool_sets.append(tools.copy())
        assert all(tool["strict"] is True for tool in tools)
        return self.turns.pop(0)


def _call_turn(*calls: ModelToolCall) -> ModelTurn:
    return ModelTurn(
        tool_calls=list(calls),
        continuation_items=[
            {
                "type": "function_call",
                "call_id": call.call_id,
                "name": call.name,
                "arguments": call.arguments,
            }
            for call in calls
        ],
        final_text=None,
        refusal=False,
        input_tokens=10,
        output_tokens=4,
    )


def _final_turn(
    answer: str,
    citations: list[str],
    insufficient: bool = False,
    arxiv_citations: list[str] | None = None,
) -> ModelTurn:
    return ModelTurn(
        tool_calls=[],
        continuation_items=[],
        final_text=json.dumps(
            {
                "answer": answer,
                "cited_openalex_ids": citations,
                "cited_arxiv_ids": arxiv_citations or [],
                "insufficient_evidence": insufficient,
            }
        ),
        refusal=False,
        input_tokens=12,
        output_tokens=6,
    )


def test_tool_registry_is_allowlisted_and_validates_arguments() -> None:
    temporary, store = _store_in_tempdir()
    try:
        registry = PaperToolRegistry(store)

        found = registry.execute("search_papers", '{"query":"research assistant","limit":5}')
        related = registry.execute("find_related_papers", '{"openalex_id":"W100","limit":5}')
        compared = registry.execute("compare_papers", '{"openalex_ids":["W100","W200"]}')
        evidence = registry.execute(
            "retrieve_paper_evidence",
            '{"query":"findings","limit":5,"source_type":"openalex","source_id":"W100"}',
        )
        forbidden = registry.execute("arbitrary_sql", '{"query":"select * from works"}')
        invalid = registry.execute("search_papers", '{"query":"x","limit":1000}')

        assert found["status"] == "ok"
        assert found["items"][0]["openalex_id"] == "W100"
        assert related["method"] == "bm25_lexical_similarity"
        assert any(item["openalex_id"] == "W200" for item in related["items"])
        assert [paper["openalex_id"] for paper in compared["papers"]] == ["W100", "W200"]
        assert evidence["status"] == "no_results"
        assert evidence["items"] == []
        assert forbidden["code"] == "tool_not_allowed"
        assert invalid["code"] == "invalid_arguments"
    finally:
        temporary.cleanup()


def test_agent_uses_server_refreshed_search_context_and_prior_conversation() -> None:
    temporary, store = _store_in_tempdir()
    try:

        class ContextOpenAlex:
            def search_works(self, query: str, **kwargs: object) -> OpenAlexPage:
                assert query == "research assistant"
                assert kwargs == {
                    "page": 1,
                    "per_page": 10,
                    "from_year": 2025,
                    "to_year": 2025,
                }
                return OpenAlexPage(
                    meta=OpenAlexMeta(count=1, page=1, per_page=10),
                    results=[
                        OpenAlexWork(
                            id="https://openalex.org/W100",
                            title="TEST source-refreshed metadata",
                            publication_year=2025,
                        )
                    ],
                    fetched_at=datetime(2026, 9, 23, tzinfo=UTC),
                )

        registry = PaperToolRegistry(store, openalex=ContextOpenAlex())
        observation = registry.load_search_context(
            AgentSearchContext(
                source="openalex",
                query="research assistant",
                from_year=2025,
                to_year=2025,
                pages=1,
            )
        )
        collected = {}
        _collect_citations(observation, collected)
        assert "openalex:W100" in collected, observation

        model = FakeModel([_final_turn("TEST metadata result [W100]", ["W100"])])
        result = AgentHarness(model, registry).run(
            "Based on those results, list the year and source link.",
            history=[
                AgentTurn(role="user", content="Search research assistant papers."),
                AgentTurn(role="assistant", content="TEST previous response."),
            ],
            search_context=AgentSearchContext(
                source="openalex",
                query="research assistant",
                from_year=2025,
                to_year=2025,
                pages=1,
            ),
        )

        assert result.status == "completed", result.model_dump()
        assert [citation.openalex_id for citation in result.citations] == ["W100"]
        assert result.trace[0].name == "current_search_context"
        assert result.trace[0].status == "ok"
        assert result.tool_calls == 1
        assert model.inputs[0][0]["content"] == "Search research assistant papers."
        assert "Current search context" in model.inputs[0][-2]["content"]
        assert (
            model.inputs[0][-1]["content"]
            == "Based on those results, list the year and source link."
        )
    finally:
        temporary.cleanup()


def test_library_search_context_is_capped_at_30_merged_items() -> None:
    temporary, store = _store_in_tempdir()
    try:
        store.list_papers = lambda **_: {
            "total": 30,
            "items": [
                {
                    "openalex_id": f"W{1000 + year}",
                    "title": f"OpenAlex {year}",
                    "publication_year": year,
                    "source_url": f"https://openalex.org/W{1000 + year}",
                }
                for year in range(1990, 2020)
            ],
        }
        store.list_arxiv_papers = lambda **_: {
            "total": 30,
            "items": [
                {
                    "arxiv_id": f"{year}.12345",
                    "title": f"arXiv {year}",
                    "published_at": f"{year}-01-01T00:00:00Z",
                    "source_url": f"https://arxiv.org/abs/{year}.12345",
                }
                for year in range(1990, 2020)
            ],
        }

        observation = PaperToolRegistry(store).load_search_context(
            AgentSearchContext(source="library", query="test", pages=3)
        )

        assert observation["status"] == "ok"
        assert len(observation["items"]) == 30
        assert [item["publication_year"] for item in observation["items"]] == sorted(
            (item["publication_year"] for item in observation["items"]), reverse=True
        )
        assert observation["items"][0]["publication_year"] == 2019
        assert observation["items"][-1]["publication_year"] == 2005
    finally:
        temporary.cleanup()


def test_openalex_tools_are_only_registered_with_client_and_call_fixed_api() -> None:
    temporary, store = _store_in_tempdir()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "meta": {"count": 1, "page": 1, "per_page": 1},
                "results": [
                    {
                        "id": "https://openalex.org/W900",
                        "title": "OpenAlex live metadata result",
                        "publication_year": 2026,
                        "abstract_inverted_index": {"Evidence": [0], "test": [1]},
                    }
                ],
            },
        )

    try:
        with OpenAlexClient(transport=httpx.MockTransport(handler)) as openalex:
            registry = PaperToolRegistry(store, openalex)
            available = registry.execute("search_openalex_works", '{"query":"evidence","limit":3}')
            assert len(registry.definitions) == 11
        assert available["status"] == "ok"
        assert available["items"][0]["openalex_id"] == "W900"
        assert available["items"][0]["abstract"] == "Evidence test"
        assert requests[0].url.host == "api.openalex.org"
        assert requests[0].url.path == "/works"
    finally:
        temporary.cleanup()


def test_agent_openalex_search_accepts_structured_user_filters() -> None:
    temporary, store = _store_in_tempdir()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"meta": {"count": 0, "page": 1, "per_page": 5}, "results": []},
        )

    try:
        with OpenAlexClient(transport=httpx.MockTransport(handler)) as client:
            registry = PaperToolRegistry(store, client)
            result = registry.execute(
                "search_openalex_works",
                '{"query":"agent research","limit":5,"from_year":2020,'
                '"to_year":2024,"open_access_only":true}',
            )
            invalid = registry.execute(
                "search_openalex_works",
                '{"query":"agent research","limit":5,"from_year":2025,'
                '"to_year":2020,"open_access_only":null}',
            )

        assert result["status"] == "no_results"
        assert requests[0].url.params["filter"] == (
            "from_publication_date:2020-01-01,to_publication_date:2024-12-31,open_access.is_oa:true"
        )
        assert invalid["code"] == "invalid_arguments"
    finally:
        temporary.cleanup()


def test_citation_expansion_tool_returns_bounded_relationships_and_citable_papers() -> None:
    temporary, store = _store_in_tempdir()
    requests: list[httpx.Request] = []

    def work(work_id: str, title: str) -> dict:
        return {
            "id": f"https://openalex.org/{work_id}",
            "title": title,
            "publication_year": 2024,
            "abstract_inverted_index": {title: [0]},
            "referenced_works": ["https://openalex.org/W901"],
        }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/works/W900":
            return httpx.Response(200, json=work("W900", "Seed paper"))
        if request.url.params.get("filter") == "openalex:W901":
            return httpx.Response(
                200,
                json={
                    "meta": {"count": 1, "page": 1, "per_page": 1},
                    "results": [work("W901", "Referenced paper")],
                },
            )
        if request.url.params.get("filter") == "cites:W900":
            return httpx.Response(
                200,
                json={
                    "meta": {"count": 1, "page": 1, "per_page": 1},
                    "results": [work("W902", "Citing paper")],
                },
            )
        return httpx.Response(404)

    try:
        with OpenAlexClient(transport=httpx.MockTransport(handler)) as client:
            registry = PaperToolRegistry(store, client)
            expanded = registry.execute(
                "expand_openalex_citations",
                '{"openalex_id":"W900","direction":"both","limit":1}',
            )
            invalid = registry.execute(
                "expand_openalex_citations",
                '{"openalex_id":"W900","direction":"both","limit":11}',
            )
            forbidden = registry.execute(
                "expand_openalex_citations",
                '{"openalex_id":"W900","direction":"both","limit":1,"url":"https://evil"}',
            )

        assert expanded["status"] == "ok"
        assert expanded["metadata_only_relationships"] is True
        assert [item["openalex_id"] for item in expanded["items"]] == ["W901", "W902"]
        assert expanded["items"][0]["citation_relationships"] == [
            {"direction": "references", "seed_openalex_id": "W900"}
        ]
        assert expanded["items"][1]["citation_relationships"] == [
            {"direction": "cited_by", "seed_openalex_id": "W900"}
        ]
        assert invalid["code"] == "invalid_arguments"
        assert forbidden["code"] == "invalid_arguments"
        assert len(requests) == 3
    finally:
        temporary.cleanup()


def test_agent_can_discover_expand_citations_and_answer_with_verified_seed_and_candidate() -> None:
    temporary, store = _store_in_tempdir()
    responses = [
        {
            "meta": {"count": 1, "page": 1, "per_page": 1},
            "results": [
                {
                    "id": "https://openalex.org/W900",
                    "title": "Seed paper",
                    "publication_year": 2025,
                    "abstract_inverted_index": {"Seed": [0], "abstract": [1]},
                    "referenced_works": ["https://openalex.org/W901"],
                }
            ],
        },
        {
            "id": "https://openalex.org/W900",
            "title": "Seed paper",
            "publication_year": 2025,
            "abstract_inverted_index": {"Seed": [0], "abstract": [1]},
            "referenced_works": ["https://openalex.org/W901"],
        },
        {
            "meta": {"count": 1, "page": 1, "per_page": 1},
            "results": [
                {
                    "id": "https://openalex.org/W901",
                    "title": "Foundational paper",
                    "publication_year": 2022,
                    "abstract_inverted_index": {"Foundational": [0], "abstract": [1]},
                }
            ],
        },
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    try:
        with OpenAlexClient(transport=httpx.MockTransport(handler)) as client:
            registry = PaperToolRegistry(store, client)
            model = FakeModel(
                [
                    _call_turn(
                        ModelToolCall(
                            "discover",
                            "search_openalex_works",
                            '{"query":"agent retrieval","limit":2}',
                        )
                    ),
                    _call_turn(
                        ModelToolCall(
                            "expand",
                            "expand_openalex_citations",
                            '{"openalex_id":"W900","direction":"references","limit":5}',
                        )
                    ),
                    _final_turn(
                        "The discovery result and one referenced work are available as metadata; "
                        "their findings require full-text evidence. [W900] [W901]",
                        ["W900", "W901"],
                    ),
                ]
            )
            result = AgentHarness(model, registry).run(
                "Find agent retrieval papers and expand one citation hop"
            )

        assert result.status == "completed"
        assert {item.openalex_id for item in result.citations} == {"W900", "W901"}
        seed = next(item for item in result.citations if item.openalex_id == "W900")
        candidate = next(item for item in result.citations if item.openalex_id == "W901")
        assert seed.publication_year == 2025
        assert seed.citation_relationships == []
        assert candidate.publication_year == 2022
        assert [item.direction for item in candidate.citation_relationships] == ["references"]
        assert candidate.citation_relationships[0].seed_openalex_id == "W900"
        assert "expand_openalex_citations" in model.instructions[1]
        assert (
            "Set insufficient_evidence=false when at least one requested item is"
            in (model.instructions[0])
        )
    finally:
        temporary.cleanup()


def test_openalex_citation_metadata_merges_observed_relationships_and_keeps_missing_year_null() -> (
    None
):
    citations = {}
    common = {
        "openalex_id": "W901",
        "title": "Candidate paper",
        "source_url": "https://openalex.org/W901",
    }
    _collect_citations(
        {
            "items": [
                {
                    **common,
                    "publication_year": 2024,
                    "citation_relationships": [
                        {"direction": "references", "seed_openalex_id": "W900"}
                    ],
                },
                {
                    **common,
                    "publication_year": None,
                    "citation_relationships": [
                        {"direction": "cited_by", "seed_openalex_id": "W902"}
                    ],
                },
            ]
        },
        citations,
    )

    candidate = citations["openalex:W901"]
    assert candidate.publication_year == 2024
    assert [item.direction for item in candidate.citation_relationships] == [
        "references",
        "cited_by",
    ]
    assert [item.seed_openalex_id for item in candidate.citation_relationships] == [
        "W900",
        "W902",
    ]
    _collect_citations(
        {
            "items": [
                {
                    "openalex_id": "W903",
                    "title": "No year paper",
                    "source_url": "https://openalex.org/W903",
                    "publication_year": None,
                }
            ]
        },
        citations,
    )
    assert citations["openalex:W903"].publication_year is None


def test_agent_deduplicates_cross_source_citations_only_by_matching_doi() -> None:
    citations = {}
    _collect_citations(
        {
            "items": [
                {
                    "openalex_id": "W910",
                    "title": "TEST OpenAlex version",
                    "source_url": "https://openalex.org/W910",
                    "doi": "https://doi.org/10.5555/Shared.DOI.",
                    "publication_year": 2024,
                },
                {
                    "arxiv_id": "2401.12345",
                    "title": "TEST arXiv version",
                    "source_url": "https://arxiv.org/abs/2401.12345",
                    "doi": "10.5555/shared.doi",
                },
                {
                    "arxiv_id": "2402.12345",
                    "title": "TEST same title but different DOI",
                    "source_url": "https://arxiv.org/abs/2402.12345",
                    "doi": "10.5555/different.doi",
                },
                {
                    "arxiv_id": "2403.12345",
                    "title": "TEST no DOI stays separate",
                    "source_url": "https://arxiv.org/abs/2403.12345",
                },
            ]
        },
        citations,
    )

    openalex = citations["openalex:W910"]
    assert citations["arxiv:2401.12345"] == openalex
    assert openalex.source == "openalex"
    assert openalex.doi == "https://doi.org/10.5555/Shared.DOI."
    assert [item.model_dump() for item in openalex.alternate_sources] == [
        {
            "source": "arxiv",
            "identifier": "2401.12345",
            "source_url": "https://arxiv.org/abs/2401.12345",
        }
    ]
    assert citations["arxiv:2402.12345"].source == "arxiv"
    assert citations["arxiv:2403.12345"].source == "arxiv"


def test_agent_can_call_arxiv_metadata_tool_and_validate_arxiv_citation() -> None:
    import app.sources.arxiv as arxiv_module

    temporary, store = _store_in_tempdir()
    arxiv_module._LAST_REQUEST_AT = None
    atom = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
          xmlns:arxiv="http://arxiv.org/schemas/atom">
      <opensearch:totalResults>1</opensearch:totalResults>
      <opensearch:startIndex>0</opensearch:startIndex>
      <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
      <entry><id>http://arxiv.org/abs/2401.12345v1</id>
        <title>Research source</title><summary>Metadata abstract</summary>
        <published>2024-01-01T00:00:00Z</published><updated>2024-01-01T00:00:00Z</updated>
        <author><name>Ada</name></author><arxiv:primary_category term="cs.AI" />
      </entry>
    </feed>"""
    try:
        with ArxivClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=atom)),
            sleep=lambda _: None,
        ) as arxiv:
            registry = PaperToolRegistry(store, arxiv=arxiv)
            assert len(registry.definitions) == 7
            model = FakeModel(
                [
                    _call_turn(
                        ModelToolCall(
                            "arxiv-call", "get_arxiv_metadata", '{"arxiv_id":"2401.12345"}'
                        )
                    ),
                    _final_turn(
                        "See the arXiv metadata record.", [], arxiv_citations=["2401.12345"]
                    ),
                ]
            )
            result = AgentHarness(model, registry).run("Find this arXiv work")

        assert result.status == "completed"
        assert result.citations[0].source == "arxiv"
        assert result.citations[0].arxiv_id == "2401.12345"
        assert result.citations[0].source_url == "https://arxiv.org/abs/2401.12345"
        assert result.citations[0].publication_year == 2024
    finally:
        temporary.cleanup()


def test_arxiv_tool_failure_is_traced_without_exposing_exception_or_retrying() -> None:
    import app.sources.arxiv as arxiv_module

    temporary, store = _store_in_tempdir()
    arxiv_module._LAST_REQUEST_AT = None

    request_count = 0

    def unavailable(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        raise httpx.ConnectError("TEST network failure with sensitive transport details")

    try:
        with ArxivClient(transport=httpx.MockTransport(unavailable), sleep=lambda _: None) as arxiv:
            registry = PaperToolRegistry(store, arxiv=arxiv)
            model = FakeModel(
                [
                    _call_turn(
                        ModelToolCall(
                            "arxiv-search",
                            "search_arxiv_metadata",
                            json.dumps(
                                {
                                    "query": "retrieval augmented generation",
                                    "limit": 3,
                                    "from_year": 2022,
                                    "to_year": 2024,
                                }
                            ),
                        )
                    ),
                    _call_turn(
                        ModelToolCall(
                            "arxiv-search-retry",
                            "search_arxiv_metadata",
                            json.dumps(
                                {
                                    "to_year": 2024,
                                    "limit": 3,
                                    "from_year": 2022,
                                    "query": "different follow-up query",
                                }
                            ),
                        )
                    ),
                    _final_turn("The arXiv source was unavailable.", [], insufficient=True),
                ]
            )
            result = AgentHarness(model, registry).run(
                "Search arXiv for retrieval augmented generation from 2022 through 2024"
            )

        failed_event = next(
            event for event in result.trace if event.name == "search_arxiv_metadata"
        )
        assert failed_event.status == "error"
        assert failed_event.error_code == "arxiv_unavailable"
        failed_events = [event for event in result.trace if event.name == "search_arxiv_metadata"]
        assert [event.error_code for event in failed_events] == [
            "arxiv_unavailable",
            "source_unavailable_after_failure",
        ]
        assert request_count == 1
        assert result.warnings == [
            "tool_error:search_arxiv_metadata:arxiv_unavailable",
            "tool_error:search_arxiv_metadata:source_unavailable_after_failure",
        ]
        assert "TEST network failure" not in result.model_dump_json()
        assert "at most once" in model.instructions[0]
    finally:
        temporary.cleanup()


def test_harness_only_returns_citations_observed_from_tool_results() -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                _call_turn(ModelToolCall("call-1", "get_paper_details", '{"openalex_id":"W100"}')),
                _final_turn("This paper is in the local catalog.", ["W100"]),
            ]
        )
        result = AgentHarness(model, PaperToolRegistry(store)).run(
            "Find a research assistant paper"
        )

        assert result.status == "completed"
        assert [citation.openalex_id for citation in result.citations] == ["W100"]
        assert result.model_input_tokens == 22
        assert result.model_output_tokens == 10
        assert result.run_id
        assert result.duration_ms >= 0
        assert [(event.kind, event.name, event.status) for event in result.trace] == [
            ("model", "responses", "ok"),
            ("tool", "get_paper_details", "ok"),
            ("model", "responses", "ok"),
        ]
        assert all(
            set(event.model_fields_set)
            <= {
                "sequence",
                "kind",
                "name",
                "status",
                "duration_ms",
                "error_code",
                "input_tokens",
                "output_tokens",
            }
            for event in result.trace
        )
        assert "untrusted data" in model.instructions[0]
        assert model.inputs[1][-1]["type"] == "function_call_output"
    finally:
        temporary.cleanup()


def test_harness_rejects_forged_citations_and_unstructured_facts() -> None:
    temporary, store = _store_in_tempdir()
    try:
        forged = FakeModel(
            [
                _call_turn(ModelToolCall("call-1", "get_paper_details", '{"openalex_id":"W100"}')),
                _final_turn("See W999 for proof.", ["W999"]),
            ]
        )
        result = AgentHarness(forged, PaperToolRegistry(store)).run("Compare these papers")

        assert result.status == "unverified_citations"
        assert result.citations == []
        assert "W999" not in result.answer

        no_citations = FakeModel([_final_turn("An unsupported claim.", [])])
        refused = AgentHarness(no_citations, PaperToolRegistry(store)).run(
            "What did the paper prove?"
        )
        assert refused.status == "insufficient_evidence"
        assert "unsupported claim" not in refused.answer
    finally:
        temporary.cleanup()


def test_harness_enforces_tool_call_budget_and_handles_provider_failure() -> None:
    temporary, store = _store_in_tempdir()
    try:
        two_calls = FakeModel(
            [
                _call_turn(
                    ModelToolCall("call-1", "get_paper_details", '{"openalex_id":"W100"}'),
                    ModelToolCall("call-2", "get_paper_details", '{"openalex_id":"W100"}'),
                )
            ]
        )
        limited = AgentHarness(two_calls, PaperToolRegistry(store), max_tool_calls=1).run(
            "Read this paper"
        )
        assert limited.status == "tool_budget_exceeded"
        assert limited.tool_calls == 0

        class FailingModel:
            def complete(self, **_kwargs) -> ModelTurn:
                raise ModelUnavailable("safe error")

        unavailable = AgentHarness(FailingModel(), PaperToolRegistry(store)).run("Find papers")
        assert unavailable.status == "model_unavailable"
        assert "safe error" not in unavailable.answer
    finally:
        temporary.cleanup()


def test_harness_enforces_decision_step_and_deadline_limits() -> None:
    temporary, store = _store_in_tempdir()
    try:
        repeated = _call_turn(
            ModelToolCall("call-1", "get_paper_details", '{"openalex_id":"W100"}')
        )
        step_limited = AgentHarness(
            FakeModel([repeated]), PaperToolRegistry(store), max_steps=1
        ).run("Find this paper")
        assert step_limited.status == "max_steps_exceeded"
        assert step_limited.tool_calls == 1

        clock_values = iter((0.0, 0.0, 46.0))
        deadline_limited = AgentHarness(
            FakeModel([_final_turn("", [], insufficient=True)]),
            PaperToolRegistry(store),
            deadline_seconds=45,
            clock=lambda: next(clock_values, 46.0),
        ).run("Find a paper")
        assert deadline_limited.status == "deadline_exceeded"
    finally:
        temporary.cleanup()


def test_harness_handles_refusal_duplicate_calls_and_malformed_final_json() -> None:
    temporary, store = _store_in_tempdir()
    try:
        refusal = ModelTurn([], [], None, True, 0, 0)
        refused = AgentHarness(FakeModel([refusal]), PaperToolRegistry(store)).run("Question")
        assert refused.status == "model_refusal"

        repeated_call = _call_turn(
            ModelToolCall("duplicate", "get_paper_details", '{"openalex_id":"W100"}')
        )
        duplicate = AgentHarness(
            FakeModel([repeated_call, repeated_call]), PaperToolRegistry(store), max_steps=3
        ).run("Question")
        assert duplicate.status == "invalid_model_output"

        malformed = ModelTurn([], [], "not-json", False, 0, 0)
        invalid = AgentHarness(FakeModel([malformed]), PaperToolRegistry(store), max_steps=1).run(
            "Question"
        )
        assert invalid.status == "invalid_model_output"
        assert invalid.warnings == ["structured_output_repair_skipped_budget"]
    finally:
        temporary.cleanup()


def test_malformed_final_answer_gets_one_tool_free_repair_and_keeps_citation_validation() -> None:
    temporary, store = _store_in_tempdir()
    try:
        malformed = ModelTurn([], [], "not-json", False, 12, 3)
        model = FakeModel(
            [
                _call_turn(ModelToolCall("details", "get_paper_details", '{"openalex_id":"W100"}')),
                malformed,
                _final_turn("TEST metadata-only result [W100]", ["W100"]),
            ]
        )
        result = AgentHarness(model, PaperToolRegistry(store), max_steps=3).run(
            "Describe the retrieved paper metadata"
        )

        assert result.status == "completed"
        assert result.model_steps == 3
        assert result.tool_calls == 1
        assert result.warnings == [
            "structured_output_repair_attempted",
            "structured_output_invalid_json",
        ]
        assert [item.openalex_id for item in result.citations] == ["W100"]
        assert model.tool_sets[2] == []
        assert "Do not call tools" in model.inputs[2][-1]["content"]
        assert "Lack of full text alone is not a reason" in model.inputs[2][-1]["content"]

        malicious_repair = FakeModel(
            [
                _call_turn(ModelToolCall("details", "get_paper_details", '{"openalex_id":"W100"}')),
                malformed,
                _call_turn(ModelToolCall("shell", "shell", "{}")),
            ]
        )
        rejected = AgentHarness(malicious_repair, PaperToolRegistry(store), max_steps=3).run(
            "Describe the retrieved paper metadata"
        )
        assert rejected.status == "invalid_model_output"
        assert rejected.tool_calls == 1
        assert rejected.warnings == [
            "structured_output_repair_attempted",
            "structured_output_invalid_json",
            "structured_output_repair_called_tool",
        ]
        assert [event.name for event in rejected.trace if event.kind == "tool"] == [
            "get_paper_details"
        ]
    finally:
        temporary.cleanup()


def test_failed_structured_answer_repair_still_rejects_invalid_output() -> None:
    temporary, store = _store_in_tempdir()
    try:
        malformed = ModelTurn([], [], "not-json", False, 0, 0)
        result = AgentHarness(
            FakeModel([malformed, malformed]), PaperToolRegistry(store), max_steps=2
        ).run("Question")

        assert result.status == "invalid_model_output"
        assert result.model_steps == 2
        assert result.warnings == [
            "structured_output_repair_attempted",
            "structured_output_invalid_json",
            "structured_output_invalid_json",
            "structured_output_repair_failed",
        ]
    finally:
        temporary.cleanup()


def test_structured_output_diagnostics_are_content_free_and_classify_schema_errors() -> None:
    assert _output_diagnostic_warnings(None) == ["structured_output_empty"]
    assert _output_diagnostic_warnings("not json") == ["structured_output_invalid_json"]
    assert _output_diagnostic_warnings('{"answer":"private text"}') == [
        "structured_output_schema_invalid"
    ]
    valid_schema_but_unverified = json.dumps(
        {
            "answer": "A result [W999]",
            "cited_openalex_ids": ["W999"],
            "cited_arxiv_ids": [],
            "insufficient_evidence": False,
        }
    )
    assert _output_diagnostic_warnings(valid_schema_but_unverified) == [
        "structured_output_citation_validation_failed"
    ]


def test_agent_route_is_disabled_by_default_and_validates_request() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        settings = Settings(_env_file=None, data_storage_path=Path(temp_dir) / "empty.sqlite3")
        from fastapi.testclient import TestClient

        client = TestClient(create_app(settings))
        disabled = client.post("/api/v1/agent/ask", json={"question": "find RAG papers"})
        invalid = client.post("/api/v1/agent/ask", json={"question": "x", "shell": "whoami"})

    assert disabled.status_code == 503
    assert disabled.json()["status"] == "model_disabled"
    assert invalid.status_code == 422


def test_agent_route_forwards_search_context_and_conversation(monkeypatch) -> None:
    observed: dict[str, object] = {}

    class FakeAgentService:
        def __init__(self, _settings, _store) -> None:
            pass

        def ask(self, question, *, history, search_context):
            observed.update(
                question=question,
                history=[turn.model_dump() for turn in history],
                search_context=search_context.model_dump() if search_context else None,
            )
            return AgentResponse(status="completed", answer="TEST response")

    monkeypatch.setattr("app.main.AgentService", FakeAgentService)
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        client = TestClient(
            create_app(Settings(_env_file=None, data_storage_path=Path(temp_dir) / "db.sqlite3"))
        )
        response = client.post(
            "/api/v1/agent/ask",
            json={
                "question": "Based on those results, list years.",
                "history": [
                    {"role": "user", "content": "Search VR papers."},
                    {"role": "assistant", "content": "TEST prior answer."},
                ],
                "search_context": {
                    "source": "openalex",
                    "query": "Virtual Reality",
                    "from_year": 2022,
                    "to_year": 2024,
                    "pages": 2,
                },
            },
        )

    assert response.status_code == 200
    assert observed["question"] == "Based on those results, list years."
    assert len(observed["history"]) == 2
    assert observed["search_context"] == {
        "source": "openalex",
        "query": "Virtual Reality",
        "from_year": 2022,
        "to_year": 2024,
        "pages": 2,
    }


def test_responses_adapter_uses_fixed_endpoint_strict_tools_and_server_secret() -> None:
    observed: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers.get("Authorization")
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": "in_progress",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "search_papers",
                        "arguments": '{"query":"RAG","limit":5}',
                    }
                ],
                "usage": {"input_tokens": 20, "output_tokens": 5},
            },
        )

    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        llm_api_key="api-secret",
        llm_model="test-model",
    )
    transport = httpx.MockTransport(respond)
    client = httpx.Client(transport=transport)
    provider = OpenAIResponsesClient(settings, http_client=client)
    try:
        turn = provider.complete(
            instructions="safe system prompt",
            input_items=[{"role": "user", "content": "RAG"}],
            tools=PaperToolRegistry(PaperStore(Path("unused.sqlite3"))).definitions,
        )
    finally:
        client.close()

    payload = observed["payload"]
    assert observed["url"] == "https://api.openai.com/v1/responses"
    assert observed["authorization"] == "Bearer api-secret"
    assert "api-secret" not in json.dumps(payload)
    assert payload["store"] is False
    assert payload["parallel_tool_calls"] is False
    assert payload["tools"][0]["strict"] is True
    assert turn.tool_calls[0].name == "search_papers"
    assert (turn.input_tokens, turn.output_tokens) == (20, 5)


def test_responses_adapter_does_not_surface_provider_error_body() -> None:
    def unauthorized(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="secret api-secret leaked in provider body")

    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        llm_api_key="api-secret",
        llm_model="test-model",
    )
    client = httpx.Client(transport=httpx.MockTransport(unauthorized))
    provider = OpenAIResponsesClient(settings, http_client=client)
    try:
        with pytest.raises(ModelUnavailable) as error:
            provider.complete(instructions="", input_items=[], tools=[])
    finally:
        client.close()

    assert "401" in str(error.value)
    assert "api-secret" not in str(error.value)
    assert "leaked" not in str(error.value)


def test_compare_contract_rejects_duplicate_or_invalid_ids() -> None:
    assert ComparePapersArgs(openalex_ids=["W100", "W200"]).openalex_ids == ["W100", "W200"]
    with pytest.raises(ValueError):
        ComparePapersArgs(openalex_ids=["W100", "W100"])
    with pytest.raises(ValueError):
        ComparePapersArgs(openalex_ids=["W100", "https://openalex.org/W200"])


def test_tool_registry_reports_no_approved_full_text_as_no_results() -> None:
    temporary, store = _store_in_tempdir()
    try:
        result = PaperToolRegistry(store).execute(
            "retrieve_paper_evidence",
            '{"query":"experimental findings","limit":5,"source_type":"openalex",'
            '"source_id":"W100"}',
        )
        assert result["status"] == "no_results"
        assert result["items"] == []
    finally:
        temporary.cleanup()


def test_agent_rag_citation_contains_license_attribution_and_verified_chunk() -> None:
    temporary, store = _store_in_tempdir()
    try:
        store.ingest_licensed_fulltext(
            source_type="openalex",
            source_id="W100",
            text="Retrieval evidence supports answers with traceable citations.",
            text_source_url="https://repository.example.org/paper.txt",
            license_id="CC-BY-4.0",
            license_url="https://creativecommons.org/licenses/by/4.0/",
            license_evidence_url="https://repository.example.org/license",
            reviewer="local-project-owner",
            attribution="A. Author, Retrieval systems for research assistants, CC BY 4.0",
            confirm_license_reviewed=True,
        )
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall(
                        "evidence-1",
                        "retrieve_paper_evidence",
                        '{"query":"traceable evidence citations","limit":3,'
                        '"source_type":"openalex","source_id":"W100"}',
                    )
                ),
                _final_turn("W100 supports the statement; see its cited passage.", ["W100"]),
            ]
        )
        response = AgentHarness(model, PaperToolRegistry(store)).run(
            "Find licensed evidence about citations"
        )

        assert response.status == "completed"
        assert len(response.citations) == 1
        citation = response.citations[0]
        assert citation.license_id == "CC-BY-4.0"
        assert citation.attribution.startswith("A. Author")
        assert citation.evidence[0].chunk_id.startswith("openalex:W100:")
        assert "traceable citations" in citation.evidence[0].excerpt
        assert "excerpts from the licensed evidence tool" in model.instructions[0]
        assert "traceable citations" in model.inputs[1][-1]["output"]
    finally:
        temporary.cleanup()
