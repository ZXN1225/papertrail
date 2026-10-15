# 当前 v19 索引 BM25 参考定位诊断

日期：2026-10-13。使用现有四篇 approved CC BY 4.0 全文；未扩充语料、未调用模型/embedding 或访问网络。

## 版本与映射

- 数据集：`backend/data/evaluation/arxiv-r01-r03-current-v19-v1.json`，SHA-256 `a5965d32a8f654cc894627eac3c1fefce712ccc55cb689ce74ec7ae766d17e70`。
- 从 v17 版本诊断重建。先读取历史参考 chunk，再按相同 chunk 文本、来源、页码和元素类型在 v19 活动版本逐一唯一映射；6 条均唯一。
- 输出绑定当前 PDF/content SHA 和 parser v19。数据集仍标记 `gold_standard=false`、`quality_claim_allowed=false`，任务来源为单人选定参考。

## 结果

| 任务 | arXiv | 参考位置 | BM25 排名 | 定位一致 |
| --- | --- | --- | ---: | --- |
| R1 | 2609.27579 | 第 3 页 paragraph | 5 | 是 |
| R2 | 2609.27579 | 第 2 页 paragraph | 1 | 是 |
| R3 | 2608.02037 | 第 9 页 figure_caption | 1 | 是 |
| R4 | 2608.02037 | 第 9 页 figure_caption | 1 | 是 |
| R5 | 2607.24663 | 第 10 页 table | 2 | 是 |
| R6 | 2607.24663 | 第 10 页 table | 3 | 是 |

六条参考均进 top 8，locator 6/6，`provider_calls=0`。两次独立运行报告字节一致，报告 SHA-256 `e1e3d5a70229c7601ffd294c97a58c795d1ab14012635d445e61b9ea1034cafc`。这只是冻结小样本上的可复现定位诊断，不是 gold recall、独立 holdout 或一般检索质量结论。

## 复现

从 `backend/` 目录运行；默认数据集当前指向 v19：

```powershell
.venv\Scripts\python.exe -m app.cli.evaluate_fulltext_retrieval `
  --output reports/current-index-fulltext-v19-rerun.json
```

CLI 通过只读 PaperStore 核对活动许可、PDF/content SHA、解析器版本及参考定位；输出不含论文全文摘录。
