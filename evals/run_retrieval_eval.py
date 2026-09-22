import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

from retrieval_metrics import bm25, metrics, overlap


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--method", choices=("overlap", "bm25"), default="bm25")
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    data = json.loads(raw)
    if data.get("synthetic") is not True or not all(item["doc_id"].startswith("TEST-") for item in data["documents"]):
        raise SystemExit("Only TEST-only synthetic evaluation data is accepted")
    rank = bm25 if args.method == "bm25" else overlap
    values, elapsed = [], []
    for case in data["queries"]:
        start = time.perf_counter()
        ranked = [identifier for _, identifier in rank(case["query"], data["documents"])]
        elapsed.append((time.perf_counter() - start) * 1000)
        values.append(metrics(ranked, case["relevance"], args.k))
    percentile = sorted(elapsed)[max(0, math.ceil(len(elapsed) * 0.95) - 1)]
    print(json.dumps({"dataset_id": data["dataset_id"], "synthetic": True, "dataset_sha256": hashlib.sha256(raw).hexdigest(), "method": args.method, "k": args.k, "queries": len(values), "hit_at_k": round(statistics.mean(item["hit"] for item in values), 6), "mrr_at_k": round(statistics.mean(item["mrr"] for item in values), 6), "ndcg_at_k": round(statistics.mean(item["ndcg"] for item in values), 6), "latency_ms": {"mean": round(statistics.mean(elapsed), 4), "p95": round(percentile, 4)}, "limitations": ["small synthetic corpus", "retrieval-only evaluation", "not a production or market-quality claim"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import math
    main()
