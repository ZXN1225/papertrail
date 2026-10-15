# 当前 v18 索引 BM25 参考定位诊断

日期：2026-10-13。用户暂缓语料扩充后，只在现有四篇已批准 CC BY 4.0 本机全文上离线重放，没有模型、embedding 或网络调用。

## 版本与重映射

- 数据集：`backend/data/evaluation/arxiv-r01-r03-current-v18-v1.json`，SHA-256 `2362cefc124848cefaa773858ee5f1f836a7271afd393709939b5751c54d895b`。
- 从 v17 诊断派生。每个旧参考 chunk 先在历史版本读取，再按完全相同的 chunk 文本、来源、页码及元素类型，在当前活动 v18 源中做唯一精确映射；六条都唯一。
- 当前活动来源 lineage 锁定到 v18。该数据集保留 `gold_standard=false`、`quality_claim_allowed=false` 和单人选定参考的声明。

## 结果

| 任务 | arXiv | 参考位置 | BM25 排名 | 定位一致 |
| --- | --- | --- | ---: | --- |
| R1 | 2609.27579 | 第 3 页 paragraph | 5 | 是 |
| R2 | 2609.27579 | 第 2 页 paragraph | 1 | 是 |
| R3 | 2608.02037 | 第 9 页 figure_caption | 1 | 是 |
| R4 | 2608.02037 | 第 9 页 figure_caption | 1 | 是 |
| R5 | 2607.24663 | 第 10 页 table | 2 | 是 |
| R6 | 2607.24663 | 第 10 页 table | 3 | 是 |

两次独立运行报告逐字节一致，报告 SHA-256 `9bf10a552cddbc9327d7f64ae7b20747ad036e684408286e7d444e76827605c9`。六个选定参考均进 top 8、locator 6/6，`provider_calls=0`。这只证明小型单人参考集上的可复现定位，不是 gold evidence recall、独立 holdout 或一般检索质量结论。

## 复现

在 `backend/` 下运行默认版本锁定数据集：

```powershell
.venv\Scripts\python.exe -m app.cli.evaluate_fulltext_retrieval `
  --output reports/current-index-fulltext-v18-rerun.json
```

默认数据集为 `arxiv-r01-r03-current-v18-v1.json`。CLI 使用只读 PaperStore，输出不含论文全文摘录；输出文件必须不存在。
