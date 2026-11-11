import json
from dataclasses import replace

import pytest

from app.agent.model import ModelTurn
from app.agent.research_runtime import (
    ResearchRuntime,
    _explicit_comparison_request,
    _explicit_multi_local_request,
    _negates_intent_cue,
)
from app.config import Settings

DOC = {
    "source_type": "personal",
    "source_id": "11111111-1111-1111-1111-111111111111",
    "title": "TEST draft",
}


class Model:
    output_schema = None

    def __init__(self, defect=None):
        self.defect = defect
        self.calls = []

    def complete(self, **kwargs):
        kind = self.output_schema["name"]
        self.calls.append(kind)
        data = json.loads(kwargs["input_items"][0]["content"])
        if kind == "Plan":
            key = next(iter(data["catalog"]))
            result = {
                "intent": "evaluate",
                "objective": "TEST evaluation",
                "clarification": "",
                "external_request_quote": "",
                "steps": [{"scope": "personal", "documents": [key], "query": "TEST results"}],
            }
            if self.defect == "foreign_document":
                result["steps"][0]["documents"] = ["other-account-doc"]
            if self.defect == "omit_explicit_target":
                result["steps"][0]["documents"] = []
            if self.defect == "compare_single_source":
                result["intent"] = "compare"
            if self.defect == "misclassify_comparison":
                result["intent"] = "evaluate"
            if self.defect == "misclassify_citation_check":
                result["intent"] = "evaluate"
            if self.defect == "external":
                result["steps"][0] = {"scope": "arxiv", "documents": [], "query": "TEST"}
        elif kind == "CitationCheckDraft":
            key = next(
                key
                for key, value in data["evidence"].items()
                if value["evidence_type"] == "fulltext"
            )
            result = {
                "checks": [
                    {
                        "claim": "TEST supported finding",
                        "status": "supported",
                        "reason": "TEST excerpt directly supports the claim.",
                        "source_key": "personal:" + DOC["source_id"],
                        "evidence_ids": [key],
                    },
                    {
                        "claim": "TEST unsupported original claim",
                        "status": "unsupported",
                        "reason": "TEST evidence does not support this claim.",
                        "source_key": None,
                        "evidence_ids": [],
                    },
                ],
                "missing": "",
                "memory": "TEST citation scope",
            }
            if self.defect == "citation_source_mismatch":
                result["checks"][0]["source_key"] = "arxiv:2401.00001"
        elif kind == "Coverage":
            result = {"gaps": "", "followups": []}
            if self.defect in {"coverage_gap", "coverage_foreign"}:
                result = {
                    "gaps": "TEST missing methods",
                    "followups": [
                        {
                            "scope": "personal",
                            "documents": [
                                next(iter(data["documents"]))
                                if self.defect == "coverage_gap"
                                else "foreign"
                            ],
                            "query": "TEST experimental methods limitations",
                        }
                    ],
                }
            if self.defect == "coverage_gap_only":
                result = {"gaps": "TEST methods coverage remains incomplete", "followups": []}
            if self.defect == "coverage_duplicate":
                followup = {
                    "scope": "personal",
                    "documents": [next(iter(data["documents"]))],
                    "query": "TEST results",
                }
                result = {"gaps": "", "followups": [followup, followup.copy()]}
        elif kind == "Draft":
            key = next(
                key
                for key, value in data["evidence"].items()
                if value["evidence_type"] == "fulltext"
            )
            result = {
                "claims": [
                    {"kind": "fact", "text": "TEST supported finding", "evidence_ids": [key]}
                ],
                "missing": "",
                "memory": "TEST retained constraint",
            }
            if self.defect == "forged_evidence":
                result["claims"][0]["evidence_ids"] = ["E999"]
        else:
            result = {
                "items": [
                    {
                        "claim_index": 0,
                        "supported": self.defect != "unsupported",
                        "reason": "TEST review",
                    }
                ]
            }
            if self.defect == "incomplete_review":
                result["items"] = []
        return ModelTurn(
            tool_calls=[],
            continuation_items=[],
            final_text=json.dumps(result),
            refusal=False,
            input_tokens=10,
            output_tokens=10,
        )


class Registry:
    def __init__(self):
        self.calls = []

    def embedding_input_tokens_upper_bound(self, name, args):
        return 0

    def execute(self, name, args, **kwargs):
        args = json.loads(args)
        self.calls.append((name, args))
        assert args["source_id"] == DOC["source_id"]
        assert kwargs["allowed_names"] == frozenset({"retrieve_paper_evidence"})
        return {
            "status": "ok",
            "items": [
                {
                    "personal_id": DOC["source_id"],
                    "source_type": "personal",
                    "source_id": DOC["source_id"],
                    "title": DOC["title"],
                    "source_url": "",
                    "private_processing": True,
                    "excerpt": "TEST supported finding",
                    "chunk_id": "private:TEST:1",
                    "locator": "page 1",
                }
            ],
        }


@pytest.mark.parametrize(
    "defect,status",
    [
        (None, "completed"),
        ("foreign_document", "workflow_incomplete"),
        ("external", "workflow_incomplete"),
        ("omit_explicit_target", "workflow_incomplete"),
        ("forged_evidence", "unverified_citations"),
        ("unsupported", "insufficient_evidence"),
        ("incomplete_review", "invalid_model_output"),
    ],
)
def test_runtime_plans_scopes_binds_and_reviews(defect, status):
    model, registry = Model(defect), Registry()
    result = ResearchRuntime(Settings(_env_file=None), model, registry).run(
        "评价我自己的论文", [], [DOC], {}
    )
    assert result.status == status
    if status == "completed":
        assert model.calls == ["Plan", "Coverage", "Draft", "Review"]
        assert result.claims[0].evidence[0].quote == "TEST supported finding"
        assert result.context_state["summary"] == "TEST retained constraint"
    if defect in {"foreign_document", "external", "omit_explicit_target"}:
        assert registry.calls == []
    if defect == "unsupported":
        assert not result.claims and not result.citations


def test_runtime_cannot_omit_explicit_document_id_from_plan():
    model, registry = Model(), Registry()
    result = ResearchRuntime(Settings(_env_file=None), model, registry).run(
        f"请总结 {DOC['source_id']}", [], [DOC], {}
    )
    assert result.status == "completed"
    assert registry.calls[0][1]["source_id"] == DOC["source_id"]

    model, registry = Model("omit_explicit_target"), Registry()
    result = ResearchRuntime(Settings(_env_file=None), model, registry).run(
        f"请总结 {DOC['source_id']}", [], [DOC], {}
    )
    assert result.status == "workflow_incomplete"
    assert registry.calls == []


def test_runtime_requires_two_local_documents_for_explicit_multi_paper_request():
    second = {
        "source_type": "openalex",
        "source_id": "WTEST1234",
        "title": "TEST second paper",
    }
    model, registry = Model(), Registry()
    result = ResearchRuntime(Settings(_env_file=None), model, registry).run(
        "比较我的论文库里的两篇论文", [], [DOC, second], {}
    )
    assert result.status == "workflow_incomplete"
    assert registry.calls == []


def test_runtime_loads_citation_check_skill_for_citation_check_intent():
    class CitationCheckModel(Model):
        def complete(self, **kwargs):
            turn = super().complete(**kwargs)
            if self.output_schema["name"] == "Plan":
                plan = json.loads(turn.final_text)
                plan["intent"] = "citation_check"
                turn = replace(turn, final_text=json.dumps(plan))
            return turn

    result = ResearchRuntime(Settings(_env_file=None), CitationCheckModel(), Registry()).run(
        "检查引用是否支持这个结论", [], [DOC], {}
    )
    assert result.status == "completed"
    assert result.context_state["skill"]["id"] == "citation-check"
    assert "TEST unsupported original claim" in result.answer
    assert "核验状态：不支持" in result.answer

    result = ResearchRuntime(
        Settings(_env_file=None), CitationCheckModel("unsupported"), Registry()
    ).run("请检查引用是否支持这个结论", [], [DOC], {})
    assert result.status == "completed"
    assert "TEST supported finding" in result.answer
    assert "核验状态：不支持" in result.answer
    assert "已省略" not in result.answer


def test_runtime_rejects_citation_check_evidence_from_a_different_source():
    class CitationCheckModel(Model):
        def complete(self, **kwargs):
            turn = super().complete(**kwargs)
            if self.output_schema["name"] == "Plan":
                plan = json.loads(turn.final_text)
                plan["intent"] = "citation_check"
                turn = replace(turn, final_text=json.dumps(plan))
            return turn

    result = ResearchRuntime(
        Settings(_env_file=None), CitationCheckModel("citation_source_mismatch"), Registry()
    ).run("请检查引用是否支持这个结论", [], [DOC], {})
    assert result.status == "unverified_citations"


def test_runtime_does_not_complete_comparison_with_only_one_observed_source():
    model, registry = Model("compare_single_source"), Registry()
    result = ResearchRuntime(Settings(_env_file=None), model, registry).run(
        "比较这篇论文", [], [DOC], {}
    )
    assert result.status == "insufficient_evidence"
    assert model.calls == ["Plan", "Coverage"]
    assert len(result.citations) == 1


def test_runtime_fails_closed_when_explicit_comparison_is_misclassified():
    model, registry = Model("misclassify_comparison"), Registry()
    result = ResearchRuntime(Settings(_env_file=None), model, registry).run(
        "请比较这篇论文", [], [DOC], {}
    )
    assert result.status == "workflow_incomplete"
    assert registry.calls == []


@pytest.mark.parametrize(
    "question,expected",
    [
        ("请比较这篇论文", True),
        ("比较两篇论文的方法", True),
        ("Compare these two papers", True),
        ("不要比较这篇论文，只总结", False),
        ("Please do not compare papers", False),
    ],
)
def test_explicit_comparison_request_detection(question, expected):
    assert _explicit_comparison_request(question) is expected


@pytest.mark.parametrize(
    "question,expected",
    [
        ("比较我的论文库里的两篇论文", True),
        ("比较两篇论文，其中一篇来自我的论文库，另一篇在线检索", False),
        ("compare two papers from my library", True),
    ],
)
def test_explicit_multi_local_request_detection(question, expected):
    assert _explicit_multi_local_request(question) is expected


@pytest.mark.parametrize(
    "question,intent,expected",
    [
        ("不要比较这篇论文，只总结", "compare", True),
        ("不要检查引用，只总结", "citation_check", True),
        ("Please do not revise this draft", "revise", True),
        ("请检查引用支持情况", "citation_check", False),
    ],
)
def test_negated_skill_cues_do_not_force_a_workflow(question, intent, expected):
    assert _negates_intent_cue(question, intent) is expected


def test_runtime_fails_closed_when_explicit_citation_check_is_misclassified():
    model, registry = Model("misclassify_citation_check"), Registry()
    result = ResearchRuntime(Settings(_env_file=None), model, registry).run(
        "请检查引用是否支持这个结论", [], [DOC], {}
    )
    assert result.status == "workflow_incomplete"
    assert registry.calls == []


def test_runtime_budget_and_cancellation_precede_provider_call():
    for settings, cancelled, status in [
        (Settings(_env_file=None, agent_max_total_tokens=256), None, "token_budget_exceeded"),
        (Settings(_env_file=None), lambda: True, "cancelled"),
    ]:
        model = Model()
        result = ResearchRuntime(settings, model, Registry(), cancelled=cancelled).run(
            "TEST", [], [DOC], {}
        )
        assert result.status == status
        assert not model.calls


def test_semantic_plan_receives_persisted_memory_and_explicit_catalog_enum():
    class InspectModel(Model):
        def complete(self, **kwargs):
            data = json.loads(kwargs["input_items"][0]["content"])
            if self.output_schema["name"] == "Plan":
                assert data["memory"]["summary"] == "TEST use British English; no causal claims"
                assert data["history"] == []  # Old turns can be outside the recent window.
                allowed = self.output_schema["schema"]["$defs"]["Step"]["properties"]["documents"][
                    "items"
                ]["enum"]
                assert allowed == ["personal:" + DOC["source_id"]]
            return super().complete(**kwargs)

    result = ResearchRuntime(Settings(_env_file=None), InspectModel(), Registry()).run(
        "继续评价它",
        [],
        [DOC],
        {"summary": "TEST use British English; no causal claims", "documents": [DOC]},
    )
    assert result.status == "completed"


@pytest.mark.parametrize("scope", ["library", "personal"])
def test_local_plan_cannot_cross_source_types(scope):
    class WrongScope(Model):
        def complete(self, **kwargs):
            turn = super().complete(**kwargs)
            if self.output_schema["name"] == "Plan":
                data = json.loads(turn.final_text)
                data["steps"][0]["scope"] = scope
                turn = replace(turn, final_text=json.dumps(data))
            return turn

    registry = Registry()
    result = ResearchRuntime(Settings(_env_file=None), WrongScope(), registry).run(
        "TEST", [], [DOC], {}
    )
    assert result.status == ("completed" if scope == "personal" else "workflow_incomplete")
    if scope == "library":
        assert not registry.calls


@pytest.mark.parametrize("count,expected", [(2, "completed"), (0, "insufficient_evidence")])
def test_discovery_renders_records_without_review(count, expected):
    class DiscoveryModel:
        output_schema = None

        def complete(self, **kwargs):
            assert self.output_schema["name"] == "Plan"
            return ModelTurn(
                [],
                [],
                json.dumps(
                    {
                        "intent": "discover",
                        "objective": "TEST search",
                        "clarification": "",
                        "external_request_quote": "OpenAlex",
                        "result_count": 2,
                        "steps": [{"scope": "openalex", "documents": [], "query": "TEST VR"}],
                    }
                ),
                False,
                10,
                10,
            )

    class DiscoveryRegistry:
        def embedding_input_tokens_upper_bound(self, *args):
            return 0

        def execute(self, name, arguments, **kwargs):
            assert json.loads(arguments)["limit"] == 2
            return {
                "status": "ok" if count else "no_results",
                "items": [
                    {
                        "openalex_id": f"W{i}",
                        "title": f"TEST paper {i}",
                        "source_url": f"https://openalex.org/W{i}",
                    }
                    for i in range(1, count + 1)
                ],
            }

    result = ResearchRuntime(Settings(_env_file=None), DiscoveryModel(), DiscoveryRegistry()).run(
        "OpenAlex find two papers", [], [], {}
    )
    assert result.status == expected
    assert result.model_steps == 1
    assert not result.claims
    assert len(result.citations) == count


@pytest.mark.parametrize(
    "defect,expected_calls,status",
    [
        ("coverage_gap", 2, "insufficient_evidence"),
        ("coverage_foreign", 1, "workflow_incomplete"),
    ],
)
def test_adaptive_retrieval_follows_gaps_within_document_boundary(defect, expected_calls, status):
    model, registry = Model(defect), Registry()
    result = ResearchRuntime(Settings(_env_file=None), model, registry).run(
        "评价我自己的论文", [], [DOC], {}
    )
    assert result.status == status
    assert len(registry.calls) == expected_calls
    if defect == "coverage_gap":
        assert registry.calls[1][1]["query"] == "TEST experimental methods limitations"
        assert model.calls == ["Plan", "Coverage", "Draft", "Review"]
        assert "retrieval_coverage_incomplete" in result.warnings
        assert "检索覆盖未完成：TEST missing methods" in result.answer


def test_coverage_gap_cannot_be_hidden_by_draft_model():
    result = ResearchRuntime(Settings(_env_file=None), Model("coverage_gap_only"), Registry()).run(
        "评价我自己的论文", [], [DOC], {}
    )

    assert result.status == "insufficient_evidence"
    assert "retrieval_coverage_incomplete" in result.warnings
    assert "TEST methods coverage remains incomplete" in result.answer


def test_skipped_coverage_check_is_disclosed_when_step_budget_is_tight():
    settings = Settings(_env_file=None).model_copy(update={"agent_max_steps": 3})
    result = ResearchRuntime(settings, Model(), Registry()).run("评价我自己的论文", [], [DOC], {})

    assert result.status == "insufficient_evidence"
    assert result.context_state["coverage"]["status"] == "skipped_budget"
    assert "retrieval_coverage_incomplete" in result.warnings
    assert "未能完成检索覆盖检查" in result.answer


def test_duplicate_coverage_followups_are_not_silently_counted_as_executed():
    result = ResearchRuntime(Settings(_env_file=None), Model("coverage_duplicate"), Registry()).run(
        "评价我自己的论文", [], [DOC], {}
    )

    assert result.status == "insufficient_evidence"
    assert result.tool_calls == 1
    assert result.context_state["coverage"]["skipped_duplicate"] is True
    assert "重复的补充检索已去重" in result.answer
