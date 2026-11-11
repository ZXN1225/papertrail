from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from app.agent.model import ModelTurn, ModelUnavailable
from app.cli.run_llm_judge import main as run_judge_cli
from app.evaluation.ai_labeled_tasks import load_dataset
from app.evaluation.live_budget import BudgetedModelClient
from app.evaluation.llm_judge import JUDGE_OUTPUT_SCHEMA, LLMJudgeError, run_llm_judge

DATASET_SHA = "a" * 64
ANSWER_BUNDLE_SHA = "b" * 64
SOURCE_SHA = "c" * 64
DOCUMENT_SHA = "d" * 64
CHUNK_ID = f"arxiv:TEST-2609.27579:{SOURCE_SHA[:16]}:1"
CHUNK_ID_PREFIX_OVERLAP = CHUNK_ID + "0"


def _dataset() -> dict[str, Any]:
    return {
        "schema": "papertrail.ai-labeled-tasks.v1",
        "dataset_id": "TEST-judge-v1",
        "synthetic": True,
        "gold_standard": False,
        "quality_claim_allowed": False,
        "human_reviewed": False,
        "label_source": "test_fixture",
        "retrieval_method": "bm25",
        "top_k": 8,
        "source_scope": "all_approved_arxiv",
        "sources": {
            "TEST-2609.27579": {
                "parser_version": "pdfplumber-layout-v1",
                "content_sha256": SOURCE_SHA,
                "source_document_sha256": DOCUMENT_SHA,
                "license_id": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
            }
        },
        "tasks": [
            {
                "task_id": "TEST-1",
                "source_id": "TEST-2609.27579",
                "question": "What result does the test paper report?",
                "expected_answerable": True,
                "evidence": {
                    "source_id": "TEST-2609.27579",
                    "chunk_id": CHUNK_ID,
                    "page_number": 1,
                    "element_type": "paragraph",
                    "quote": "TEST evidence for the reported result.",
                },
            }
        ],
    }


def _answer_bundle() -> dict[str, Any]:
    return {
        "schema": "papertrail.llm-judge-input.v1",
        "candidate_model": "TEST-candidate-model",
        "dataset_sha256": DATASET_SHA,
        "synthetic": True,
        "answers": [
            {
                "response_id": "TEST-response-1",
                "task_id": "TEST-1",
                "cohort_id": "TEST-arm-a",
                "answer": f"The result is supported. [{CHUNK_ID}]",
                "abstained": False,
                "cited_chunk_ids": [CHUNK_ID],
            }
        ],
    }


class TESTStore:
    readonly = True
    synthetic = True

    def __init__(self, *, content_sha: str = SOURCE_SHA) -> None:
        self.content_sha = content_sha

    def list_current_fulltext_metadata(self, *, source_type: str | None = None):
        assert source_type == "arxiv"
        return [
            {
                "source_type": "arxiv",
                "source_id": "TEST-2609.27579",
                "license_id": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "content_sha256": self.content_sha,
                "source_document_sha256": DOCUMENT_SHA,
                "parser_version": "pdfplumber-layout-v1",
            }
        ]

    def list_current_fulltext_chunks(self):
        rows = [
            {
                "chunk_id": CHUNK_ID,
                "source_type": "arxiv",
                "source_id": "TEST-2609.27579",
                "content_sha256": self.content_sha,
                "evidence_text": "TEST evidence for the reported result.",
                "text": "TEST fallback body",
            }
        ]
        rows.append({**rows[0], "chunk_id": CHUNK_ID_PREFIX_OVERLAP})
        return rows


class TESTJudgeModel:
    synthetic = True

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {
            "answer_relevance": 4,
            "evidence_support": 5,
            "citation_quality": 4,
            "abstention_appropriate": False,
            "supported_evidence_ids": ["E1"],
            "unsupported_claims": [],
            "rationale": "TEST the cited excerpt directly supports the answer.",
        }
        self.request: dict[str, Any] | None = None

    def complete(self, **request: Any) -> ModelTurn:
        self.request = request
        return ModelTurn(
            [], [], json.dumps(self.payload), False, input_tokens=100, output_tokens=30
        )


def _run(
    model: TESTJudgeModel,
    *,
    store: TESTStore | None = None,
    answer_bundle: dict[str, Any] | None = None,
):
    guarded = BudgetedModelClient(
        model,
        input_price_per_million_usd=Decimal("1"),
        output_price_per_million_usd=Decimal("1"),
        max_cost_usd=Decimal("1"),
        max_provider_calls=2,
        max_output_tokens=600,
    )
    report = run_llm_judge(
        store or TESTStore(),
        _dataset(),
        DATASET_SHA,
        answer_bundle or _answer_bundle(),
        ANSWER_BUNDLE_SHA,
        guarded,
        judge_model="TEST-judge-model",
        seed=23,
    )
    return report, guarded


def test_judge_is_blinded_tool_free_and_uses_frozen_evidence_aliases():
    model = TESTJudgeModel()
    report, guarded = _run(model)

    assert report["status"] == "completed"
    assert report["gold_standard"] is False
    assert report["human_reviewed"] is False
    assert report["quality_claim_allowed"] is False
    assert report["judge_independence"].startswith("declared model names differ")
    assert report["summary"]["cohorts"]["TEST-arm-a"]["mean_scores"]["evidence_support"] == 5
    assert report["results"][0]["evidence_aliases"] == {"E1": CHUNK_ID}
    assert model.request is not None
    assert model.request["tools"] == []
    assert model.request["output_schema"] == JUDGE_OUTPUT_SCHEMA
    prompt_text = model.request["input_items"][0]["content"]
    assert CHUNK_ID not in prompt_text
    assert "candidate_model" not in prompt_text
    assert guarded.calls_attempted == 1


def test_judge_marks_unknown_evidence_alias_unavailable():
    model = TESTJudgeModel(
        {
            "answer_relevance": 4,
            "evidence_support": 5,
            "citation_quality": 4,
            "abstention_appropriate": False,
            "supported_evidence_ids": ["E99"],
            "unsupported_claims": [],
            "rationale": "TEST invalid evidence alias",
        }
    )
    report, _guarded = _run(model)

    assert report["status"] == "partial"
    assert report["results"][0]["status"] == "unavailable"
    assert report["results"][0]["failure_reason"] == "judge_referenced_unknown_evidence"
    assert report["summary"]["cohorts"]["TEST-arm-a"]["judged_count"] == 0


def test_provider_failure_accounts_for_unjudged_answers():
    class FailingModel(TESTJudgeModel):
        def complete(self, **request: Any) -> ModelTurn:
            raise ModelUnavailable("TEST provider unavailable")

    bundle = _answer_bundle()
    bundle["answers"].append(
        {
            **bundle["answers"][0],
            "response_id": "TEST-response-2",
            "cohort_id": "TEST-arm-b",
        }
    )
    report, _guarded = _run(FailingModel(), answer_bundle=bundle)

    assert report["status"] == "partial"
    assert [row["status"] for row in report["results"]] == ["unavailable", "not_judged"]
    assert report["summary"]["unavailable_count"] == 1
    assert report["summary"]["not_judged_count"] == 1
    assert report["summary"]["cohorts"]["TEST-arm-b"]["not_judged_count"] == 1
    assert report["budget"]["provider_calls"] == 1
    assert report["budget"]["successful_provider_calls"] == 0


def test_overlapping_chunk_ids_are_replaced_longest_first():
    model = TESTJudgeModel()
    bundle = _answer_bundle()
    bundle["answers"][0]["answer"] = f"Supported by [{CHUNK_ID}][{CHUNK_ID_PREFIX_OVERLAP}]"
    bundle["answers"][0]["cited_chunk_ids"].append(CHUNK_ID_PREFIX_OVERLAP)

    report, _guarded = _run(model, answer_bundle=bundle)

    assert model.request is not None
    payload = json.loads(model.request["input_items"][0]["content"])
    assert CHUNK_ID not in payload["answer"]
    assert CHUNK_ID_PREFIX_OVERLAP not in payload["answer"]
    aliases = {
        chunk_id: alias for alias, chunk_id in report["results"][0]["evidence_aliases"].items()
    }
    expected = f"Supported by [{aliases[CHUNK_ID]}][{aliases[CHUNK_ID_PREFIX_OVERLAP]}]"
    assert payload["answer"] == expected


def test_judge_cli_defaults_to_zero_call_dry_run(tmp_path, capsys):
    dataset_path = tmp_path / "tasks.json"
    answers_path = tmp_path / "answers.json"
    dataset_path.write_text(json.dumps(_dataset()), encoding="utf-8")
    _loaded_dataset, dataset_sha = load_dataset(dataset_path)
    answer_bundle = _answer_bundle()
    answer_bundle["dataset_sha256"] = dataset_sha
    answers_path.write_text(json.dumps(answer_bundle), encoding="utf-8")

    exit_code = run_judge_cli(
        [
            "--dataset",
            str(dataset_path),
            "--answers",
            str(answers_path),
            "--output",
            str(tmp_path / "report.json"),
            "--judge-model",
            "TEST-judge-model",
            "--max-cost-usd",
            "0.10",
            "--input-price-per-million-usd",
            "1",
            "--output-price-per-million-usd",
            "1",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["provider_calls"] == 0
    assert not (tmp_path / "report.json").exists()


def test_judge_fails_closed_on_stale_corpus_and_same_model():
    model = TESTJudgeModel()
    guarded = BudgetedModelClient(
        model,
        input_price_per_million_usd=Decimal("1"),
        output_price_per_million_usd=Decimal("1"),
        max_cost_usd=Decimal("1"),
        max_provider_calls=2,
        max_output_tokens=600,
    )
    with pytest.raises(LLMJudgeError, match="lineage differs"):
        run_llm_judge(
            TESTStore(content_sha="e" * 64),
            _dataset(),
            DATASET_SHA,
            _answer_bundle(),
            ANSWER_BUNDLE_SHA,
            guarded,
            judge_model="TEST-judge-model",
        )
    assert model.request is None

    with pytest.raises(LLMJudgeError, match="different"):
        run_llm_judge(
            TESTStore(),
            _dataset(),
            DATASET_SHA,
            _answer_bundle(),
            ANSWER_BUNDLE_SHA,
            guarded,
            judge_model="TEST-candidate-model",
        )
