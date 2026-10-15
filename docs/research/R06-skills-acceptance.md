# R06：产品运行时 Skills 验收

**2026-10-13 最新结果：** 修复后同题真实运行已完成。Skills 关闭/开启各 6 项、各 12 次模型请求；机器门禁分别 3/6、4/6 项 `completed`，本地费用估算分别 USD 0.284490、0.308938。用户已按 PDF 核验这 7 个单 Agent 选定答案均获原文支持，但 Skills 关闭的 R4 旧引用缺 `(d)` 且图注类型误标；严格计入引用有效时为 2/6 vs 4/6。单轮小样本不能证明 Skills 一般收益。详见 [修复后试运行结果](R06-R07-live-postfix-result.md)；以下为此前阶段状态。

2026-10-13 最新状态：用户已授权 `gpt-5.6-sol` 六题各一次的 Skills on/off 与多 Agent 对照，首次 USD 2、技术修订后追加最多 USD 2。本机五次受限试运行中，第 5 次 R1–R5 两个单 Agent 臂答案均被 `unverified_evidence` 拒绝，R6 未运行。另在最多 USD 0.50 总上限内两组 R1 诊断共四次模型请求，先定位字段/换行错误，再定位重复完整 JSON 的适配器错误；适配器已修复，第二组原报告离线回放机械通过，用户确认该 R1 模型主张 `supported`，但不能代替原运行状态或 Skills 对照。下一轮六题三臂 dry-run 已通过，付费执行需新授权。见 [预注册协议](R06-R07-live-eval-protocol.md) 和 [试运行事件记录](R06-R07-live-pilot-interruption.md)。下文早期“未调用真实模型”是当时阶段快照。

日期：2026-10-11。当前验收的是确定性选择和权限契约，不是模型效果提升。

## 实现

- 提供 `paper-qa`、`compare-papers`、`research-brief` 三个产品任务 Skills。
- 固定 registry 记录版本与正文 SHA-256；正文漂移会被拒绝，避免未经审阅的技能指令静默改变。
- Skill 只能提供任务指导。模型可见工具定义及实际执行工具都受既有工具 registry、白名单和 Skill 建议集合交集约束。
- `AgentHarness(skills_enabled=True|False)` 提供同题对照开关，默认保持启用；关闭时使用同一系统规则与完整固定工具 registry，不放宽工具权限或 citation/evidence gate。该开关尚未暴露到生产 API。

## 自动验收

- 测试覆盖 Skill 选择、hash 完整性、正文漂移拒绝，以及 Skills 不得绕过工具白名单。
- 新增 TEST 同题双运行契约：使用相同问题和相同模型输出，比较 Skills 开/关的终答、证据、引用与工具调用；Skill 版本元数据只在开启组出现。定向测试通过。
- 本轮全后端回归 184 passed，1 个 Starlette/AnyIO 上游弃用 warning；本地 mock 测试不构成真实模型效果评估。
- 不调用真实模型；当前相同结果是固定 mock 输出下的 harness contract，不代表 Skills 开/关效果；没有准确率或成本收益声明。

## 后续可选评测

若要评估 Skills 是否改进实际答案，应使用获准语料、人工核验的任务和相同模型/预算，预先固定评分准则，并同时报告质量、拒答、安全违规、token 与耗时。不得用合成契约测试替代此评测。
