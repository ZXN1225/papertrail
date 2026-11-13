from __future__ import annotations

import json
import sys
import types

from app.cli import parse_private_pdf


def test_private_pdf_worker_forwards_configured_mineru_tier(tmp_path, monkeypatch) -> None:
    source = tmp_path / "TEST-paper.pdf"
    destination = tmp_path / "parsed.json"
    source.write_bytes(b"TEST synthetic input")
    called: dict[str, object] = {}

    mineru_module = types.ModuleType("mineru")
    mineru_module.__path__ = []
    config_module = types.ModuleType("mineru.config")
    config_module.get_config = lambda: types.SimpleNamespace(
        model=types.SimpleNamespace(vlm=types.SimpleNamespace(server_url=None))
    )
    monkeypatch.setitem(sys.modules, "mineru", mineru_module)
    monkeypatch.setitem(sys.modules, "mineru.config", config_module)
    monkeypatch.setattr(sys, "argv", ["parse_private_pdf", str(source), str(destination)])
    monkeypatch.setenv("PAPERTRAIL_MINERU_TIER", "advanced")
    monkeypatch.setattr(parse_private_pdf, "read_pdf_bytes", lambda _path: b"TEST PDF")

    def fake_parse(pdf_bytes: bytes, *, tier: str) -> dict[str, object]:
        called.update(pdf_bytes=pdf_bytes, tier=tier)
        return {"parser_version": "mineru-TEST-papertrail-v11", "elements": []}

    monkeypatch.setattr(parse_private_pdf, "parse_pdf_bytes_mineru", fake_parse)

    parse_private_pdf.main()

    assert called == {"pdf_bytes": b"TEST PDF", "tier": "advanced"}
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "parser_version": "mineru-TEST-papertrail-v11",
        "elements": [],
    }
