"""Validated, prompt-only runtime skills with fixed tool allowlists."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.tools import TOOL_DEFINITIONS

SKILLS_PATH = Path(__file__).with_name("skills.json")
_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_SKILL_CHARS = 4_000
_KNOWN_TOOL_NAMES = {item["name"] for item in TOOL_DEFINITIONS}


class RuntimeSkill(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=240)
    instructions: str = Field(min_length=1, max_length=_MAX_SKILL_CHARS)
    allowed_tools: tuple[str, ...] = Field(min_length=1, max_length=16)


class RuntimeSkillRegistry:
    """Loads trusted, packaged workflow instructions; never loads executable code."""

    def __init__(self, path: Path = SKILLS_PATH) -> None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            skills = [RuntimeSkill.model_validate(item) for item in raw]
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise ValueError("runtime_skill_catalog_invalid") from exc
        names = [skill.name for skill in skills]
        if (
            not skills
            or len(names) != len(set(names))
            or any(not _NAME_PATTERN.fullmatch(name) for name in names)
            or any(not set(skill.allowed_tools).issubset(_KNOWN_TOOL_NAMES) for skill in skills)
        ):
            raise ValueError("runtime_skill_catalog_invalid")
        self._skills = {skill.name: skill for skill in skills}

    @property
    def skills(self) -> tuple[RuntimeSkill, ...]:
        return tuple(self._skills.values())

    def activation_definition(self) -> dict:
        names = list(self._skills)
        return {
            "type": "function",
            "name": "activate_skill",
            "description": (
                "Activate one built-in research workflow before using its paper tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "enum": names}},
                "required": ["name"],
                "additionalProperties": False,
            },
            "strict": True,
        }

    def menu(self) -> str:
        return "\n".join(f"- {skill.name}: {skill.description}" for skill in self.skills)

    def activate(self, arguments: str, available_tool_names: set[str]) -> dict:
        try:
            payload = json.loads(arguments)
        except (json.JSONDecodeError, TypeError):
            return {"status": "error", "code": "invalid_arguments"}
        if not isinstance(payload, dict) or set(payload) != {"name"}:
            return {"status": "error", "code": "invalid_arguments"}
        skill = self._skills.get(payload["name"]) if isinstance(payload["name"], str) else None
        if skill is None:
            return {"status": "error", "code": "skill_not_allowed"}
        permitted = [name for name in skill.allowed_tools if name in available_tool_names]
        if not permitted:
            return {"status": "error", "code": "skill_unavailable"}
        return {
            "status": "ok",
            "skill": skill.name,
            "instructions": skill.instructions,
            "available_tool_names": permitted,
        }
