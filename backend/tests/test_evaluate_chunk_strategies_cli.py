from __future__ import annotations

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
            return [{"chunk_id": "TEST-chunk", "source_id": "2401.00001"}]

        def list_current_fulltext_embeddings(self, **_kwargs):
            return {"TEST-chunk": None}

    monkeypatch.setattr(evaluate_chunk_strategies, "PaperStore", ReadOnlyStore)
    monkeypatch.setattr(evaluate_chunk_strategies, "run_evaluation", lambda *_args, **_kwargs: {})

    def unexpected_provider(*_args, **_kwargs):
        raise AssertionError("incomplete vectors must be detected before query embedding")

    monkeypatch.setattr(evaluate_chunk_strategies, "embed_task_queries", unexpected_provider)

    assert evaluate_chunk_strategies.main(_args(output)) == 2
    assert not output.exists()
