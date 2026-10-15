"""Conservative per-request guard for explicitly authorized live evaluations.

This is an experimental billing estimate, not a provider-side spending limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.agent.model import (
    ModelClient,
    ModelTurn,
    ModelUnavailable,
    estimate_input_tokens_upper_bound,
)

_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class LiveCallUsage:
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: str
    preflight_upper_cost_usd: str
    final_text: str | None
    tool_calls: tuple[dict[str, str], ...]
    refusal: bool


class BudgetedModelClient:
    """Block new provider requests when the local cost estimate exceeds the cap."""

    def __init__(
        self,
        inner: ModelClient,
        *,
        input_price_per_million_usd: Decimal,
        output_price_per_million_usd: Decimal,
        max_cost_usd: Decimal,
        max_provider_calls: int,
        max_output_tokens: int,
    ) -> None:
        if (
            input_price_per_million_usd <= 0
            or output_price_per_million_usd <= 0
            or max_cost_usd <= 0
            or max_provider_calls < 1
            or max_output_tokens < 1
        ):
            raise ValueError("live price, cap and call limits must be positive")
        self.inner = inner
        self.input_price = input_price_per_million_usd
        self.output_price = output_price_per_million_usd
        self.max_cost = max_cost_usd
        self.max_provider_calls = max_provider_calls
        self.max_output_tokens = max_output_tokens
        self.estimated_spend = Decimal(0)
        self.calls_attempted = 0
        self.call_usage: list[LiveCallUsage] = []
        self.halt_reason: str | None = None

    def complete(
        self,
        *,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_output_tokens: int | None = None,
    ) -> ModelTurn:
        if self.halt_reason is not None:
            raise ModelUnavailable("Live evaluation has stopped.")
        if self.calls_attempted >= self.max_provider_calls:
            self.halt_reason = "provider_call_cap_reached"
            raise ModelUnavailable("Live evaluation provider-call cap reached.")
        output_limit = min(
            self.max_output_tokens,
            max_output_tokens if max_output_tokens is not None else self.max_output_tokens,
        )
        input_upper = estimate_input_tokens_upper_bound(
            instructions=instructions,
            input_items=input_items,
            tools=tools,
            max_output_tokens=output_limit,
        )
        reserved = self._cost(input_upper, output_limit)
        if self.estimated_spend + reserved > self.max_cost:
            self.halt_reason = "cost_preflight_cap_reached"
            raise ModelUnavailable("Live evaluation cost preflight cap reached.")
        self.calls_attempted += 1
        try:
            turn = self.inner.complete(
                instructions=instructions,
                input_items=input_items,
                tools=tools,
                max_output_tokens=output_limit,
            )
        except Exception:
            # A failed HTTP request may still have been billed. Hold the full
            # preflight reservation and stop rather than retrying blindly.
            self.estimated_spend += reserved
            self.halt_reason = "provider_failure_usage_unknown"
            raise
        actual = self._cost(turn.input_tokens, turn.output_tokens)
        if turn.input_tokens == 0 and turn.output_tokens == 0:
            self.estimated_spend += reserved
            self.halt_reason = "provider_usage_missing"
        else:
            self.estimated_spend += max(actual, Decimal(0))
            if turn.input_tokens > input_upper or turn.output_tokens > output_limit:
                self.halt_reason = "provider_usage_exceeded_preflight_bound"
            elif self.estimated_spend > self.max_cost:
                self.halt_reason = "observed_cost_cap_exceeded"
        self.call_usage.append(
            LiveCallUsage(
                input_tokens=turn.input_tokens,
                output_tokens=turn.output_tokens,
                estimated_cost_usd=str(actual),
                preflight_upper_cost_usd=str(reserved),
                final_text=turn.final_text,
                tool_calls=tuple(
                    {"name": call.name, "arguments": call.arguments} for call in turn.tool_calls
                ),
                refusal=turn.refusal,
            )
        )
        return turn

    @property
    def estimated_spend_usd(self) -> str:
        return str(self.estimated_spend)

    def _cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (
            Decimal(input_tokens) * self.input_price + Decimal(output_tokens) * self.output_price
        ) / _MILLION
