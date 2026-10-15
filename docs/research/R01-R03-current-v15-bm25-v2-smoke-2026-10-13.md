# Current v15 index replay with BM25 v2

Date: 2026-10-13. After the baseline smoke showed R1's reviewed right-column passage at rank 47/48, I tested a small, versioned English plural normalizer. It normalizes regular `-s/-es/-ies` forms and a short list of common scientific irregulars; CJK bigram behavior stays unchanged. BM25 and hybrid identifiers are versioned as v2. No parser output, stored PDF content, database rows, or embedding data changed.

The exact same six questions were replayed against the same active v15 PDF content in read-only SQLite. The user-reviewed target ranks were R1 **5**, R2 **1**, R3 **1**, R4 **1**, R5 **2**, and R6 **3**. Compared with the v1 baseline, R1 moved from 47/48 into the top 8; the other five target ranks were unchanged. Every reference target appeared in top 8 in this six-question replay.

This supports a narrow retrieval fix for a plural/singular mismatch. It does **not** establish general Recall@8, independent quality, or answer-generation accuracy. The existing P05 frozen OpenAlex corpus could not be replayed because its exact snapshot and content hashes are absent from the current local database. Larger quality evaluation remains open; the user has deferred corpus expansion.

## Evidence and reproduction

- Full ranked output, chunk IDs, locators, scores, and per-source content hashes: [JSON report](R01-R03-current-v15-bm25-v2-smoke-2026-10-13.json), SHA-256 `20260901215b9e1dceca22b39746719895d0dd230031258ad2eeecb9be1db1dd`.
- v1 comparator: [baseline report](R01-R03-current-v15-bm25-smoke-2026-10-13.md); old v13 frozen pilot labels and hashes were not migrated.
- Retrieval identifiers: `okapi-bm25-v2`, `bm25_fulltext_v2`, `hybrid_rrf_v2`; tokenizer `unicode-latin-cjk-bigram-plural-v2`.
- Automated checks: tokenizer/BM25 unit tests 7 passed; research-task synthetic evaluation tests 15 passed; full locked backend suite 255 passed with one existing Starlette/AnyIO deprecation warning; Ruff check passed; Ruff format passed for `app tests tools` (79 files); OpenAPI export SHA remains `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`. `ruff format --check .` reports all 96 files formatted but exits nonzero because the pre-existing inaccessible `backend/.pytest-tmp` directory cannot be enumerated. No OpenAPI schema change.
