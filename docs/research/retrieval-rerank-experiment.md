# Retrieval rerank experiment

## Current implementation

The read-only licensed-corpus evaluator now supports four arms: BM25, dense cosine, Hybrid RRF, and `bm25_dense_rerank`. The rerank arm first selects up to 128 BM25 candidates, then orders only those candidates by cosine similarity between the query embedding and already-indexed chunk embeddings. It adds no model dependency or second provider request.

This is a dense-vector reranker, not a cross-encoder. It cannot recover relevant evidence that BM25 omitted from its candidate pool. Evaluation reports identify the method, candidate limit, embedding model, retrieval latency, and make clear that retrieval latency excludes the query-embedding provider call. The evaluator remains read-only and reports `quality_claim_allowed=false` for AI-labeled and synthetic datasets.

## Running a paired comparison

The command below sends the full query set to the configured embedding provider. It requires an explicitly approved transfer and a positive cost ceiling that covers the full task set. Reports contain AI-generated answers/questions where present; keep outputs in the ignored local reports directory.

```powershell
uv run --locked python -m app.cli.evaluate_ai_labeled_tasks `
  --dataset data/evaluation/ai-labeled-licensed-v1.json `
  --output reports/rerank-comparison.json `
  --retrieval-method bm25 `
  --retrieval-method dense `
  --retrieval-method hybrid `
  --retrieval-method bm25_dense_rerank `
  --max-query-embeddings <task-count> `
  --max-cost-usd <approved-positive-limit> `
  --confirm-data-transfer
```

BM25 alone can be run without provider settings or data-transfer confirmation. Do not compare report numbers from different corpus/parser/chunker hashes as if they were a paired experiment. The licensed manifest is AI-labeled and not an independently adjudicated gold set; it supports diagnostics only.

## Limits and next step

This checkout has no local approved full-text database, so the four arms have not been run on the licensed taskset here and there is no strategy winner. The synthetic regression validates ranking mechanics only. Chunking is still fixed at the indexed version; alternate chunk strategies and anchor remapping have not been implemented. Do not change production defaults until chunk arms are available and a held-out human-reviewed evaluation favors a method. MinerU chart interpretation accuracy also requires licensed, manually checked chart examples; generated chart descriptions remain unverified evidence.
