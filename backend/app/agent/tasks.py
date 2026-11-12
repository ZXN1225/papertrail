"""Versioned task contracts for the research assistant capability layer."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.agent.document_context import LOCAL_DOCUMENT_CUES
from app.agent.skills import LoadedSkill, SkillLoadError, load_skill, select_skill

TASK_REGISTRY_VERSION = "1.7.0"


@dataclass(frozen=True, slots=True)
class TaskSpec:
    task_id: str
    skill_id: str
    workflow: tuple[str, ...]
    required_tool_stages: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class PreparedTask:
    spec: TaskSpec
    skill: LoadedSkill
    external_requested: bool = False
    requested_sources: tuple[str, ...] = ()


_TASKS: dict[str, TaskSpec] = {
    "paper-qa": TaskSpec(
        "paper-qa", "paper-qa", ("retrieve", "form_claims", "validate_evidence", "answer")
    ),
    "compare-papers": TaskSpec(
        "compare-papers",
        "compare-papers",
        ("identify_papers", "compare_fields", "retrieve_findings", "validate_evidence", "answer"),
        (("compare_papers",),),
    ),
    "research-brief": TaskSpec(
        "research-brief",
        "research-brief",
        ("search", "retrieve", "synthesize_claims", "validate_evidence", "answer"),
        (("search_papers", "search_openalex_works", "search_arxiv_metadata"),),
    ),
    "draft-revision": TaskSpec(
        "draft-revision",
        "draft-revision",
        ("understand_revision_goal", "retrieve_if_needed", "revise", "validate_claims", "answer"),
    ),
    "citation-check": TaskSpec(
        "citation-check",
        "citation-check",
        ("retrieve", "match_claims_to_evidence", "report_supported_and_missing", "answer"),
        (("retrieve_paper_evidence",),),
    ),
    "personal-paper-qa": TaskSpec(
        "personal-paper-qa",
        "paper-qa",
        ("retrieve_personal_paper", "form_claims", "validate_evidence", "answer"),
        (("retrieve_paper_evidence",),),
    ),
    "library-paper-qa": TaskSpec(
        "library-paper-qa",
        "paper-qa",
        ("retrieve_library_papers", "form_claims", "validate_evidence", "answer"),
        (("retrieve_paper_evidence",),),
    ),
    "mixed-draft-revision": TaskSpec(
        "mixed-draft-revision",
        "draft-revision",
        (
            "retrieve_library_papers",
            "retrieve_personal_draft",
            "propose_revision",
            "validate_evidence",
        ),
        (("retrieve_paper_evidence",),),
    ),
    "external-paper-search": TaskSpec(
        "external-paper-search",
        "research-brief",
        ("search_requested_sources", "select_papers", "validate_metadata", "answer"),
    ),
    "library-online-research": TaskSpec(
        "library-online-research",
        "research-brief",
        ("search_requested_sources", "retrieve_library_papers", "validate_evidence", "answer"),
        (("retrieve_paper_evidence",),),
    ),
}
_LIBRARY_CUES = re.compile(
    r"我(?:的|这|自己)?(?:论文库|文献库)|个人(?:论文库|文献库)|"
    r"my (?:paper|research|document) library",
    re.IGNORECASE,
)
_MANUSCRIPT_CUES = re.compile(
    r"我(?:的|自己|自己的|本人|写的)?(?:稿件|论文稿件|论文草稿|草稿|论文(?!库))|"
    r"我的手稿|my (?:own )?(?:draft|manuscript)",
    re.IGNORECASE,
)
_PERSONAL_PAPER_CUES = LOCAL_DOCUMENT_CUES
_EXTERNAL_CUES = re.compile(
    r"联网|在线|网上|arxiv上|arxiv 上|openalex上|openalex 上|搜索新|查找新|最新(?:研究|论文|文献)|"
    r"online|on arxiv|on openalex",
    re.IGNORECASE,
)
_EXTERNAL_NEGATION_CUES = re.compile(
    r"不(?:要|需要|用|必|想|希望)|无需|无须|别|避免|禁止|拒绝|不联网|离线(?:模式|处理)?|"
    r"\b(?:don't|do not|does not|without|no need to|no (?:online|web|internet)|offline only|"
    r"not (?:use|using|search|searching|go|going|browse|access))\b",
    re.IGNORECASE,
)
_INTENT_CLAUSE_BREAKS = re.compile(
    r"[，,;；。.!?\n]+|但是|不过|而是|但|\bbut\b|\bhowever\b|\binstead\b",
    re.IGNORECASE,
)
_FOLLOWUP_CUES = re.compile(
    r"这篇|该论文|这两篇|上述|刚才|上面|继续(?:总结|分析|比较|解释)|该文|那篇|"
    r"this paper|that paper|these papers|follow.?up",
    re.IGNORECASE,
)
_SEARCH_CUES = re.compile(
    r"搜索|检索|查找|寻找|找出|找|search|find.*(?:papers|articles|research)", re.IGNORECASE
)
TASK_REGISTRY_SHA256 = hashlib.sha256(
    json.dumps(
        {
            "version": TASK_REGISTRY_VERSION,
            "tasks": [
                {
                    "task_id": spec.task_id,
                    "skill_id": spec.skill_id,
                    "workflow": spec.workflow,
                    "required_tool_stages": spec.required_tool_stages,
                }
                for _, spec in sorted(_TASKS.items())
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


def prepare_task(
    task_text: str,
    *,
    prior_user_questions: Sequence[str] = (),
    library_ids: Sequence[tuple[str, str]] = (),
    target_source_type: str | None = None,
) -> PreparedTask:
    """Select a pinned built-in skill and its fixed workflow contract."""
    selection = select_skill(task_text)
    intent_clauses = _INTENT_CLAUSE_BREAKS.split(task_text)
    affirmative_clauses = tuple(
        clause
        for clause in intent_clauses
        if not _EXTERNAL_NEGATION_CUES.search(clause)
        and (_EXTERNAL_CUES.search(clause) or _has_named_source_search(clause))
    )
    named_sources = tuple(
        source
        for source, cue in (("openalex", r"openalex"), ("arxiv", r"arxiv"))
        if any(re.search(cue, clause, re.IGNORECASE) for clause in affirmative_clauses)
    )
    named_search = bool(named_sources)
    explicit_external = bool(affirmative_clauses)

    def mentions_saved_id(text: str) -> bool:
        return any(
            source_id
            and re.search(
                r"(?<![A-Za-z0-9.])" + re.escape(source_id) + r"(?![A-Za-z0-9.])",
                text,
                re.IGNORECASE,
            )
            for _, source_id in library_ids
        )

    saved_id_mentioned = mentions_saved_id(task_text)
    library_followup = bool(
        prior_user_questions
        and _FOLLOWUP_CUES.search(task_text)
        and (
            _LIBRARY_CUES.search(prior_user_questions[-1])
            or mentions_saved_id(prior_user_questions[-1])
        )
        and not has_explicit_external_request(prior_user_questions[-1])
    )
    personal_followup = bool(
        prior_user_questions
        and _FOLLOWUP_CUES.search(task_text)
        and _PERSONAL_PAPER_CUES.search(prior_user_questions[-1])
        and not has_explicit_external_request(prior_user_questions[-1])
    )
    mixed_request = bool(
        _MANUSCRIPT_CUES.search(task_text)
        and (_LIBRARY_CUES.search(task_text) or saved_id_mentioned or library_followup)
    )
    task_id = (
        "mixed-draft-revision"
        if mixed_request
        else "library-online-research"
        if explicit_external and _LIBRARY_CUES.search(task_text)
        else "external-paper-search"
        if named_search
        else "personal-paper-qa"
        if not explicit_external and target_source_type == "personal"
        else "library-paper-qa"
        if not explicit_external and target_source_type in {"openalex", "arxiv"}
        else "library-paper-qa"
        if not explicit_external
        and (_LIBRARY_CUES.search(task_text) or saved_id_mentioned or library_followup)
        else "personal-paper-qa"
        if not explicit_external and (LOCAL_DOCUMENT_CUES.search(task_text) or personal_followup)
        else selection.skill_id
    )
    spec = _TASKS.get(task_id)
    if spec is None:
        raise SkillLoadError("selected skill has no registered task contract")
    if selection.skill_id != spec.skill_id:
        selection = select_skill(task_text, requested_skill=spec.skill_id)
    return PreparedTask(
        spec=spec,
        skill=load_skill(selection),
        external_requested=explicit_external,
        requested_sources=(
            named_sources or ("openalex", "arxiv")
            if task_id == "library-online-research"
            else named_sources
            if task_id == "external-paper-search"
            else ()
        ),
    )


def _has_named_source_search(text: str) -> bool:
    return bool(re.search(r"openalex|arxiv", text, re.IGNORECASE) and _SEARCH_CUES.search(text))


def has_explicit_external_request(text: str) -> bool:
    """Require an affirmative clause before enabling public-source tools."""
    return any(
        not _EXTERNAL_NEGATION_CUES.search(clause)
        and (_EXTERNAL_CUES.search(clause) or _has_named_source_search(clause))
        for clause in _INTENT_CLAUSE_BREAKS.split(text)
    )
