from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.agent.contracts import (
    AgentQuestion,
    AgentTurn,
    ComparePapersArgs,
    RetrieveEvidenceArgs,
)
from app.agent.harness import AgentHarness, _collect_citations
from app.agent.model import (
    ModelToolCall,
    ModelTurn,
    ModelUnavailable,
    OpenAIResponsesClient,
)
from app.agent.tools import PaperToolRegistry
from app.config import Settings
from app.embeddings.client import EmbeddingBatch, EmbeddingError
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
        self.tool_names: list[set[str]] = []
        self.output_token_limits: list[int | None] = []

    def complete(
        self,
        *,
        instructions: str,
        input_items: list[dict],
        tools: list[dict],
        max_output_tokens: int | None = None,
    ) -> ModelTurn:
        self.instructions.append(instructions)
        self.inputs.append(input_items.copy())
        self.tool_names.append({tool["name"] for tool in tools})
        self.output_token_limits.append(max_output_tokens)
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
    personal_citations: list[str] | None = None,
    claims: list[dict] | None = None,
) -> ModelTurn:
    return ModelTurn(
        tool_calls=[],
        continuation_items=[],
        final_text=json.dumps(
            {
                "answer": answer,
                "cited_openalex_ids": citations,
                "cited_arxiv_ids": arxiv_citations or [],
                "cited_personal_ids": personal_citations or [],
                "claims": claims or [],
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


def test_no_results_is_visible_in_tool_trace() -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall(
                        "TEST-empty",
                        "retrieve_paper_evidence",
                        '{"query":"TEST nonmatching","limit":3}',
                    )
                ),
                _final_turn("TEST insufficient", [], insufficient=True),
            ]
        )
        result = AgentHarness(model, PaperToolRegistry(store), skills_enabled=False).run(
            "TEST search"
        )
        assert result.status == "insufficient_evidence"
        assert [event.status for event in result.trace if event.kind == "tool"] == ["no_results"]
    finally:
        temporary.cleanup()


def test_large_retrieval_observation_retains_complete_top_ranked_items() -> None:
    temporary, store = _store_in_tempdir()

    class LargeRegistry(PaperToolRegistry):
        def execute(self, name, arguments, **kwargs):
            return {
                "status": "ok",
                "items": [
                    {"excerpt": "TEST-" + str(index) + "x" * 12000, "retrieval_context": "y" * 1000}
                    for index in range(8)
                ],
            }

    try:
        model = FakeModel(
            [
                _call_turn(ModelToolCall("TEST-large", "retrieve_paper_evidence", "{}")),
                _final_turn("", [], insufficient=True),
            ]
        )
        result = AgentHarness(model, LargeRegistry(store), skills_enabled=False).run("TEST large")
        output = next(
            item for item in model.inputs[-1] if item.get("type") == "function_call_output"
        )
        observed = json.loads(output["output"])
        assert result.status == "insufficient_evidence"
        assert 1 <= len(observed["items"]) < 8
        assert observed["items"][0]["excerpt"] == "TEST-0" + "x" * 12000
        assert all("retrieval_context" not in item for item in observed["items"])
        assert [event.status for event in result.trace if event.kind == "tool"] == ["ok"]
    finally:
        temporary.cleanup()


@pytest.mark.parametrize("arxiv_status", ["ok", "error", "no_results"])
def test_external_search_uses_both_sources_reserves_final_turn_and_reports_partial(arxiv_status):
    temporary, store = _store_in_tempdir()

    class SearchRegistry(PaperToolRegistry):
        def execute(self, name, arguments, **kwargs):
            assert name in kwargs["allowed_names"]
            if name == "search_openalex_works":
                return {
                    "status": "ok",
                    "items": [
                        {
                            "openalex_id": "W100",
                            "title": "TEST openalex paper",
                            "source_url": "https://openalex.org/W100",
                        }
                    ],
                }
            if arxiv_status != "ok":
                return {"status": arxiv_status, "code": "arxiv_unavailable"}
            return {
                "status": "ok",
                "items": [
                    {
                        "arxiv_id": "2401.12345",
                        "title": "TEST arxiv paper",
                        "source_url": "https://arxiv.org/abs/2401.12345",
                    }
                ],
            }

    claims = [
        {
            "text": "TEST openalex paper",
            "evidence": [
                {
                    "source_id": "W100",
                    "quote": "TEST openalex paper",
                    "evidence_type": "metadata",
                    "source_field": "title",
                    "chunk_id": None,
                }
            ],
        }
    ]
    if arxiv_status == "ok":
        claims.append(
            {
                "text": "TEST arxiv paper",
                "evidence": [
                    {
                        "source_id": "2401.12345",
                        "quote": "TEST arxiv paper",
                        "evidence_type": "metadata",
                        "source_field": "title",
                        "chunk_id": None,
                    }
                ],
            }
        )
    try:
        with (
            OpenAlexClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as oa,
            ArxivClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as arxiv,
        ):
            model = FakeModel(
                [
                    _call_turn(
                        ModelToolCall(
                            "TEST-oa", "search_openalex_works", '{"query":"TEST","limit":3}'
                        )
                    ),
                    _call_turn(
                        ModelToolCall(
                            "TEST-ax", "search_arxiv_metadata", '{"query":"TEST","limit":3}'
                        )
                    ),
                    _final_turn(
                        "",
                        ["W100"],
                        arxiv_citations=["2401.12345"] if arxiv_status == "ok" else [],
                        claims=claims,
                    ),
                ]
            )
            result = AgentHarness(model, SearchRegistry(store, oa, arxiv), max_steps=3).run(
                "在OpenAlex和Arxiv中搜索三篇相关论文"
            )
            assert result.status == "completed"
            assert model.tool_names[0] == {"search_openalex_works", "search_arxiv_metadata"}
            assert model.tool_names[-1] == set()
            if arxiv_status == "error":
                assert "arXiv 搜索失败" in result.answer
            elif arxiv_status == "no_results":
                assert "arXiv 本次没有找到" in result.answer
            else:
                assert {c.source for c in result.citations} == {"openalex", "arxiv"}
    finally:
        temporary.cleanup()


def test_mixed_library_and_online_request_requires_both_steps() -> None:
    temporary, store = _store_in_tempdir()

    class SearchRegistry(PaperToolRegistry):
        def execute(self, name, arguments, **kwargs):
            assert name in kwargs["allowed_names"]
            if name == "search_openalex_works":
                return {"status": "no_results", "items": []}
            if name == "retrieve_paper_evidence":
                return {"status": "no_results", "items": []}
            raise AssertionError(name)

    try:
        with OpenAlexClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as oa:
            model = FakeModel(
                [
                    _call_turn(
                        ModelToolCall(
                            "TEST-online", "search_openalex_works", '{"query":"TEST","limit":3}'
                        )
                    ),
                    _call_turn(
                        ModelToolCall(
                            "TEST-local", "retrieve_paper_evidence", '{"query":"TEST","limit":3}'
                        )
                    ),
                    _final_turn("", [], insufficient=True),
                ]
            )
            registry = SearchRegistry(store, oa, user_id="TEST-owner")
            result = AgentHarness(model, registry, max_steps=3).run(
                "结合我的论文库并在OpenAlex搜索相关研究"
            )
            assert result.status == "insufficient_evidence"
            assert model.tool_names[0] == {"search_openalex_works", "retrieve_paper_evidence"}
            assert registry.library_only
            assert [event.name for event in result.trace if event.kind == "tool"] == [
                "search_openalex_works",
                "retrieve_paper_evidence",
            ]
    finally:
        temporary.cleanup()


def test_mixed_source_task_rejects_early_answer_without_local_retrieval() -> None:
    temporary, store = _store_in_tempdir()

    class SearchRegistry(PaperToolRegistry):
        def execute(self, name, arguments, **kwargs):
            assert name == "search_openalex_works"
            return {"status": "no_results", "items": []}

    try:
        with OpenAlexClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as oa:
            model = FakeModel(
                [
                    _call_turn(
                        ModelToolCall(
                            "TEST-online", "search_openalex_works", '{"query":"TEST","limit":3}'
                        )
                    ),
                    _final_turn("", [], insufficient=True),
                ]
            )
            result = AgentHarness(model, SearchRegistry(store, oa), max_steps=2).run(
                "结合我的论文库并在OpenAlex搜索相关研究"
            )
            assert result.status == "workflow_incomplete"
    finally:
        temporary.cleanup()


def test_mixed_source_repairs_answer_omitting_retrieved_local_evidence() -> None:
    temporary, store = _store_in_tempdir()

    class SearchRegistry(PaperToolRegistry):
        def execute(self, name, arguments, **kwargs):
            if name == "search_openalex_works":
                return {
                    "status": "ok",
                    "items": [
                        {
                            "openalex_id": "W100",
                            "title": "TEST public paper",
                            "source_url": "https://openalex.org/W100",
                        }
                    ],
                }
            return {
                "status": "ok",
                "items": [
                    {
                        "arxiv_id": "2401.12345",
                        "title": "TEST local paper",
                        "source_url": "https://arxiv.org/abs/2401.12345",
                        "private_processing": True,
                        "chunk_id": "private:TEST:1",
                        "locator": "page 1",
                        "excerpt": "TEST local evidence",
                    }
                ],
            }

    public = {
        "text": "TEST public paper",
        "evidence": [
            {
                "source_id": "W100",
                "quote": "TEST public paper",
                "evidence_type": "metadata",
                "source_field": "title",
                "chunk_id": None,
            }
        ],
    }
    local = {
        "text": "TEST local evidence",
        "evidence": [
            {
                "source_id": "2401.12345",
                "quote": "TEST local evidence",
                "evidence_type": "fulltext",
                "source_field": "excerpt",
                "chunk_id": "private:TEST:1",
            }
        ],
    }
    try:
        with OpenAlexClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as oa:
            model = FakeModel(
                [
                    _call_turn(
                        ModelToolCall("TEST-online", "search_openalex_works", "{}"),
                        ModelToolCall("TEST-local", "retrieve_paper_evidence", "{}"),
                    ),
                    _final_turn("", ["W100"], claims=[public]),
                    _final_turn(
                        "", ["W100"], arxiv_citations=["2401.12345"], claims=[public, local]
                    ),
                ]
            )
            result = AgentHarness(model, SearchRegistry(store, oa), max_steps=4).run(
                "结合我的论文库并在OpenAlex搜索相关研究"
            )
            assert result.status == "completed"
            assert len(result.claims) == 2
            assert model.tool_names[-1] == set()
    finally:
        temporary.cleanup()


def test_incomplete_provider_output_is_reported_without_parsing_partial_json() -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel([ModelTurn([], [], '{"answer":', False, 10, 20, incomplete=True)])
        result = AgentHarness(model, PaperToolRegistry(store)).run("TEST output limit")
        assert result.status == "invalid_model_output"
        assert result.warnings == ["model_output_incomplete"]
        assert not result.citations
        assert result.trace[-1].status == "incomplete"
    finally:
        temporary.cleanup()


def test_truncated_final_retries_once_using_only_existing_evidence() -> None:
    temporary, store = _store_in_tempdir()
    try:
        claim = "TEST paper is in the catalog."
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall("TEST-details", "get_paper_details", '{"openalex_id":"W100"}')
                ),
                ModelTurn(
                    [],
                    [],
                    None,
                    False,
                    10,
                    20,
                    incomplete=True,
                    incomplete_reason="max_output_tokens",
                ),
                _final_turn(
                    claim,
                    ["W100"],
                    claims=[
                        {
                            "text": claim,
                            "evidence": [
                                {
                                    "source_id": "W100",
                                    "quote": "Retrieval systems for research assistants",
                                    "evidence_type": "metadata",
                                    "source_field": "title",
                                    "chunk_id": None,
                                }
                            ],
                        }
                    ],
                ),
            ]
        )
        result = AgentHarness(model, PaperToolRegistry(store), skills_enabled=False).run(
            "TEST paper"
        )
        assert result.status == "completed"
        assert result.model_steps == 3
        assert model.tool_names[-1] == set()
    finally:
        temporary.cleanup()


def test_content_filter_incomplete_does_not_trigger_output_retry() -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall("TEST-details", "get_paper_details", '{"openalex_id":"W100"}')
                ),
                ModelTurn(
                    [], [], None, False, 10, 20, incomplete=True, incomplete_reason="content_filter"
                ),
            ]
        )
        result = AgentHarness(model, PaperToolRegistry(store), skills_enabled=False).run(
            "TEST paper"
        )
        assert result.status == "invalid_model_output"
        assert result.model_steps == 2
        assert len(model.inputs) == 2
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
                        "The arXiv record https://arxiv.org/abs/2401.12345v1 "
                        "is titled Research source.",
                        [],
                        arxiv_citations=["2401.12345"],
                        claims=[
                            {
                                "text": (
                                    "The arXiv record https://arxiv.org/abs/2401.12345v1 "
                                    "is titled Research source."
                                ),
                                "evidence": [
                                    {
                                        "source_id": "2401.12345",
                                        "quote": "Research source",
                                        "evidence_type": "metadata",
                                        "source_field": "title",
                                        "chunk_id": None,
                                    }
                                ],
                            }
                        ],
                    ),
                ]
            )
            result = AgentHarness(model, registry, max_total_tokens=20_000).run(
                "Find this arXiv work"
            )

            uncited_model = FakeModel(
                [
                    _call_turn(
                        ModelToolCall(
                            "arxiv-call-2", "get_arxiv_metadata", '{"arxiv_id":"2401.12345"}'
                        )
                    ),
                    _final_turn(
                        "This result is https://arxiv.org/abs/2401.12345v1.",
                        [],
                    ),
                    _final_turn(
                        "The arXiv record https://arxiv.org/abs/2401.12345v1 "
                        "is titled Research source.",
                        [],
                        arxiv_citations=["2401.12345"],
                        claims=[
                            {
                                "text": (
                                    "The arXiv record https://arxiv.org/abs/2401.12345v1 "
                                    "is titled Research source."
                                ),
                                "evidence": [
                                    {
                                        "source_id": "2401.12345",
                                        "quote": "Research source",
                                        "evidence_type": "metadata",
                                        "source_field": "title",
                                        "chunk_id": None,
                                    }
                                ],
                            }
                        ],
                    ),
                ]
            )
            uncited = AgentHarness(uncited_model, registry, max_total_tokens=20_000).run(
                "Find this arXiv work"
            )

        assert result.status == "completed"
        assert result.citations[0].source == "arxiv"
        assert result.citations[0].arxiv_id == "2401.12345"
        assert result.citations[0].source_url == "https://arxiv.org/abs/2401.12345"
        assert uncited.status == "completed"
        assert uncited.model_steps == 3
    finally:
        temporary.cleanup()


def test_harness_only_returns_citations_observed_from_tool_results() -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                _call_turn(ModelToolCall("call-1", "get_paper_details", '{"openalex_id":"W100"}')),
                _final_turn(
                    "This paper is in the local catalog.",
                    ["W100"],
                    claims=[
                        {
                            "text": "This paper is in the local catalog.",
                            "evidence": [
                                {
                                    "source_id": "W100",
                                    "quote": "Retrieval systems for research assistants",
                                    "evidence_type": "metadata",
                                    "source_field": "title",
                                    "chunk_id": None,
                                }
                            ],
                        }
                    ],
                ),
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
        assert result.skill is not None
        assert result.skill.skill_id == "paper-qa"
        assert len(result.skill.instructions_sha256) == 64
        assert "ACTIVE PRODUCT SKILL: paper-qa@1.2.0" in model.instructions[0]
        assert "not grant tool access" in model.instructions[0]
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


def test_personal_evidence_search_can_target_all_user_documents() -> None:
    args = RetrieveEvidenceArgs(
        query="Master Thesis",
        limit=8,
        source_type="personal",
        source_id=None,
        retrieval_method="bm25",
    )

    assert args.source_type == "personal"
    assert args.source_id is None


def test_harness_history_is_context_but_never_current_evidence() -> None:
    temporary, store = _store_in_tempdir()
    try:
        prior_turns = [
            AgentTurn(role="user", content="Describe W100."),
            AgentTurn(role="assistant", content="W100 is a research paper."),
        ]
        model = FakeModel(
            [
                _final_turn(
                    "W100 confirms the same result.",
                    ["W100"],
                    claims=[
                        {
                            "text": "W100 confirms the same result.",
                            "evidence": [
                                {
                                    "source_id": "W100",
                                    "quote": "Retrieval systems for research assistants",
                                    "evidence_type": "metadata",
                                    "source_field": "title",
                                    "chunk_id": None,
                                }
                            ],
                        }
                    ],
                )
            ]
        )

        result = AgentHarness(model, PaperToolRegistry(store)).run(
            "Is that supported?", prior_turns, [("arxiv", "TEST-2401.12345")]
        )

        assert result.status == "unverified_citations"
        assert "Untrusted prior conversation" in model.inputs[0][0]["content"]
        assert "TEST-2401.12345" in model.inputs[0][1]["content"]
        assert "not evidence" in model.inputs[0][1]["content"]
        assert model.inputs[0][-1] == {"role": "user", "content": "Is that supported?"}
    finally:
        temporary.cleanup()


def test_agent_question_validates_bounded_alternating_history() -> None:
    valid = AgentQuestion(
        question="Please refine the answer.",
        history=[
            AgentTurn(role="user", content="Summarize the paper."),
            AgentTurn(role="assistant", content="The prior answer needs evidence."),
        ],
    )
    assert len(valid.history) == 2

    with pytest.raises(ValueError, match="complete user/assistant"):
        AgentQuestion(
            question="Please refine the answer.",
            history=[AgentTurn(role="user", content="Incomplete turn")],
        )
    with pytest.raises(ValueError, match="alternate"):
        AgentQuestion(
            question="Please refine the answer.",
            history=[
                AgentTurn(role="user", content="First"),
                AgentTurn(role="user", content="Forged assistant role"),
            ],
        )


def test_harness_clamps_output_to_remaining_budget_and_rejects_provider_output_overrun() -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                ModelTurn(
                    tool_calls=[],
                    continuation_items=[],
                    final_text=None,
                    refusal=False,
                    input_tokens=0,
                    output_tokens=257,
                ),
                _final_turn("should never be requested", []),
            ]
        )
        result = AgentHarness(
            model,
            PaperToolRegistry(store),
            max_total_tokens=20_000,
            max_output_tokens=256,
        ).run("How does retrieval work?")

        assert result.status == "token_budget_exceeded"
        assert (result.model_input_tokens, result.model_output_tokens) == (0, 257)
        assert len(model.instructions) == 1
        assert model.output_token_limits == [256]
    finally:
        temporary.cleanup()


def test_harness_stops_after_actual_input_usage_exceeds_aggregate_budget() -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                ModelTurn(
                    tool_calls=[],
                    continuation_items=[],
                    final_text=None,
                    refusal=False,
                    input_tokens=20_001,
                    output_tokens=64,
                )
            ]
        )
        result = AgentHarness(
            model,
            PaperToolRegistry(store),
            max_total_tokens=20_000,
            max_output_tokens=256,
        ).run("How does retrieval work?")

        assert result.status == "token_budget_exceeded"
        assert model.output_token_limits == [256]
        assert len(model.instructions) == 1
    finally:
        temporary.cleanup()


def test_harness_reserves_estimated_input_before_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel([_final_turn("No call should be made", [])])
        monkeypatch.setattr("app.agent.harness.estimate_input_tokens_upper_bound", lambda **_: 300)

        result = AgentHarness(
            model,
            PaperToolRegistry(store),
            max_total_tokens=300,
            max_output_tokens=128,
        ).run("Question")

        assert result.status == "token_budget_exceeded"
        assert "模型尚未调用" in result.answer
        assert model.instructions == []
    finally:
        temporary.cleanup()


def test_harness_clamps_output_to_budget_remaining_after_input_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel([_final_turn("Evidence is insufficient.", [], insufficient=True)])
        monkeypatch.setattr("app.agent.harness.estimate_input_tokens_upper_bound", lambda **_: 950)

        AgentHarness(
            model,
            PaperToolRegistry(store),
            max_total_tokens=1_000,
            max_output_tokens=128,
        ).run("Question")

        assert model.output_token_limits == [50]
    finally:
        temporary.cleanup()


def test_harness_stops_if_provider_input_usage_exceeds_preflight_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                ModelTurn(
                    tool_calls=[],
                    continuation_items=[],
                    final_text=None,
                    refusal=False,
                    input_tokens=201,
                    output_tokens=1,
                )
            ]
        )
        monkeypatch.setattr("app.agent.harness.estimate_input_tokens_upper_bound", lambda **_: 200)

        result = AgentHarness(
            model,
            PaperToolRegistry(store),
            max_total_tokens=1_000,
            max_output_tokens=128,
        ).run("Question")

        assert result.status == "token_budget_exceeded"
        assert len(model.instructions) == 1
    finally:
        temporary.cleanup()


def test_unregistered_model_tool_name_is_redacted_from_response_and_persisted_trace() -> None:
    temporary, store = _store_in_tempdir()
    try:
        secret = "TEST-SECRET private question text"
        model = FakeModel(
            [
                _call_turn(ModelToolCall("call-secret", secret, "{}")),
                _final_turn("Evidence is insufficient.", [], insufficient=True),
            ]
        )
        result = AgentHarness(model, PaperToolRegistry(store)).run(secret)
        run_id = str(uuid4())
        assert store.create_agent_run(run_id, secret)
        store.finish_agent_run(run_id, result)
        persisted = store.get_agent_run(run_id)

        serialized = json.dumps(
            {"response": result.model_dump(mode="json"), "persisted": persisted},
            ensure_ascii=False,
        )
        assert result.status == "insufficient_evidence"
        assert any(event.name == "unknown_tool" for event in result.trace)
        assert persisted is not None
        assert persisted["status"] == "completed"
        assert persisted["result_status"] == "insufficient_evidence"
        assert secret not in serialized
    finally:
        temporary.cleanup()


def test_personal_paper_question_cannot_call_arxiv_metadata() -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall(
                        "call-arxiv",
                        "get_arxiv_metadata",
                        '{"arxiv_id":"2401.12345"}',
                    )
                ),
                _final_turn("Evidence is insufficient.", [], insufficient=True),
            ]
        )
        result = AgentHarness(model, PaperToolRegistry(store)).run(
            "根据我已入库的论文(Master Thesis)解释论文的发现"
        )

        assert model.tool_names[0] == {"retrieve_paper_evidence"}
        assert "source_type='personal'" in model.instructions[0]
        assert result.status == "workflow_incomplete"
        assert all(event.name != "get_arxiv_metadata" for event in result.trace)
    finally:
        temporary.cleanup()


def test_saved_paper_followup_does_not_expose_arxiv_tools() -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                _call_turn(ModelToolCall("TEST-call", "get_arxiv_metadata", "{}")),
                _final_turn("TEST insufficient", [], insufficient=True),
            ]
        )
        history = [
            AgentTurn(role="user", content="比较我的论文库中的两篇论文"),
            AgentTurn(role="assistant", content="TEST comparison"),
        ]
        result = AgentHarness(model, PaperToolRegistry(store)).run(
            "那么总结2511.22858这篇论文", history, [("arxiv", "2511.22858")]
        )
        assert model.tool_names[0] == {"retrieve_paper_evidence"}
        assert result.skill is not None and result.skill.task_id == "library-paper-qa"
        assert "tool_not_allowed" in model.inputs[1][-1]["output"]
    finally:
        temporary.cleanup()


def test_harness_shared_token_budget_counts_embedding_tokens() -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall(
                        "evidence-call",
                        "retrieve_paper_evidence",
                        '{"query":"research results","limit":3,'
                        '"source_type":null,"source_id":null,"retrieval_method":"bm25"}',
                    )
                )
            ]
        )

        class EmbeddingBudgetRegistry(PaperToolRegistry):
            def execute(self, name: str, arguments: str, **kwargs: object) -> dict:
                return {
                    "status": "no_results",
                    "items": [],
                    "_embedding_input_tokens": 20_000,
                }

        result = AgentHarness(
            model,
            EmbeddingBudgetRegistry(store),
            max_total_tokens=20_000,
        ).run("Find evidence for this research question")

        assert result.status == "token_budget_exceeded"
        assert result.total_observed_tokens == 20_014
        assert len(model.inputs) == 1
    finally:
        temporary.cleanup()


def test_harness_stops_when_embedding_usage_cannot_be_verified() -> None:
    class FailingEmbeddings:
        model = "TEST-embedding"

        def embed(self, _texts: list[str]):
            raise EmbeddingError("invalid_provider_response")

    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall(
                        "TEST-embedding-call",
                        "retrieve_paper_evidence",
                        '{"query":"TEST query","limit":1,"retrieval_method":"dense"}',
                    )
                ),
                _final_turn("This must not be requested.", []),
            ]
        )
        registry = PaperToolRegistry(store, embeddings=FailingEmbeddings())
        result = AgentHarness(model, registry).run("TEST use dense evidence")

        assert result.status == "usage_unavailable"
        assert result.warnings == ["embedding_invalid_provider_response"]
        assert len(model.instructions) == 1
        assert result.tool_calls == 1
        assert result.trace[-1].status == "error"
    finally:
        temporary.cleanup()


def test_harness_preflights_embedding_against_remaining_shared_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SpyEmbeddings:
        model = "TEST-embedding"
        called = False

        def embed(self, _texts: list[str]) -> EmbeddingBatch:
            self.called = True
            return EmbeddingBatch(model=self.model, vectors=[[1.0]], input_tokens=1)

    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall(
                        "TEST-embedding-preflight",
                        "retrieve_paper_evidence",
                        '{"query":"TEST query","limit":1,"source_type":null,'
                        '"source_id":null,"retrieval_method":"dense"}',
                    )
                )
            ]
        )
        embeddings = SpyEmbeddings()
        monkeypatch.setattr(
            "app.agent.harness.estimate_input_tokens_upper_bound", lambda **_: 1_000
        )
        result = AgentHarness(
            model,
            PaperToolRegistry(store, embeddings=embeddings),
            max_total_tokens=1_047,
        ).run("TEST use dense evidence")

        assert result.status == "token_budget_exceeded"
        assert not embeddings.called
        assert result.tool_calls == 0
    finally:
        temporary.cleanup()


def test_harness_stops_if_embedding_usage_exceeds_preflight_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class OverreportingEmbeddings:
        model = "TEST-embedding"

        def embed(self, _texts: list[str]) -> EmbeddingBatch:
            return EmbeddingBatch(model=self.model, vectors=[[1.0]], input_tokens=2_000)

    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall(
                        "TEST-embedding-overbound",
                        "retrieve_paper_evidence",
                        '{"query":"TEST query","limit":1,"source_type":null,'
                        '"source_id":null,"retrieval_method":"dense"}',
                    )
                ),
                _final_turn("must not be requested", []),
            ]
        )
        monkeypatch.setattr(
            "app.agent.harness.estimate_input_tokens_upper_bound", lambda **_: 1_000
        )
        result = AgentHarness(
            model,
            PaperToolRegistry(store, embeddings=OverreportingEmbeddings()),
            max_total_tokens=10_000,
        ).run("TEST use dense evidence")

        assert result.status == "token_budget_exceeded"
        assert result.total_observed_tokens > 0
        assert len(model.instructions) == 1
    finally:
        temporary.cleanup()


def test_harness_stops_before_model_when_serialized_context_exceeds_budget() -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel([_final_turn("should not run", [])])
        result = AgentHarness(model, PaperToolRegistry(store), max_context_chars=100).run(
            "How does retrieval work?"
        )

        assert result.status == "context_budget_exceeded"
        assert model.instructions == []
    finally:
        temporary.cleanup()


def test_harness_honors_cooperative_cancellation_before_model_call() -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel([_final_turn("should not run", [])])
        result = AgentHarness(
            model, PaperToolRegistry(store), cancellation_requested=lambda: True
        ).run("How does retrieval work?")

        assert result.status == "cancelled"
        assert model.instructions == []
    finally:
        temporary.cleanup()


def test_selected_skill_limits_model_tools_and_rejects_execution_bypass() -> None:
    temporary, store = _store_in_tempdir()
    try:
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall(
                        "outside-skill", "compare_papers", '{"openalex_ids":["W100","W200"]}'
                    )
                ),
                _final_turn("", [], insufficient=True),
            ]
        )
        result = AgentHarness(model, PaperToolRegistry(store)).run("What is in this paper?")

        assert result.status == "insufficient_evidence"
        assert "compare_papers" not in model.tool_names[0]
        assert "tool_not_allowed_for_skill" in model.inputs[1][-1]["output"]
        assert set(result.skill.allowed_tools) == model.tool_names[0]
    finally:
        temporary.cleanup()


def test_skills_on_off_switch_preserves_same_question_and_evidence_contract() -> None:
    temporary, store = _store_in_tempdir()
    question = "What is the title of W100?"
    try:

        def model_for_run() -> FakeModel:
            claim = "The paper is titled Retrieval systems for research assistants."
            return FakeModel(
                [
                    _call_turn(
                        ModelToolCall("call-1", "get_paper_details", '{"openalex_id":"W100"}')
                    ),
                    _final_turn(
                        claim,
                        ["W100"],
                        claims=[
                            {
                                "text": claim,
                                "evidence": [
                                    {
                                        "source_id": "W100",
                                        "quote": "Retrieval systems for research assistants",
                                        "evidence_type": "metadata",
                                        "source_field": "title",
                                        "chunk_id": None,
                                    }
                                ],
                            }
                        ],
                    ),
                ]
            )

        skilled_model = model_for_run()
        baseline_model = model_for_run()
        skilled = AgentHarness(skilled_model, PaperToolRegistry(store)).run(question)
        baseline = AgentHarness(baseline_model, PaperToolRegistry(store), skills_enabled=False).run(
            question
        )

        assert skilled.status == baseline.status == "completed"
        assert skilled.answer == baseline.answer
        assert skilled.claims == baseline.claims
        assert [item.openalex_id for item in skilled.citations] == [
            item.openalex_id for item in baseline.citations
        ]
        assert skilled.tool_calls == baseline.tool_calls == 1
        assert skilled.skill is not None
        assert skilled.skill.task_id == "paper-qa"
        assert len(skilled.skill.task_registry_sha256) == 64
        assert len(skilled.skill.prompt_sha256) == 64
        assert baseline.skill is None
        assert "ACTIVE PRODUCT SKILL" in skilled_model.instructions[0]
        assert "ACTIVE PRODUCT SKILL" not in baseline_model.instructions[0]
    finally:
        temporary.cleanup()


def test_harness_rejects_forged_citations_and_unstructured_facts() -> None:
    temporary, store = _store_in_tempdir()
    try:
        forged = FakeModel(
            [
                _call_turn(ModelToolCall("call-1", "get_paper_details", '{"openalex_id":"W100"}')),
                _final_turn("See W999 for proof.", ["W999"]),
                _final_turn("Evidence is insufficient.", [], insufficient=True),
            ]
        )
        result = AgentHarness(forged, PaperToolRegistry(store)).run("Compare these papers")

        assert result.status == "insufficient_evidence"
        assert result.citations == []
        assert "W999" not in result.answer
        assert forged.tool_names[-1] == set()

        unsupported_evidence = FakeModel(
            [
                _call_turn(ModelToolCall("call-2", "get_paper_details", '{"openalex_id":"W100"}')),
                _final_turn(
                    "The paper reports a 99 percent improvement.",
                    ["W100"],
                    claims=[
                        {
                            "text": "The paper reports a 99 percent improvement.",
                            "evidence": [
                                {
                                    "source_id": "W100",
                                    "quote": "99 percent",
                                    "evidence_type": "metadata",
                                    "source_field": "abstract",
                                    "chunk_id": None,
                                }
                            ],
                        }
                    ],
                ),
            ]
        )
        rejected = AgentHarness(unsupported_evidence, PaperToolRegistry(store)).run(
            "What did the paper report?"
        )
        assert rejected.status == "unverified_evidence"
        assert rejected.citations == []

        no_citations = FakeModel([_final_turn("An unsupported claim.", [])])
        refused = AgentHarness(no_citations, PaperToolRegistry(store)).run(
            "What did the paper prove?"
        )
        assert refused.status == "insufficient_evidence"
        assert "unsupported claim" not in refused.answer
    finally:
        temporary.cleanup()


def test_harness_rejects_unclaimed_sentence_even_when_another_claim_is_grounded() -> None:
    temporary, store = _store_in_tempdir()
    try:
        first_sentence = "W100 is present in the catalog."
        model = FakeModel(
            [
                _call_turn(ModelToolCall("details", "get_paper_details", '{"openalex_id":"W100"}')),
                _final_turn(
                    f"{first_sentence} It proves a 99% accuracy gain.",
                    ["W100"],
                    claims=[
                        {
                            "text": first_sentence,
                            "evidence": [
                                {
                                    "source_id": "W100",
                                    "quote": "Retrieval systems for research assistants",
                                    "evidence_type": "metadata",
                                    "source_field": "title",
                                    "chunk_id": None,
                                }
                            ],
                        }
                    ],
                ),
            ]
        )
        result = AgentHarness(model, PaperToolRegistry(store)).run("Describe W100")

        assert result.status == "unverified_evidence"
        assert "99% accuracy gain" not in result.answer
    finally:
        temporary.cleanup()


def test_library_answer_displays_only_verified_claim_text() -> None:
    item = {
        "arxiv_id": "2401.12345",
        "source_url": "https://arxiv.org/abs/2401.12345",
        "title": "TEST paper",
        "chunk_id": "TEST-chunk",
        "locator": "TEST page 2",
        "excerpt": "TEST verified source excerpt.",
        "private_processing": True,
    }
    citations, quotes = {}, {}
    _collect_citations({"items": [item]}, citations, quotes)
    claim = {
        "text": "TEST supported claim.",
        "evidence": [
            {
                "source_id": "2401.12345",
                "quote": "TEST verified source excerpt.",
                "evidence_type": "fulltext",
                "source_field": "excerpt",
                "chunk_id": "TEST-chunk",
            }
        ],
    }
    answer = json.dumps(
        {
            "answer": "TEST unsupported introduction. TEST supported claim.",
            "cited_openalex_ids": [],
            "cited_arxiv_ids": ["2401.12345"],
            "cited_personal_ids": [],
            "claims": [claim],
            "insufficient_evidence": False,
        }
    )
    result = AgentHarness._finalize(
        answer, citations, quotes, [], 1, 2, 0, 0, use_claim_text_only=True
    )
    assert result.status == "completed"
    assert result.answer == "TEST supported claim."
    assert "unsupported" not in result.answer
    body = json.loads(answer)
    body["answer"] = ""
    compact = AgentHarness._finalize(
        json.dumps(body), citations, quotes, [], 1, 2, 0, 0, use_claim_text_only=True
    )
    assert compact.status == "completed"
    assert compact.answer == "TEST supported claim."


@pytest.mark.parametrize(
    ("library_count", "expected"), [(2, "completed"), (1, "insufficient_evidence")]
)
def test_mixed_draft_task_requires_claimed_private_evidence_from_both_sources(
    library_count: int, expected: str
) -> None:
    temporary, store = _store_in_tempdir()
    personal_id = str(uuid4())
    library_ids = ["2401.12345", "2401.12346"][:library_count]

    def item(source_id: str, personal: bool) -> dict:
        return {
            "personal_id" if personal else "arxiv_id": source_id,
            "source_type": "personal" if personal else "arxiv",
            "source_id": source_id,
            "source_url": "" if personal else f"https://arxiv.org/abs/{source_id}",
            "private_processing": True,
            "title": "TEST document",
            "chunk_id": f"private:{source_id}:0",
            "locator": "TEST page 1",
            "excerpt": f"TEST verified excerpt {source_id}",
        }

    class MixedRegistry(PaperToolRegistry):
        def execute(self, name, arguments, **kwargs):
            args = json.loads(arguments)
            if args.get("source_type") == "personal":
                return {"status": "ok", "items": [item(personal_id, True)]}
            return {"status": "ok", "items": [item(i, False) for i in library_ids]}

    refs = [(personal_id, True), *[(i, False) for i in library_ids]]
    claims = [
        {
            "text": f"TEST advice {chr(65 + n)}",
            "evidence": [
                {
                    "source_id": source_id,
                    "quote": f"TEST verified excerpt {source_id}",
                    "evidence_type": "fulltext",
                    "source_field": "excerpt",
                    "chunk_id": f"private:{source_id}:0",
                }
            ],
        }
        for n, (source_id, _) in enumerate(refs)
    ]
    try:
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall(
                        "TEST-library", "retrieve_paper_evidence", '{"query":"TEST","limit":5}'
                    ),
                    ModelToolCall(
                        "TEST-draft",
                        "retrieve_paper_evidence",
                        '{"query":"TEST","limit":5,"source_type":"personal"}',
                    ),
                ),
                _final_turn(
                    "\n".join(c["text"] for c in claims),
                    [],
                    arxiv_citations=library_ids,
                    personal_citations=[personal_id],
                    claims=claims,
                ),
            ]
        )
        result = AgentHarness(model, MixedRegistry(store)).run(
            "借鉴我这论文库中两篇论文，对我自己稿件论文的Introduction提出修改建议"
        )
        assert result.status == expected
        assert model.tool_names[0] == {"retrieve_paper_evidence"}
        assert result.skill is not None and result.skill.task_id == "mixed-draft-revision"
    finally:
        temporary.cleanup()


@pytest.mark.parametrize("online", [False, True])
def test_mixed_task_exposes_remote_tools_only_on_explicit_request(online: bool) -> None:
    temporary, store = _store_in_tempdir()
    try:
        with ArxivClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as arxiv:
            model = FakeModel([_final_turn("TEST insufficient", [], insufficient=True)])
            question = "借鉴我的论文库对我自己的稿件提出建议"
            if online:
                question += "，同时联网查找最新论文"
            AgentHarness(model, PaperToolRegistry(store, arxiv=arxiv)).run(question)
            assert "retrieve_paper_evidence" in model.tool_names[0]
            assert ("get_arxiv_metadata" in model.tool_names[0]) is online
    finally:
        temporary.cleanup()


def test_remote_metadata_cannot_satisfy_mixed_task_library_evidence() -> None:
    temporary, store = _store_in_tempdir()
    personal_id = str(uuid4())

    class RemoteOnlyRegistry(PaperToolRegistry):
        def execute(self, name, arguments, **kwargs):
            if name == "get_arxiv_metadata":
                return {
                    "status": "ok",
                    "paper": {
                        "arxiv_id": "2401.12345",
                        "source_url": "https://arxiv.org/abs/2401.12345",
                        "title": "TEST remote title",
                    },
                }
            return {
                "status": "ok",
                "items": [
                    {
                        "personal_id": personal_id,
                        "source_type": "personal",
                        "source_id": personal_id,
                        "source_url": "",
                        "private_processing": True,
                        "title": "TEST draft",
                        "chunk_id": f"private:{personal_id}:0",
                        "locator": "TEST page 1",
                        "excerpt": "TEST draft evidence",
                    }
                ],
            }

    claims = [
        {
            "text": "TEST advice A",
            "evidence": [
                {
                    "source_id": personal_id,
                    "quote": "TEST draft evidence",
                    "evidence_type": "fulltext",
                    "source_field": "excerpt",
                    "chunk_id": f"private:{personal_id}:0",
                }
            ],
        },
        {
            "text": "TEST advice B",
            "evidence": [
                {
                    "source_id": "2401.12345",
                    "quote": "TEST remote title",
                    "evidence_type": "metadata",
                    "source_field": "title",
                    "chunk_id": None,
                }
            ],
        },
    ]
    try:
        with ArxivClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as arxiv:
            model = FakeModel(
                [
                    _call_turn(
                        ModelToolCall("TEST-draft", "retrieve_paper_evidence", "{}"),
                        ModelToolCall("TEST-remote", "get_arxiv_metadata", "{}"),
                    ),
                    _final_turn(
                        "\n".join(c["text"] for c in claims),
                        [],
                        arxiv_citations=["2401.12345"],
                        personal_citations=[personal_id],
                        claims=claims,
                    ),
                ]
            )
            result = AgentHarness(model, RemoteOnlyRegistry(store, arxiv=arxiv)).run(
                "借鉴我的论文库和我的稿件提出建议，并联网搜索"
            )
            assert result.status == "insufficient_evidence"
            assert not result.claims
    finally:
        temporary.cleanup()


def test_harness_rejects_unclaimed_chinese_sentence_without_whitespace() -> None:
    temporary, store = _store_in_tempdir()
    try:
        claimed = "本地目录包含该论文。"
        model = FakeModel(
            [
                _call_turn(ModelToolCall("details", "get_paper_details", '{"openalex_id":"W100"}')),
                _final_turn(
                    f"{claimed}该论文报告准确率提升99%。",
                    ["W100"],
                    claims=[
                        {
                            "text": claimed,
                            "evidence": [
                                {
                                    "source_id": "W100",
                                    "quote": "Retrieval systems for research assistants",
                                    "evidence_type": "metadata",
                                    "source_field": "title",
                                    "chunk_id": None,
                                }
                            ],
                        }
                    ],
                ),
            ]
        )
        result = AgentHarness(model, PaperToolRegistry(store)).run("描述 W100")

        assert result.status == "unverified_evidence"
        assert "准确率提升99%" not in result.answer
    finally:
        temporary.cleanup()


def test_harness_does_not_accept_metadata_abstract_as_fulltext_evidence() -> None:
    temporary, store = _store_in_tempdir()
    try:
        claim = "该论文报告准确率提升99%。"
        model = FakeModel(
            [
                _call_turn(ModelToolCall("details", "get_paper_details", '{"openalex_id":"W100"}')),
                _final_turn(
                    claim,
                    ["W100"],
                    claims=[
                        {
                            "text": claim,
                            "evidence": [
                                {
                                    "source_id": "W100",
                                    "quote": "Retrieval systems support research assistants",
                                    "evidence_type": "metadata",
                                    "source_field": "abstract",
                                    "chunk_id": None,
                                }
                            ],
                        }
                    ],
                ),
            ]
        )
        result = AgentHarness(model, PaperToolRegistry(store)).run("W100 的结果是什么？")

        assert result.status == "unverified_evidence"
        assert "准确率提升99%" not in result.answer
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
        credentials = {"username": "HarnessTestUser", "password": "TEST password secure 123"}
        assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
        assert client.post("/api/v1/auth/login", json=credentials).status_code == 200
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
        llm_reasoning_effort="low",
    )
    transport = httpx.MockTransport(respond)
    client = httpx.Client(transport=transport)
    provider = OpenAIResponsesClient(settings, http_client=client)
    try:
        turn = provider.complete(
            instructions="safe system prompt",
            input_items=[{"role": "user", "content": "RAG"}],
            tools=PaperToolRegistry(PaperStore(Path("unused.sqlite3"))).definitions,
            max_output_tokens=64,
        )
    finally:
        client.close()

    payload = observed["payload"]
    assert observed["url"] == "https://api.openai.com/v1/responses"
    assert observed["authorization"] == "Bearer api-secret"
    assert "api-secret" not in json.dumps(payload)
    assert payload["store"] is False
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["max_output_tokens"] == 64
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

    assert error.value.code == "model_auth_error"
    assert "api-secret" not in str(error.value)
    assert "leaked" not in str(error.value)


def test_responses_adapter_preserves_safe_incomplete_reason() -> None:
    settings = Settings(
        _env_file=None, llm_provider="openai", llm_api_key="TEST-key", llm_model="TEST-model"
    )
    response = {
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
        "output": [],
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
    ) as client:
        turn = OpenAIResponsesClient(settings, http_client=client).complete(
            instructions="TEST", input_items=[], tools=[]
        )
    assert turn.incomplete is True
    assert turn.incomplete_reason == "max_output_tokens"


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "model_auth_error"),
        (429, "model_rate_limited"),
        (500, "model_provider_error"),
        (400, "model_request_rejected"),
    ],
)
def test_model_provider_failures_have_safe_error_codes(status_code, expected) -> None:
    settings = Settings(
        _env_file=None, llm_provider="openai", llm_api_key="TEST-secret", llm_model="TEST-model"
    )
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status_code, text="TEST-secret provider body")
        )
    )
    try:
        with pytest.raises(ModelUnavailable) as error:
            OpenAIResponsesClient(settings, http_client=client).complete(
                instructions="TEST", input_items=[], tools=[]
            )
        assert error.value.code == expected
        assert "TEST-secret" not in str(error.value)
    finally:
        client.close()


def test_model_timeout_has_distinct_safe_error_code() -> None:
    settings = Settings(
        _env_file=None, llm_provider="openai", llm_api_key="TEST-secret", llm_model="TEST-model"
    )

    def timed_out(request):
        raise httpx.ReadTimeout("TEST private detail", request=request)

    client = httpx.Client(transport=httpx.MockTransport(timed_out))
    try:
        with pytest.raises(ModelUnavailable) as error:
            OpenAIResponsesClient(settings, http_client=client).complete(
                instructions="TEST", input_items=[], tools=[]
            )
        assert error.value.code == "model_timeout"
        assert "private detail" not in str(error.value)
    finally:
        client.close()


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"input_tokens": 10},
        {"input_tokens": "10", "output_tokens": 1},
        {"input_tokens": -1, "output_tokens": 1},
        {"input_tokens": True, "output_tokens": 1},
    ],
)
def test_responses_adapter_fails_closed_when_usage_is_missing_or_invalid(usage) -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "TEST-call",
                        "name": "search_papers",
                        "arguments": '{"query":"TEST","limit":1}',
                    }
                ],
                "usage": usage,
            },
        )

    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        llm_api_key="TEST-key",
        llm_model="TEST-model",
    )
    client = httpx.Client(transport=httpx.MockTransport(respond))
    provider = OpenAIResponsesClient(settings, http_client=client)
    try:
        with pytest.raises(ModelUnavailable, match="usage"):
            provider.complete(instructions="TEST", input_items=[], tools=[])
    finally:
        client.close()


@pytest.mark.parametrize(
    ("fragments", "expected"),
    [
        (['{"answer":"TEST result"}'] * 2, '{"answer":"TEST result"}'),
        (['{"answer":"TEST result"}{"answer":"TEST result"}'], '{"answer":"TEST result"}'),
        (['{"answer":', '"TEST result"}'], '{"answer":"TEST result"}'),
        (
            ['{"answer":"TEST result"}', '{"answer":"TEST conflicting result"}'],
            '{"answer":"TEST result"}{"answer":"TEST conflicting result"}',
        ),
    ],
)
def test_responses_adapter_handles_repeated_complete_json_without_breaking_fragments(
    fragments: list[str], expected: str
) -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": text}]}
                    for text in fragments
                ],
                "usage": {"input_tokens": 10, "output_tokens": 10},
            },
        )

    settings = Settings(
        _env_file=None, llm_provider="openai", llm_api_key="TEST-key", llm_model="TEST-model"
    )
    client = httpx.Client(transport=httpx.MockTransport(respond))
    try:
        turn = OpenAIResponsesClient(settings, http_client=client).complete(
            instructions="TEST instructions", input_items=[], tools=[]
        )
    finally:
        client.close()
    assert turn.final_text == expected


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


@pytest.mark.parametrize(
    ("source_field", "quote", "expected_status"),
    [
        ("excerpt", "TEST system separates\ningestion and retrieval.", "completed"),
        ("fulltext", "TEST system separates\ningestion and retrieval.", "unverified_evidence"),
        ("excerpt", "TEST system separates ingestion and retrieval.", "unverified_evidence"),
        ("fulltext", "TEST system separates ingestion and retrieval.", "unverified_evidence"),
    ],
)
def test_synthetic_multiline_evidence_requires_exact_field_and_quote(
    source_field: str, quote: str, expected_status: str
) -> None:
    temporary, store = _store_in_tempdir()

    class TESTMultilineRegistry(PaperToolRegistry):
        synthetic = True

        def execute(self, name: str, arguments: str, **kwargs: object) -> dict:
            return {
                "status": "ok",
                "items": [
                    {
                        "openalex_id": "W100",
                        "title": "TEST-multiline paper",
                        "chunk_id": "TEST-multiline-chunk",
                        "excerpt": "TEST system separates\ningestion and retrieval.",
                        "retrieval_context": "TEST duplicate index-only text",
                        "source_url": "https://openalex.org/W100",
                        "license_id": "CC0-1.0",
                    }
                ],
            }

    try:
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall(
                        "TEST-call", "retrieve_paper_evidence", '{"query":"TEST system","limit":1}'
                    )
                ),
                _final_turn(
                    "TEST system separates ingestion and retrieval.",
                    ["W100"],
                    claims=[
                        {
                            "text": "TEST system separates ingestion and retrieval.",
                            "evidence": [
                                {
                                    "source_id": "W100",
                                    "quote": quote,
                                    "evidence_type": "fulltext",
                                    "source_field": source_field,
                                    "chunk_id": "TEST-multiline-chunk",
                                }
                            ],
                        }
                    ],
                ),
            ]
        )
        result = AgentHarness(model, TESTMultilineRegistry(store), skills_enabled=False).run(
            "Describe the TEST synthetic system"
        )
        assert result.status == expected_status
        assert "retrieval_context" not in model.inputs[1][-1]["output"]
        assert "TEST system separates" in model.inputs[1][-1]["output"]
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
        chunk_id = store.list_current_fulltext_chunks()[0]["chunk_id"]
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
                _final_turn(
                    "W100 supports the statement; see its cited passage.",
                    ["W100"],
                    claims=[
                        {
                            "text": "W100 supports the statement; see its cited passage.",
                            "evidence": [
                                {
                                    "source_id": "W100",
                                    "quote": "with traceable citations",
                                    "evidence_type": "fulltext",
                                    "source_field": "excerpt",
                                    "chunk_id": chunk_id,
                                }
                            ],
                        }
                    ],
                ),
            ]
        )
        response = AgentHarness(
            model,
            PaperToolRegistry(store),
            max_total_tokens=50_000,
        ).run("Find licensed evidence about citations")

        assert response.status == "completed"
        assert response.claims[0].evidence[0].quote == "with traceable citations"
        assert response.claims[0].evidence[0].chunk_id == chunk_id
        assert len(response.citations) == 1
        citation = response.citations[0]
        assert citation.license_id == "CC-BY-4.0"
        assert citation.attribution.startswith("A. Author")
        assert citation.evidence[0].chunk_id.startswith("openalex:W100:")
        assert "traceable citations" in citation.evidence[0].excerpt
        assert "evidence-tool excerpts" in model.instructions[0]
        assert "traceable citations" in model.inputs[1][-1]["output"]
    finally:
        temporary.cleanup()


def test_harness_repairs_unverified_personal_citation_once() -> None:
    temporary, store = _store_in_tempdir()
    personal_id = str(uuid4())
    wrong_personal_id = str(uuid4())
    excerpt = "TEST personal evidence supports the stated research purpose."

    class TESTPersonalRegistry(PaperToolRegistry):
        synthetic = True

        def __init__(self) -> None:
            super().__init__(store)
            self._handlers["retrieve_paper_evidence"] = (
                RetrieveEvidenceArgs,
                lambda _args: {
                    "status": "ok",
                    "items": [
                        {
                            "personal_id": personal_id,
                            "source_type": "personal",
                            "source_id": personal_id,
                            "source_url": "",
                            "private_processing": True,
                            "title": "TEST personal paper",
                            "chunk_id": "TEST-personal-chunk",
                            "locator": "第 2 页",
                            "excerpt": excerpt,
                        }
                    ],
                },
            )

    try:
        answer = "TEST paper states its research purpose."
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall(
                        "TEST-personal-call",
                        "retrieve_paper_evidence",
                        '{"query":"TEST purpose","limit":2}',
                    )
                ),
                _final_turn(
                    answer,
                    [],
                    personal_citations=[wrong_personal_id],
                    claims=[
                        {
                            "text": answer,
                            "evidence": [
                                {
                                    "source_id": personal_id,
                                    "quote": "TEST personal evidence",
                                    "evidence_type": "fulltext",
                                    "source_field": "excerpt",
                                    "chunk_id": "TEST-personal-chunk",
                                }
                            ],
                        }
                    ],
                ),
                _final_turn(
                    answer,
                    [],
                    personal_citations=[personal_id],
                    claims=[
                        {
                            "text": answer,
                            "evidence": [
                                {
                                    "source_id": personal_id,
                                    "quote": "TEST personal evidence",
                                    "evidence_type": "fulltext",
                                    "source_field": "excerpt",
                                    "chunk_id": "TEST-personal-chunk",
                                }
                            ],
                        }
                    ],
                ),
            ]
        )

        result = AgentHarness(model, TESTPersonalRegistry(), skills_enabled=False).run(
            "TEST personal-paper question"
        )

        assert result.status == "completed"
        assert result.model_steps == 3
        assert result.tool_calls == 1
        assert result.citations[0].personal_id == personal_id
        assert model.tool_names[2] == set()
        repair_request = model.inputs[2][-1]["content"]
        assert personal_id in repair_request
        assert "Do not call tools" in repair_request
    finally:
        temporary.cleanup()


@pytest.mark.parametrize(
    ("claim_text", "quote", "expected_status"),
    [
        (
            "Group A recorded 91% recall after 10 ms [W100].",
            "Group A recorded 91% recall after 10 ms.",
            "completed",
        ),
        (
            "Group A recorded 19% recall after 10 ms [W100].",
            "Group A recorded 91% recall after 10 ms.",
            "unverified_evidence",
        ),
        (
            "Group A recorded 91% recall after 10 s [W100].",
            "Group A recorded 91% recall after 10 ms.",
            "unverified_evidence",
        ),
        (
            "Group A improved recall to 91% after 10 ms [W100].",
            "Group A improved recall to 91% after 10 ms.",
            "completed",
        ),
        (
            "Group A improved recall to 91% after 10 ms [W100].",
            "Group A recall decreased to 91% after 10 ms.",
            "unverified_evidence",
        ),
        (
            "Group A did not improve recall to 91% after 10 ms [W100].",
            "Group A improved recall to 91% after 10 ms.",
            "unverified_evidence",
        ),
        (
            "Group B recorded 91% recall after 10 ms [W100].",
            "Group A recorded 91% recall after 10 ms.",
            "unverified_evidence",
        ),
        (
            "Group A recorded 91% recall after 10 ms [W100].",
            "Group A recorded 19% recall. Group B recorded 91% recall after 10 ms.",
            "unverified_evidence",
        ),
    ],
)
def test_agent_rejects_claim_numeric_unit_direction_or_condition_mismatch(
    claim_text: str, quote: str, expected_status: str
) -> None:
    temporary, store = _store_in_tempdir()

    class SyntheticEvidenceRegistry(PaperToolRegistry):
        def execute(self, name: str, arguments: str, **kwargs: object) -> dict:
            assert name == "retrieve_paper_evidence"
            return {
                "status": "ok",
                "items": [
                    {
                        "openalex_id": "W100",
                        "source_url": "https://openalex.org/W100",
                        "title": "TEST-synthetic paper",
                        "chunk_id": "TEST-synthetic-chunk",
                        "locator": "page 1",
                        "excerpt": quote,
                        "license_id": "CC0-1.0",
                    }
                ],
            }

    try:
        model = FakeModel(
            [
                _call_turn(
                    ModelToolCall(
                        "synthetic-evidence",
                        "retrieve_paper_evidence",
                        '{"query":"TEST synthetic result","limit":3,'
                        '"source_type":"openalex","source_id":"W100"}',
                    )
                ),
                _final_turn(
                    claim_text,
                    ["W100"],
                    claims=[
                        {
                            "text": claim_text,
                            "evidence": [
                                {
                                    "source_id": "W100",
                                    "quote": quote,
                                    "evidence_type": "fulltext",
                                    "source_field": "excerpt",
                                    "chunk_id": "TEST-synthetic-chunk",
                                }
                            ],
                        }
                    ],
                ),
            ]
        )
        result = AgentHarness(model, SyntheticEvidenceRegistry(store)).run(
            "Check this TEST-synthetic evidence"
        )

        assert result.status == expected_status
    finally:
        temporary.cleanup()


def test_harness_records_expanded_parent_sibling_as_citable_observed_evidence() -> None:
    item = {
        "openalex_id": "W900",
        "source_url": "https://openalex.org/W900",
        "title": "TEST parent expansion",
        "chunk_id": "TEST-primary-chunk",
        "locator": "TEST page 1 paragraph",
        "excerpt": "Primary child passage.",
        "expanded_evidence": [
            {
                "chunk_id": "TEST-sibling-chunk",
                "locator": "TEST page 1 paragraph continued",
                "excerpt": "Sibling child reports value 42.",
            }
        ],
    }
    citations = {}
    observed_quotes = {}

    _collect_citations({"items": [item]}, citations, observed_quotes)

    assert any(
        quote == "Sibling child reports value 42."
        and chunk_id == "TEST-sibling-chunk"
        and evidence_type == "fulltext"
        and source_field == "excerpt"
        for quote, chunk_id, evidence_type, source_field in observed_quotes["openalex:W900"]
    )
    assert [span.chunk_id for span in citations["openalex:W900"].evidence] == [
        "TEST-primary-chunk",
        "TEST-sibling-chunk",
    ]


def test_harness_reports_reserved_and_actual_tokens_at_provider_boundaries() -> None:
    temporary, store = _store_in_tempdir()
    try:
        updates = []
        model = FakeModel([_final_turn("", [], insufficient=True)])
        result = AgentHarness(
            model,
            PaperToolRegistry(store),
            progress_callback=lambda reserved, actual, trace: updates.append(
                (reserved, actual, trace)
            ),
        ).run("TEST budget progress")

        assert result.status == "insufficient_evidence"
        assert len(updates) == 2
        assert updates[0][0] > 0 and updates[0][1] == 0
        assert updates[1][0] == 0
        assert updates[1][1] == result.total_observed_tokens
        assert updates[1][2][-1].kind == "model"
    finally:
        temporary.cleanup()


def test_citation_check_requires_retrieval_before_accepting_a_final_answer() -> None:
    temporary, store = _store_in_tempdir()
    try:
        skipped = AgentHarness(
            FakeModel([_final_turn("", [], insufficient=True)]),
            PaperToolRegistry(store),
            max_total_tokens=30_000,
        ).run("检查引用是否支持这段论述")
        completed_retrieval = AgentHarness(
            FakeModel(
                [
                    _call_turn(
                        ModelToolCall(
                            "TEST-citation-retrieval",
                            "retrieve_paper_evidence",
                            '{"query":"TEST unsupported citation","limit":2}',
                        )
                    ),
                    _final_turn("", [], insufficient=True),
                ]
            ),
            PaperToolRegistry(store),
            max_total_tokens=30_000,
        ).run("检查引用是否支持这段论述")

        assert skipped.status == "workflow_incomplete"
        assert completed_retrieval.status == "insufficient_evidence"
        assert completed_retrieval.tool_calls == 1
    finally:
        temporary.cleanup()


@pytest.mark.parametrize(
    ("question", "tool_name", "arguments"),
    [
        (
            "比较论文 W100 和 W200",
            "compare_papers",
            '{"openalex_ids":["W100","W200"]}',
        ),
        (
            "写一份文献综述",
            "search_papers",
            '{"query":"retrieval research","limit":2}',
        ),
    ],
)
def test_comparison_and_research_brief_require_their_search_stage(
    question: str, tool_name: str, arguments: str
) -> None:
    temporary, store = _store_in_tempdir()
    try:
        skipped = AgentHarness(
            FakeModel([_final_turn("", [], insufficient=True)]),
            PaperToolRegistry(store),
            max_total_tokens=30_000,
        ).run(question)
        staged = AgentHarness(
            FakeModel(
                [
                    _call_turn(ModelToolCall("TEST-stage", tool_name, arguments)),
                    _final_turn("", [], insufficient=True),
                ]
            ),
            PaperToolRegistry(store),
            max_total_tokens=30_000,
        ).run(question)

        assert skipped.status == "workflow_incomplete"
        assert staged.status == "insufficient_evidence"
        assert staged.tool_calls == 1
    finally:
        temporary.cleanup()
