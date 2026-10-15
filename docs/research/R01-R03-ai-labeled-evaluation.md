# R01/R03 AI 标注评测集与真实语料检索结果

数据集：`backend/data/evaluation/ai-labeled-licensed-v1.json`（schema `papertrail.ai-labeled-tasks.v1`）
运行报告：`data/storage/ai-labeled-v1-report.json`（Git 忽略）
评测执行：`backend/app/cli/evaluate_ai_labeled_tasks.py`（只读，0 次 provider 调用）

## 这是什么，不是什么

**是**：在**当前活动的 9 篇 CC BY 4.0 许可全文（v27、3,294 chunks）**上，一套 53 题的检索落地评测——
44 道可答题（每题绑定一个真实 `chunk_id` 与逐字原文片段）+ 9 道不可答题（题目所问的事实在整个语料中不存在）。

**不是**：人工金标。标签由 AI Agent 编写，数据集里 `label_source = "ai_agent_review"`、
`human_reviewed = false`、`gold_standard = false`、`quality_claim_allowed = false`。
代码层面强制这些字段，任何声称人工复核或金标的dataset都会被 runner 拒绝。

**主要偏差（必须随数字一起引用）**：题目是从**同一个被评测的索引**里写出来的，所以这个分数偏乐观，
只能说明"索引内部自洽且可检索"，不能外推为对第三方提问的检索质量。

## 标签怎么来的，怎么校验的

1. `tools/export_labeling_candidates.py` 按来源均匀抽出 108 个候选 chunk（每篇 12 个，正文/表格/图注，≥240 字符）。
2. 三个独立 Agent 各读 3 篇的候选，产出 44 道可答题（每题含 `chunk_id`、页码、元素类型、逐字引用）与 9 道不可答题。
   Agent 被要求用**切片**而不是手打来生成引用，并各自做了自检。
3. `tools/build_ai_labeled_dataset.py` 做**机械**复核后组装：引用必须在所指 chunk 里逐字存在、
   来源/页码/元素类型必须一致、`table_lookup`/`figure_caption` 只能落在对应元素类型上、
   不可答题的事实必须**在整个语料中都不出现**。**不通过的任务直接丢弃并打印原因**——本次丢弃 1 条
   （`AI-2610.06874-01`：`quote_not_verbatim`）。两个独立环节（Agent 自检 + 构建器复核）仍然抓到了 1 条不合格标签，
   说明这层校验不是形式主义。

## 结果（top_k = 8，全库 3,294 chunks/查询，0 provider calls）

| 指标 | 结果 |
| --- | --- |
| **证据命中 @1** | **26 / 44 = 59.1%** |
| **证据命中 @8** | **39 / 44 = 88.6%** |
| 未进 top-8 | 5 题 |

按题型：

| 题型 | 题数 | 证据命中 @8 |
| --- | --- | --- |
| `figure_caption` | 5 | **5/5 = 100%** |
| `multi_hop` | 12 | 11/12 = 91.7% |
| `single_fact` | 24 | 22/24 = 91.7% |
| `table_lookup` | 3 | **1/3 = 33.3%** |

**不可答题的可分性**（诊断，不是质量结论）：BM25 top-1 分数上，可答题均值 **32.47**（最高 57.43），
不可答题均值 **18.30**（最高 27.65）。本样本中**不可答题的最高分低于可答题的均值**，
即一个固定阈值就能把两组完全分开——这是一条可复核的观察，但样本只有 9 道负例，不足以声称普遍可用。

## 两个值得记录的结论

1. **`table_lookup` 是明确短板（1/3）**，与 R02 记录的表头切词/单元格归属缺陷方向一致。
   这不是巧合：表格列标签不可复原时，按表头词语提问自然检索不到。
   该题型样本仅 3 道，因此只能作为**线索**而非结论。
2. **检索的失败集中在"答案分散/需要跨段"的题**：top-8 未中的 5 题分别为
   `AI-2608.20519-01/05`、`AI-2609.27579-05`、`AI-2610.06874-02`、`AI-2610.12662-05`。

## 复现

```powershell
cd backend
$env:PYTHONIOENCODING='utf-8'

# 1) 抽候选（只读活动库，输出在 Git 忽略目录，因为含论文正文）
..\.venv\Scripts\python.exe -m tools.export_labeling_candidates --per-source 12

# 2) 组装并机械校验（Agent 标签 -> 数据集）
..\.venv\Scripts\python.exe -m tools.build_ai_labeled_dataset `
  --batch ..\data\storage\labeling\labeled-batch1.json `
  --batch ..\data\storage\labeling\labeled-batch2.json `
  --batch ..\data\storage\labeling\labeled-batch3.json `
  --output data\evaluation\ai-labeled-licensed-v1.json

# 3) 评测（只读，拒绝覆盖已有报告）
..\.venv\Scripts\python.exe -m app.cli.evaluate_ai_labeled_tasks `
  --dataset data\evaluation\ai-labeled-licensed-v1.json `
  --output ..\data\storage\ai-labeled-v1-report.json
```

数据集 SHA-256 `72e22a2624d62a6a53c5c995bf1964de5e1e6e5468a6aa1e58a03882288436cb`
（组装时打印的构建哈希为 `3352e917…`，差异来自组装后按 task_id 排序与写入缩进，以 runner 读到的文件 SHA 为准）。

契约测试：`backend/tests/test_ai_labeled_tasks.py`（8 项，全部使用 `TEST-*` / `synthetic=true` 夹具，
并断言 runner 会拒绝声称人工复核、金标或质量声明的数据集）。

## 边界

- AI 标签不是人工金标；引用这些数字时必须同时说明 `label_source = ai_agent_review`。
- 题目源自被评测索引本身，分数偏乐观；不代表对独立提问的检索质量。
- 不可答题只有 9 道，可分性观察是线索而非阈值建议。
- 语言为英文、语料为 9 篇、无跨语言与跨领域泛化证据。
- **数据集**：未经人工核验，不得作为"高质量检索系统"的证明。
