# PaperTrail 论文助手 Agent Harness 架构

## 2026-11-11 文档身份与有限上下文

- 根据当前账号的已索引文档标题或编号解析唯一目标；本地单篇任务由工具层限定该来源，多个候选时询问。最近 40 个用户问题仅用于连续指代解析，模型上下文仍为最近 4 轮；这是规则窗口，不是经过验证的上下文摘要或完整会话状态。
- 明确同时请求论文库与公开检索时，联合任务要求本地全文检索和指定公开搜索。本地与公开来源的事实证据要求不同，缺少本地全文证据不报告完整成功。真实混合来源测试目前尚未达到稳定完成。

## 2026-11-10 指定公开来源搜索

- 明确要求搜索 OpenAlex 或 arXiv 的独立任务只开放相应来源的搜索工具，分别要求完成搜索；空结果和上游故障保留状态，部分结果明确提示未覆盖的来源。最后一轮预留给无工具的回答，引用仍须通过本轮来源和原文元数据校验。
- 搜索意图识别仍采用规则，不是通用语义路由器；单次成功不能代表所有混合意图和网络异常都已解决。引用校验不保证论文与问题语义相关，也不验证研究结论。

## 2026-11-10 混合来源任务补充

- 本次参考 [OpenAI Harness 工程](https://openai.com/index/harness-engineering/) 对工具、上下文和反馈循环的说明，以及 [LangChain Harness Profiles](https://docs.langchain.com/oss/python/deepagents/profiles) 关于按运行配置控制工具可见性的设计。项目继续使用现有 Harness，未引入新框架。
- 任务路由仍以可审计的规则为主，并非通用语义分类器或工具相关性打分。针对论文库加个人稿件的写作请求，新增混合来源任务：默认只允许全文检索，并由服务端区分账号关联的论文库 PDF 与个人稿件。仅在请求明确联网时增加公开检索工具。
- 上下文可用于识别追问、理解写作目标和选择检索方向，不作为本轮证据。混合任务要求本轮实际引用账号内个人稿件和论文库的私有全文块；明确要求两篇时至少需要两篇不同论文。公开元数据不能满足本地论文库证据要求；缺失任一来源时明确返回证据不足。
- 工具 trace 区分 no_results 和 ok；任务 ID、注册版本、工具白名单和是否明确联网可供审计。引用检验保证来源、块、精确摘录及部分数字/方向约束；不证明建议与摘录之间存在语义蕴含。
- 当前路由依然可能遇到未覆盖的自然语言表达；本次真实用户问题的一次完成不代表广泛质量保证。后续应增加涵盖多来源、话题切换、联网意图和证据不足的评测集，并评估模型规划和工具相关性排序的准确率、成本与权限边界。

更新日期：2026-11-09

## 目标与结论

PaperTrail 已有受限的单 Agent 工具循环、论文来源白名单、用户隔离检索、Skill hash 校验、运行预算和逐 claim 引用校验。当前问题不是缺一个大型 Agent 框架，而是这些能力没有被组织成任务级工作流，且运行管理仍主要依赖单进程内存。

继续保留现有 `AgentHarness` 作为执行内核。目标结构是能力层、连接层、构建层、运行管理层，各层通过稳定契约协作。生产默认单 Agent；多 Agent 只用于离线对照，在得到稳定的质量收益且成本可接受前不进入产品路径。

## 设计原则

1. 先用固定工作流完成高频科研任务，再允许有预算的有限规划；Agent 不拥有任意执行权限。
2. 模型输出是候选内容。来源、引用、授权、owner scope、费用和 run 状态由服务端校验。
3. Skills 只影响任务方法、输出格式和工具建议，不改变执行权限。
4. 私有论文、用户问题和摘录默认不写入第三方 tracing；run 记录只存复现所需的版本、ID、哈希、状态和用量。
5. “token 守卫”与“账单硬上限”分开表述。无法在请求前得知真实 provider 用量时，不承诺绝对费用上限。
6. 重启恢复默认不重放模型或外部 API 请求；仅在幂等且有明确 checkpoint 的本地步骤可继续。

## 分层架构

| 层 | 职责 | PaperTrail 组件/契约 | 不变量 |
|---|---|---|---|
| 能力层 | 表达用户要完成的科研工作 | `TaskSpec`：`paper_qa`、`compare_papers`、`research_brief`、`draft_revision`、`citation_check`；现有内置 Skills 给出任务指引 | 每种能力定义输入、所需来源、证据策略、输出 schema、拒答条件；Skill 不授予权限 |
| 连接层 | 连接模型、文献来源、共享/个人索引 | `ModelClient`、OpenAlex/arXiv clients、`PaperToolRegistry`、`PrivateDocumentService`、embedding client | 固定 host、严格参数、超时和重试边界、owner scope；所有文档内容均视作不可信输入 |
| 构建层 | 将任务组装为有界检索/证据/写作工作流 | `WorkflowPlan` + `WorkflowStep`：search → retrieve → organize claims → validate → render；不确定时最多有限补检索 | 每步产物有 schema 和预算；写作阶段只能使用已验证的 claims；最终引用经过服务端重建 |
| 运行管理层 | 预算、生命周期、取消、恢复、审计 | `RunManager`、SQLite run ledger、budget ledger、worker lease、脱敏 trace、request idempotency | 每个 run 有唯一 owner 和状态迁移；取消可持久化；失败不伪装成成功；私有正文不进入 trace |

### 能力层

Skill 是任务级提示和约束，不是 agent 自治插件。Skill registry 继续 pin 版本与内容 SHA-256。新增能力先定义 `TaskSpec`，例如：

```text
task_id: draft_revision
inputs: draft_text, user_library_ids, revision_goal
workflow: retrieve_related_evidence? -> revise -> claim_check -> render
outputs: revised_text, change_summary, evidence_claims[], unsupported_changes[]
```

文稿修改可按“语言编辑”和“事实性改动”分别输出。只有引用核验成功的事实性改动才附论文依据；没有证据的润色不冒充论文结论。系统不把文稿改写结果自动写回用户文件。

### 连接层

保留已实现的适配器接口，不把 OpenAI 或某家 Agent SDK 作为领域接口。每个 adapter 返回规范化的 `ProviderResult`：结果、请求 ID、输入/输出用量（若供应商提供）、延迟、可重试分类和错误码。连接器固定 HTTPS host、deadline、并发和最多一次安全重试；论文搜索只读。

工具执行授权取以下集合的交集：本次已注册工具、当前用户/匿名身份允许集合、TaskSpec 允许集合、Skill 建议集合。Skill 建议不能扩大工具集合。owner id 必须从认证上下文注入，不能由模型参数传入。

### 构建层

默认工作流是 PaperQA2 式的窄环：候选检索、证据收集、答案组织；确定性模式可省去额外 agent 规划步骤。需要补证据时，Harness 允许模型在固定工具集内做有限查询改写，但每次补检索消耗同一 run 预算。

推荐阶段契约：

1. `Plan`: 从 TaskSpec 生成结构化、有界的检索目标；简单查询可直接使用原问题。
2. `Retrieve`: 调用本地 BM25/已配置来源工具，记录 source ID、chunk ID、页码/定位符和 evidence SHA。
3. `Claims`: 输出原子 claim 候选，每条绑定 observed evidence；书目 metadata 与全文发现分开。
4. `Validate`: 精确核验 quote、来源/owner、许可证属性、chunk 归属、claim 与 answer 拼接；拒绝无依据或格式不合约的条目。
5. `Render`: 只渲染验证通过的 claims，并附来源、页码和未解决缺口。

外部论文内文本可能含提示注入，只作为 evidence 字符串，不执行其中命令。`compare_papers` 和固定字段抽取优先后端确定性处理，模型只负责解释。

### 运行管理层

目标状态机：

```text
accepted -> executing -> completed
                  -> failed
                  -> cancel_requested -> cancelled
                  -> interrupted
```

`interrupted` 不自动重放已发出的模型/API 请求。当前 run ledger 记录 owner、问题/历史哈希、阶段、取消标记、worker ID、短期 lease、token 上限/预留/实际 usage、耗时和脱敏 trace；完成时另记录 task/skill/model/prompt/parser/chunker 版本。可选的账号级 UTC 创建日 token 预算已实现，默认关闭。禁止存原始问题、完整私有摘录、密钥或自由工具参数。

预算由 `BudgetLedger` 管理：请求前按模型 tokenizer（可用时）或保守字节上界预留输入，给输出留上限；embedding、模型调用、重试均从同一 run 预算扣减。请求后用 provider usage 对账，超出时停止后续调用并标记 `budget_exceeded`。预留只能限制应用继续发请求，不能追回已经发生的单次 provider 费用。若要账单硬限制，必须另有 provider 侧 project budget/quota 或预付费代理。

SQLite 单机阶段使用短事务抢占 run 和 `lease_expires_at`；worker 定期 heartbeat。重启时过期 lease 标记 `interrupted`，可提示用户重新开始。不可恢复模型调用中间态。只有具备持久化输入、确定性输出和幂等键的步骤（例如本地索引派生）才允许恢复。

Trace 默认本地脱敏记录，字段为 sequence、phase、tool/model 名、status、latency、usage、source/chunk ID 与错误码。第三方 trace exporter 默认关闭；开启前必须删去用户问题、论文摘录和私有 ID，并配置保留期与用户隔离策略。

## 当前实现评估

### 已有，可继续复用

- `backend/app/agent/harness.py`：单 Agent 有界循环、step/tool/context/deadline/token 限制、取消检查、工具结果清洗、最终 claim/citation 验证。
- `backend/app/agent/tools.py`：固定工具白名单、严格 Pydantic 参数、只读 OpenAlex/arXiv/本地检索；用户私有检索走 owner scope。
- `backend/app/agent/skills.py`：确定性 Skill 选择、hash pin、Skill 不能扩工具权限。
- `backend/app/agent/service.py`：模型、来源客户端、embedding 与 Harness wiring。
- `agent_runs` 数据表与 `/agent/runs/{id}`、`/cancel`：已持久化取消意图与阶段；worker 持有 30 秒 lease，每 5 秒续租。状态查询或取消请求遇到过期 lease 时才将 run 标为 interrupted/cancelled；不自动重放模型请求，不需要进程启动钩子。
- 用户会话单独存储；每轮历史有界且带哈希。会话 memory 和 Agent 执行 run 是不同对象。

### 主要差距

1. 输入 token 的保守上界不是 provider 精确 tokenizer；应用预算与 provider 自报都不是绝对费用硬上限。
2. 取消已跨进程持久化，worker 退出后的回收在查询/取消时惰性发生；尚无常驻队列或自动安全续跑。
3. Run ledger 创建时先记录 TaskSpec/Skill/model 与当前 PDF parser/chunker 版本；正常结束再补 prompt SHA 和用量。进程在首次 provider 请求前后终止，仍能追溯启动时的任务版本。模型请求不会自动重放。
4. 五类 Skills 已映射到 TaskSpec；部分任务阶段由必要工具门槛强制，其余阶段仍依赖同一 Harness 的工具/引用校验，不单独执行多个 task executor。
5. 评测候选集、本机复核包和严格登记协议已实现。250 页扫描样本的 18 页包只完成工具 smoke，没有调用外部模型；另从五篇获准私有处理的论文自动选 10 页并登记 17 条本机 AI 辅助视觉观察，全部标为 `ai_assisted_unverified`。观察只用于定位可复现的 caption 关联问题并驱动定向 parser 修复，没有准确率指标，也不能当作人工 gold。

## 实施阶段与验收

### H1：任务契约与流水线（小步）

- 定义 TaskSpec 和明确输出 schema，将现有 Skill metadata 接到任务类型；保持现有 harness/API 向后兼容。
- 先实现 `paper_qa` 与 `citation_check` 的 deterministic stages；随后 compare/research brief/draft revision。
- 已实现：`TaskSpec` 固定定义五种工作流；对比论文必须完成 `compare_papers`，研究简报必须完成来源搜索，引用核验必须先做证据检索。模型提前终答时 Harness 以 `workflow_incomplete` 拒绝；任务选择继续复用确定性 Skills 和只读工具交集。
- 验收：五种任务选择、必要工具阶段和提前终答拒绝均由无 provider 测试覆盖。工作流仍由同一 Harness 执行，不引入分散的 task executor。

### H2：持久运行管理

- 已实现：迁移增加 `phase`、`cancel_requested_at`、`worker_id`、`lease_expires_at`；取消请求按 owner 和 active 状态条件更新，worker heartbeat 每 5 秒续 30 秒 lease。
- API 的取消先持久化，再通知本机 event；run loop 每个模型/工具边界检查取消标记。
- 状态/取消 API 首次观察到过期 lease 时将 run 标为 interrupted 或 cancelled，不重放模型请求；用户可显式重试并生成新 run。
- 已验收：跨实例取消、真实子进程终止后由新 app 实例回收、lease 续租/过期、取消与恢复并发竞争、run owner 隔离、断连、重复 run ID；停止状态由单条条件更新原子决定。

### H3：预算和连接器弹性

- 统一 provider timeout/error taxonomy/retry policy；重试需幂等且纳入同一预算。
- 请求前按能力预留；请求后 usage 对账；缺失 usage 对收费型调用失败关闭。
- 验收：模型、embedding 同一预算；预算耗尽不再发下一调用；提供商超时/限流/usage 缺失均有明确状态。
- 已实现：每个 run 持久保存 token 上限；模型/embedding 前记录保守预留，返回后对账 actual，并逐调用写入脱敏 trace/heartbeat。未知 provider usage 保留未结清 reservation；模型与 embedding 共用现有单 run token 上限。
- 已实现：run 创建时保存 TaskSpec/Skill registry 与 instructions SHA、workflow、模型 ID，以及 PDF parser adapter/chunker 版本；完成时补充 system+skill prompt SHA 与实际用量。run ledger 不保存问题/回答/论文摘录，interrupted run 也保留启动版本。
- 已实现：可选的每账号 UTC 创建日 token 限额；默认关闭，运维设置正整数后启用，准入检查覆盖并发活动 run 的 token 预算预留。
- 尚未实现：基于模型实时价目计算美元限额及 provider 侧账单硬上限。当前 token reservation 是应用防护，不是可保证的账单上限。

### H4：审计与评测闭环

- 记录脱敏工作流阶段 trace 和版本；完成从自动 MinerU 候选集到本地 AI 辅助复核的可复现 pipeline，标签注明 `ai_assisted_unverified`。
- 建立独立 holdout 任务评估检索、引用精确率/覆盖率、拒答、延迟、token 与失败状态；人工未审核的数据集不得标为 gold。
- 验收：同一输入与版本可复现结构指标；AI 辅助结论单独统计；隐私扫描确认 trace 无原文。

已实现的本机复核包包括候选 PDF 页图、对应 MinerU 元素/warnings、source/report/candidate/image SHA 和固定提示模板版本。提交登记会校验页码、当前页 element ID、parser/提示版本及所有 provenance SHA；schema 禁止附加 `gold` 等字段。输入图片和解析正文写入 `backend/reports/live_eval/mineru/` 忽略目录。250 页扫描卷的 18 页候选只用于 H4 工具 smoke；五篇许可论文另经自动选页后生成 10 页包并登记 17 项观察，均为 `ai_assisted_unverified`。复核触发的跨面板总图注与表标题关联规则已有定向 parser 修复和真实页重解析；无人工金标、无准确率结论。

MinerU 自动候选页命令：

```powershell
cd backend
uv run --locked python -m tools.build_mineru_review_set `
  .test-tmp/TEST-jama-pages-001-250.pdf `
  reports/live_eval/mineru/TEST-jama-pages-001-250-standard.json `
  --per-stratum 4 --seed 20261109
```

默认输出到忽略的 `reports/live_eval/mineru/`，只含 hash、页码、类型计数与 warning code；是 review candidate manifest，不是自动标注结果或 gold benchmark。

### H5：何时考虑多 Agent

维持 production 单 Agent。只有配对评测表明对指定任务有稳定质量提升，且 p95 延迟、provider 成本、冲突/引用错误均在预算内，才按 task 开实验性多 Agent。worker 必须共用 run cancel/deadline/token/tool budget，最终答案由同一服务端 validator 校验；worker 共识本身不是正确性证据。

## 外部设计参考

- PaperQA2 将研究问题拆为 paper search、evidence gathering、answer generation；同时提供硬编码路径来降低 agent 调度成本。PaperTrail 借鉴阶段边界，不复用其权限/许可假设：[PaperQA2 实现](https://github.com/Future-House/paper-qa/blob/main/README.md)。
- Elicit 系统综述产品将搜索、筛选、抽取和报告作为可检查的阶段；借鉴过程透明和结构化抽取：[Elicit workflow](https://support.elicit.com/en/articles/14759154-systematic-reviews-in-elicit)。
- OpenAI Agents SDK 展示 Agent/Runner、tools/guardrails、sessions 与 tracing 的职责分离；PaperTrail 借鉴边界，但保留自己的 provider 适配和隐私策略：[Agents](https://openai.github.io/openai-agents-python/agents/)、[Sessions](https://openai.github.io/openai-agents-python/sessions/)、[Tracing](https://openai.github.io/openai-agents-python/tracing/)。

这些参考描述的是各自公开设计，不证明其内部生产实现，也不代表其输出自动正确。
