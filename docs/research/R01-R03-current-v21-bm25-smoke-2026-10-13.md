# 当前 v21 索引 BM25 参考定位诊断

日期：2026-10-13。对 9 篇活动全文中的原六题参考做版本迁移检查后，在 v21 活动索引上只读重放。无网络、模型或 embedding 调用。

## 映射与边界

- 新诊断清单：`backend/data/evaluation/arxiv-r01-r03-current-v21-v1.json`，SHA-256 `8c6e9783e28313421f4af4284e4de028d953a9a2f37c5415d2d29ad2d41cf92e`。
- 六条旧参考仅当 `retrieval_text`、`evidence_text`、source、page、element type 在当前 approved parser 版本中唯一完全匹配时映射；6/6 唯一映射。此过程只更新 chunk ID 和 source lineage，不重新判定语义支持度，也不把旧人审标签迁移成 v21 标签。
- 本运行只查询任务指定的三个 arXiv ID，未在 9 篇全部文献之间竞争 top-8；因此新增五篇不能影响本报告排名。结果是版本回归 smoke，不是全库检索评测。
- 清单和结果均为 `gold_standard=false`、`quality_claim_allowed=false`、`reference_status=single_reviewer_selected_reference`。

## 结果

| 任务 | 来源 | 页 / 类型 | 参考排名 | 定位匹配 |
|---|---|---|---:|---|
| R1 | 2609.27579 | 3 / paragraph | 5 | 是 |
| R2 | 2609.27579 | 2 / paragraph | 1 | 是 |
| R3 | 2608.02037 | 9 / figure_caption | 1 | 是 |
| R4 | 2608.02037 | 9 / figure_caption | 1 | 是 |
| R5 | 2607.24663 | 10 / table | 2 | 是 |
| R6 | 2607.24663 | 10 / table | 3 | 是 |

selected reference 命中 top-8 为 6/6，locator 6/6，provider calls 0。报告只写入本机忽略目录 `backend/reports/current-index-fulltext-v21.json`。

## 复现

从 `backend/` 运行：

```powershell
.venv\Scripts\python.exe -m app.cli.evaluate_fulltext_retrieval `
  --dataset data/evaluation/arxiv-r01-r03-current-v21-v1.json `
  --output reports/current-index-fulltext-v21-replay.json
```

输出为版本锁定的参考排名诊断，不是独立 holdout、gold evidence recall、一般 RAG 质量或新语料收益结论。后续已新增独立全库诊断，参考 top-8 为 4/6，见 [全库记录](R01-R03-current-v21-full-corpus-2026-10-13.md)。本源内报告仍保持原范围。
