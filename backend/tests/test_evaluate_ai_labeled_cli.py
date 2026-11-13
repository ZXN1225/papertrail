from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.cli.evaluate_ai_labeled_tasks import (
    embed_task_queries,
    estimate_task_query_embedding_budget,
)


class _FakeEmbeddingClient:
    model = "TEST-embedding-model"

    def __init__(self, _settings: Any) -> None:
        self.calls: list[list[str]] = []
        self.closed = False

    def embed(self, texts: list[str]):
        self.calls.append(texts)
        return SimpleNamespace(
            model=self.model,
            vectors=[[float(index + 1), 1.0] for index, _ in enumerate(texts)],
            input_tokens=sum(len(text.encode("utf-8")) for text in texts),
        )

    def close(self) -> None:
        self.closed = True


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        embedding_provider="openai",
        embedding_price_per_million_usd=0.02,
    )


def _dataset() -> dict[str, Any]:
    return {
        "tasks": [
            {"task_id": "TEST-task-1", "question": "TEST method A"},
            {"task_id": "TEST-task-2", "question": "TEST method B"},
        ]
    }


def test_embedding_budget_requires_explicit_transfer_confirmation() -> None:
    with pytest.raises(ValueError, match="confirm-data-transfer"):
        embed_task_queries(
            _dataset(),
            _settings(),
            max_query_embeddings=2,
            max_cost_usd="0.01",
            confirm_data_transfer=False,
        )


def test_embedding_budget_estimate_prevents_provider_call() -> None:
    def unexpected_client(_settings):
        raise AssertionError("budget preflight must happen before provider construction")

    with pytest.raises(ValueError, match="upper-bound estimate"):
        embed_task_queries(
            _dataset(),
            _settings(),
            max_query_embeddings=2,
            max_cost_usd="0.000000001",
            confirm_data_transfer=True,
            client_factory=unexpected_client,
        )


def test_embedding_queries_are_bounded_and_usage_is_reported() -> None:
    client = _FakeEmbeddingClient(_settings())

    vectors, usage = embed_task_queries(
        _dataset(),
        _settings(),
        max_query_embeddings=2,
        max_cost_usd="0.01",
        confirm_data_transfer=True,
        client_factory=lambda _settings: client,
    )

    assert vectors == {"TEST-task-1": [1.0, 1.0], "TEST-task-2": [2.0, 1.0]}
    assert usage["provider_calls"] == 1
    assert usage["query_count"] == 2
    assert usage["calculated_cost_usd"] == "5.2E-7"
    assert client.closed is True


def test_query_embedding_budget_can_be_estimated_without_provider_client() -> None:
    budget = estimate_task_query_embedding_budget(
        _dataset(),
        _settings(),
        max_query_embeddings=2,
        max_cost_usd="0.01",
    )

    assert budget["query_count"] == 2
    assert budget["provider_call_upper_bound"] == 1
    assert budget["input_utf8_bytes_upper_bound"] == 26
    assert budget["estimated_upper_bound_cost_usd"] == "5.2E-7"
