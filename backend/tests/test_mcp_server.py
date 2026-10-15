from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.server.mcpserver.exceptions import ToolError

from app.agent.tools import PaperToolRegistry
from app.mcp_server import _configured_database_path, _execute, create_mcp_server
from app.storage.repository import PaperStore


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_actual_mcp_client_calls_same_read_only_registry_contract() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        store = PaperStore(Path(temporary_dir) / "empty-catalog.sqlite3")
        store.migrate()
        before = hashlib.sha256(store.database_path.read_bytes()).hexdigest()
        server = create_mcp_server(store)
        direct = PaperToolRegistry(store).execute(
            "search_papers", '{"query":"TEST synthetic query","limit":3}'
        )

        async with Client(server, raise_exceptions=True, read_timeout_seconds=3) as client:
            tools = await client.list_tools()
            mcp_result = await client.call_tool(
                "search_papers", {"query": "TEST synthetic query", "limit": 3}
            )
        tool_names = [tool.name for tool in tools.tools]

        assert tool_names == [
            "search_papers",
            "get_paper_details",
            "find_related_papers",
            "compare_papers",
            "retrieve_paper_evidence",
        ]
        evidence_tool = next(tool for tool in tools.tools if tool.name == "retrieve_paper_evidence")
        method_schema = evidence_tool.input_schema["properties"]["retrieval_method"]
        assert "dense" not in json.dumps(method_schema)
        assert "hybrid" not in json.dumps(method_schema)
        structured = getattr(mcp_result, "structured_content", None)
        if structured is None:
            text_blocks = [block.text for block in mcp_result.content if hasattr(block, "text")]
            assert len(text_blocks) == 1
            structured = json.loads(text_blocks[0])
        assert structured == direct
        assert structured["status"] == "no_results"
        assert hashlib.sha256(store.database_path.read_bytes()).hexdigest() == before


@pytest.mark.anyio
async def test_mcp_does_not_create_a_missing_database() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        data_path = Path(temporary_dir) / "missing" / "catalog.sqlite3"
        async with Client(
            create_mcp_server(PaperStore(data_path)), read_timeout_seconds=3
        ) as client:
            result = await client.call_tool("search_papers", {"query": "TEST query", "limit": 2})

        assert result.is_error is True
        assert not data_path.exists()
        assert not data_path.parent.exists()


@pytest.mark.anyio
async def test_mcp_tool_failures_are_marked_as_protocol_errors() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        store = PaperStore(Path(temporary_dir) / "catalog.sqlite3")
        store.migrate()
        async with Client(create_mcp_server(store), read_timeout_seconds=3) as client:
            result = await client.call_tool("get_paper_details", {"openalex_id": "bad-id"})

        assert result.is_error is True
        assert "invalid_arguments" in result.content[0].text


def test_mcp_registry_rejects_unregistered_or_invalid_inputs() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        store = PaperStore(Path(temporary_dir) / "catalog.sqlite3")
        registry = PaperToolRegistry(store)
        assert registry.execute("arbitrary_sql", '{"query":"select 1"}') == {
            "status": "error",
            "code": "tool_not_allowed",
        }
        assert registry.execute("search_papers", '{"query":"x","limit":999}') == {
            "status": "error",
            "code": "invalid_arguments",
        }


@pytest.mark.parametrize(
    "status", ["embedding_unavailable", "embedding_error", "embeddings_missing"]
)
def test_mcp_embedding_failures_are_protocol_errors(status: str) -> None:
    class EmbeddingFailureRegistry:
        def execute(self, name: str, arguments: str) -> dict[str, object]:
            return {"status": status, "code": "provider_unavailable"}

    with pytest.raises(ToolError, match="provider_unavailable"):
        _execute(EmbeddingFailureRegistry(), "retrieve_paper_evidence", {})  # type: ignore[arg-type]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status", ["embedding_unavailable", "embedding_error", "embeddings_missing"]
)
async def test_mcp_client_sees_embedding_failure_as_protocol_error(status: str) -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        store = PaperStore(Path(temporary_dir) / "catalog.sqlite3")

        class EmbeddingFailureRegistry(PaperToolRegistry):
            def execute(self, name: str, arguments: str, **kwargs: object) -> dict[str, object]:
                if name == "retrieve_paper_evidence":
                    return {"status": status, "code": "provider_unavailable"}
                return super().execute(name, arguments, **kwargs)  # type: ignore[arg-type]

        registry = EmbeddingFailureRegistry(store)
        async with Client(create_mcp_server(_registry=registry), read_timeout_seconds=3) as client:
            result = await client.call_tool(
                "retrieve_paper_evidence", {"query": "TEST query", "limit": 2}
            )

        assert result.is_error is True
        assert "provider_unavailable" in result.content[0].text


@pytest.mark.anyio
async def test_mcp_client_launches_stdio_server_subprocess() -> None:
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary_dir:
        data_path = Path(temporary_dir) / "stdio-catalog.sqlite3"
        PaperStore(data_path).migrate()
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server"],
            cwd=Path(__file__).parents[1],
            env={**os.environ, "DATA_STORAGE_PATH": str(data_path)},
        )
        async with Client(parameters, read_timeout_seconds=10) as client:
            tools = await client.list_tools()
            result = await client.call_tool(
                "search_papers", {"query": "TEST stdio contract", "limit": 2}
            )

        assert "retrieve_paper_evidence" in [tool.name for tool in tools.tools]
        assert result.structured_content == {
            "status": "no_results",
            "scanned_documents": 0,
            "catalog_documents": 0,
            "truncated": False,
            "items": [],
        }


def test_mcp_uses_configured_database_path_without_provider_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "papertrail.sqlite3"
    PaperStore(database_path).migrate()
    monkeypatch.setenv("DATA_STORAGE_PATH", str(database_path))
    captured: dict[str, object] = {}

    class CapturingRegistry:
        def __init__(self, store: PaperStore) -> None:
            captured["store"] = store

        @property
        def definitions(self) -> list[dict[str, object]]:
            return []

        def execute(self, name: str, arguments: str) -> dict[str, object]:
            return {"status": "error", "code": "not_used"}

    monkeypatch.setattr("app.mcp_server.PaperToolRegistry", CapturingRegistry)
    create_mcp_server()

    assert _configured_database_path() == database_path
    readonly_store = captured["store"]
    assert isinstance(readonly_store, PaperStore)
    assert readonly_store.readonly is True


def test_mcp_resolves_relative_database_path_from_backend_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_STORAGE_PATH", "data\\papertrail.sqlite3")

    assert _configured_database_path() == Path(__file__).parents[1] / "data" / "papertrail.sqlite3"
