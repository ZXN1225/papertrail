# 当前 v20 索引 BM25 参考定位诊断

日期：2026-10-13。使用四篇已批准 CC BY 4.0 全文；未扩充语料、未调用模型/embedding 或访问网络。

## 版本与映射

- 数据集：`backend/data/evaluation/arxiv-r01-r03-current-v20-v1.json`，SHA-256 `f49494c587dd023a71b7860b480728a34833ce880e43f0e0826b2a5263f56bd6`。
- 从 v19 诊断版本化：六条历史 reference 均按 retrieval text、evidence text、source、page 和 element type 在 v20 活动索引唯一匹配；未将 v19 chunk ID 或人工标签原样迁移。
- 当前四篇活动全文的 parser 均为 `pdfplumber-layout-v20`，license 为 CC-BY-4.0，PDF SHA 与许可复核时间保持不变。
- 数据集和报告均为 `gold_standard=false`、`quality_claim_allowed=false`，参考来自单人选择的小样本。

## 结果

| 任务 | arXiv | 参考位置 | BM25 排名 | 定位一致 |
| --- | --- | --- | ---: | --- |
| R1 | 2609.27579 | 第 3 页 paragraph | 5 | 是 |
| R2 | 2609.27579 | 第 2 页 paragraph | 1 | 是 |
| R3 | 2608.02037 | 第 9 页 figure_caption | 1 | 是 |
| R4 | 2608.02037 | 第 9 页 figure_caption | 1 | 是 |
| R5 | 2607.24663 | 第 10 页 table | 2 | 是 |
| R6 | 2607.24663 | 第 10 页 table | 3 | 是 |

六条参考均进入 top 8，locator 6/6，`provider_calls=0`。两次运行报告字节一致，SHA-256 `4b55361e8ba4a940e5340f86ad55af1af9251a1a3280cce878437971e5c1ba0a`。这只是冻结小样本上的可复现定位诊断，不是 gold recall、独立 holdout 或一般检索质量结论。

## 复现

从 `backend/` 目录运行；默认数据集当前指向 v20：

```powershell
.venv\Scripts\python.exe -m app.cli.evaluate_fulltext_retrieval `
  --output reports/current-index-fulltext-v20-new-run.json
```

CLI 通过只读 PaperStore 核对活动许可、PDF/content SHA、解析器版本与参考定位；输出不含论文全文摘录。
