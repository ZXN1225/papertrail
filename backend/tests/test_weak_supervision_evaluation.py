from app.evaluation.weak_supervision import (
    generate_candidates,
    partition_candidates,
    score_weak_retrieval,
)


def test_candidate_generation_is_deterministic_and_never_gold():
    chunks = [
        {
            "chunk_id": "TEST-1",
            "source_id": "2401.00001",
            "evidence_text": "Retrieval augmented generation supports grounded answers. "
            "Different retrievers have different recall.",
        }
    ]
    first = generate_candidates(chunks)
    assert first == generate_candidates(chunks)
    assert first["weak_supervision"] is True
    assert first["gold_standard"] is False
    assert first["quality_claim_allowed"] is False
    assert first["candidates"][0]["weak_relevant_chunk_ids"] == ["TEST-1"]


def test_weak_metrics_report_multiple_retrieval_views():
    scored = score_weak_retrieval(["c1", "c2", "c3"], ["c2", "c3"], k=2)
    assert scored["precision@2"] == 0.5
    assert scored["recall@2"] == 0.5
    assert scored["mrr@2"] == 0.5


def test_candidate_splits_are_stable_and_keep_each_paper_in_one_split():
    candidates = [
        {"query_id": str(index), "source_id": f"paper-{index // 2}"} for index in range(40)
    ]
    report = partition_candidates(candidates)
    assert report == partition_candidates(candidates)
    owners = {
        source_id: split
        for split, source_ids in report["source_ids"].items()
        for source_id in source_ids
    }
    assert len(owners) == 20
    for split, rows in report["splits"].items():
        assert all(owners[row["source_id"]] == split for row in rows)
    assert report["gold_standard"] is False
