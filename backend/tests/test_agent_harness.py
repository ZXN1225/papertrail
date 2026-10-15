from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.agent.contracts import AgentQuestion, AgentTurn, ComparePapersArgs
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
            result = AgentHarness(model, registry).run("Find this arXiv work")

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
                ]
            )
            uncited = AgentHarness(uncited_model, registry).run("Find this arXiv work")

        assert result.status == "completed"
        assert result.citations[0].source == "arxiv"
        assert result.citations[0].arxiv_id == "2401.12345"
        assert result.citations[0].source_url == "https://arxiv.org/abs/2401.12345"
        assert uncited.status == "unverified_citations"
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
        assert "ACTIVE PRODUCT SKILL: paper-qa@1.0.0" in model.instructions[0]
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
            "Is that supported?", prior_turns
        )

        assert result.status == "unverified_citations"
        assert "Untrusted prior conversation" in model.inputs[0][0]["content"]
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
                    "_embedding_input_tokens": 12_000,
                }

        result = AgentHarness(
            model,
            EmbeddingBudgetRegistry(store),
            max_total_tokens=12_000,
        ).run("Find evidence for this research question")

        assert result.status == "token_budget_exceeded"
        assert result.total_observed_tokens == 12_014
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
            ]
        )
        result = AgentHarness(forged, PaperToolRegistry(store)).run("Compare these papers")

        assert result.status == "unverified_citations"
        assert result.citations == []
        assert "W999" not in result.answer

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
            max_output_tokens=64,
        )
    finally:
        client.close()

    payload = observed["payload"]
    assert observed["url"] == "https://api.openai.com/v1/responses"
    assert observed["authorization"] == "Bearer api-secret"
    assert "api-secret" not in json.dumps(payload)
    assert payload["store"] is False
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

    assert "401" in str(error.value)
    assert "api-secret" not in str(error.value)
    assert "leaked" not in str(error.value)


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
        assert "excerpts from the licensed evidence tool" in model.instructions[0]
        assert "traceable citations" in model.inputs[1][-1]["output"]
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
