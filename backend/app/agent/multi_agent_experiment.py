"""Feature-isolated sequential multi-agent experiment coordinator.

This module is intentionally not wired into the production ask route. It exists to
run a controlled worker/supervisor comparison without changing the single-agent default.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from app.agent.contracts import AgentResponse

Worker = Callable[[str, int, int, float, Callable[[], bool]], AgentResponse]
Decision = Literal["consensus", "conflict", "insufficient_workers", "budget_exceeded", "cancelled"]


@dataclass(frozen=True)
class WorkerSpec:
    name: str
    run: Worker


@dataclass(frozen=True)
class WorkerResult:
    name: str
    status: str
    total_observed_tokens: int
    tool_calls: int
    response: AgentResponse
    failure_type: str | None = None


@dataclass(frozen=True)
class MultiAgentExperimentResult:
    decision: Decision
    workers: tuple[WorkerResult, ...]
    selected_response: AgentResponse | None
    total_observed_tokens: int
    total_tool_calls: int


class MultiAgentExperiment:
    """Run bounded workers sequentially under one aggregate token/tool/deadline budget."""

    def __init__(
        self,
        workers: Sequence[WorkerSpec],
        *,
        max_workers: int = 3,
        max_total_tokens: int = 12_000,
        max_tool_calls: int = 12,
        deadline_seconds: float = 90.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not workers or not 1 <= max_workers <= 3:
            raise ValueError("one to three workers are required")
        if max_total_tokens < 1 or max_tool_calls < 1 or deadline_seconds <= 0:
            raise ValueError("experiment budgets must be positive")
        selected = tuple(workers[:max_workers])
        if len({worker.name for worker in selected}) != len(selected):
            raise ValueError("worker names must be unique")
        self.workers = selected
        self.max_total_tokens = max_total_tokens
        self.max_tool_calls = max_tool_calls
        self.deadline_seconds = deadline_seconds
        self.clock = clock

    def run(
        self,
        task: str,
        *,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> MultiAgentExperimentResult:
        cancelled = cancellation_requested or (lambda: False)
        started = self.clock()
        token_total = 0
        tool_total = 0
        results: list[WorkerResult] = []
        successful: list[WorkerResult] = []
        decision: Decision = "insufficient_workers"

        for worker in self.workers:
            if cancelled():
                decision = "cancelled"
                break
            remaining_seconds = self.deadline_seconds - (self.clock() - started)
            remaining_tokens = self.max_total_tokens - token_total
            remaining_tools = self.max_tool_calls - tool_total
            if remaining_seconds <= 0 or remaining_tokens <= 0 or remaining_tools <= 0:
                decision = "budget_exceeded"
                break

            try:
                response = worker.run(
                    task,
                    remaining_tokens,
                    remaining_tools,
                    remaining_seconds,
                    cancelled,
                )
            except Exception as error:  # Keep a worker failure isolated and redacted.
                response = AgentResponse(
                    status="model_unavailable",
                    answer="Worker failed before returning a response.",
                )
                results.append(
                    WorkerResult(
                        name=worker.name,
                        status="failed",
                        total_observed_tokens=0,
                        tool_calls=0,
                        response=response,
                        failure_type=type(error).__name__[:80],
                    )
                )
                continue
            observed_tokens = _observed_tokens(response)
            token_total += observed_tokens
            tool_total += response.tool_calls
            result = WorkerResult(
                name=worker.name,
                status=response.status,
                total_observed_tokens=observed_tokens,
                tool_calls=response.tool_calls,
                response=response,
            )
            results.append(result)
            if response.status == "completed":
                successful.append(result)
            if token_total > self.max_total_tokens or tool_total > self.max_tool_calls:
                decision = "budget_exceeded"
                break
            if self.clock() - started >= self.deadline_seconds:
                decision = "budget_exceeded"
                break

        selected_response: AgentResponse | None = None
        if len(successful) >= 2:
            signatures = {_response_signature(item.response) for item in successful}
            if len(signatures) == 1:
                decision = "consensus"
                selected_response = successful[0].response
            else:
                decision = "conflict"
        elif decision not in {"budget_exceeded", "cancelled"}:
            decision = "insufficient_workers"

        return MultiAgentExperimentResult(
            decision=decision,
            workers=tuple(results),
            selected_response=selected_response,
            total_observed_tokens=token_total,
            total_tool_calls=tool_total,
        )


def _observed_tokens(response: AgentResponse) -> int:
    # Trust the larger of the declared aggregate and the sum visible in trace
    # components so an inconsistent worker cannot understate usage in one field.
    trace_tokens = sum(
        event.input_tokens + event.output_tokens for event in response.trace if event.kind == "tool"
    )
    component_total = response.model_input_tokens + response.model_output_tokens + trace_tokens
    return max(response.total_observed_tokens, component_total)


def _response_signature(response: AgentResponse) -> str:
    """Require exact agreement on structured claims and cited source identities."""
    return json.dumps(
        {
            "claims": [claim.model_dump(mode="json") for claim in response.claims],
            "citations": sorted(
                citation.openalex_id or citation.arxiv_id or "" for citation in response.citations
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
