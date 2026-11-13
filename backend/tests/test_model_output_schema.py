from __future__ import annotations

import json
from typing import Any

import httpx

from app.agent.model import OpenAIResponsesClient, estimate_input_tokens_upper_bound
from app.config import Settings
from app.evaluation.llm_judge import JUDGE_OUTPUT_SCHEMA


def test_responses_client_accepts_a_separate_strict_schema_and_disables_tools():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "{}"}],
                    }
                ],
                "usage": {"input_tokens": 20, "output_tokens": 10},
            },
        )

    settings = Settings(
        llm_provider="openai",
        llm_api_key="TEST-key",
        llm_model="TEST-judge-model",
        llm_max_output_tokens=600,
        embedding_provider="disabled",
    )
    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAIResponsesClient(settings, http_client=http)
    client.complete(
        instructions="TEST judge",
        input_items=[{"role": "user", "content": "TEST question"}],
        tools=[],
        max_output_tokens=100,
        output_schema=JUDGE_OUTPUT_SCHEMA,
    )

    assert captured["text"]["format"] == JUDGE_OUTPUT_SCHEMA
    assert captured["tool_choice"] == "none"
    assert captured["tools"] == []
    assert captured["store"] is False
    custom_bound = estimate_input_tokens_upper_bound(
        instructions="TEST judge",
        input_items=[{"role": "user", "content": "TEST question"}],
        tools=[],
        max_output_tokens=100,
        output_schema=JUDGE_OUTPUT_SCHEMA,
    )
    assert custom_bound > 4_096
