from app.evaluation.weak_supervision import generate_candidates, score_weak_retrieval


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
