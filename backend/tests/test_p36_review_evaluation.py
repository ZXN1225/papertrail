from __future__ import annotations

import csv
import io

import pytest

from app.evaluation.p36_evaluation import (
    CSV_COLUMNS,
    evaluate_reviewed_pool,
    parse_completed_review_csv,
)
from app.evaluation.p36_pool import build_blind_review_pool


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
        "corpus": {"snapshot_id": "snapshot-1", "work_ids": work_ids, "content_sha256": hashes},
        "queries": queries,
    }
    docs = [
        {
            "openalex_id": work_id,
            "content_sha256": hashes[work_id],
            "title": f"Paper {work_id}",
            "publication_year": 2024,
            "abstract": (f"Abstract {work_id} 😀²" if work_id == "W0" else f"Abstract {work_id}"),
            "source_url": f"https://openalex.org/{work_id}",
        }
        for work_id in work_ids
    ]
    metadata = {
        "review_status": "awaiting_human_review",
        "corpus_snapshot_id": "snapshot-1",
        "corpus_work_ids": work_ids,
        "corpus_content_sha256": hashes,
        "documents": docs,
    }

    def report(offset):
        rows = []
        for index, query in enumerate(queries):
            rows.append(
                {
                    "query_id": query["query_id"],
                    "text": query["text"],
                    "bucket": query["bucket"],
                    "ndcg@10_spread": 1 - index / 100,
                    "methods": {
                        method: {
                            "top_10": [f"W{(offset + index + n + shift) % 100}" for n in range(10)]
                        }
                        for method, shift in (("bm25", 0), ("dense", 20), ("hybrid_rrf_k60", 40))
                    },
                }
            )
        return {
            "report_schema": "papertrail-p14-retrieval-comparison-v1",
            "dataset": {"judgment_status": "assistant_labeled", "sha256": "dataset-sha"},
            "corpus": {"snapshot_id": "snapshot-1", "document_count": 100, "query_count": 30},
            "queries_ranked_by_method_disagreement": rows,
        }

    return (
        dataset,
        "dataset-sha",
        metadata,
        report(0),
        report(10),
    )


def _built_pool():
    dataset, dataset_sha, metadata, small, large = _inputs()
    return build_blind_review_pool(
        dataset, dataset_sha, metadata, small, "small-sha", large, "large-sha"
    )


def _csv_bytes(pack, *, encoding: str = "utf-8-sig", omit_last: bool = False) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    rows = pack["rows"][:-1] if omit_last else pack["rows"]
    for index, original in enumerate(rows):
        row = {
            column: "" if original.get(column) is None else str(original[column])
            for column in CSV_COLUMNS
        }
        if encoding == "cp936":
            row = {
                key: value.translate(str.maketrans({"¹": "1", "²": "2", "³": "3"}))
                for key, value in row.items()
            }
        row["reviewed_grade"] = str(index % 4)
        row["reviewed"] = "TRUE"
        row["review_note"] = "人工复核" if index == 0 else ""
        writer.writerow(row)
    return stream.getvalue().encode(encoding, errors="replace")


def test_completed_csv_is_imported_and_rankers_are_scored_only_on_the_pool():
    pack, audit = _built_pool()
    judgments, csv_hash, csv_encoding = parse_completed_review_csv(_csv_bytes(pack), pack)
    report = evaluate_reviewed_pool(
        pack,
        audit,
        judgments,
        reviewer="reviewer",
        csv_sha256=csv_hash,
        csv_encoding=csv_encoding,
    )

    assert report["dataset"]["judgment_status"] == "human_reviewed_candidate_pool"
    assert report["dataset"]["reviewed_pair_count"] == len(pack["rows"])
    assert report["dataset"]["quality_claim_allowed"] is False
    assert report["pool"]["unjudged_handling"].startswith("exclude all papers")
    assert report["methods"]["bm25"]["delta_vs_bm25"] is None
    assert set(report["methods"]) == {
        "bm25",
        "small_dense",
        "small_hybrid_rrf_k60",
        "large_dense",
        "large_hybrid_rrf_k60",
    }


def test_completed_csv_accepts_excel_windows_936_encoding():
    pack, _ = _built_pool()
    judgments, _, csv_encoding = parse_completed_review_csv(
        _csv_bytes(pack, encoding="cp936"), pack
    )
    assert len(judgments) == len(pack["rows"])
    assert csv_encoding["encoding"] == "cp936"
    assert csv_encoding["replacement_characters"] > 0
    assert csv_encoding["superscript_digit_normalizations"] == 1
    assert judgments[pack["rows"][0]["row_id"]]["review_note"] == "人工复核"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("omit", "incomplete"),
        ("grade", "integer from 0 through 3"),
        ("reviewed", "reviewed=true"),
        ("tamper", "protected field title"),
    ],
)
def test_completed_csv_rejects_incomplete_or_changed_review(mutation: str, message: str):
    pack, _ = _built_pool()
    raw = _csv_bytes(pack)
    if mutation == "omit":
        raw = _csv_bytes(pack, omit_last=True)
    else:
        text = raw.decode("utf-8-sig")
        lines = text.splitlines()
        cells = next(csv.reader([lines[1]]))
        if mutation == "grade":
            cells[CSV_COLUMNS.index("reviewed_grade")] = "4"
        elif mutation == "reviewed":
            cells[CSV_COLUMNS.index("reviewed")] = "false"
        else:
            cells[CSV_COLUMNS.index("title")] = "Changed title"
        changed = io.StringIO(newline="")
        csv.writer(changed, lineterminator="\n").writerow(cells)
        lines[1] = changed.getvalue().rstrip("\n")
        raw = ("\n".join(lines) + "\n").encode("utf-8-sig")

    from app.evaluation.p36_pool import PoolReviewError

    with pytest.raises(PoolReviewError, match=message):
        parse_completed_review_csv(raw, pack)
