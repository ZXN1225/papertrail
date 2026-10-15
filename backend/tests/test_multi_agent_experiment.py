from __future__ import annotations

from collections.abc import Callable

from app.agent.contracts import AgentResponse, Claim, ClaimEvidence
from app.agent.multi_agent_experiment import MultiAgentExperiment, WorkerSpec


def _response(
    text: str = "TEST-supported claim",
    *,
    tokens: int = 10,
    tools: int = 1,
    status: str = "completed",
) -> AgentResponse:
    claims = (
        [
            Claim(
                text=text,
                evidence=[
                    ClaimEvidence(
                        source_id="W100",
                        quote="TEST synthetic evidence",
                        evidence_type="fulltext",
                        source_field="excerpt",
                        chunk_id="TEST-CHUNK-001",
                    )
                ],
            )
        ]
        if status == "completed"
        else []
    )
    return AgentResponse(
        status=status,  # type: ignore[arg-type]
        answer=text if status == "completed" else "TEST worker did not complete",
        claims=claims,
        model_input_tokens=tokens // 2,
        model_output_tokens=tokens - tokens // 2,
        total_observed_tokens=tokens,
        tool_calls=tools,
    )


def _worker(
    response: AgentResponse,
    seen_budgets: list[tuple[int, int, float]] | None = None,
) -> Callable[[str, int, int, float, Callable[[], bool]], AgentResponse]:
    def run(
        task: str,
        token_budget: int,
        tool_budget: int,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> AgentResponse:
        assert task.startswith("TEST")
        assert not cancelled()
        if seen_budgets is not None:
            seen_budgets.append((token_budget, tool_budget, deadline))
        return response

    return run


def test_multi_agent_requires_exact_claim_and_citation_consensus() -> None:
    experiment = MultiAgentExperiment(
        [
            WorkerSpec("evidence-reviewer", _worker(_response())),
            WorkerSpec("critic", _worker(_response())),
        ]
    )

    result = experiment.run("TEST compare single and multi-agent")

    assert result.decision == "consensus"
    assert result.selected_response is not None
    assert result.total_observed_tokens == 20
    assert result.total_tool_calls == 2
    assert [item.name for item in result.workers] == ["evidence-reviewer", "critic"]


def test_multi_agent_conflict_does_not_merge_worker_answers() -> None:
    experiment = MultiAgentExperiment(
        [
            WorkerSpec("evidence-reviewer", _worker(_response("TEST claim A"))),
            WorkerSpec("critic", _worker(_response("TEST claim B"))),
        ]
    )

    result = experiment.run("TEST identify conflict")

    assert result.decision == "conflict"
    assert result.selected_response is None


def test_multi_agent_stops_when_shared_budget_is_exhausted() -> None:
    seen: list[tuple[int, int, float]] = []
    experiment = MultiAgentExperiment(
        [
            WorkerSpec("evidence-reviewer", _worker(_response(tokens=12), seen)),
            WorkerSpec("critic", _worker(_response(), seen)),
        ],
        max_total_tokens=10,
        max_tool_calls=3,
    )

    result = experiment.run("TEST exhaust aggregate budget")

    assert result.decision == "budget_exceeded"
    assert len(result.workers) == 1
    assert len(seen) == 1
    assert seen[0][0] == 10


def test_multi_agent_passes_decreasing_budgets_to_sequential_workers() -> None:
    seen: list[tuple[int, int, float]] = []
    experiment = MultiAgentExperiment(
        [
            WorkerSpec("evidence-reviewer", _worker(_response(tokens=10, tools=2), seen)),
            WorkerSpec("critic", _worker(_response(tokens=5, tools=1), seen)),
        ],
        max_total_tokens=20,
        max_tool_calls=5,
    )

    experiment.run("TEST inspect shared limits")

    assert [budget[:2] for budget in seen] == [(20, 5), (10, 3)]


def test_multi_agent_honors_cancellation_before_starting_next_worker() -> None:
    cancelled = False

    def first_worker(
        task: str,
        token_budget: int,
        tool_budget: int,
        deadline: float,
        cancellation_requested: Callable[[], bool],
    ) -> AgentResponse:
        nonlocal cancelled
        cancelled = True
        return _response()

    second_started = False

    def second_worker(
        task: str,
        token_budget: int,
        tool_budget: int,
        deadline: float,
        cancellation_requested: Callable[[], bool],
    ) -> AgentResponse:
        nonlocal second_started
        second_started = True
        return _response()

    result = MultiAgentExperiment(
        [WorkerSpec("first", first_worker), WorkerSpec("second", second_worker)]
    ).run("TEST cancel experiment", cancellation_requested=lambda: cancelled)

    assert result.decision == "cancelled"
    assert len(result.workers) == 1
    assert not second_started


def test_multi_agent_has_a_hard_worker_limit() -> None:
    experiment = MultiAgentExperiment(
        [
            WorkerSpec("one", _worker(_response())),
            WorkerSpec("two", _worker(_response())),
            WorkerSpec("three", _worker(_response())),
            WorkerSpec("four", _worker(_response())),
        ],
        max_workers=3,
    )

    assert len(experiment.workers) == 3


def test_multi_agent_isolates_worker_exception_and_keeps_running() -> None:
    def fail(*args: object, **kwargs: object) -> AgentResponse:
        raise RuntimeError("sensitive provider detail must not be returned")

    experiment = MultiAgentExperiment(
        [
            WorkerSpec("failed", fail),
            WorkerSpec("reviewer", _worker(_response())),
            WorkerSpec("critic", _worker(_response())),
        ]
    )

    result = experiment.run("TEST survive partial failure")

    assert result.decision == "consensus"
    assert [worker.status for worker in result.workers] == ["failed", "completed", "completed"]
    assert result.workers[0].failure_type == "RuntimeError"
    assert "sensitive provider detail" not in result.workers[0].response.answer


def test_multi_agent_uses_trace_components_when_aggregate_underreports() -> None:
    underreported = AgentResponse(
        status="completed",
        answer="TEST supported claim",
        claims=_response().claims,
        total_observed_tokens=1,
        model_input_tokens=10,
        model_output_tokens=5,
        trace=[
            {
                "sequence": 1,
                "kind": "tool",
                "name": "retrieve_evidence",
                "status": "ok",
                "duration_ms": 1,
                "input_tokens": 7,
                "output_tokens": 0,
            }
        ],
        tool_calls=1,
    )
    experiment = MultiAgentExperiment(
        [WorkerSpec("worker", _worker(underreported))],
        max_total_tokens=20,
    )

    result = experiment.run("TEST enforce reported components")

    assert result.decision == "budget_exceeded"
    assert result.total_observed_tokens == 22
