from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.embeddings.client import EmbeddingBatch, EmbeddingError
from tools.evaluate_true_candidate_rerank import BatchCache, _select_shortlists


def test_shortlist_respects_each_task_source_scope():
    candidates = [
        {
            "chunk_id": "TEST-A",
            "source_id": "2401.00001",
            "title": "TEST first paper",
            "section_path": "[]",
            "text": "TEST target evidence",
        },
        {
            "chunk_id": "TEST-B",
            "source_id": "2401.00002",
            "title": "TEST second paper",
            "section_path": "[]",
            "text": "TEST target evidence",
        },
    ]
    dataset = {
        "sources": {"2401.00001": {}, "2401.00002": {}},
        "tasks": [{"task_id": "R1", "source_id": "2401.00001", "question": "TEST target evidence"}],
    }

    scoped_hits, scoped_candidates = _select_shortlists(candidates, dataset)
    global_hits, global_candidates = _select_shortlists(
        candidates, {**dataset, "source_scope": "all_approved_arxiv"}
    )

    assert scoped_hits["R1"] == ["TEST-A"]
    assert set(scoped_candidates) == {"TEST-A"}
    assert set(global_hits["R1"]) == {"TEST-A", "TEST-B"}
    assert set(global_candidates) == {"TEST-A", "TEST-B"}


def test_batch_cache_dry_run_and_successful_resume_without_raw_text(tmp_path):
    cache = BatchCache(tmp_path / "cache", "a" * 64, "TEST-model", 2)
    texts = ["TEST private candidate"]
    price = Decimal("0.02")
    preview = cache.inspect([texts], price)
    assert preview["cached_batch_count"] == 0
    assert preview["remaining_batch_count"] == 1
    assert not cache.path.exists()

    class Client:
        calls = 0

        def embed(self, inputs):
            self.calls += 1
            assert inputs == texts
            return EmbeddingBatch(model="TEST-model", vectors=[[1.0, 0.0]], input_tokens=3)

    client = Client()
    vectors, tokens, called = cache.get_or_embed(texts, client, price, Decimal("0.01"))
    assert (vectors, tokens, called) == ([[1.0, 0.0]], 3, True)
    assert client.calls == 1
    vectors, tokens, called = cache.get_or_embed(texts, client, price, Decimal("0.01"))
    assert (vectors, tokens, called) == ([[1.0, 0.0]], 3, False)
    assert client.calls == 1
    assert cache.inspect([texts], price)["remaining_batch_count"] == 0
    assert all(
        "TEST private candidate" not in path.read_text(encoding="utf-8")
        for path in cache.path.iterdir()
    )


def test_timeout_reserves_attempt_before_retry(tmp_path):
    cache = BatchCache(tmp_path / "cache", "b" * 64, "TEST-model", 2)
    texts = ["TEST one"]
    price = Decimal("0.02")
    cap = Decimal("0.0000002")

    class TimeoutClient:
        calls = 0

        def embed(self, _inputs):
            self.calls += 1
            raise EmbeddingError("timeout")

    client = TimeoutClient()
    with pytest.raises(EmbeddingError, match="timeout"):
        cache.get_or_embed(texts, client, price, cap)
    assert client.calls == 1
    preview = cache.inspect([texts], price)
    assert preview["attempted_utf8_bytes_reserved"] == len(texts[0].encode("utf-8"))
    assert Decimal(preview["estimated_cumulative_upper_bound_cost_usd"]) > cap
    with pytest.raises(ValueError, match="cumulative embedding attempt"):
        cache.get_or_embed(texts, client, price, cap)
    assert client.calls == 1


def test_cli_dry_run_then_live_report_resumes_without_new_provider_call(
    tmp_path, monkeypatch, capsys
):
    from tools import evaluate_true_candidate_rerank as cli

    text = "TEST evidence"
    dataset = {
        "dataset_id": "TEST-true-rerank",
        "sources": {"2401.00001": {}},
        "tasks": [{"task_id": "R1", "source_id": "2401.00001", "question": "TEST evidence"}],
        "top_k": 1,
    }
    baseline = {
        "dataset": {"quality_claim_allowed": False},
        "strategies": {
            "TEST-arm": {
                "tasks": [
                    {
                        "reference_span": [0, len(text)],
                        "reference_element_id": "TEST-element",
                        "evidence_span_covered": True,
                    }
                ],
                "metrics_macro_average": {"hit@1": 1.0},
            }
        },
    }

    class Store:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_current_fulltext_metadata(self, **_kwargs):
            return {"title": "TEST paper"}

        def list_current_fulltext_elements(self, **_kwargs):
            return [{"element_id": "TEST-element", "text": text}]

        def list_current_fulltext_chunks(self, **_kwargs):
            return [{"chunk_id": "TEST-parent", "text": text}]

        def list_current_fulltext_embeddings(self, **_kwargs):
            return {"TEST-parent": [1.0, 0.0]}

    client_calls = []

    class Client:
        def __init__(self, _settings):
            pass

        def embed(self, inputs):
            client_calls.append(inputs)
            return EmbeddingBatch(
                model="TEST-model", vectors=[[1.0, 0.0] for _ in inputs], input_tokens=2
            )

        def close(self):
            pass

    monkeypatch.setattr(cli, "load_dataset", lambda _path: (dataset, "a" * 64))
    monkeypatch.setattr(cli, "run_evaluation", lambda *_args: baseline)
    monkeypatch.setattr(cli, "PaperStore", Store)
    monkeypatch.setattr(cli, "STRATEGIES", {"TEST-arm": (1800, 0)})
    monkeypatch.setattr(
        cli,
        "chunk_pdf_elements",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                element_id="TEST-element",
                ordinal=0,
                text=text,
                section_path="[]",
                char_start=0,
                char_end=len(text),
            )
        ],
    )
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(
            embedding_model="TEST-model",
            embedding_dimensions=2,
            embedding_price_per_million_usd=0.02,
            embedding_provider="openai",
            resolved_data_storage_path=tmp_path / "TEST.sqlite3",
        ),
    )
    monkeypatch.setattr(cli, "OpenAIEmbeddingClient", Client)
    monkeypatch.setattr(cli, "LOCAL_CACHE_ROOT", tmp_path / "cache")

    def args(output):
        return [
            "--dataset",
            "TEST-dataset.json",
            "--output",
            str(output),
            "--max-query-embeddings",
            "1",
            "--max-new-texts",
            "1",
            "--max-new-utf8-bytes",
            "100",
            "--max-cost-usd",
            "0.01",
        ]

    first = tmp_path / "TEST-report-1.json"
    assert cli.main(args(first)) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["source_scope"] == "exact_arxiv_id_per_task"
    assert preview["provider_calls"] == 0
    assert not client_calls
    assert not first.exists()

    assert cli.main([*args(first), "--execute", "--confirm-data-transfer"]) == 0
    capsys.readouterr()
    report = json.loads(first.read_text(encoding="utf-8"))
    assert report["provider_calls_this_run"] == 1
    assert report["arms"]["TEST-arm"]["candidate_vector_rerank"]["hit@1"] == 1.0
    assert report["arms"]["TEST-arm"]["candidate_vector_span_coverage"] == 1.0
    assert len(client_calls) == 1

    second = tmp_path / "TEST-report-2.json"
    assert cli.main([*args(second), "--execute", "--confirm-data-transfer"]) == 0
    capsys.readouterr()
    second_report = json.loads(second.read_text(encoding="utf-8"))
    assert second_report["provider_calls_this_run"] == 0
    assert len(client_calls) == 1
