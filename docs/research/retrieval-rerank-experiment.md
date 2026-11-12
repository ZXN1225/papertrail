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

The four arms above compare retrievers only on the currently indexed chunks. A separate paired chunk evaluator now compares 900/1,800-byte candidates under BM25 and an explicitly named parent-embedding proxy rerank. That proxy inherits vectors from the current 1,800-byte indexed chunks; it is not a true child-chunk embedding or cross-encoder. It requires explicit permission to send task questions for query embeddings, and paper text remains local. The strategy has not been run on query embeddings in this task because no data-transfer confirmation was supplied. Do not change production defaults until a held-out human-reviewed evaluation favors a method. MinerU chart interpretation accuracy also requires licensed, manually checked chart examples; generated chart descriptions remain unverified evidence.
