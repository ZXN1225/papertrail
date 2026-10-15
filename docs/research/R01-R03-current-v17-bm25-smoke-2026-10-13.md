# 当前 v17 索引 BM25 参考定位诊断

日期：2026-10-13。使用当前四篇 approved CC-BY-4.0 全文索引，按 arXiv ID 隔离检索；无模型或 embedding provider 调用。

## 冻结与映射

- Dataset：`backend/data/evaluation/arxiv-r01-r03-current-v17-v1.json`，SHA-256 `8a81f4652ff0e0b7050d4512ed753aa3c806195ba0dd0b390834414a200f3151`。
- 从 v15 六题诊断派生，保留同一问题和单人选定参考。每条旧参考按 chunk 全文、PDF 页码、元素类型在对应 v17 来源中精确匹配，六条均唯一；这只是版本迁移定位，不是新的人审，也没有把旧 chunk ID 直接沿用。
- 三篇来源与当前活动 v17 parser/content/PDF SHA 锁定。结果 JSON 位于本机忽略目录 `backend/reports/current-index-fulltext-v17-v1.json`，CLI 每次要求新输出路径，避免覆盖。
- 两次独立只读重放报告逐字节一致，报告 SHA-256 `a879fdd0dd62098f59687938516bb7913be86b0f64485b03ccd315c67ce335ce`。

## 结果

| 任务 | arXiv | 参考位置 | BM25 排名 | 定位一致 |
| --- | --- | --- | ---: | --- |
| R1 | 2609.27579 | 第 3 页 paragraph | 5 | 是 |
| R2 | 2609.27579 | 第 2 页 paragraph | 1 | 是 |
| R3 | 2608.02037 | 第 9 页 figure_caption | 1 | 是 |
| R4 | 2608.02037 | 第 9 页 figure_caption | 1 | 是 |
| R5 | 2607.24663 | 第 10 页 table | 2 | 是 |
| R6 | 2607.24663 | 第 10 页 table | 3 | 是 |

六条单人选定参考均进入 top 8，页码/元素类型与参考一致；summary 为 6/6。`provider_calls=0`、`gold_standard=false`、`quality_claim_allowed=false`。这只能说明这六条既有参考 passage 在本次版本中可被 BM25 找到，不是 gold recall、独立 holdout 或一般检索质量结论；R1 排名第 5 的相关性仍需更广泛查询和人工 qrels 才能判断。

## 复现

从 `backend/` 运行：

```powershell
.venv\Scripts\python.exe -m app.cli.evaluate_fulltext_retrieval `
  --output reports/current-index-fulltext-v17-rerun.json
```

Runner 要求只读 `PaperStore`，检查当前许可、PDF/content SHA、parser version 与 chunk locator；输出不含全文摘录。
