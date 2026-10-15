from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from app.agent.skills import (
    SKILL_REGISTRY,
    SKILL_REGISTRY_SHA256,
    SkillLoadError,
    load_skill,
    prepare_skill,
    select_skill,
)


def test_registry_contains_only_the_three_product_skills() -> None:
    assert set(SKILL_REGISTRY) == {"paper-qa", "compare-papers", "research-brief"}
    with pytest.raises(TypeError):
        SKILL_REGISTRY["other"] = SKILL_REGISTRY["paper-qa"]  # type: ignore[index]


@pytest.mark.parametrize(
    ("task", "expected", "reason"),
    [
        ("请比较论文 A 和论文 B 的实验设置", "compare-papers", "matched_comparison_cue"),
        ("写一份该方向的文献综述", "research-brief", "matched_research_brief_cue"),
        ("What is the main result of this paper?", "paper-qa", "default_focused_question"),
        ("paper-qa: explain the abstract", "paper-qa", "matched_skill_trigger:paper-qa"),
    ],
)
def test_select_skill_uses_deterministic_task_cues(task: str, expected: str, reason: str) -> None:
    selected = select_skill(task)

    assert selected.skill_id == expected
    assert selected.reason == reason
    assert selected.registry_sha256 == SKILL_REGISTRY_SHA256


def test_explicit_skill_selection_wins_and_unknown_names_are_rejected() -> None:
    selected = select_skill("写一份文献综述", requested_skill="paper-qa")

    assert selected.skill_id == "paper-qa"
    assert selected.reason == "explicit_request"
    with pytest.raises(ValueError, match="unknown skill"):
        select_skill("question", requested_skill="../../arbitrary-file")


@pytest.mark.parametrize("skill_id", ["paper-qa", "compare-papers", "research-brief"])
def test_loaded_skill_is_registry_pinned_and_reports_its_content_hash(skill_id: str) -> None:
    loaded = prepare_skill("ordinary question", requested_skill=skill_id)
    definition = SKILL_REGISTRY[skill_id]

    assert loaded.skill_id == skill_id
    assert loaded.version == definition.version
    assert loaded.instructions
    assert (
        loaded.instructions_sha256
        == hashlib.sha256(_read_builtin_file(definition.filename).encode("utf-8")).hexdigest()
    )
    assert loaded.registry_sha256 == SKILL_REGISTRY_SHA256
    assert loaded.selection_reason == "explicit_request"
    assert set(loaded.recommended_tools) <= {
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
    assert "licensing" in loaded.instructions
    assert "citation" in loaded.instructions


def test_loader_rejects_selection_from_another_registry_fingerprint() -> None:
    selected = select_skill("question")
    stale = replace(selected, registry_sha256="0" * 64)

    with pytest.raises(SkillLoadError, match="different skill registry"):
        load_skill(stale)


def test_loader_rejects_unreviewed_content_drift(tmp_path, monkeypatch) -> None:
    import app.agent.skills as skills_module

    selected = select_skill("question")
    definition = SKILL_REGISTRY[selected.skill_id]
    source = _read_builtin_file(definition.filename)
    (tmp_path / definition.filename).write_text(source + "\nUnreviewed change.\n", encoding="utf-8")
    monkeypatch.setattr(skills_module, "_SKILL_DIRECTORY", tmp_path)

    with pytest.raises(SkillLoadError, match="content hash"):
        load_skill(selected)


def _read_builtin_file(filename: str) -> str:
    # The filename comes from the statically tested registry, never from user input.
    from pathlib import Path

    return (Path(__file__).parents[1] / "app" / "agent" / "skill_specs" / filename).read_text(
        encoding="utf-8"
    )
