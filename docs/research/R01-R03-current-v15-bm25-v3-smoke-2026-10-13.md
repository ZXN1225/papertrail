# Current v15 index replay with BM25 v3

Date: 2026-10-13. A code review of the v2 suffix rules found that singular `lens`, `gas`, `alias`, `canvas`, and related terms could be truncated as if they were plurals, while some of their plural forms were not reduced to the same token. The tokenizer now protects these common singulars and explicitly maps the corresponding ambiguous plural forms. This changes the retrieval contract, so tokenizer, BM25, full-text BM25, hybrid, and synthetic scoring identifiers were bumped to v3/v4 as applicable.

I replayed the exact same six questions against the active v15 chunks using read-only SQLite. All six reference ranks stayed at R1 **5**, R2 **1**, R3 **1**, R4 **1**, R5 **2**, and R6 **3**. Every per-question top-8 chunk ID list and active content hash matched the v2 diagnostic. No PDF content, parser output, database row, embedding, provider call, or network access was involved.

This is a compatibility regression check on the same six selected questions, not independent evidence of general retrieval quality. The broader R01–R03 quality gate remains open; the user has deferred corpus expansion.

## Evidence

- Machine-readable report: [JSON](R01-R03-current-v15-bm25-v3-smoke-2026-10-13.json), SHA-256 `b02dbf7d0982d70e770c079e5c3081ac848fdc9f43793915333b650d8ee145ea`.
- Compared with the v2 replay: [prior JSON](R01-R03-current-v15-bm25-v2-smoke-2026-10-13.json); v2 report SHA-256 `20260901215b9e1dceca22b39746719895d0dd230031258ad2eeecb9be1db1dd`.
- Retrieval identifiers: tokenizer `unicode-latin-cjk-bigram-plural-v3`, BM25 `okapi-bm25-v3`, full-text BM25 `bm25_fulltext_v3`, Hybrid `hybrid_rrf_v3`.
- Focused tests after the final edit: BM25/metrics, full-text API, and synthetic research-task regression, **37 passed, 1 existing Starlette/AnyIO deprecation warning**. Full backend suite: **255 passed, 1 same warning**. Ruff check passed; format check passed for `app tests tools` (79 files); OpenAPI export passed and SHA stayed `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`. The initial `uv` invocation could not access its user cache; checks ran with the already-installed locked project virtual environment. Root `git diff --check` passed.
