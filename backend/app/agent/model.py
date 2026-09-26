"""Small Responses API adapter behind an injectable model-turn protocol."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config import Settings

API_URL = "https://api.openai.com/v1/responses"
FINAL_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "name": "papertrail_research_answer",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "cited_openalex_ids": {
                "type": "array",
                "items": {"type": "string", "pattern": "^W[0-9]+$"},
            },
            "cited_arxiv_ids": {
                "type": "array",
                "items": {"type": "string", "minLength": 4, "maxLength": 64},
            },
            "insufficient_evidence": {"type": "boolean"},
        },
        "required": ["answer", "cited_openalex_ids", "cited_arxiv_ids", "insufficient_evidence"],
        "additionalProperties": False,
    },
}


@dataclass(frozen=True)
class ModelToolCall:
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ModelTurn:
    tool_calls: list[ModelToolCall]
    continuation_items: list[dict[str, Any]]
    final_text: str | None
    refusal: bool
    input_tokens: int
    output_tokens: int
    incomplete_reason: str | None = None


class ModelClient(Protocol):
    def complete(
        self,
        *,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelTurn: ...


class ModelUnavailable(RuntimeError):
    """A safe, non-sensitive model provider error."""


class OpenAIResponsesClient:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        if (
            settings.llm_provider != "openai"
            or settings.llm_api_key is None
            or not settings.llm_model
        ):
            raise ValueError("OpenAI LLM provider is not configured")
        self.settings = settings
        self._owns_client = http_client is None
        self.client = http_client or httpx.Client(
            timeout=httpx.Timeout(settings.llm_timeout_seconds),
            follow_redirects=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def complete(
        self,
        *,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelTurn:
        payload = {
            "model": self.settings.llm_model,
            "instructions": instructions,
            "input": input_items,
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "text": {"format": FINAL_ANSWER_SCHEMA},
            "max_output_tokens": self.settings.llm_max_output_tokens,
            "store": False,
        }
        try:
            response = self.client.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {self.settings.llm_api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as error:
            raise ModelUnavailable("OpenAI Responses API request failed.") from error
        if response.status_code < 200 or response.status_code >= 300:
            raise ModelUnavailable(f"OpenAI Responses API returned HTTP {response.status_code}.")
        try:
            body = response.json()
        except ValueError as error:
            raise ModelUnavailable("OpenAI Responses API returned invalid JSON.") from error
        if not isinstance(body, dict) or not isinstance(body.get("output"), list):
            raise ModelUnavailable("OpenAI Responses API returned an invalid response shape.")

        calls: list[ModelToolCall] = []
        final_fragments: list[str] = []
        refusal = False
        output_items = body["output"]
        for item in output_items:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "function_call":
                call_id = item.get("call_id")
                name = item.get("name")
                arguments = item.get("arguments")
                if all(isinstance(value, str) for value in (call_id, name, arguments)):
                    calls.append(ModelToolCall(call_id, name, arguments))
            elif item.get("type") == "message" and isinstance(item.get("content"), list):
                for content in item["content"]:
                    if not isinstance(content, dict):
                        continue
                    if content.get("type") == "output_text" and isinstance(
                        content.get("text"), str
                    ):
                        final_fragments.append(content["text"])
                    elif content.get("type") == "refusal":
                        refusal = True
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        input_tokens = _nonnegative_int(usage.get("input_tokens"))
        output_tokens = _nonnegative_int(usage.get("output_tokens"))
        incomplete = (
            body.get("incomplete_details")
            if isinstance(body.get("incomplete_details"), dict)
            else {}
        )
        incomplete_reason = (
            incomplete.get("reason")
            if body.get("status") == "incomplete"
            and incomplete.get("reason") in {"max_output_tokens", "content_filter"}
            else "unknown"
            if body.get("status") == "incomplete"
            else None
        )
        return ModelTurn(
            tool_calls=calls,
            continuation_items=[item for item in output_items if isinstance(item, dict)],
            final_text="".join(final_fragments) or None,
            refusal=refusal,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            incomplete_reason=incomplete_reason,
        )


def encode_tool_result(call_id: str, observation: dict[str, Any]) -> dict[str, str]:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": json.dumps(observation, ensure_ascii=False, sort_keys=True),
    }


def _nonnegative_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
