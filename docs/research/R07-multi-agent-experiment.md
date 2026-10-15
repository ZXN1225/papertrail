# R07：Multi-agent 实验框架验收

**2026-10-13 最新结果：** 修复后六题双 worker 臂全部运行，24 次模型请求：R3 `consensus` 且该答案经用户核对 PDF 获 `supported`；R1/R2 `conflict`，R4/R5/R6 `insufficient_workers`。本地多 Agent/Skills 关闭费用估算比约 2.20，超出路线图建议的 ≤1.5 倍启用门槛；框架继续不接入生产。其余多 Agent 最终项无人工支持标签，不能把 worker 个体答案偷换成成功。详见 [修复后试运行结果](R06-R07-live-postfix-result.md)；以下为此前阶段状态。

2026-10-13 最新状态：用户已完成三篇许可 PDF 六题单人核验，并先后授权 `gpt-5.6-sol` 六题三臂对照的 USD 2 + 最多 USD 2。本机五次真实模型尝试中，第 5 次完成 R1–R5 多 Agent 臂，但均为 `insufficient_workers`；R6 未运行。随后在同一最多 USD 0.50 总上限内两组 R1 单 Agent 诊断共四次请求，定位并修复输出字段/换行与重复完整 JSON 问题；用户已确认单 Agent R1 四层主张 `supported`，尚无修订后的真实多 Agent 对照。独立六题三臂 dry-run 已通过，新的付费试验需明确授权。没有有效的六题配对收益结论。旧段落中“未调用真实模型/待许可题集/待模型预算”均是此前阶段快照。详见 [live 协议](R06-R07-live-eval-protocol.md)、[试运行事件记录](R06-R07-live-pilot-interruption.md) 与 [六题结果](R01-R03-real-evidence-pilot-result.md)。

更新：2026-10-12。用户选择先实现默认禁用框架；三篇新增许可 PDF 已在本机索引，六题候选待人审。真实收益验收还需冻结经人工核验的任务，并由用户明确 provider/模型、题数、重复次数与费用上限。

## 框架边界

- `MultiAgentExperiment` 当前不接入生产 `/api/v1/agent/ask`，不自动增加调用或费用。
- 顺序执行，worker 数量硬上限为 3；共享观测 token、tool-call、deadline 和取消预算，每个后续 worker 收到剩余预算。
- 至少两名成功 worker 的结构化 claims 与 citation IDs 完全相同时才返回 consensus。若结论冲突，不拼接或重写成综合答案。
- 输出保留每个 worker 的状态，便于比较与归因。框架继承主 Harness 的工具白名单与引用契约。

## 配对评测器

新增 `app.evaluation.multi_agent.evaluate_paired_runs` 与 `python -m app.cli.evaluate_multi_agent`，接收预先冻结的 task 数据集 SHA、同一 task 的单 Agent/多 Agent 结果和每题重复 trial。输入按 `{task_id, trial, arm}` 唯一标识，两个 arm 必须有完全匹配的题目与 trial；少一侧、重复行或非法数值都会失败，不会自动丢题。

- 重复 trial 先在每道题内部取成功率，再按题目等权计算总体差值；同时报告每题结果、evidence-valid 比例、安全违规数、token、成本、平均延迟及 multi/single 总成本比。
- 对逐题成功率差值给出固定 seed 的 paired-task percentile bootstrap 95% 区间。区间是描述性不确定度信息，不代表小样本具有统计显著性。
- CLI 必须同时传入冻结任务清单和 trial 输入；它会读取清单原始字节并核验 SHA-256、数据 synthetic 状态，以及观测 task ID 与任务清单的精确集合相等。任务清单要求严格字段、唯一任务 ID；合成数据集/任务 ID 必须使用 `TEST-*` 且逐项 `synthetic=true`，真实数据集/任务不得使用 `TEST-*`，并且每道真实任务至少关联一个非空来源引用。
- 报告绑定已核验的任务清单 SHA 和 trial 输入 SHA。`label_source` 与 review SHA 是调用者声明，报告明确标作 `*_declared`；评估器不会验证许可证或人审内容，也不会授予质量声明权限，因此 `quality_claim_allowed` 固定为 false。真实数据结果仍需独立人工复核后才能形成项目层面的质量结论。
- 演示输入：`backend/data/evaluation/TEST-multi-agent-paired-v1.json`。本地运行：

```powershell
cd backend
uv run --locked python -m app.cli.evaluate_multi_agent `
  --input data/evaluation/TEST-multi-agent-paired-v1.json `
  --dataset data/evaluation/TEST-multi-agent-taskset-v1.json `
  --output reports/TEST-multi-agent-paired-report.json
```

演示使用手写 TEST 结果，不调用模型，不构成收益或质量证据。许可语料现已有四篇本机 PDF；真实评测仍须人工逐题 outcome/evidence/safety 标签，并经用户确认模型、题数、重复次数和费用上限。新增六题候选见 [R01/R03 核验包](R01-R03-real-evidence-pilot-review.md)。

2026-10-11 在当前工作树重新运行演示 CLI：冻结任务清单 hash 校验通过，清单 2 题、每臂 2 次 trial；合成样例汇总为 single-agent success `0.00`、multi-agent `0.75`、任务级差值 `+0.75`、配对 bootstrap 区间 `[0.50, 1.00]`、成本比 `1.40`，evidence-valid 均为 `1.00`、安全违规均为 `0`。这只是脚手架输入的预置结果，不是 Agent 实际执行；报告在 Git 忽略目录 `backend/reports/audit-multi-agent.json`，并仍明确 `quality_claim_allowed=false`。

## 自动验收

- 8 个 synthetic 协调器测试覆盖 consensus、分歧、共享预算耗尽、递减预算、取消、worker 数量硬上限、worker 异常隔离与 trace 分项用量防低报；配对评测器现有 8 个测试。
- 配对评测器测试覆盖按题聚合、重复运行、不确定度可复现、成本比、安全与 evidence 指标、未配对失败、synthetic 标签门禁、冻结清单 SHA 校验及 task ID 精确匹配；固定 TEST 输入可由 CLI 生成本机 JSON 报告。
- R07 阶段验收时：配对评估定向测试 `8 passed`；协调器另有 `8` 项 synthetic 契约测试。该阶段全后端 `195 passed, 1` 个 Starlette/AnyIO 弃用 warning；Ruff check/format 通过；TEST CLI smoke 成功且报告核验 manifest SHA、关闭质量声明。合成数据仅验证实现控制流和统计管线，不是质量标签或论文质量证明；后续全项目补强结果见 R08 验收记录。
- 没有真实任务集、真实模型或付费调用；没有单 Agent / 多 Agent 的准确率、拒答率、费用、延迟对照。故当前不建议接入产品默认路径。

## 真实收益验收门槛

已取得四篇逐篇许可的本机 PDF，六题新候选尚需人工标注。用户明确模型、任务题数、重复次数与费用上限后，固定同题单 Agent baseline，逐题追踪 citation/evidence，预先设定成功标准，同时报告安全违规、拒答、token、费用、延迟与失败率。样本量不足时仅报告描述性差异，不宣称统计显著。
