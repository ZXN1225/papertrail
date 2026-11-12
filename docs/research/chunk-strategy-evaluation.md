# Read-only chunk strategy comparison

## Arms and runtime

`python -m app.cli.evaluate_chunk_strategies` compares the current structure-preserving PDF chunker at 1,800 UTF-8 bytes with the same algorithm capped at 900 bytes. Table row/header structure, source element IDs, page numbers, bounding boxes, and half-open element-local offsets are retained. The production ingestion version remains unchanged; alternative chunks exist only in evaluator memory.

The command reads one frozen manifest and current approved full-text snapshot in read-only mode. It rejects stale hashes/parser versions/licenses, requires complete current-corpus coverage for the `all_approved_arxiv` scope, bounds source bytes/chunks, and refuses to overwrite a report. If a valid table header cannot fit in the 900-byte arm without losing its structure, that arm is reported unavailable while the 1,800-byte arm remains measurable. It performs no provider calls and persists no alternate chunks or embeddings.

```powershell
uv run --locked python -m app.cli.evaluate_chunk_strategies `
  --dataset data/evaluation/arxiv-r01-r03-current-v27-v1.json `
  --output reports/chunk-strategy-v1.json
```

Use a manifest whose parser version, source PDF hashes, approved-text hashes, and source set exactly match the local current index. A MinerU report requires a separately frozen MinerU manifest; a pdfplumber result cannot stand in for it.

## Anchor projection and metrics

Each selected reference chunk is checked against the active source ID, content hash, page, element type, element ID, and exact character interval. A candidate chunk is treated as relevant only when its source interval overlaps that selected interval in the same parser element. Reports show Hit/MRR/NDCG/Precision/Recall@k, exact selected-span coverage across retrieved chunks, candidate count, chunk-build time, index-build time, and BM25 search latency.

These labels measure retrieval of a previously selected source span, not independent human relevance judgments. The diagnostic manifest is single-reviewer selected-reference data, so the report always says `gold_standard=false` and `quality_claim_allowed=false`. It is useful for paired strategy diagnostics, not a universal quality score or a production-default decision by itself.

MinerU visual descriptions remain separate `model_generated_unverified` evidence and are not included in exact-text chunk candidates. Figure captions remain searchable. This evaluator does not measure whether MinerU read chart values or trends correctly; that requires a separately licensed and manually checked chart set. The current arms vary chunk size only; overlap/semantic windows, other retrieval methods, and chunk-plus-rerank interaction have not yet been compared here.

## Local approved-corpus run (2026-11-12)

A read-only diagnostic was run against the local frozen v27 snapshot: 9 approved CC-BY-4.0 sources and 6 selected-reference tasks. The source database was schema version 22 while this checkout requires version 23, so evaluation used a disposable copy migrated in `.local`; the original database SHA-256 was unchanged. No embedding/model provider calls were made. Dataset manifest SHA-256: `87db19bece61ca54190b5b634ee0a0f731e3c5c0972acd9fdedf4b3f23e461a5`.

| Chunk arm | Chunks | Hit@1 | MRR@8 | NDCG@5 | Recall@5 | Full selected-span coverage | BM25 mean / p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1,800 bytes | 3,294 | 0.500 | 0.622 | 0.712 | 1.000 | 1.000 | 1.71 / 4.70 ms |
| 900 bytes | 3,575 | 0.333 | 0.561 | 0.620 | 0.917 | 0.833 | 2.12 / 6.15 ms |

At `@3`, the smaller arm had higher Hit (0.833 vs 0.667), Precision (0.278 vs 0.222), and Recall (0.750 vs 0.667). On this six-task diagnostic, the 1,800-byte arm ranked the selected spans better overall and covered all selected spans within top 8; the 900-byte arm missed one full span. These small single-reviewer reference results are not a gold benchmark or a general quality estimate, and do not justify a production chunker change.

One selected chunk ID was stale after chunking changes. The evaluator now remaps it only when the historical chunk is from the same PDF hash and its exact evidence text occurs uniquely on the same current page and element type. It fails closed otherwise. This exact text remap resolved 1/6 tasks; the other 5 used current chunk IDs.

The local approved snapshot uses `pdfplumber-layout-v27`, not MinerU. It provides no evidence about MinerU parsing or visual chart accuracy. MinerU chart evaluation, real BM25-vs-rerank comparison, and chunk×rerank interaction remain open.
