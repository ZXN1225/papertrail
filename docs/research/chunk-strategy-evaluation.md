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

Before executing that arm, use `--dry-run` with the same dataset, query cap and cost cap. It checks
the local vector index and reports query-only transfer cost without creating a provider client,
writing the report, or sending data. The cost is a UTF-8 byte upper bound and applies only to query
embeddings. If chunk vectors are missing, the preview separately estimates the cost of embedding
their full text; that full-text transfer is a distinct operation and is not approved by the query
confirmation flag. A complete index and configured dimensions are required before live reranking.

The full-text index CLI has its own offline preview and transfer boundary. It only selects chunks
missing a vector for the configured model/dimensions. Live indexing requires `--confirm-data-transfer`,
`--max-chunks`, and `--max-cost-usd`; the preview requires the latter two bounds but never calls the
provider:

```powershell
uv run --locked python -m app.cli.index_fulltext_embeddings `
  --source-type arxiv `
  --source-id 2401.00001 `
  --dry-run `
  --max-chunks 5000 `
  --max-cost-usd 0.05
```

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

The local approved snapshot uses `pdfplumber-layout-v27`, not MinerU. It provides no evidence about MinerU parsing or visual chart accuracy. Chunk×parent-proxy-rerank has a runnable paired evaluator, but a held-out independently reviewed task set is still needed before choosing a production strategy.

## Local rerank dry-run (2026-11-12)

The read-only preview ran against a disposable migrated copy of the approved v27 corpus (9 sources,
3,294 active chunks). The configured `text-embedding-3-small` model had no current vectors for any
chunk, so the parent-vector rerank arm is not runnable yet. Six task queries total 404 UTF-8 bytes;
their query-only embedding upper-bound estimate is `$0.00000808`. Building the absent full-text
index would submit 825,894 UTF-8 bytes, with an estimated upper-bound cost of `$0.01651788` at the
configured price. This byte estimate is conservative and not provider token usage. The preview made
zero provider calls, wrote no report, and the original user database hash remained unchanged. This
preview transferred no full text and performed no rerank; these estimates are not evidence of
retrieval quality or rerank benefit.

## Authorized live index and paired rerank diagnostic (2026-11-12)

After the user authorized this exact corpus and six questions and updated the local API credential,
one approved question succeeded as a minimal connectivity probe (13 input tokens, estimated
`$0.00000026`); an earlier transient error returned no usage. The isolated schema-23 copy was
then indexed with `text-embedding-3-small` at 1,536 dimensions: 3,294 current approved chunks,
212,879 provider-reported input tokens, and an estimated `$0.00425758` at the configured
`$0.02`/million-token price. The six questions used one additional embedding request, 92 input
tokens, and an estimated `$0.00000184`. The report is local and ignored at
`backend/.local/chunk-rerank-live-v1.json`; no vectors, paper text, or query embeddings were
committed. The local report SHA-256 is
`BBB7B421B46ED7AE76D2B072C02D0709BAB618C83CBBBEB2C67BC8BE56DB9B92`.
The original user database SHA-256 remained
`C2A77E1E63CE999B4E9D2591B1CDD3D374CBD0EAA399A97652C999A9810811CC`.

| 1,800-byte, zero-overlap arm | Hit@1 | MRR@8 | NDCG@5 | Recall@5 | Full selected-span coverage | Local mean / p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | .500 | .622 | .712 | 1.000 | 1.000 | 1.22 / 3.05 |
| BM25 then parent-vector proxy rerank | .333 | .417 | .439 | .500 | .500 | 49.99 / 70.95 |

The local latency figures exclude the embedding provider call (about 3.36 seconds for all six
questions). This parent-vector proxy promoted some selected spans and demoted others; on these six
single-reviewer tasks it is worse overall than BM25. Do not enable it as a production default on
this evidence. The labels are selected source spans, not independently judged relevance; the
report retains `gold_standard=false` and `quality_claim_allowed=false`.

A separate read-only input comparison found that the stored indexed `text` differs from the
evaluator's candidate `text` for 2,946/3,294 chunks even in this zero-overlap arm; exact
`evidence_text` agrees for all 3,294. The indexer embeds stored `text`, so the vector is a
parent-input proxy even where the candidate and parent span match. This negative result does not
measure the quality of embedding the candidate text itself.

The other five chunk configurations reported `candidate_to_parent_embedding_mapping_failed`,
not a retrieval score. A separate read-only span-mapping audit of the same frozen snapshot found
child chunks crossing two current parent chunk boundaries: 62/3,575 (900/0), 132/3,605
(900/10%), 118/3,418 (1,200/0), 132/3,451 (1,200/10%), and 131/3,304 (1,800/10%). The
evaluator requires every child to fit exactly
inside one parent to avoid presenting a parent vector as a genuine child embedding. A valid
cross-chunk rerank comparison needs embeddings of those child chunks or a separately specified
multi-parent proxy, with its own data-transfer scope and quality limits. The existing index and
this report provide neither a true child-vector nor a cross-encoder comparison.

During the connectivity check, a transient `provider_unavailable` also exposed that the chunk
evaluation CLI let `EmbeddingError` escape as a Python traceback. The CLI now reports only the safe
error code and exits nonzero without writing a result file; a focused fake-provider test covers it.

## True candidate-vector experiment: invalidated attempts (2026-11-12)

The user separately authorized candidate-text embeddings for the same frozen nine-source,
six-question snapshot. A first local script sent 1,098 deduplicated candidate texts (897,709
UTF-8 bytes) and the six questions to `text-embedding-3-small` in 19 completed calls. The provider
reported 214,826 input tokens, estimated `$0.00429652` at the configured price. Subsequent
method review found that this script selected BM25 candidates across all nine papers while the
frozen manifest and baseline evaluate each task within its specified paper. The resulting local
report `backend/.local/true-candidate-rerank-v1.json` (SHA-256
`DCF52B8036777FE1547624395E8F42201CD088E20D75F2CA36696635EFE9DC0A`) is **invalid for
paired comparison**. A same-directory `.INVALID.txt` sidecar marks it without altering the
original report. Its rerank numbers must not be interpreted or used to choose a strategy.

A corrected, read-only source-scoped preview found 2,221 selected candidate IDs and 824 new
deduplicated texts (690,259 UTF-8 bytes) across six arms. Together with the same six questions
(404 bytes), the estimated upper bound was `$0.01381326` for at most 14 calls. The attempted
corrected run stopped on an embedding timeout before a report was written. The one-off script did
not persist per-batch vectors or usage, so completed work and cost from that interrupted run are
unknown. No further provider retry is made under the previous estimate cap. The original user
database SHA-256 remained unchanged.

A reproducible runner needs to enforce the manifest's source scope, preserve batch progress and
provider usage only in an ignored local cache, and stop when the remaining authorized estimate
cannot cover another attempt. Before that runner completed, there was **no valid true candidate
vector rerank comparison**. The existing BM25 and parent-vector proxy results above remain
separate exploratory diagnostics, not MinerU chart-quality evidence or an independent gold set.

The new `python -m tools.evaluate_true_candidate_rerank` command implements that source-scope
and retry boundary. It defaults to a read-only, zero-provider dry-run. It requires an explicit
dataset, output path, query count, new-text count, new UTF-8 byte cap, and positive estimated
cost cap. A live run additionally requires `--execute --confirm-data-transfer` and an enabled
OpenAI embedding provider. The current frozen-snapshot preview used:

```powershell
uv run --locked python -m tools.evaluate_true_candidate_rerank `
  --dataset data/evaluation/arxiv-r01-r03-current-v27-v1.json `
  --output .local/true-candidate-rerank-replay.json `
  --max-query-embeddings 6 `
  --max-new-texts 824 `
  --max-new-utf8-bytes 690259 `
  --max-cost-usd 0.02
```

The command uses the configured read-only database, embedding model, dimensions, and price; this
snapshot needs the isolated schema-23 copy and `text-embedding-3-small`/1,536. It reuses current
vectors only for exactly equal candidate input text. Each attempted provider batch reserves its
UTF-8 byte estimate **before** the call in an ignored `.local/candidate-rerank-cache/<plan hash>`
ledger. Completed batches store text hashes and vectors, without raw text, in that ignored cache.
The next dry-run shows cached batches, remaining batches, and cumulative attempt reservation;
live retry is rejected if the reservation plus remaining transfer exceeds the supplied cap.
This is a local estimate gate, not a provider billing limit. It cannot reconstruct the unknown
usage or vectors from the earlier one-off timed-out attempt, so no additional live call was made
while completing this runner.

## Correct source-scoped candidate-vector rerank (2026-11-13)

After a new, explicit transfer authorization, the runner completed on the same isolated schema-23
copy and frozen v27 manifest. Its preflight selected 2,221 candidate IDs across six chunk arms,
824 new unique texts (690,259 UTF-8 bytes), and six queries (404 UTF-8 bytes), with
`source_scope=exact_arxiv_id_per_task`. All 36 task/arm rankings contain only their task's source;
every shortlist has at most 128 candidates. The local batch cache completed 14/14 batches.
Provider-reported input was 170,342 tokens, estimated `$0.00340684` at the configured
`$0.02`/million token price, versus the preflight UTF-8 byte upper estimate `$0.01381326` and
the CLI `$0.02` estimate cap. These are not provider billing limits. The earlier invalid and
timed-out attempts are separate; the timed-out attempt's charge remains unknown.

| Chunk arm | BM25 MRR@8 / NDCG@5 | Candidate-vector MRR@8 / NDCG@5 | Full span coverage BM25 / vector |
|---|---:|---:|---:|
| 900 bytes, no overlap | .561 / .620 | .417 / .438 | .833 / .500 |
| 900 bytes, max 10% overlap | .561 / .580 | .500 / .500 | .833 / .500 |
| 1,200 bytes, no overlap | .533 / .586 | .500 / .500 | .833 / .500 |
| 1,200 bytes, max 10% overlap | .538 / .573 | .500 / .500 | .833 / .500 |
| 1,800 bytes, no overlap | .622 / .712 | .417 / .438 | 1.000 / .500 |
| 1,800 bytes, max 10% overlap | .631 / .720 | .417 / .438 | 1.000 / .500 |

The result is a true candidate-input embedding comparison within BM25 top-128, not the earlier
parent-vector proxy or an all-corpus dense retrieval experiment. On these six single-reviewer
selected-span tasks, vector reranking degraded every arm; the production default remains BM25
with the existing 1,800-byte chunker. The corpus uses `pdfplumber-layout-v27`, so this is not a
MinerU, chart, cross-encoder, or general user-query quality measurement. A separately reviewed,
larger held-out set is still required for a production quality threshold or strategy selection.

The ignored local report is `backend/.local/true-candidate-rerank-replay.json`, SHA-256
`B7695763DAD43C060083B9582B975A3C999F6B4821D906FAD02030714204BC27`;
`quality_claim_allowed=false`. Original user SQLite SHA-256 remains
`C2A77E1E63CE999B4E9D2591B1CDD3D374CBD0EAA399A97652C999A9810811CC`.
