# Read-only chunk strategy comparison

## Arms and runtime

`python -m app.cli.evaluate_chunk_strategies` compares the current structure-preserving PDF chunker at 900, 1,200, and 1,800 UTF-8 bytes, each with zero overlap and a maximum overlap target of 10% of the byte cap. Whitespace alignment can make realized overlap smaller than that maximum. Overlap applies only to text elements; table row/header structure remains non-overlapping. Source element IDs, page numbers, bounding boxes, and half-open element-local offsets are retained. The production ingestion version remains unchanged; alternative chunks exist only in evaluator memory. Each chunk configuration has a BM25 arm and an optional parent-embedding proxy rerank arm.

The command reads one frozen manifest and current approved full-text snapshot in read-only mode. It rejects stale hashes/parser versions/licenses, requires complete current-corpus coverage for the `all_approved_arxiv` scope, bounds source bytes/chunks, and refuses to overwrite a report. If a valid table header cannot fit in the 900-byte arm without losing its structure, that arm is reported unavailable while the 1,800-byte arm remains measurable. The default BM25 path performs no provider calls and neither path persists alternate chunks or embeddings.

BM25 is the zero-provider default:

```powershell
uv run --locked python -m app.cli.evaluate_chunk_strategies `
  --dataset data/evaluation/arxiv-r01-r03-current-v27-v1.json `
  --output reports/chunk-strategy-v1.json
```

To compare reranking, the explicitly acknowledged operation sends only task questions to the
configured embedding provider. The evaluator uses existing current chunk vectors and does not send
paper excerpts or alternate chunks. Both the question-count cap and estimated-cost cap are required:

```powershell
uv run --locked python -m app.cli.evaluate_chunk_strategies `
  --dataset data/evaluation/arxiv-r01-r03-current-v27-v1.json `
  --output reports/chunk-rerank-v1.json `
  --parent-embedding-rerank `
  --confirm-data-transfer `
  --max-query-embeddings 6 `
  --max-cost-usd 0.01
```

Use a manifest whose parser version, source PDF hashes, approved-text hashes, and source set exactly match the local current index. A MinerU report requires a separately frozen MinerU manifest; a pdfplumber result cannot stand in for it.

## Anchor projection and metrics

Each selected reference chunk is checked against the active source ID, content hash, page, element type, element ID, and exact character interval. A candidate chunk is treated as relevant only when its source interval overlaps that selected interval in the same parser element. Reports show Hit/MRR/NDCG/Precision/Recall@k, exact selected-span coverage across retrieved chunks, candidate count, chunk-build time, index-build time, and BM25 search latency.

These labels measure retrieval of a previously selected source span, not independent human relevance judgments. The diagnostic manifest is single-reviewer selected-reference data, so the report always says `gold_standard=false` and `quality_claim_allowed=false`. It is useful for paired strategy diagnostics, not a universal quality score or a production-default decision by itself.

The rerank arm uses the existing 1,800-byte indexed chunk vector as a proxy for each candidate chunk. Mapping requires exact source ID, source content hash, element ID/type, page, and half-open span containment in exactly one active indexed chunk; ambiguous or missing matches disable that arm. Candidates are selected by the first 128 unique BM25 parent chunks, then sorted by cosine similarity; children under one parent keep BM25 order. This avoids a 900-byte arm spending its entire budget on siblings, but it is not true child-chunk embedding, dense retrieval, or a cross-encoder. The report gives the mean children-per-parent and selected unique-parent count, and separates local retrieval latency from query embedding provider usage. Missing/incomplete vectors disable reranking rather than silently dropping affected tasks.

MinerU visual descriptions remain separate `model_generated_unverified` evidence and are not included in exact-text chunk candidates. Figure captions remain searchable. This evaluator does not measure whether MinerU read chart values or trends correctly; that requires a separately licensed and manually checked chart set. It compares chunk size/overlap and this parent-vector proxy; semantic windows, true child-chunk embeddings, and cross-encoder reranking remain unevaluated. Chunk-level MRR/NDCG can shift when a method creates more overlapping relevant chunks, so interpret them beside exact evidence-span coverage and the raw candidate count.

## Local overlap ablation (2026-11-12)

The same frozen v27 manifest and 9-source local approved snapshot were replayed from a disposable `.local` database copy. The original user database SHA-256 remained `C2A77E1E63CE999B4E9D2591B1CDD3D374CBD0EAA399A97652C999A9810811CC`; the diagnostic used 6 single-reviewer selected-reference tasks and 0 provider calls. Results remain `gold_standard=false` and `quality_claim_allowed=false`.

| Chunk configuration | Chunks | Hit@1 | MRR@8 | NDCG@5 | Recall@5 | Full span coverage | BM25 mean / p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| 900 bytes, no overlap | 3,575 | .333 | .561 | .620 | .917 | .833 | 1.36 / 3.40 |
| 900 bytes, max 10% overlap target | 3,605 | .333 | .561 | .580 | .833 | .833 | 1.36 / 3.81 |
| 1,200 bytes, no overlap | 3,418 | .333 | .533 | .586 | .833 | .833 | 1.21 / 3.06 |
| 1,200 bytes, max 10% overlap target | 3,451 | .333 | .538 | .573 | .833 | .833 | 1.20 / 3.08 |
| 1,800 bytes, no overlap | 3,294 | .500 | .622 | .712 | 1.000 | 1.000 | 1.13 / 3.12 |
| 1,800 bytes, max 10% overlap target | 3,304 | .500 | .631 | .720 | 1.000 | 1.000 | 1.13 / 2.89 |

The 1,800-byte overlap arm has a small MRR/NDCG increase without changing span coverage; 900-byte overlap lowers NDCG/Recall and adds chunks; 1,200-byte overlap changes ranking little and does not change coverage. Six single-reviewer tasks are insufficient to choose a production default; no ingestion setting changed. Rerank arms were unavailable because no query embeddings were supplied; no external query data was sent.

## Local approved-corpus run (2026-11-12)

A read-only diagnostic was run against the local frozen v27 snapshot: 9 approved CC-BY-4.0 sources and 6 selected-reference tasks. The source database was schema version 22 while this checkout requires version 23, so evaluation used a disposable copy migrated in `.local`; the original database SHA-256 was unchanged. No embedding/model provider calls were made. Dataset manifest SHA-256: `87db19bece61ca54190b5b634ee0a0f731e3c5c0972acd9fdedf4b3f23e461a5`.

| Chunk arm | Chunks | Hit@1 | MRR@8 | NDCG@5 | Recall@5 | Full selected-span coverage | BM25 mean / p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1,800 bytes | 3,294 | 0.500 | 0.622 | 0.712 | 1.000 | 1.000 | 1.71 / 4.70 ms |
| 900 bytes | 3,575 | 0.333 | 0.561 | 0.620 | 0.917 | 0.833 | 2.12 / 6.15 ms |

At `@3`, the smaller arm had higher Hit (0.833 vs 0.667), Precision (0.278 vs 0.222), and Recall (0.750 vs 0.667). On this six-task diagnostic, the 1,800-byte arm ranked the selected spans better overall and covered all selected spans within top 8; the 900-byte arm missed one full span. These small single-reviewer reference results are not a gold benchmark or a general quality estimate, and do not justify a production chunker change.

One selected chunk ID was stale after chunking changes. The evaluator now remaps it only when the historical chunk is from the same PDF hash and its exact evidence text occurs uniquely on the same current page and element type. It fails closed otherwise. This exact text remap resolved 1/6 tasks; the other 5 used current chunk IDs.

The local approved snapshot uses `pdfplumber-layout-v27`, not MinerU. It provides no evidence about MinerU parsing or visual chart accuracy. Chunk×parent-proxy-rerank has a runnable paired evaluator, but a real rerank run requires explicit query-embedding data-transfer consent and a complete local embedding index; no strategy winner is claimed until that run and a held-out reviewed task set exist.
