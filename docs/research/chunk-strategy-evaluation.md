# Read-only chunk strategy comparison

## Arms and runtime

`python -m app.cli.evaluate_chunk_strategies` compares the current structure-preserving PDF chunker at 1,800 UTF-8 bytes with the same algorithm capped at 900 bytes. Table row/header structure, source element IDs, page numbers, bounding boxes, and half-open element-local offsets are retained. The production ingestion version remains unchanged; alternative chunks exist only in evaluator memory.

The command reads one frozen manifest and current approved full-text snapshot in read-only mode. It rejects stale hashes/parser versions/licenses, requires complete current-corpus coverage for the `all_approved_arxiv` scope, bounds source bytes/chunks, and refuses to overwrite a report. It performs no provider calls and persists no alternate chunks or embeddings.

```powershell
uv run --locked python -m app.cli.evaluate_chunk_strategies `
  --dataset data/evaluation/arxiv-r01-r03-current-v27-v1.json `
  --output reports/chunk-strategy-v1.json
```

Use a manifest whose parser version, source PDF hashes, approved-text hashes, and source set exactly match the local current index. A MinerU report requires a separately frozen MinerU manifest; a pdfplumber result cannot stand in for it.

## Anchor projection and metrics

Each selected reference chunk is checked against the active source ID, content hash, page, element type, element ID, and exact character interval. A candidate chunk is treated as relevant only when its source interval overlaps that selected interval in the same parser element. Reports show Hit/MRR/NDCG/Recall@k, exact selected-span coverage across retrieved chunks, candidate count, chunk-build time, index-build time, and BM25 search latency.

These labels measure retrieval of a previously selected source span, not independent human relevance judgments. The diagnostic manifest is single-reviewer selected-reference data, so the report always says `gold_standard=false` and `quality_claim_allowed=false`. It is useful for paired strategy diagnostics, not a universal quality score or a production-default decision by itself.

MinerU visual descriptions remain separate `model_generated_unverified` evidence and are not included in exact-text chunk candidates. Figure captions remain searchable. This evaluator does not measure whether MinerU read chart values or trends correctly; that requires a separately licensed and manually checked chart set. The current arms vary chunk size only; overlap/semantic windows, other retrieval methods, and chunk-plus-rerank interaction have not yet been compared here.
