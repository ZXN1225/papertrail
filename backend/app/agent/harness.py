"""Server-controlled bounded ReAct loop over typed deterministic tools."""

from __future__ import annotations

import json
from time import monotonic

from pydantic import ValidationError

from app.agent.contracts import AgentDecision, ToolObservation
from app.profiles.service import DomainError


class AgentHarness:
    MAX_DECISION_ROUNDS = 4
    MAX_TOOL_CALLS = 8
    TIME_LIMIT_SECONDS = 45.0
    MAX_OBSERVATION_CHARS = 16000

    def __init__(self, profile_service, registry, provider, clock=monotonic):
        self.profiles = profile_service
        self.registry = registry
        self.provider = provider
        self.clock = clock

    @staticmethod
    def _dedup_key(call):
        return (
            call.name
            + ":"
            + json.dumps(call.arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )

    def _bounded(self, observation):
        encoded = json.dumps(observation.data, ensure_ascii=False, default=str)
        if len(encoded) <= self.MAX_OBSERVATION_CHARS:
            return observation
        return observation.model_copy(
            update={
                "status": "partial",
                "data": {"truncated": True, "preview": encoded[: self.MAX_OBSERVATION_CHARS]},
                "missing_fields": sorted(
                    set(observation.missing_fields + ["observation_truncated"])
                ),
            }
        )

    def _error(self, name, code, message):
        return ToolObservation(
            name=name,
            status="error",
            data={},
            evidence_ids=[],
            missing_fields=[],
            error_code=code,
        )

    def run(self, cookie, request):
        snapshot = self.profiles.read(cookie, request.profile_id, request.profile_revision)
        profile = snapshot.profile
        if self.provider.name == "disabled":
            return {
                "status": "provider_disabled",
                "profile_id": snapshot.id,
                "profile_revision": snapshot.revision,
                "tool_calls_used": 0,
                "decision_rounds_used": 0,
                "observations": [],
                "pending_question": None,
                "reason": "MODEL_DISABLED",
            }
        started, observations, cache = self.clock(), [], {}
        rounds = tool_calls = 0
        while rounds < self.MAX_DECISION_ROUNDS and tool_calls < self.MAX_TOOL_CALLS:
            if self.clock() - started >= self.TIME_LIMIT_SECONDS:
                return self._response(
                    "timed_out", snapshot, tool_calls, rounds, observations, "TIME_LIMIT"
                )
            context = {
                "message": request.message,
                "profile": profile.model_dump(mode="json"),
                "observations": [item.model_dump(mode="json") for item in observations],
            }
            try:
                decision = AgentDecision.model_validate(
                    self.provider.decide(context, self.registry.schema_names())
                )
            except (ValidationError, StopIteration, TypeError, ValueError):
                return self._response(
                    "failed",
                    snapshot,
                    tool_calls,
                    rounds,
                    observations,
                    "INVALID_PROVIDER_DECISION",
                )
            rounds += 1
            if decision.kind == "final":
                return self._response(
                    "completed", snapshot, tool_calls, rounds, observations, decision.reason
                )
            if decision.kind == "clarify":
                return self._response(
                    "clarifying", snapshot, tool_calls, rounds, observations, decision.question
                )
            if decision.tool_call is None:
                return self._response(
                    "failed", snapshot, tool_calls, rounds, observations, "MISSING_TOOL_CALL"
                )
            tool_calls += 1
            key = self._dedup_key(decision.tool_call)
            if key in cache:
                observation = cache[key].model_copy(update={"deduplicated": True})
            else:
                try:
                    observation = self.registry.execute(decision.tool_call, profile)
                except (ValidationError, ValueError) as exc:
                    observation = self._error(
                        decision.tool_call.name, "INVALID_TOOL_ARGUMENTS", str(exc)
                    )
                except DomainError as exc:
                    observation = self._error(decision.tool_call.name, exc.code, exc.message)
                cache[key] = observation
            observations.append(self._bounded(observation))
        reason = "TOOL_CALL_LIMIT" if tool_calls >= self.MAX_TOOL_CALLS else "DECISION_ROUND_LIMIT"
        return self._response("partial", snapshot, tool_calls, rounds, observations, reason)

    @staticmethod
    def _response(status, snapshot, tool_calls, rounds, observations, reason):
        return {
            "status": status,
            "profile_id": snapshot.id,
            "profile_revision": snapshot.revision,
            "tool_calls_used": tool_calls,
            "decision_rounds_used": rounds,
            "observations": observations,
            "pending_question": reason if status == "clarifying" else None,
            "reason": reason if status != "clarifying" else None,
        }
