# P36 盲审候选池：准备与人工复核

## 目标与范围

P14/P17 在同一冻结 P13 题集上比较五种排序配置，但相关性标签来自未核验的 AI 建议。本阶段先从方法排名中构造规模受控、隐藏单篇来源方法的候选池，交由人工逐项判断；完成复核后再实施导入和基于该盲审集的排序评测。候选池按旧 AI 标签上的方法分歧挑选，因此是困难案例集，不能估计一般用户查询的总体检索表现。

## 候选池规则

- 从 P14/P17 的 30 个查询中，按 P14 `NDCG@10` 方法分歧从高到低选取查询；相同分歧按 query ID 排序，每个意图桶最多选 1 个，默认 8 个。
- 取 BM25、Small Dense、Small Hybrid、Large Dense、Large Hybrid 各自前 5 篇的并集；同一查询—论文组合只复核一次，默认上限 200 项。
- 审核 CSV 只包含问题、意图桶、论文元数据、来源链接和空白评分；不包含排序器名称、名次、AI 建议评分。映射保存在单独的本机忽略审计文件，不应与盲审 CSV 一起提供给评审者。
- 0=不相关，1=背景或部分相关，2=直接相关，3=高度相关。每项需将 `reviewed` 改为 `true`；没有完成审核的项目仍是未知，不能解释为 0。

## 本机生成记录

```powershell
cd backend
uv run --locked python -m app.cli.prepare_p36_review
```

默认输出均位于 Git 忽略的 `backend/reports/`：

- `p36-blind-review.csv`：供人工填写的盲审表格；建议用 Excel 打开并另存为 `p36-blind-review-completed.csv`，不要覆盖原始文件。
- `p36-blind-review-pack.json`：同一盲审数据的机器可读副本。
- `p36-blind-review-audit.json`：数据和报告哈希、抽样查询及排序来源映射，仅供本地审计。

默认题集选择 8 个意图桶查询，排序器各取前 5 名；每查询候选取并集去重。本次候选池实际为 101 个 query-paper pairs，低于 200 上限。完成审核后用以下命令校验 CSV 并生成只对盲审池计分的本地报告：

```powershell
cd backend
uv run --locked python -m app.cli.evaluate_p36_review --confirm-human-review --reviewer me
```

报告写入 Git 忽略的 `backend/reports/p36-human-reviewed-pool-report.json`；不覆盖盲审表或来源报告。

## 当前状态

- [x] 仅从匹配的数据集哈希、P14/P17 报告与 P13 冻结语料元数据构建候选池。
- [x] 查询按意图桶分层，候选去重，项目数硬限制为 200。
- [x] 评审视图隐藏单篇候选的排序来源、名次和 AI 建议等级；审计映射单独保存。
- [x] 盲审池逻辑、CSV 导入和评测合计 12 项定向测试通过；本机生成 8 个查询、101 个候选项。
- [x] 用户完成 101 项审核；导入校验覆盖字段、完整性、评分范围、审核标记、row ID 和来源元数据。
- [x] 生成仅对池内候选排序、切点为 @1/@3/@5 的方法对照报告；未进入池内的论文保持未判断状态。
- [x] 全量后端测试 `130 passed`，Ruff check/format、Web 格式检查和 `git diff --check` 通过。

本阶段的标注由人工完成。LLM-as-judge 若后续采用，须先与该盲审样本对照并报告一致性，不能取代人工判断或被描述为人工金标。

## 本机盲审结果（2026-09-25）

人工分级分布：0 分 20 项，1 分 27 项，2 分 19 项，3 分 35 项。只在每个查询的盲审候选池内评分；方法排名限于各自生成池的 top-5，不计算全语料 Recall。完整确定性汇总报告位于 Git 忽略的 `backend/reports/p36-human-reviewed-pool-report.json`，审核 CSV 与排序来源审计文件也保留在同一忽略目录。

| 排序方法 | MRR@5 | NDCG@5 | 相对 BM25 的 NDCG@5 差值 |
| -------- | -----: | ------: | -----------------------: |
| BM25 | 0.8750 | 0.5444 | — |
| Small Dense | 0.9063 | 0.7251 | +0.1807 |
| Small Hybrid RRF@60 | 0.9167 | 0.7171 | +0.1728 |
| Large Dense | 1.0000 | 0.8856 | +0.3412 |
| Large Hybrid RRF@60 | 0.9063 | 0.8027 | +0.2583 |

Large Dense 在此盲审挑战集中分数最高，但这不是一般质量提升结论：只评了 8 个查询，查询由旧 AI 标签上的方法分歧挑选，候选来自五种方法前五名并集，且只有一位评审。分数只用于定位这些困难问题上的排序差异，不替代跨主题、随机抽样或多评审评估。P36 报告设置 `exploratory_only=true` 和 `quality_claim_allowed=false`。

CSV 由 Excel 以 Windows-936 编码保存。导入器核对到 5 个摘要字段存在可复现的 codepage 转换（8 个不可表示字符及 1 个上标数字变换），并将其记录在报告的 `human_review.csv_encoding`；除此之外的元数据变动会拒绝导入。
