from app.evaluation.weak_supervision import (
    build_dataset_from_store,
    generate_candidates,
    partition_candidates,
    run_evaluation,
    score_weak_retrieval,
)


def test_candidate_generation_is_deterministic_and_never_gold():
    chunks = [
        {
            "chunk_id": "TEST-1",
            "source_id": "2401.00001",
            "source_type": "arxiv",
            "source_status": "approved",
            "license_id": "CC-BY-4.0",
            "content_sha256": "a" * 64,
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
    assert first["candidates"][0]["source_content_sha256"] == "a" * 64
    assert first["candidates"][0]["answer_term"] not in first["candidates"][0]["query"].split()
    assert first["candidates"][0]["bucket"] == "masked_source_chunk_lookup"


def test_candidate_generation_rejects_private_or_unapproved_sources():
    chunk = {
        "chunk_id": "TEST-1",
        "source_id": "private-user-paper",
        "source_type": "personal",
        "source_status": "approved",
        "license_id": "CC-BY-4.0",
        "content_sha256": "a" * 64,
        "text": "Private manuscript contains enough words for a masked retrieval query.",
    }
    try:
        generate_candidates([chunk])
    except ValueError as error:
        assert "approved licensed public full text" in str(error)
    else:
        raise AssertionError("private text must not enter candidate exports")


def test_weak_metrics_report_multiple_retrieval_views():
    scored = score_weak_retrieval(["c1", "c2", "c3"], ["c2", "c3"], k=2)
    assert scored["precision@2"] == 0.5
    assert scored["recall@2"] == 0.5
    assert scored["mrr@2"] == 0.5
    assert score_weak_retrieval(["c1", "c2", "c3"], ["c3"], k=2)["mrr@2"] == 0.0
    short = score_weak_retrieval(["c2"], ["c2"], k=5)
    assert short["precision@5"] == 0.2
    assert short["returned_precision@5"] == 1.0


def test_weak_metrics_reject_invalid_cutoffs_and_duplicate_rankings():
    for ranking, k in [(["c1"], 0), (["c1", "c1"], 2)]:
        try:
            score_weak_retrieval(ranking, ["c1"], k=k)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid metric input should be rejected")


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
    assert report["split_counts"]["source_count"] == {"train": 13, "dev": 3, "test": 4}
    assert report["split_counts"]["complete"] is True


def test_candidate_split_reports_missing_groups_for_small_corpora():
    report = partition_candidates([{"query_id": "q1", "source_id": "paper-1"}])
    assert report["split_counts"]["complete"] is False
    assert report["split_counts"]["missing"]


def test_store_dataset_builder_is_read_only_pinned_and_license_filtered():
    source = {
        "source_type": "arxiv",
        "source_id": "2401.00001",
        "title": "A licensed paper",
        "source_url": "https://arxiv.org/abs/2401.00001",
        "status": "approved",
        "content_sha256": "a" * 64,
        "source_document_sha256": "b" * 64,
        "license_id": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "license_evidence_url": "https://example.org/license-evidence",
        "text_source_url": "https://example.org/paper.pdf",
        "attribution": "Author, A licensed paper",
        "parser_version": "pdfplumber-layout-v1",
        "chunker_version": "chunker-v1",
    }

    unused_source = {
        **source,
        "source_id": "2401.00002",
        "content_sha256": "c" * 64,
        "source_document_sha256": "d" * 64,
    }

    class Store:
        readonly = True

        def __init__(self):
            self.sources = [source, unused_source]

        def list_current_fulltext_metadata(self, *, source_type=None):
            return self.sources

        def list_current_fulltext_chunks(self, *, source_type=None):
            return [
                {
                    "chunk_id": "chunk-1",
                    "source_type": "arxiv",
                    "source_id": "2401.00001",
                    "content_sha256": "a" * 64,
                    "text": "Retrieval augmented generation supports grounded answers.",
                }
            ]

    dataset = build_dataset_from_store(Store())
    assert dataset == build_dataset_from_store(Store())
    assert dataset["sources"]["2401.00001"]["attribution"] == "Author, A licensed paper"
    assert dataset["sources"]["2401.00001"]["parser_version"] == "pdfplumber-layout-v1"
    assert dataset["gold_standard"] is False
    assert dataset["split_counts"]["complete"] is False
    assert "2401.00002" in dataset["sources"]

    store = Store()

    def search(query, *, limit, source_type, retrieval_method):
        assert query
        assert limit == 5
        assert source_type is None
        assert retrieval_method == "bm25"
        return {
            "status": "ok",
            "truncated": False,
            "items": [
                {
                    "chunk_id": "chunk-1",
                    "source_id": "2401.00001",
                    "content_sha256": "a" * 64,
                }
            ],
        }

    store.search_fulltext_evidence = search
    report = run_evaluation(store, dataset, split="all")
    assert report["summary"]["query_count"] == 1
    assert report["summary"]["metrics"]["recall@5"] == 1.0
    assert report["gold_standard"] is False

    store.sources = [{**source, "content_sha256": "e" * 64}, unused_source]
    try:
        run_evaluation(store, dataset, split="all")
    except ValueError as error:
        assert "active source lineage differs" in str(error)
    else:
        raise AssertionError("stale corpus snapshots must be rejected")


def test_store_dataset_builder_rejects_writable_store():
    class Store:
        readonly = False

    try:
        build_dataset_from_store(Store())
    except ValueError as error:
        assert "read-only PaperStore" in str(error)
    else:
        raise AssertionError("writable stores must not be accepted")
