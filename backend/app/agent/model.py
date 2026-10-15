"""Small Responses API adapter behind an injectable model-turn protocol."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config import Settings

API_URL = "https://api.openai.com/v1/responses"
_INPUT_TOKEN_OVERHEAD_BYTES = 4_096
METADATA_CITABLE_FIELDS = (
    "title",
    "publication_year",
    "published_at",
    "updated_at",
    "doi",
    "authors",
    "categories",
    "primary_category",
    "cited_by_count",
)
FINAL_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "name": "papertrail_research_answer",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "Exactly the claim texts joined by one newline, with no extras.",
            },
            "cited_openalex_ids": {
                "type": "array",
                "items": {"type": "string", "pattern": "^W[0-9]+$"},
            },
            "cited_arxiv_ids": {
                "type": "array",
                "items": {"type": "string", "minLength": 4, "maxLength": 64},
            },
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "minLength": 1, "maxLength": 1_000},
                        "evidence": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 8,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "source_id": {
                                        "type": "string",
                                        "minLength": 4,
                                        "maxLength": 64,
                                    },
                                    "quote": {
                                        "type": "string",
                                        "minLength": 1,
                                        "maxLength": 1_000,
                                        "description": (
                                            "An exact contiguous substring of the observed field. "
                                            "Preserve whitespace, line breaks, hyphens "
                                            "and symbols. Encode line breaks as JSON escapes."
                                        ),
                                    },
                                    "evidence_type": {
                                        "type": "string",
                                        "enum": ["metadata", "fulltext"],
                                    },
                                    "source_field": {
                                        "type": "string",
                                        "enum": ["excerpt", *METADATA_CITABLE_FIELDS],
                                        "description": (
                                            "For fulltext always use excerpt. For metadata use "
                                            "the exact observed bibliographic field name."
                                        ),
                                    },
                                    "chunk_id": {"type": ["string", "null"], "maxLength": 180},
                                },
                                "required": [
                                    "source_id",
                                    "quote",
                                    "evidence_type",
                                    "source_field",
                                    "chunk_id",
                                ],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["text", "evidence"],
                    "additionalProperties": False,
                },
            },
            "insufficient_evidence": {"type": "boolean"},
        },
        "required": [
            "answer",
            "cited_openalex_ids",
            "cited_arxiv_ids",
            "claims",
            "insufficient_evidence",
        ],
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


class ModelClient(Protocol):
    def complete(
        self,
        *,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_output_tokens: int | None = None,
    ) -> ModelTurn: ...


def estimate_input_tokens_upper_bound(
    *,
    instructions: str,
    input_items: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    max_output_tokens: int,
) -> int:
    """Return a conservative UTF-8 byte bound plus provider-envelope reserve."""
    request_shape = {
        "instructions": instructions,
        "input": input_items,
        "tools": tools,
        "text": {"format": FINAL_ANSWER_SCHEMA},
        "max_output_tokens": max_output_tokens,
    }
    return len(json.dumps(request_shape, ensure_ascii=False).encode("utf-8")) + (
        _INPUT_TOKEN_OVERHEAD_BYTES
    )


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
        max_output_tokens: int | None = None,
    ) -> ModelTurn:
        output_limit = (
            self.settings.llm_max_output_tokens if max_output_tokens is None else max_output_tokens
        )
        if output_limit < 1 or output_limit > self.settings.llm_max_output_tokens:
            raise ValueError("max_output_tokens must be within the configured model limit")
        payload = {
            "model": self.settings.llm_model,
            "instructions": instructions,
            "input": input_items,
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "text": {"format": FINAL_ANSWER_SCHEMA},
            "max_output_tokens": output_limit,
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
        usage = body.get("usage")
        if not isinstance(usage, dict):
            raise ModelUnavailable("OpenAI Responses API omitted token usage.")
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        if not _is_nonnegative_int(input_tokens) or not _is_nonnegative_int(output_tokens):
            raise ModelUnavailable("OpenAI Responses API returned invalid token usage.")
        final_text = _collapse_identical_complete_json("".join(final_fragments)) or None
        return ModelTurn(
            tool_calls=calls,
            continuation_items=[item for item in output_items if isinstance(item, dict)],
            final_text=final_text,
            refusal=refusal,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def encode_tool_result(call_id: str, observation: dict[str, Any]) -> dict[str, str]:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": json.dumps(observation, ensure_ascii=False, sort_keys=True),
    }


def _collapse_identical_complete_json(text: str) -> str:
    """Collapse only exact repeats of one complete JSON object, not partial fragments."""
    try:
        parsed, end = json.JSONDecoder().raw_decode(text)
    except ValueError:
        return text
    if not isinstance(parsed, dict) or end == len(text) or end == 0:
        return text
    first = text[:end]
    if len(text) % end == 0 and text == first * (len(text) // end):
        return first
    return text


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
