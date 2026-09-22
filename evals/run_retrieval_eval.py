"""Run deterministic retrieval comparisons on TEST-only relevance judgments."""

import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import time
from pathlib import Path

from retrieval_metrics import bm25, metrics, overlap, reciprocal_rank_fusion

ROOT = Path(__file__).resolve().parents[1]


def rank_query(method, query, documents):
    if method == "overlap":
        return [identifier for _, identifier in overlap(query, documents)]
    lexical = [identifier for _, identifier in bm25(query, documents)]
    if method == "bm25":
        return lexical
    overlap_rank = [identifier for _, identifier in overlap(query, documents)]
    return [identifier for identifier, _ in reciprocal_rank_fusion([lexical, overlap_rank])]


def evaluate_method(data, method, k):
    by_bucket = {}
    all_scores, elapsed = [], []
    for case in data["queries"]:
        started = time.perf_counter()
        ranked = rank_query(method, case["query"], data["documents"])
        elapsed.append((time.perf_counter() - started) * 1000)
        score = metrics(ranked, case["relevance"], k)
        all_scores.append(score)
        by_bucket.setdefault(case["bucket"], []).append(score)
    p95 = sorted(elapsed)[max(0, math.ceil(len(elapsed) * 0.95) - 1)]

    def average(scores):
        return {
            "hit_at_k": round(statistics.mean(row["hit"] for row in scores), 6),
            "mrr_at_k": round(statistics.mean(row["mrr"] for row in scores), 6),
            "ndcg_at_k": round(statistics.mean(row["ndcg"] for row in scores), 6),
        }

    return {
        **average(all_scores),
        "by_bucket": {bucket: average(scores) for bucket, scores in sorted(by_bucket.items())},
        "latency_ms": {
            "mean": round(statistics.mean(elapsed), 4),
            "p95": round(p95, 4),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k must be >= 1")
    raw = args.dataset.read_bytes()
    data = json.loads(raw)
    documents, queries = data.get("documents", []), data.get("queries", [])
    if (
        data.get("synthetic") is not True
        or not documents
        or not queries
        or not all(item.get("doc_id", "").startswith("TEST-") for item in documents)
        or not all(item.get("case_id", "").startswith("TEST-") for item in queries)
    ):
        raise SystemExit("Only non-empty TEST-only synthetic evaluation data is accepted")
    document_ids = [item.get("doc_id") for item in documents]
    case_ids = [item.get("case_id") for item in queries]
    if len(document_ids) != len(set(document_ids)) or len(case_ids) != len(set(case_ids)):
        raise SystemExit("Document and query IDs must be unique")
    known_documents = set(document_ids)
    for case in queries:
        if not case.get("bucket") or not case.get("relevance"):
            raise SystemExit(f"{case.get('case_id')}: bucket and relevance are required")
        if not set(case["relevance"]).issubset(known_documents):
            raise SystemExit(f"{case['case_id']}: relevance references unknown documents")
        if not all(isinstance(value, int) and value > 0 for value in case["relevance"].values()):
            raise SystemExit(f"{case['case_id']}: relevance grades must be positive integers")
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    report = {
        "dataset_id": data["dataset_id"],
        "synthetic": True,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "commit": commit,
        "python": platform.python_version(),
        "k": args.k,
        "documents": len(documents),
        "queries": len(queries),
        "methods": {
            method: evaluate_method(data, method, args.k)
            for method in ("overlap", "bm25", "rrf_overlap_bm25")
        },
        "limitations": [
            "synthetic dataset with synthetic gold relevance labels",
            "retrieval only; no live catalog, price, or model interaction",
            "latency is a local microbenchmark and is not an API or production SLO",
        ],
    }
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        target = args.output if args.output.is_absolute() else ROOT / args.output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
