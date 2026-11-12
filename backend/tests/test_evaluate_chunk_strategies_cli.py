from __future__ import annotations

import json
from types import SimpleNamespace

from app.cli import evaluate_chunk_strategies


def _dataset():
    return {
        "dataset_id": "TEST-chunk-rerank-cli",
        "sources": {"2401.00001": {}},
        "tasks": [{"task_id": "R1", "question": "TEST query"}],
    }


def _args(output):
    return [
        "--dataset",
        "TEST-dataset.json",
        "--output",
        str(output),
        "--parent-embedding-rerank",
        "--confirm-data-transfer",
        "--max-query-embeddings",
        "1",
        "--max-cost-usd",
        "0.01",
    ]


def test_existing_output_is_rejected_before_provider_or_database_access(tmp_path, monkeypatch):
    output = tmp_path / "existing-report.json"
    output.write_text("TEST-preserve", encoding="utf-8")
    monkeypatch.setattr(
        evaluate_chunk_strategies, "load_dataset", lambda _path: (_dataset(), "a" * 64)
    )
    monkeypatch.setattr(
        evaluate_chunk_strategies,
        "get_settings",
        lambda: SimpleNamespace(resolved_data_storage_path=tmp_path / "missing.sqlite3"),
    )

    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("existing output must be checked before external work")

    monkeypatch.setattr(evaluate_chunk_strategies, "PaperStore", unexpected_call)
    monkeypatch.setattr(evaluate_chunk_strategies, "embed_task_queries", unexpected_call)

    assert evaluate_chunk_strategies.main(_args(output)) == 2
    assert output.read_text(encoding="utf-8") == "TEST-preserve"


def test_incomplete_embedding_index_is_rejected_before_provider_call(tmp_path, monkeypatch):
    output = tmp_path / "report.json"
    dataset = _dataset()
    monkeypatch.setattr(
        evaluate_chunk_strategies, "load_dataset", lambda _path: (dataset, "a" * 64)
    )
    monkeypatch.setattr(
        evaluate_chunk_strategies,
        "get_settings",
        lambda: SimpleNamespace(
            resolved_data_storage_path=tmp_path / "papers.sqlite3",
            embedding_model="TEST-model",
            embedding_dimensions=None,
        ),
    )

    class ReadOnlyStore:
        def __init__(self, *_args, **_kwargs):
            pass

        def list_current_fulltext_chunks(self, **_kwargs):
            return [{"chunk_id": "TEST-chunk", "source_id": "2401.00001", "text": "TEST text"}]

        def list_current_fulltext_embeddings(self, **_kwargs):
            return {"TEST-chunk": None}

    monkeypatch.setattr(evaluate_chunk_strategies, "PaperStore", ReadOnlyStore)
    monkeypatch.setattr(evaluate_chunk_strategies, "run_evaluation", lambda *_args, **_kwargs: {})

    def unexpected_provider(*_args, **_kwargs):
        raise AssertionError("incomplete vectors must be detected before query embedding")

    monkeypatch.setattr(evaluate_chunk_strategies, "embed_task_queries", unexpected_provider)

    assert evaluate_chunk_strategies.main(_args(output)) == 2
    assert not output.exists()


def test_rerank_dry_run_checks_index_and_estimates_without_transfer(tmp_path, monkeypatch, capsys):
    output = tmp_path / "report.json"
    dataset = _dataset()
    monkeypatch.setattr(
        evaluate_chunk_strategies, "load_dataset", lambda _path: (dataset, "a" * 64)
    )
    monkeypatch.setattr(
        evaluate_chunk_strategies,
        "get_settings",
        lambda: SimpleNamespace(
            resolved_data_storage_path=tmp_path / "papers.sqlite3",
            embedding_model="TEST-embedding-model",
            embedding_dimensions=2,
            embedding_provider="disabled",
            embedding_price_per_million_usd=0.02,
        ),
    )

    class ReadOnlyStore:
        readonly = True
        complete = True

        def __init__(self, *_args, **_kwargs):
            pass

        def list_current_fulltext_chunks(self, **_kwargs):
            return [{"chunk_id": "TEST-chunk", "source_id": "2401.00001", "text": "TEST text"}]

        def list_current_fulltext_embeddings(self, **_kwargs):
            return {"TEST-chunk": [1.0, 0.0] if self.complete else None}

    monkeypatch.setattr(evaluate_chunk_strategies, "PaperStore", ReadOnlyStore)
    monkeypatch.setattr(evaluate_chunk_strategies, "run_evaluation", lambda *_args, **_kwargs: {})

    def unexpected_provider(*_args, **_kwargs):
        raise AssertionError("dry-run must never create an embedding provider")

    monkeypatch.setattr(evaluate_chunk_strategies, "embed_task_queries", unexpected_provider)
    args = [
        "--dataset",
        "TEST-dataset.json",
        "--output",
        str(output),
        "--parent-embedding-rerank",
        "--dry-run",
        "--max-query-embeddings",
        "1",
        "--max-cost-usd",
        "0.01",
    ]

    assert evaluate_chunk_strategies.main(args) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["provider_calls"] == 0
    assert preview["query_count"] == 1
    assert preview["query_embedding_model"] == "TEST-embedding-model"
    assert preview["embedding_provider_enabled"] is False
    assert preview["data_transfer_approved"] is False
    assert preview["confirm_data_transfer_required_for_execute"] is True
    assert preview["report_written"] is False
    assert not output.exists()

    monkeypatch.setattr(
        evaluate_chunk_strategies,
        "get_settings",
        lambda: SimpleNamespace(
            resolved_data_storage_path=tmp_path / "papers.sqlite3",
            embedding_model="TEST-embedding-model",
            embedding_dimensions=None,
            embedding_provider="disabled",
            embedding_price_per_million_usd=0.02,
        ),
    )
    assert evaluate_chunk_strategies.main(args) == 0
    unverified_dimension_preview = json.loads(capsys.readouterr().out)
    assert unverified_dimension_preview["embedding_dimensions_configured"] is False
    assert unverified_dimension_preview["embedding_dimensions_match"] is None
    assert unverified_dimension_preview["rerank_index_complete"] is False
    assert not output.exists()

    ReadOnlyStore.complete = False
    monkeypatch.setattr(
        evaluate_chunk_strategies,
        "get_settings",
        lambda: SimpleNamespace(
            resolved_data_storage_path=tmp_path / "papers.sqlite3",
            embedding_model="TEST-embedding-model",
            embedding_dimensions=2,
            embedding_provider="disabled",
            embedding_price_per_million_usd=0.02,
        ),
    )
    assert evaluate_chunk_strategies.main(args) == 0
    incomplete_preview = json.loads(capsys.readouterr().out)
    assert incomplete_preview["provider_calls"] == 0
    assert incomplete_preview["rerank_index_complete"] is False
    assert incomplete_preview["missing_vector_count"] == 1
    assert incomplete_preview["missing_vector_text_bytes_upper_bound"] == len(b"TEST text")
    assert float(incomplete_preview["estimated_missing_fulltext_embedding_cost_usd"]) > 0
    assert incomplete_preview["data_transfer_approved"] is False
    assert not output.exists()
