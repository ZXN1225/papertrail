# R01–R03 本机许可语料扩充记录

日期：2026-10-13。该记录核对了用户放入项目根目录的 10 份 PDF。全文仅在本机处理，不纳入 Git。

## 准入结论

既有 4 篇均保留原有 CC BY 4.0 审核与索引。新增 PDF 中有 5 篇的官方 arXiv 许可入口指向 CC BY 4.0，并已依项目白名单导入；另有 1 篇许可为 CC BY-NC-SA 4.0，不符合当前只接收 CC0/CC BY 4.0 的项目白名单，因此没有创建活动全文索引。该论文的元数据 API 导入失败超时，当前数据库中未查到此 arXiv ID。

| arXiv | 本机 PDF | 官方论文页 | PDF 许可 | 页数 | v21 chunks | 导入 |
|---|---|---|---|---:|---:|---|
| 2610.09789 | `cooperation, Defection, and the commons.pdf` | [arXiv:2610.09789](https://arxiv.org/abs/2610.09789) | CC BY 4.0 | 14 | 285 | approved |
| 2610.12662 | `evaluating llms for translating.pdf` | [arXiv:2610.12662](https://arxiv.org/abs/2610.12662) | CC BY 4.0 | 21 | 346 | approved |
| 2609.39773 | `riemannian flow models with.pdf` | [arXiv:2609.39773](https://arxiv.org/abs/2609.39773) | CC BY 4.0 | 41 | 1,482 | approved |
| 2610.06874 | `statistical turbulence and.pdf` | [arXiv:2610.06874](https://arxiv.org/abs/2610.06874) | CC BY 4.0 | 36 | 705 | approved |
| 2610.10204 | `Three-dimensional Largrangian.pdf` | [arXiv:2610.10204](https://arxiv.org/abs/2610.10204) | CC BY 4.0 | 18 | 684 | approved |
| 2610.13595 | `A data-driven heuristic.pdf` | [arXiv:2610.13595](https://arxiv.org/abs/2610.13595) | CC BY-NC-SA 4.0 | 21 | — | excluded by allowlist |

CC BY-4.0 licenses were checked through the paper-specific arXiv `view license` links, which resolve to [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). The excluded record's license resolves to [Creative Commons Attribution-NonCommercial-ShareAlike 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). License and metadata sources are not conflated: arXiv metadata snapshots record the metadata source's CC0 distribution terms; each PDF manifest separately records its paper license, evidence URL, version, attribution and local PDF SHA-256.

## Lineage and parser state

- The five allowlisted additions have source metadata imported from the official arXiv API at version v1, then local PDF processing under `pdfplumber-layout-v21`.
- A read-only lineage audit verified all 9 approved PDFs: license state, PDF SHA-256, active parser version, metadata chunk count and per-chunk content SHA agree. Total active corpus: **9 papers, 4,871 chunks, 217 PDF pages**. This is a lineage result, not a parsing-accuracy or retrieval-quality result.
- New active chunks: 3,502. Current parser warning counts for the five additions: 9 for 2610.09789, 6 for 2610.12662, 8 for 2609.39773, 30 for 2610.06874 and 5 for 2610.10204. Warnings are retained and should be investigated; warning counts alone are not error rates.
- A local-only review package compares parser-v21 table/caption elements to 17 rendered original pages. It is at `backend/reports/live_eval/corpus-expansion-v21-human-review.md` with adjacent PNGs. The 2610.09789 p5 table is preserved as single-column visual lines because its structured geometry is unreliable; the record warns that column relationships are unavailable. The 2610.12662 p14 Table 2 no longer includes following prose. Other selected multi-column/rotated/complex-table pages still need human verification.
- Importing 2610.13595 metadata from the official API timed out; a read-only database check found no record for this ID. Its PDF remains unprocessed.

## Deferred and excluded work

- To reach the nominal 10-full-text target under the current allowlist, replace the excluded CC BY-NC-SA paper with a CC BY 4.0/CC0 PDF, or explicitly ask to reconsider share-alike implications. No policy change was made.
- The 17-item review packet awaits human comparison against the PDFs. The previously pending v20 Figure 5 bbox image also remains a separate visual gate.
- No new LLM, embedding or paid-model evaluation ran. No PDF, full text, database, or generated review package was added to Git; no commit or GitHub upload was made.
