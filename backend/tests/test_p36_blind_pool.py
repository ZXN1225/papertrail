from __future__ import annotations

import pytest

from app.evaluation.p36_pool import PoolReviewError, build_blind_review_pool


def _inputs():
    work_ids = [f"W{index}" for index in range(100)]
    hashes = {work_id: f"hash-{work_id}" for work_id in work_ids}
    queries = [
        {
            "query_id": f"Q{index:02}",
            "text": f"research question {index}",
            "bucket": f"bucket-{index:02}",
            "relevance": [0] * 100,
        }
        for index in range(30)
    ]
    dataset = {
        "dataset_id": "papertrail-p13-rag-retrieval-ai-labeled-v1",
        "dataset_version": 1,
        "judgment_status": "assistant_labeled",
        "corpus": {
            "snapshot_id": "snapshot-1",
            "work_ids": work_ids,
            "content_sha256": hashes,
        },
        "queries": queries,
    }
    dataset_sha = "dataset-sha"
    documents = [
        {
            "openalex_id": work_id,
            "content_sha256": hashes[work_id],
            "title": f"Paper {work_id}",
            "publication_year": 2024,
            "abstract": f"Abstract {work_id}",
            "source_url": f"https://openalex.org/{work_id}",
        }
        for work_id in work_ids
    ]
    metadata_pack = {
        "review_status": "awaiting_human_review",
        "corpus_snapshot_id": "snapshot-1",
        "corpus_work_ids": work_ids,
        "corpus_content_sha256": hashes,
        "documents": documents,
    }

    def report(offset: int):
        rows = []
        for index, query in enumerate(queries):
            rows.append(
                {
                    "query_id": query["query_id"],
                    "text": query["text"],
                    "bucket": query["bucket"],
                    "ndcg@10_spread": 1 - index / 100,
                    "methods": {
                        "bm25": {"top_10": [f"W{(offset + index + n) % 100}" for n in range(10)]},
                        "dense": {
                            "top_10": [f"W{(offset + index + n + 20) % 100}" for n in range(10)]
                        },
                        "hybrid_rrf_k60": {
                            "top_10": [f"W{(offset + index + n + 40) % 100}" for n in range(10)]
                        },
                    },
                }
            )
        return {
            "report_schema": "papertrail-p14-retrieval-comparison-v1",
            "dataset": {
                "judgment_status": "assistant_labeled",
                "sha256": dataset_sha,
            },
            "corpus": {
                "snapshot_id": "snapshot-1",
                "document_count": 100,
                "query_count": 30,
            },
            "queries_ranked_by_method_disagreement": rows,
        }

    return dataset, dataset_sha, metadata_pack, report(0), report(10)


def test_blind_pool_is_deterministic_bounded_and_hides_method_judgments():
    inputs = _inputs()
    pack, audit = build_blind_review_pool(
        *inputs[:3], inputs[3], "small-sha", inputs[4], "large-sha"
    )

    assert pack["sampling"]["query_count"] == 8
    assert pack["sampling"]["candidate_pair_count"] <= 200
    assert len(pack["rows"]) == len({row["row_id"] for row in pack["rows"]})
    assert all(row["reviewed_grade"] is None and row["reviewed"] is False for row in pack["rows"])
    assert all("origins" not in row and "suggested_grade" not in row for row in pack["rows"])
    assert all("origins" in row for row in audit["origins"])
    assert "challenge sample" in audit["selection_rule"]

    repeated, repeated_audit = build_blind_review_pool(
        *inputs[:3], inputs[3], "small-sha", inputs[4], "large-sha"
    )
    assert pack == repeated
    assert audit == repeated_audit


@pytest.mark.parametrize("mutation", ["status", "hash", "corpus", "query_count"])
def test_blind_pool_rejects_mismatched_source_evidence(mutation: str):
    dataset, dataset_sha, pack, small, large = _inputs()
    if mutation == "status":
        dataset["judgment_status"] = "human_reviewed"
    elif mutation == "hash":
        small["dataset"]["sha256"] = "stale"
    elif mutation == "corpus":
        large["corpus"]["snapshot_id"] = "other"
    else:
        small["queries_ranked_by_method_disagreement"].pop()

    with pytest.raises(PoolReviewError):
        build_blind_review_pool(dataset, dataset_sha, pack, small, "s", large, "l")


def test_blind_pool_rejects_depth_that_could_exceed_pair_budget():
    with pytest.raises(PoolReviewError, match="depth"):
        build_blind_review_pool(*_inputs()[:3], _inputs()[3], "s", _inputs()[4], "l", depth=6)
