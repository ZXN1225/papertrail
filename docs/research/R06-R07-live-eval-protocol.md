# R06/R07：真实模型小样本对照预注册草案

**2026-10-13 实际运行状态：** 用户批准的修复后独立六题三臂运行已完成 18/18 arm、48/48 调用，本地费用估算 USD 1.219042；机器结果与限制见 [修复后试运行结果](R06-R07-live-postfix-result.md)。8 个选定答案机械通过且用户核验其回答均获 PDF 支持；R4 旧引用缺标签/图注类型错误，已修复 parser 并建立新索引版本，原运行状态不追写。多 Agent 仅 R3 consensus，费用比已超建议启用门槛。以下历史预注册文字保留运行前冻结口径。

日期：2026-10-13。用户已授权三篇许可论文检索摘录发送 OpenAI `gpt-5.6-sol`，6 题、每题 1 次、首轮总上限 USD 2；后又授权**新增最多 USD 2**用于修订后同模型同题的有效 trial。五次六题试运行及其技术性缺陷见 [中止与修订记录](R06-R07-live-pilot-interruption.md)。第 5 次完成 R1–R5 的 15 个 arm，但无答案通过证据门禁，R6 未运行。用户另在 USD 0.50 总上限内先后授权两组各最多两次 R1 调用：第一组定位全文证据字段和原文换行错误；第二组输出符合证据要求，但适配器将两份相同完整 JSON 拼接导致原运行 `invalid_model_output`。适配器已修复，原报告离线回放机械通过，用户已确认该 R1 模型四层主张 `supported`；原运行状态不改。下一轮六题三臂固定对照已完成 dry-run，需新的费用/调用授权。当前没有可用于 Skills 或多 Agent 收益判断的完整六题配对结果。

## 2026-10-12 技术性中止后的约束修订

新运行每个 worker 最多调用一次指定 arXiv 源的本地 BM25 工具，检索后动态移除工具定义并要求输出答案或明确证据不足；每个 worker 最多两次模型请求。工具 schema 仅暴露该论文 ID、`arxiv` 与 `bm25`，与执行层一致；BM25 顺序及最多 8 项保持不变，响应仅返回引用所需的片段和定位，避免重复 parser 上下文占用费用。六题、单/Skills on/双 worker 三臂共最多 24 个 worker 和 48 次 provider 请求。上下文上限为 120k 字符、单 worker 观测 token 上限 20k、多 Agent 共享上限 40k、输出上限 600 tokens。模型、六题原文、来源范围、原人审标签均未变化。旧缺陷运行不作为可评分 trial 计入效果统计；新授权的 USD 2 是追加额度，与旧运行分账。若下一请求的本地保守预估超剩余 USD 1.10，立刻停机；真实生成答案仍需人工语义审阅。

## 已冻结输入

- 三篇逐篇确认 CC BY 4.0 的本机论文；[原始六题候选与 BM25 前 8 条记录](R01-R03-real-evidence-pilot-v1.json) SHA-256 `9ceb30530faff7fae5a6ea085479b6755d6277077211c306e6758cd52e2ae0e3`。
- [用户六题审阅记录](R01-R03-real-evidence-pilot-human-review-v1.json) SHA-256 `4b9ff6eef31968df19343c06407a01be4c5b17826b1c9dde3999696d58fd8f5d`；候选答案由助手拟写，3 条获 supported、3 条获 unsupported。原始候选 JSON 保持不变。
- [R07 任务清单](../../backend/data/evaluation/arxiv-r01-r03-human-pilot-taskset-v1.json) SHA-256 `9122147fa003be028a74c210e36e7df23d7bf49cd02e7e98f9ae4d480e658a0b`；符合现有配对评估 CLI 的真实任务 manifest schema，六题 ID 与来源逐一对应。清单不包含生成答案，也不使人审标签变成通用金标。
- 每题只使用原候选文件中的 `question`；给每个对照组相同的目标 arXiv ID，以与原 PDF 核验范围一致。目标 ID 只是检索过滤条件，不提供预期答案、正确数值或用户标签。每个模型运行使用全新、独立的上下文和本轮工具观察。

## 比较组与运行顺序

1. **单 Agent / Skills 关闭**：`AgentHarness(skills_enabled=False)`，固定只读工具白名单、BM25、同一模型和预算。
2. **单 Agent / Skills 开启**：`AgentHarness(skills_enabled=True)`，除 Skill 指导和其允许的工具交集外，其他条件与第 1 组一致。
3. **双 worker 多 Agent**：调用默认不接入生产路径的 `MultiAgentExperiment`，顺序运行两个与第 2 组相同模型/工具的 worker，共享预算；只有结构化 claims 和 citation IDs 完全一致才接受 consensus，冲突/不足分别计失败，不把其中最好的 worker 偷换为多 Agent 结果。

任务按 R1–R6 顺序配对；每题顺序为 Skills 关闭、Skills 开启、双 worker，多 Agent worker 顺序执行。六题一轮将执行 6 次 Skills 关闭、6 次 Skills 开启及至多 12 次多 Agent worker，共**至多 24 个 Harness 运行**。修订后每个 Harness 最多 2 个模型步骤，故最多 48 次 provider 调用；实际可能更少。任何上限触发都保留已运行项并标为未完成，不删除失败题或补配对结果。

## 评分与报告

- 新试验生成后，运行 `python -m app.cli.prepare_live_review` 从固定本机报告生成一次性 `backend/reports/live_eval/gpt-5.6-sol-r01-r03-postfix-review.json`。它绑定报告 SHA，按题/arm 列出答案、claim、citation locator 与多 Agent worker 状态；`human_review` 字段保持 `null`。文件包含模型生成内容和许可摘录，必须继续留在 Git 忽略目录。审阅者逐题核对 PDF 后另存人工标签记录；不能把该模板当作已完成的人审或自动成功率。
- 按用户对原 PDF 的六题核验给出每题预期事实：R1 四层 Data/Indexing/Retrieval/Generation；R2 不执行控制操作；R3 488 nm 与 150 nm SiN；R4 (d) 70 nm、(e) 220 nm a-Si:H；R5 strict vital recall 70.3%、hallucination rate 8.7%；R6 NDCG@10 最高是 Hybrid RAG 73.6%。这些事实只用于**运行后的人工评分**，不注入模型上下文。
- 每条模型回答独立标注：任务正确/部分/错误/拒答、每条事实主张的原文支持、引用定位有效性、数值与对象绑定、工具/许可/安全违规。只看引用格式或机械 Harness 通过不能推断语义正确；同一用户的原六题候选标签也不能代替对新生成回答的人审。
- 主报告按题先聚合重复 trial，再汇总任务成功率、错误/拒答、证据有效率、token、估算费用、延迟及失败率；单/多 Agent 严格同题同 trial 配对，报告各题差值与不确定性。六题均可答，不报告不可答题拒答率。六题规模只支持探索性描述，不宣称统计显著或普遍收益。
- R1、R4 在冻结的只读 BM25 诊断中未检出**指定直接证据 chunk**；真实模型即使给出正确答案，也要分别记录它实际调用工具取回的来源，不能回填为该次 BM25 命中。

## 调用与数据边界

- 当前产品仅实现 OpenAI Responses。用户已明确批准本次 `gpt-5.6-sol`/6 题/1 次/USD 2 及摘录外发；运行器只接受该模型和不高于 USD 2 的总额，不能自动替换模型。OpenAI 官方 [模型页](https://developers.openai.com/api/docs/models/gpt-5.6-sol) 与 [价格页](https://developers.openai.com/api/docs/pricing) 当前列明标准短上下文输入 $4/百万 tokens、输出 $20/百万 tokens；保守守卫按长上下文输入 $8、输出 $30/百万 tokens 计。密钥只放本机根 `.env` 的 `LLM_API_KEY`，不在聊天中发送，也不写报告。
- 实验驱动仅可使用本机只读 `PaperStore` 和固定 Agent 工具，不开启联网 arXiv/OpenAlex 或任意 URL、shell、SQL、自由写库；embedding 保持关闭。输入论文 SHA/索引 SHA、问题、模型/配置、Skill SHA、检索结果与每次用量需随运行记录绑定。生成正文和论文摘录只保存在 Git 忽略的本机报告目录，提交材料仅含脱敏汇总。
- 已实现 `python -m app.cli.run_live_eval`：默认只做冻结 SHA、许可与当前 index 的只读预检；live 需同时给 `--execute --confirm-licensed-excerpts`。它只暴露单篇 arXiv 范围的 BM25 证据工具，不开放网络搜索或 embedding。每次模型调用返回后记录 token/费用估计；每个 arm 写入 Git 忽略目录 `backend/reports/live_eval/`，并拒绝同一报告路径二次付费执行。`TEST-*`/`synthetic=true` 合成守卫测试与本机 dry-run 已通过；加入离线审阅包工具后的当前完整后端回归 **248 passed、1 warning**。后续报告还记录模型校验前结构化输出供本地失败分析，旧报告不追写。现有 `evaluate_multi_agent` CLI 仍只对外部审阅后的 paired observations 汇总，**不会发起模型调用**，真实生成输出不能自动转成“成功”。
- 每轮 API 调用只能在用量返回后得到准确 token；任何本地美元预估不能保证 provider 最终账单严格不越过一个正在执行的请求。获准运行时需先依据已确认模型的官方价格设定保守单次调用上界；若下一次调用的保守上界将超预算，就停止，不启动该请求。模型价格、计费方式、配置及停止阈值应在运行前冻结并记录。

## 当前人工门槛

修复后六题运行及 [A–E 五组 PDF 人审](R06-R07-postfix-human-review-v1.json)已完成，48 次调用授权全部用尽。下一个人工步骤是最终项目验收；如要扩大真实模型样本或重新跑修复后的索引，必须另行确认题数、模型、调用数和费用上限。费用是本地估算而非服务商账单硬上限；前述 R1/R4 冻结检索漏命中与有限样本限制保留。
