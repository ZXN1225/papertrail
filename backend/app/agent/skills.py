"""Safe, deterministic loading of built-in product skills.

Skills provide task guidance only. They cannot add tools, change tool permissions,
or override citation, licensing, and evidence validation performed by the harness.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

SKILL_REGISTRY_VERSION = "1.0.0"

# These names describe the existing bounded, read-only tool surface. A selected
# skill can recommend a subset; the harness remains responsible for intersecting
# suggestions with the tools actually registered for the run.
_READ_ONLY_TOOL_NAMES = frozenset(
    {
        "search_papers",
        "get_paper_details",
        "find_related_papers",
        "compare_papers",
        "retrieve_paper_evidence",
        "search_openalex_works",
        "get_openalex_work",
        "search_openalex_authors",
        "get_openalex_author",
        "list_openalex_author_works",
        "search_arxiv_metadata",
        "get_arxiv_metadata",
    }
)


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    skill_id: str
    version: str
    description: str
    filename: str
    triggers: tuple[str, ...]
    recommended_tools: tuple[str, ...]
    content_sha256: str


@dataclass(frozen=True, slots=True)
class SkillSelection:
    skill_id: str
    version: str
    reason: str
    registry_version: str
    registry_sha256: str


@dataclass(frozen=True, slots=True)
class LoadedSkill:
    skill_id: str
    version: str
    description: str
    instructions: str
    instructions_sha256: str
    registry_version: str
    registry_sha256: str
    selection_reason: str
    recommended_tools: tuple[str, ...]


class SkillLoadError(RuntimeError):
    """A built-in skill is missing, unsafe, or inconsistent with its registry."""


_DEFINITIONS: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        skill_id="paper-qa",
        version="1.0.0",
        description="Answer a focused research question from traceable paper evidence.",
        filename="paper-qa.SKILL.md",
        triggers=("paper-qa", "论文问答", "论文问题", "研究问题", "paper question"),
        recommended_tools=(
            "get_paper_details",
            "retrieve_paper_evidence",
            "search_papers",
            "search_arxiv_metadata",
            "get_arxiv_metadata",
        ),
        content_sha256="1eacc79e1a5caa97eb1fd9e32117d57d280f4665a9ce438c2af8d5cc8d84e160",
    ),
    SkillDefinition(
        skill_id="compare-papers",
        version="1.0.0",
        description="Compare selected papers while keeping metadata and findings distinct.",
        filename="compare-papers.SKILL.md",
        triggers=("compare-papers", "比较论文", "对比论文", "论文异同", "compare papers"),
        recommended_tools=("compare_papers", "get_paper_details", "retrieve_paper_evidence"),
        content_sha256="23956415131a859928e9b4efc3e81d9c265df26e3b2f130c1c194085927b2d10",
    ),
    SkillDefinition(
        skill_id="research-brief",
        version="1.0.0",
        description="Create a concise, evidence-linked research brief or literature overview.",
        filename="research-brief.SKILL.md",
        triggers=("research-brief", "研究简报", "文献综述", "研究综述", "literature review"),
        recommended_tools=(
            "search_papers",
            "get_paper_details",
            "retrieve_paper_evidence",
            "find_related_papers",
            "search_openalex_works",
            "search_arxiv_metadata",
        ),
        content_sha256="0d504fc8a996a8c1dc69307347f55a26a39ea4bf41924efda103d929d2cfdb61",
    ),
)

SKILL_REGISTRY: Mapping[str, SkillDefinition] = MappingProxyType(
    {definition.skill_id: definition for definition in _DEFINITIONS}
)
_SKILL_DIRECTORY = Path(__file__).with_name("skill_specs")
_REGISTRY_CANONICAL = json.dumps(
    {
        "version": SKILL_REGISTRY_VERSION,
        "skills": [
            {
                "id": definition.skill_id,
                "version": definition.version,
                "description": definition.description,
                "filename": definition.filename,
                "triggers": definition.triggers,
                "recommended_tools": definition.recommended_tools,
                "content_sha256": definition.content_sha256,
            }
            for definition in _DEFINITIONS
        ],
    },
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
SKILL_REGISTRY_SHA256 = hashlib.sha256(_REGISTRY_CANONICAL.encode("utf-8")).hexdigest()

_COMPARE_PATTERNS = re.compile(
    r"比较|对比|异同|区别|compare\s+papers|paper\s+comparison", re.IGNORECASE
)
_BRIEF_PATTERNS = re.compile(
    r"文献综述|研究综述|研究简报|综述|literature\s+review|research\s+brief", re.IGNORECASE
)


def select_skill(task_text: str, *, requested_skill: str | None = None) -> SkillSelection:
    """Select a built-in skill from an explicit ID or simple deterministic task cues."""
    if requested_skill is not None:
        definition = SKILL_REGISTRY.get(requested_skill)
        if definition is None:
            raise ValueError(f"unknown skill: {requested_skill}")
        reason = "explicit_request"
    else:
        definition, reason = _select_from_text(task_text)

    return SkillSelection(
        skill_id=definition.skill_id,
        version=definition.version,
        reason=reason,
        registry_version=SKILL_REGISTRY_VERSION,
        registry_sha256=SKILL_REGISTRY_SHA256,
    )


def load_skill(selection: SkillSelection) -> LoadedSkill:
    """Load one registry-pinned Markdown file; no user-controlled path is accepted."""
    definition = SKILL_REGISTRY.get(selection.skill_id)
    if definition is None or definition.version != selection.version:
        raise SkillLoadError("selection does not match a registered skill version")
    if (
        selection.registry_version != SKILL_REGISTRY_VERSION
        or selection.registry_sha256 != SKILL_REGISTRY_SHA256
    ):
        raise SkillLoadError("selection was created against a different skill registry")

    # Use only the filename pinned in the immutable built-in registry. Reject
    # symlinks so a skill cannot redirect file loading outside this package.
    path = _SKILL_DIRECTORY / definition.filename
    try:
        if _SKILL_DIRECTORY.is_symlink() or path.is_symlink():
            raise SkillLoadError("skill spec path is not a regular built-in file")
        raw = path.read_bytes()
    except OSError as error:
        raise SkillLoadError("built-in skill spec could not be read") from error
    if hashlib.sha256(raw).hexdigest() != definition.content_sha256:
        raise SkillLoadError("built-in skill content hash does not match its reviewed pin")

    try:
        text = raw.decode("utf-8")
        metadata, instructions = _parse_skill_file(text)
    except (UnicodeDecodeError, ValueError) as error:
        raise SkillLoadError("built-in skill spec metadata is invalid") from error

    expected = {
        "name": definition.skill_id,
        "description": definition.description,
        "version": definition.version,
        "allowed-tools": ",".join(definition.recommended_tools),
    }
    if metadata != expected:
        raise SkillLoadError("built-in skill spec does not match its registry")
    if not set(definition.recommended_tools) <= _READ_ONLY_TOOL_NAMES:
        raise SkillLoadError("skill recommends a tool outside the fixed read-only surface")

    return LoadedSkill(
        skill_id=definition.skill_id,
        version=definition.version,
        description=definition.description,
        instructions=instructions,
        instructions_sha256=hashlib.sha256(raw).hexdigest(),
        registry_version=SKILL_REGISTRY_VERSION,
        registry_sha256=SKILL_REGISTRY_SHA256,
        selection_reason=selection.reason,
        recommended_tools=definition.recommended_tools,
    )


def prepare_skill(task_text: str, *, requested_skill: str | None = None) -> LoadedSkill:
    """Select and load a skill in one call for a harness integration point."""
    return load_skill(select_skill(task_text, requested_skill=requested_skill))


def _select_from_text(task_text: str) -> tuple[SkillDefinition, str]:
    normalized = task_text.strip().casefold()
    if _BRIEF_PATTERNS.search(normalized):
        return SKILL_REGISTRY["research-brief"], "matched_research_brief_cue"
    if _COMPARE_PATTERNS.search(normalized):
        return SKILL_REGISTRY["compare-papers"], "matched_comparison_cue"
    for definition in _DEFINITIONS:
        if any(trigger.casefold() in normalized for trigger in definition.triggers):
            return definition, f"matched_skill_trigger:{definition.skill_id}"
    return SKILL_REGISTRY["paper-qa"], "default_focused_question"


def _parse_skill_file(text: str) -> tuple[dict[str, str], str]:
    """Parse the deliberately small, single-line YAML-like front matter we support."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing front matter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("unterminated front matter") from error

    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if not separator or not key or not value.strip() or key in metadata:
            raise ValueError("invalid or duplicate metadata key")
        metadata[key] = value.strip()
    if set(metadata) != {"name", "description", "version", "allowed-tools"}:
        raise ValueError("unsupported metadata fields")
    instructions = "\n".join(lines[end + 1 :]).strip()
    if not instructions:
        raise ValueError("empty skill instructions")
    return metadata, instructions
