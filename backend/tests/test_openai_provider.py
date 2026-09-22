import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.agent.provider import OpenAIProvider, ProviderError
from app.agent.tools import ToolRegistry
from app.common.config import Settings


def provider():
    return OpenAIProvider("TEST-secret", "gpt-test", "https://api.openai.com/v1")


def response_for(name, arguments):
    return {
        "output": [
            {
                "type": "function_call",
                "name": name,
                "arguments": json.dumps(arguments),
            }
        ]
    }


class MockResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, _size=-1):
        return json.dumps(self.payload).encode()


def test_openai_provider_maps_tool_decision_and_sends_bounded_stateless_request():
    call = response_for("search_catalog", {"query": "TEST-机箱"})

    with patch("app.agent.provider.urlopen", return_value=MockResponse(call)) as send:
        decision = provider().decide(
            {"message": "TEST query", "observations": []},
            [
                {
                    "name": "search_catalog",
                    "description": "Search TEST items",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
        )

    assert decision.kind == "tool" and decision.tool_call.name == "search_catalog"
    request = send.call_args.args[0]
    payload = json.loads(request.data)
    assert request.full_url == "https://api.openai.com/v1/responses"
    assert request.get_header("Authorization") == "Bearer TEST-secret"
    assert send.call_args.kwargs["timeout"] == 15
    assert payload["store"] is False and payload["parallel_tool_calls"] is False
    assert payload["max_output_tokens"] == 512
    assert {item["name"] for item in payload["tools"]} >= {
        "search_catalog",
        "agent_final",
        "agent_clarify",
    }


@pytest.mark.parametrize(
    ("name", "arguments", "kind"),
    [
        ("agent_final", {"text": "TEST grounded answer"}, "final"),
        ("agent_clarify", {"question": "TEST clarification?"}, "clarify"),
    ],
)
def test_openai_provider_maps_terminal_decisions(name, arguments, kind):
    fake = MockResponse(response_for(name, arguments))
    with patch("app.agent.provider.urlopen", return_value=fake):
        decision = provider().decide({}, [])
    assert decision.kind == kind


def test_openai_provider_rejects_unknown_tool_and_sanitizes_transport_error():
    fake = MockResponse(response_for("run_shell", {"cmd": "bad"}))
    with (
        patch("app.agent.provider.urlopen", return_value=fake),
        pytest.raises(ProviderError, match="invalid decision"),
    ):
        provider().decide({}, [])
    with patch("app.agent.provider.urlopen", side_effect=OSError("TEST-secret upstream detail")):
        with pytest.raises(ProviderError) as error:
            provider().decide({}, [])
    assert "TEST-secret" not in str(error.value)


def test_openai_settings_require_key_only_when_explicitly_enabled():
    assert Settings(_env_file=None, llm_provider="disabled").llm_provider == "disabled"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_provider="openai", llm_api_key="")
    enabled = Settings(
        _env_file=None,
        llm_provider="openai",
        llm_api_key="TEST-key",
        llm_model="gpt-test",
    )
    assert enabled.llm_provider == "openai"


def test_tool_schema_export_contains_only_server_registry_tools():
    registry = ToolRegistry(catalog=None)
    schemas = registry.schema_definitions()
    names = {schema["name"] for schema in schemas}
    assert names == set(registry.schema_names())
    assert "run_shell" not in names and "execute_sql" not in names
