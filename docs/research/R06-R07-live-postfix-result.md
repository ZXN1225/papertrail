# R06/R07 修复后六题真实试运行：机械结果与单人 PDF 人审

日期：2026-10-13。协议：[六题三臂预注册](R06-R07-live-eval-protocol.md)。用户明确批准 `gpt-5.6-sol`、三篇 CC BY 4.0 论文、六题各一次、Skills 关闭/开启/双 worker 三臂，最多 48 次 provider 请求，新增本地保守费用守卫 USD 2。此次只运行固定 `--post-fix-six-task` 一次；运行前许可/当前全文索引/冻结输入 SHA 预检通过。

原始报告在 Git 忽略的 `backend/reports/live_eval/gpt-5.6-sol-r01-r03-postfix-6x1.json`，SHA-256 `3e60cdfdcda8068348f04eb2c4a95d53226a68818484fb23302fad822042d5f2`。**18/18 arm、48/48 请求完成，无停机**；本地费用估算 USD **1.219042**，不是服务商最终账单。授权的 48 次调用已全部使用，不因估算金额低于上限而追加请求。原有诊断和旧六题报告均未覆盖。

| 题目 | Skills 关闭 | Skills 开启 | 双 worker 多 Agent |
| --- | --- | --- | --- |
| R1 | `insufficient_evidence` | `completed` | `conflict` |
| R2 | `completed` | `completed` | `conflict` |
| R3 | `completed` | `completed` | `consensus` |
| R4 | `completed` | `unverified_evidence` | `insufficient_workers` |
| R5 | `unverified_evidence` | `unverified_evidence` | `insufficient_workers` |
| R6 | `unverified_evidence` | `completed` | `insufficient_workers` |

`completed` 仅表示结构化格式、当前检索来源、逐字 quote、chunk 与有限数字/单位/条件规则通过；`consensus` 还要求双 worker 的 claim 文本和 citation IDs 完全相同。它们**不是语义正确或 PDF 人工支持标签**。多 Agent R1/R2 两个 worker 各自通过机械门禁，措辞不同导致精确 consensus 为 `conflict`；不把它们改算为多 Agent 成功。R4 的一个 quote 没带 `(d)` 标签，R5/R6 的表格数据行 quote 没带表头列义，说明本轮部分拒绝源自保守证据门禁；不改写原运行状态。R1/R4 冻结 BM25 指定直接 chunk 漏命中记录仍保留，不能以本轮生成答案回填旧检索指标。

| Arm | 请求数 | 输入 tokens | 输出 tokens | 本地费用估算 USD |
| --- | ---: | ---: | ---: | ---: |
| Skills 关闭 | 12 | 28,380 | 1,915 | 0.284490 |
| Skills 开启 | 12 | 31,421 | 1,919 | 0.308938 |
| 双 worker 多 Agent | 24 | 63,108 | 4,025 | 0.625614 |

多 Agent / Skills 关闭的本地费用估算比约 **2.20**，已高于路线图建议的 **≤1.5 倍**启用门槛；多 Agent 仍不接入生产路径。六题一次只提供探索性观察，不足以证明或否定一般质量收益。Skills on/off 的机械通过数不能在语义人审前解释为质量提升。

一次性本机 [原 JSON 人审包](../../backend/reports/live_eval/gpt-5.6-sol-r01-r03-postfix-review.json) SHA-256 `c05ed5a3ea5b8301d0ec3f09a3db442f99a35458ddf6e6bb255a99e637f1f8b2` 保持不变。用户随后逐组核验 [A–E 五组 PDF 清单](../../backend/reports/live_eval/gpt-5.6-sol-r01-r03-postfix-human-check.md)：五组答案均为 `supported`，对应 8 个机器选定答案；其余 10 个 arm 没有被人工判成正确或错误。标签与限制另存无模型正文的 [机器可读记录](R06-R07-postfix-human-review-v1.json)，已填写的本机忽略副本 SHA-256 `a100664a64698c260461713b50b2ffa4fc3cb3810aefdcdacdbbf486b8a78a49`。此前单独 R1 的人审标签没有继承给本次运行。

| 组 | 运行项 | PDF 回答支持 | 引用核验与限制 |
| --- | --- | --- | --- |
| A | R1 Skills 开启 | supported | 第 3 页四层及顺序一致。 |
| B | R2 Skills 关闭、开启 | supported | 第 2 页明确为决策支持，不执行控制操作。 |
| C | R3 三臂 | supported | 第 9 页 Figure 5(a) 的 488 nm / 150 nm SiN 对应正确。 |
| D | R4 Skills 关闭 | supported | **旧引用不合格**：quote 缺少前行 `(d) Transition`，旧解析器将图注续行误标为 `paragraph`。回答事实获 PDF 支持，不能把旧引用改记为完整。 |
| E | R6 Skills 开启 | supported | 第 10 页 Table III 全列最高为 Hybrid RAG 73.6%，第 11 页段落亦支持；摘录为解析器文本的逐字子串，未证明与视觉 PDF 的空格、换行严格同形。 |

独立只读 SQLite 校验了这 8 个引用的**旧快照内部定位**：每个 chunk 存在，元素半开字符范围与存储摘录一致，quote 在该摘录内，返回 locator 与存储值一致。它不验证 PDF 像素排版；D 的语义类型错误依旧成立。按“机器选定且用户确认答案支持”计，本次为 Skills 关闭 3/6、开启 4/6、多 Agent 1/6；若还要求旧引用的图注类型/标签完整，Skills 关闭仅 2/6。R5 各臂没有机器选定答案，不能把未经人工审核的原始生成文本判错。六题一次、无盲法或第二审阅者，不具备一般化收益证明；多 Agent 成本比 2.20 且仅一题 consensus，维持生产默认关闭。

用户反馈驱动的 parser v14 修复了 Figure 5 跨行图注：第 9 页完整 `(d)`/70 nm 与 `(e)`/220 nm 现在同属一个 `figure_caption`，bbox 为 `[72.0,666.27,523.26,759.92]`。合成跨行及双栏顺序回归通过；旧运行/旧索引版本不追写。已用原许可 manifest 本机重新导入该论文，当前版本 SHA-256 `f6d9bcbf4bc7e88aba296103255c8f5463bbe3ad424ac77fdb0e887855f3f5a3`、315 chunks；同一 R4 问题的只读 BM25 前 8 条中，完整图注为**第 1 条**。这是修复后新索引的检索 smoke，不能回填冻结旧版 R4 的指定直接 chunk 漏命中，也没有重跑付费模型。

本阶段不提交 PDF/全文、原始模型报告、JSON 人审包或 A–E 原文核验清单；仅本文件保留无生成正文的汇总和本机工件 SHA。
