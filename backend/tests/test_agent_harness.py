from types import SimpleNamespace
from uuid import uuid4

from app.agent.contracts import AgentDecision, AgentPreviewRequest, ToolCall, ToolObservation
from app.agent.harness import AgentHarness
from app.agent.provider import DisabledProvider, ScriptedProvider
from app.agent.run_service import AgentRunService
from app.agent.tools import ToolRegistry


class Profiles:
    def __init__(self):
        self.snapshot = SimpleNamespace(
            id=uuid4(),
            revision=1,
            profile=SimpleNamespace(model_dump=lambda **_: {"budget_max_minor": 100000}),
        )

    def read(self, cookie, profile_id, revision):
        assert cookie == "TEST-cookie" and revision == 1
        return self.snapshot


class Registry:
    def __init__(self):
        self.calls = 0

    def schema_names(self):
        return ["search_catalog"]

    def execute(self, call, profile):
        self.calls += 1
        return ToolObservation(
            name=call.name,
            status="ok",
            data={"items": [], "data_version": None},
            evidence_ids=[],
            missing_fields=[],
        )


def request(profiles):
    return AgentPreviewRequest(
        profile_id=profiles.snapshot.id, profile_revision=1, message="TEST agent request"
    )


def test_disabled_provider_never_executes_a_tool():
    profiles, registry = Profiles(), Registry()
    result = AgentHarness(profiles, registry, DisabledProvider()).run(
        "TEST-cookie", request(profiles)
    )
    assert result["status"] == "provider_disabled" and registry.calls == 0


def test_scripted_harness_deduplicates_read_calls_and_keeps_structured_observations():
    profiles, registry = Profiles(), Registry()
    provider = ScriptedProvider(
        [
            AgentDecision(kind="tool", tool_call=ToolCall(name="search_catalog", arguments={})),
            AgentDecision(kind="tool", tool_call=ToolCall(name="search_catalog", arguments={})),
            AgentDecision(kind="final", reason="TEST_DONE"),
        ]
    )
    result = AgentHarness(profiles, registry, provider).run("TEST-cookie", request(profiles))
    assert result["status"] == "completed" and result["tool_calls_used"] == 2
    assert registry.calls == 1 and result["observations"][1].deduplicated is True


def test_harness_stops_at_tool_budget_instead_of_looping_forever():
    profiles, registry = Profiles(), Registry()
    provider = ScriptedProvider(
        [
            AgentDecision(
                kind="tool",
                tool_call=ToolCall(name="search_catalog", arguments={"query": str(index)}),
            )
            for index in range(9)
        ]
    )
    harness = AgentHarness(profiles, registry, provider)
    harness.MAX_DECISION_ROUNDS = 20
    result = harness.run("TEST-cookie", request(profiles))
    assert result["status"] == "partial" and result["reason"] == "TOOL_CALL_LIMIT"
    assert result["tool_calls_used"] == 8 and registry.calls == 8


def test_catalog_tool_returns_json_only_observation_data():
    class Catalog:
        def list_products(self, *args):
            return {"items": [{"id": uuid4()}], "data_version": uuid4()}

    observation = ToolRegistry(Catalog()).execute(
        ToolCall(name="search_catalog", arguments={"region": "CN"}),
        SimpleNamespace(),
    )
    assert isinstance(observation.data["items"][0]["id"], str)
    assert observation.data_version is not None


def test_answer_contract_uses_only_structured_tool_candidates_and_citations():
    document_id, chunk_id, data_version = uuid4(), uuid4(), uuid4()
    result = {
        "status": "completed",
        "profile_revision": 2,
        "reason": "TEST_DONE",
        "observations": [
            ToolObservation(
                name="rank_laptops",
                status="ok",
                evidence_ids=[],
                missing_fields=["current_offer"],
                data_version=data_version,
                data={"candidates": [{"sku_id": "TEST-SKU"}]},
            ),
            ToolObservation(
                name="retrieve_knowledge",
                status="ok",
                evidence_ids=[],
                missing_fields=[],
                data={
                    "citations": [
                        {
                            "document_id": str(document_id),
                            "chunk_id": str(chunk_id),
                            "title": "TEST",
                            "canonical_url": "https://example.test",
                            "locator": "p1",
                        }
                    ]
                },
            ),
        ],
    }
    answer = AgentRunService._answer(result)
    assert answer.candidates[0].data["sku_id"] == "TEST-SKU"
    assert answer.citations[0].document_id == document_id
    assert answer.missing_fields == ["current_offer"] and answer.data_version == data_version


def test_answer_uses_model_summary_but_candidates_remain_tool_derived():
    answer = AgentRunService._answer(
        {
            "status": "completed",
            "profile_revision": 1,
            "final_text": "依据工具结果，目前没有符合条件的可展示商品。",
            "reason": None,
            "observations": [],
        }
    )
    assert answer.summary.startswith("依据工具结果")
    assert answer.candidates == []
