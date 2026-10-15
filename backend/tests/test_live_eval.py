"""Synthetic-only checks for the opt-in real-paper evaluation guard."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from app.agent.harness import AgentHarness
from app.agent.model import ModelToolCall, ModelTurn, ModelUnavailable
from app.cli.run_live_eval import ScopedEvidenceTools, main
from app.evaluation.live_budget import BudgetedModelClient


class TESTModel:
    synthetic = True

    def __init__(self, *, usage: tuple[int, int] = (120, 30), fail: bool = False) -> None:
        self.usage = usage
        self.fail = fail
        self.calls = 0

    def complete(
        self,
        *,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_output_tokens: int | None = None,
    ) -> ModelTurn:
        assert instructions == "TEST instructions"
        assert input_items[0]["content"] == "TEST question"
        self.calls += 1
        if self.fail:
            raise ModelUnavailable("TEST provider failure")
        return ModelTurn([], [], None, False, *self.usage)


def _guard(inner: TESTModel, *, cap: str = "1") -> BudgetedModelClient:
    return BudgetedModelClient(
        inner,
        input_price_per_million_usd=Decimal("1"),
        output_price_per_million_usd=Decimal("1"),
        max_cost_usd=Decimal(cap),
        max_provider_calls=2,
        max_output_tokens=100,
    )


def _call(guard: BudgetedModelClient) -> ModelTurn:
    return guard.complete(
        instructions="TEST instructions",
        input_items=[{"role": "user", "content": "TEST question"}],
        tools=[],
    )


def test_live_cost_preflight_prevents_request() -> None:
    inner = TESTModel()
    guard = _guard(inner, cap="0.000001")
    with pytest.raises(ModelUnavailable):
        _call(guard)
    assert inner.calls == 0
    assert guard.halt_reason == "cost_preflight_cap_reached"


def test_live_guard_counts_usage_and_stops_at_call_cap() -> None:
    inner = TESTModel()
    guard = _guard(inner)
    _call(guard)
    _call(guard)
    with pytest.raises(ModelUnavailable):
        _call(guard)
    assert inner.calls == 2
    assert guard.estimated_spend == Decimal("0.000300")
    assert guard.halt_reason == "provider_call_cap_reached"
    assert guard.call_usage[0].final_text is None
    assert guard.call_usage[0].tool_calls == ()
    assert guard.call_usage[0].refusal is False


def test_live_guard_reserves_failed_or_unmetered_request() -> None:
    failed = _guard(TESTModel(fail=True))
    with pytest.raises(ModelUnavailable):
        _call(failed)
    assert failed.estimated_spend > 0
    assert failed.halt_reason == "provider_failure_usage_unknown"
    unmetered = _guard(TESTModel(usage=(0, 0)))
    _call(unmetered)
    assert unmetered.estimated_spend > 0
    assert unmetered.halt_reason == "provider_usage_missing"


def test_live_guard_keeps_synthetic_raw_turn_for_local_failure_audit() -> None:
    class TESTOutputModel(TESTModel):
        synthetic = True

        def complete(
            self,
            *,
            instructions: str,
            input_items: list[dict[str, Any]],
            tools: list[dict[str, Any]],
            max_output_tokens: int | None = None,
        ) -> ModelTurn:
            self.calls += 1
            return ModelTurn(
                [ModelToolCall("TEST-call", "retrieve_paper_evidence", "TEST arguments")],
                [],
                "TEST raw answer",
                False,
                20,
                10,
            )

    guard = _guard(TESTOutputModel())
    _call(guard)
    assert guard.call_usage[0].final_text == "TEST raw answer"
    assert guard.call_usage[0].tool_calls == (
        {"name": "retrieve_paper_evidence", "arguments": "TEST arguments"},
    )


class TESTStore:
    synthetic = True

    def __init__(self) -> None:
        self.calls = 0

    def search_fulltext_evidence(self, query: str, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        assert query == "TEST synthetic query"
        assert kwargs["source_id"] == "TEST-2609.27579"
        assert kwargs["retrieval_method"] == "bm25"
        return {
            "status": "ok",
            "items": [
                {
                    "chunk_id": "TEST-CHUNK-001",
                    "source_id": "TEST-2609.27579",
                    "arxiv_id": "TEST-2609.27579",
                    "title": "TEST synthetic paper",
                    "source_url": "https://example.test/TEST-2609.27579",
                    "excerpt": "TEST synthetic evidence",
                    "expanded_evidence": ["TEST expanded text excluded"],
                    "retrieval_context": "TEST parser context excluded",
                }
            ],
        }


class TESTRegistry:
    synthetic = True

    def __init__(self, store: TESTStore) -> None:
        self.store = store

    def definitions_for(self, allowed_names: frozenset[str] | None) -> list[dict[str, Any]]:
        return (
            [
                {
                    "name": "retrieve_paper_evidence",
                    "parameters": {
                        "properties": {
                            "source_type": {"enum": ["arxiv", "openalex", None]},
                            "source_id": {"type": "string"},
                            "retrieval_method": {"enum": ["bm25", "dense", "hybrid"]},
                        }
                    },
                }
            ]
            if allowed_names
            else []
        )

    def execute(
        self, name: str, arguments: str, *, allowed_names: frozenset[str] | None = None
    ) -> dict[str, Any]:
        parsed = json.loads(arguments)
        return self.store.search_fulltext_evidence(
            parsed["query"], **{key: value for key, value in parsed.items() if key != "query"}
        )


def test_scoped_tool_rejects_cross_source_and_dense_calls() -> None:
    store = TESTStore()
    tools = ScopedEvidenceTools(store, "TEST-2609.27579")  # type: ignore[arg-type]
    tools.registry = TESTRegistry(store)  # type: ignore[assignment]
    assert [item["name"] for item in tools.definitions] == ["retrieve_paper_evidence"]
    properties = tools.definitions[0]["parameters"]["properties"]
    assert properties["source_id"]["enum"] == ["TEST-2609.27579"]
    assert properties["retrieval_method"]["enum"] == ["bm25"]
    valid = {
        "query": "TEST synthetic query",
        "limit": 1,
        "source_type": "arxiv",
        "source_id": "TEST-2609.27579",
        "retrieval_method": "bm25",
    }
    accepted = tools.execute("retrieve_paper_evidence", json.dumps(valid))
    assert accepted["status"] == "ok"
    assert accepted["items"][0]["excerpt"] == "TEST synthetic evidence"
    assert "expanded_evidence" not in accepted["items"][0]
    assert "retrieval_context" not in accepted["items"][0]
    assert store.calls == 1
    assert tools.definitions == []
    for change in ({"source_id": "TEST-other"}, {"retrieval_method": "dense"}):
        rejected = tools.execute("retrieve_paper_evidence", json.dumps(valid | change))
        assert rejected["status"] == "error"
        assert rejected["code"] == "single_retrieval_limit_reached"
    assert tools.execute("search_papers", "{}")["status"] == "error"
    assert store.calls == 1


def test_scoped_tool_rejects_cross_source_on_first_call() -> None:
    store = TESTStore()
    tools = ScopedEvidenceTools(store, "TEST-2609.27579")  # type: ignore[arg-type]
    tools.registry = TESTRegistry(store)  # type: ignore[assignment]
    rejected = tools.execute(
        "retrieve_paper_evidence",
        json.dumps(
            {
                "query": "TEST synthetic query",
                "limit": 1,
                "source_type": "arxiv",
                "source_id": "TEST-other",
                "retrieval_method": "bm25",
            }
        ),
    )
    assert rejected == {"status": "error", "code": "source_scope_or_method_invalid"}
    assert tools.definitions == []
    assert store.calls == 0


def test_synthetic_harness_gets_one_retrieval_then_must_finish() -> None:
    store = TESTStore()
    tools = ScopedEvidenceTools(store, "TEST-2609.27579")  # type: ignore[arg-type]
    tools.registry = TESTRegistry(store)  # type: ignore[assignment]
    names_seen: list[list[str]] = []

    class TESTTwoTurnModel:
        synthetic = True

        def complete(
            self,
            *,
            instructions: str,
            input_items: list[dict[str, Any]],
            tools: list[dict[str, Any]],
            max_output_tokens: int | None = None,
        ) -> ModelTurn:
            names_seen.append([item["name"] for item in tools])
            if len(names_seen) == 1:
                args = json.dumps(
                    {
                        "query": "TEST synthetic query",
                        "limit": 1,
                        "source_type": "arxiv",
                        "source_id": "TEST-2609.27579",
                        "retrieval_method": "bm25",
                    }
                )
                call = ModelToolCall("TEST-call-1", "retrieve_paper_evidence", args)
                return ModelTurn(
                    [call],
                    [
                        {
                            "type": "function_call",
                            "call_id": call.call_id,
                            "name": call.name,
                            "arguments": call.arguments,
                        }
                    ],
                    None,
                    False,
                    20,
                    10,
                )
            return ModelTurn(
                [],
                [],
                json.dumps(
                    {
                        "answer": "TEST evidence insufficient",
                        "cited_openalex_ids": [],
                        "cited_arxiv_ids": [],
                        "claims": [],
                        "insufficient_evidence": True,
                    }
                ),
                False,
                30,
                12,
            )

    result = AgentHarness(
        TESTTwoTurnModel(),  # type: ignore[arg-type]
        tools,  # type: ignore[arg-type]
        max_steps=2,
        max_context_chars=120_000,
    ).run("[paper-qa] TEST synthetic question")
    assert result.status == "insufficient_evidence"
    assert result.model_steps == 2
    assert names_seen == [["retrieve_paper_evidence"], []]
    assert store.calls == 1


def test_live_cli_never_substitutes_a_different_model(capsys: Any) -> None:
    assert main(["--model", "TEST-other"]) == 2
    assert "gpt-5.6-sol" in capsys.readouterr().err


def test_r1_diagnostic_refuses_cap_above_fifty_cents(capsys: Any) -> None:
    assert main(["--diagnostic-r1", "--max-cost-usd", "0.51"]) == 2
    assert "USD 0.50" in capsys.readouterr().err


def test_r1_verification_refuses_cap_above_remaining_authorized_budget(capsys: Any) -> None:
    assert main(["--verify-diagnostic-r1", "--max-cost-usd", "0.46"]) == 2
    assert "USD 0.45" in capsys.readouterr().err


def test_post_fix_six_task_refuses_model_substitution(capsys: Any) -> None:
    assert main(["--post-fix-six-task", "--model", "TEST-other"]) == 2
    assert "gpt-5.6-sol" in capsys.readouterr().err
