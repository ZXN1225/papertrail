from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.agent.contracts import ComparePapersArgs
from app.agent.harness import AgentHarness
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

    def complete(
        self, *, instructions: str, input_items: list[dict], tools: list[dict]
    ) -> ModelTurn:
        self.instructions.append(instructions)
        self.inputs.append(input_items.copy())
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
            assert len(registry.definitions) == 10
        assert available["status"] == "ok"
        assert available["items"][0]["openalex_id"] == "W900"
        assert available["items"][0]["abstract"] == "Evidence test"
        assert requests[0].url.host == "api.openalex.org"
        assert requests[0].url.path == "/works"
    finally:
        temporary.cleanup()


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
        invalid = AgentHarness(FakeModel([malformed]), PaperToolRegistry(store)).run("Question")
        assert invalid.status == "invalid_model_output"
    finally:
        temporary.cleanup()


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
