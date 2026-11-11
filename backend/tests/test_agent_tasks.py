from __future__ import annotations

import pytest

from app.agent.skills import SKILL_REGISTRY
from app.agent.tasks import prepare_task
from app.config import Settings
from app.main import _agent_run_harness_metadata


@pytest.mark.parametrize(
    ("question", "skill_id", "workflow"),
    [
        (
            "论文问答：总结论文的主要发现",
            "paper-qa",
            ("retrieve", "form_claims", "validate_evidence", "answer"),
        ),
        (
            "根据我已入库的论文(Master Thesis)解释其主要发现",
            "personal-paper-qa",
            ("retrieve_personal_paper", "form_claims", "validate_evidence", "answer"),
        ),
        (
            "比较论文：总结两篇论文的区别",
            "compare-papers",
            (
                "identify_papers",
                "compare_fields",
                "retrieve_findings",
                "validate_evidence",
                "answer",
            ),
        ),
        (
            "写一份文献综述",
            "research-brief",
            ("search", "retrieve", "synthesize_claims", "validate_evidence", "answer"),
        ),
        (
            "润色论文这段文字",
            "draft-revision",
            (
                "understand_revision_goal",
                "retrieve_if_needed",
                "revise",
                "validate_claims",
                "answer",
            ),
        ),
        (
            "检查引用是否支持这段论述",
            "citation-check",
            ("retrieve", "match_claims_to_evidence", "report_supported_and_missing", "answer"),
        ),
    ],
)
def test_task_contract_selects_skill_and_fixed_workflow(
    question: str, skill_id: str, workflow: tuple[str, ...]
) -> None:
    prepared = prepare_task(question)

    assert prepared.spec.task_id == skill_id
    assert prepared.spec.workflow == workflow
    assert prepared.skill.skill_id == ("paper-qa" if skill_id == "personal-paper-qa" else skill_id)
    registry_skill_id = "paper-qa" if skill_id == "personal-paper-qa" else skill_id
    assert set(prepared.skill.recommended_tools) <= set(
        SKILL_REGISTRY[registry_skill_id].recommended_tools
    )


def test_tasks_define_required_tool_stages_for_comparisons_and_reviews() -> None:
    comparison = prepare_task("比较论文 A 与论文 B").spec
    citation_check = prepare_task("检查引用是否支持论述").spec

    assert comparison.required_tool_stages == (("compare_papers",),)
    assert citation_check.required_tool_stages == (("retrieve_paper_evidence",),)
    personal = prepare_task("根据我本地论文 Master Thesis 回答")
    assert personal.spec.required_tool_stages == (("retrieve_paper_evidence",),)
    assert personal.skill.skill_id == "paper-qa"


@pytest.mark.parametrize(
    ("question", "sources"),
    [
        (
            "请你帮我在OpenAlex和Arxiv中搜索总共3篇跟VR and Stress Reduction有关的论文。",
            ("openalex", "arxiv"),
        ),
        ("在 arXiv 搜索 VR 论文", ("arxiv",)),
        ("search OpenAlex for VR papers", ("openalex",)),
    ],
)
def test_named_online_sources_select_external_search(question, sources) -> None:
    task = prepare_task(question)
    assert task.spec.task_id == "external-paper-search"
    assert task.requested_sources == sources
    assert task.external_requested


def test_library_plus_online_search_requires_both_source_types() -> None:
    task = prepare_task("结合我的论文库并在OpenAlex搜索相关研究")
    assert task.spec.task_id == "library-online-research"
    assert task.requested_sources == ("openalex",)
    assert task.spec.required_tool_stages == (("retrieve_paper_evidence",),)


@pytest.mark.parametrize(
    "question",
    [
        "比较我的论文库中已经解析的两篇RAG论文的研究方法",
        "请将我的论文库中标题为 TEST 的论文内容总结出来",
    ],
)
def test_library_questions_select_account_scoped_fulltext_workflow(question: str) -> None:
    task = prepare_task(question)
    assert task.spec.task_id == "library-paper-qa"
    assert task.spec.required_tool_stages == (("retrieve_paper_evidence",),)
    assert task.skill.skill_id == "paper-qa"


def test_saved_paper_followup_uses_library_but_explicit_online_request_does_not() -> None:
    library = [("arxiv", "2511.22858")]
    previous = ["比较我的论文库中两篇论文"]
    assert (
        prepare_task(
            "那么请总结概况2511.22858这篇论文", prior_user_questions=previous, library_ids=library
        ).spec.task_id
        == "library-paper-qa"
    )


def test_personal_paper_followup_keeps_local_scope() -> None:
    task = prepare_task(
        "那么请你根据原文，对这篇论文做出评价。",
        prior_user_questions=["根据我已入库的论文 Master Thesis 解释论文立意"],
    )
    assert task.spec.task_id == "personal-paper-qa"
    assert not task.external_requested


def test_mixed_draft_and_library_task_retains_both_sources_and_explicit_web_intent() -> None:
    library = [("arxiv", "2511.22858")]
    previous = ["比较我的论文库中两篇论文"]
    question = (
        "那么请你借鉴我这论文库中两篇论文的写作思路，"
        "对我自己稿件论文中Introduction部分提出具体的修改建议。"
    )
    task = prepare_task(question)
    assert task.spec.task_id == "mixed-draft-revision"
    assert task.spec.required_tool_stages == (("retrieve_paper_evidence",),)
    assert task.skill.skill_id == "draft-revision"
    assert task.external_requested is False
    online = prepare_task(question + "请同时联网查找相关研究。")
    assert online.spec.task_id == "mixed-draft-revision"
    assert online.external_requested is True
    metadata = _agent_run_harness_metadata(question, Settings(_env_file=None))
    assert metadata["runtime_version"] == "research-runtime-2"
    assert "task_id" not in metadata
    followup = prepare_task(
        "结合我的稿件给这篇论文提出修改建议",
        prior_user_questions=["总结2511.22858"],
        library_ids=[("arxiv", "2511.22858")],
    )
    assert followup.spec.task_id == "mixed-draft-revision"
    assert (
        prepare_task("参考我的论文库，对我写的论文提出修改建议").spec.task_id
        == "mixed-draft-revision"
    )
    assert (
        prepare_task(
            "再解释这篇的局限", prior_user_questions=["总结2511.22858"], library_ids=library
        ).spec.task_id
        == "library-paper-qa"
    )
    assert (
        prepare_task(
            "请在arxiv上搜索2511.22858", prior_user_questions=previous, library_ids=library
        ).spec.task_id
        != "library-paper-qa"
    )
    assert prepare_task("概述2511.228589", library_ids=library).spec.task_id != "library-paper-qa"
    assert (
        prepare_task(
            "查找其他领域的最新论文", prior_user_questions=previous, library_ids=library
        ).spec.task_id
        != "library-paper-qa"
    )


def test_run_start_metadata_captures_pinned_task_versions_without_user_text() -> None:
    metadata = _agent_run_harness_metadata(
        "检查引用是否支持这段论述: TEST private draft", Settings(_env_file=None)
    )

    assert metadata["runtime_version"] == "research-runtime-2"
    assert metadata["workflow"][0] == "semantic-plan"
    assert "TEST private draft" not in str(metadata)


def test_enabled_daily_token_budget_covers_at_least_one_run() -> None:
    with pytest.raises(ValueError, match="must cover at least one agent run"):
        Settings(_env_file=None, agent_daily_user_token_budget=100)
