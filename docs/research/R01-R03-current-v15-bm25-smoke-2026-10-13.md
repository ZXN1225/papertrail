# Current v15 full-text BM25 smoke

Date: 2026-10-13. This is a read-only replay of the same six frozen questions against the four currently active local PDF indexes after the v15 rebuild. It did not call a provider, alter the database, or migrate old labels. The machine-readable ranks, chunk IDs, locators, and active content hashes are in [the JSON record](R01-R03-current-v15-bm25-smoke-2026-10-13.json), SHA-256 `102fd55df4a5bdbe257d8c39222411c8512554567824eb52eaf73083214b55f3`.

| Task | User-reviewed source locator | Current top-8 rank | Observation |
| --- | --- | ---: | --- |
| R1 | Page 3, right-column four-layer description | 47/48 (not in top 8) | Results include an introductory paragraph that mentions four layers, but omit the right-column details naming them. |
| R2 | Page 2, decision-support paragraph | 1/48 | Correct page and paragraph ranked first. |
| R3 | Page 9, Figure 5(a) caption | 1/315 | Full caption ranked first. |
| R4 | Page 9, Figure 5(d)/(e) caption | 1/315 | Repaired full caption ranked first and contains both panel-to-thickness mappings. |
| R5 | Page 10, Table II, Agentic GraphRAG row | 2/743 | Correct table row chunk is in top 8. |
| R6 | Page 10, Table III, NDCG@10 comparison | 3/743 | Correct table chunk is in top 8. |

The observed top-8 count is 5/6 for these six selected references only. Full-source ranks were reproduced with the same `BM25Index` implementation and title/retrieval-text fields used by repository search, ranked across all current chunks for each exact source; this confirmed R1's reference chunk at rank 47 of 48. These are **not** independent holdout results, a general retrieval recall estimate, parser-wide accuracy, or evidence that the answer generator is correct. In particular, R1 should not be counted as successful just because a nearby page-3 introductory paragraph was retrieved. The question set and human judgments are unchanged; prior labels remain bound to the old frozen source-content hashes and are not silently relabeled as v15 gold evidence.

## Reproduction boundary

- Retrieval: `bm25_fulltext_v1`, exact arXiv source scope, top 8; local SQLite opened read-only.
- Frozen question, pilot dataset, human-review, and taskset SHA-256 values are recorded in the JSON.
- The old pilot used parser v13. This replay records current active content hashes per task; it does not rewrite or replace the original v13 pilot results.
- R1 target element is page 3's right-column parent paragraph (current chunk `...:36`); it ranks 47/48. The top 8 contains a page-3 lead-in but not the four-layer details.
