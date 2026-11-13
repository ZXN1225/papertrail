# PaperTrail 代码实施计划

> 本计划以 `docs/General_Plan.md` 为产品基线。实施按阶段提交可审查改动；不删除现有测试、研究报告或评测材料，除非逐个证明已过时且不再有审计/回归价值。用户已有本地改动和本地数据必须保留。

## 2026-11-07 实施状态

- 阶段 1–5 的首版已完成：认证和所有权、个人库、未发表“我的稿件”、会话与 Agent Skills、MinerU 私有 PDF 上传/索引、双工作区 UI；个人稿件可由本人私有检索与引用。
- 私有上传采用逐篇用户声明，仅允许本人账号内处理；共享全文仍走逐篇许可白名单。
- 合成与 mock 验收已通过；用户已提供五篇 PDF 用于本机解析试验，修复长表 chunk、并排表格标题和相邻图注错配。独立 AI 抽查发现表格数值和图注 OCR 仍不可信，私有 Agent 暂不引用图表片段；阶段 3 的全面盲审和冻结检索题集仍待完成，不宣称解析质量已全面提升。
- 产品运行时继续采用单 Agent；阶段 6 的多 Agent 优势评测不是首发要求，未接入生产 Agent。

## 工程基线

- 后端：当前 FastAPI + Pydantic + SQLite/migrations，使用锁定的 uv 依赖。
- 前端：当前 Next.js + React + TypeScript，使用 pnpm 锁文件。
- 账号：密码哈希库优先选成熟 Argon2id 实现；浏览器仅持有 opaque session cookie，服务端保存 session hash/expiry/revocation。
- MinerU：独立解析适配层与异步/可轮询任务接口；先评估官方可本地运行版本及硬件要求，再固定兼容版本。未经明确许可不调用远程解析 API。
- 数据迁移：SQLite 通过连续迁移，不覆盖数据库；解析/索引使用新 parser/index version，保留旧版本直到回归和 lineage 检查通过。

## 执行方式与多 Agent 分工

主 Agent 是唯一集成协调者，负责任务拆分、接口契约、依赖顺序、迁移审查、合并和最终验证。Subagent 只处理边界清楚、互不写同一文件的任务；共享工作树前先约定独立文件范围。不得并行改同一 migration、API schema 或核心 workspace 组件。

| 阶段 | 执行模式 | 分工与交付 |
|---|---|---|
| 0 现状/威胁审查 | 主 Agent + 只读 subagent 可并行 | 主 Agent盘点 schema/API；subagent只读审查 Web 用户流程和隐私风险，交付 findings，不改文件。 |
| 1 账号及所有权 | 主 Agent 单独实现 | 涉及认证、session、迁移与全部私有查询的高耦合变更，避免并行实现。独立 subagent 可只读安全复核。 |
| 2 个人论文库 | 主 Agent；API 契约稳定后可拆分 | 后端与前端可由不同 subagent 在互斥目录实现；主 Agent先定 OpenAPI 契约并负责集成。 |
| 3 MinerU/RAG | 主 Agent 单独统筹；只读评审可并行 | parser lineage、授权、索引迁移高度耦合；subagent可独立审查 MinerU输出评测集或提供只读设计评审，不直接碰生产索引。 |
| 4 Agent skills/会话 | 主 Agent；独立 skill 文档可并行 | skill 文件任务可在审查后独立撰写；服务端权限、记忆和引用验证由主 Agent完成。 |
| 5 Web 双工作区 | API 契约稳定后并行有界实现 | UI 子任务按不同页面/组件边界分配；主 Agent维护共享导航、状态模型和整体验收。 |
| 6 回归/安全验收 | 并行只读审查 | 后端安全与前端流程可独立审阅；所有修复由主 Agent统筹，最终全套门禁顺序执行。 |

多 Agent 不默认开启产品运行路径。委派采用精简 handoff：目标、允许文件、接口契约、验收项、不可触碰路径；不给无关历史和 secrets。子任务必须输出修改文件、验证证据、风险和未完成项。主 Agent逐项审查，不以“subagent完成”代替验收。

## 阶段 0：基线盘点与契约

1. 记录当前 git status、数据库 schema/migration 头、API OpenAPI、页面入口和现有测试。
2. 盘点所有论文/全文/Agent API 的存取路径，形成用户所有权检查清单。
3. 定义 API：注册、登录、登出、当前用户；个人库 list/add/remove/detail；私有会话 CRUD；上传和解析任务状态。
4. 给每个 endpoint 定义 401/403/404/409/413/422/429/503 行为及响应模型。

**完成条件：** API 合同和迁移顺序经主 Agent审查；不触碰本地数据库和 PDF。

## 阶段 1：认证、session 和数据库隔离

### 后端实施

1. 新 migration：`users`（规范化唯一 username、password_hash、created_at/status）、`sessions`（session token hash、user_id、expires_at、revoked_at、created_at）。索引、外键和唯一约束在 SQLite 层强制。
2. 注册时规范化账号名并校验长度/字符；数据库唯一约束作为并发冲突最终防线，冲突返回 409。
3. 密码用 Argon2id 哈希；登录错误对账号不存在和密码错误返回统一消息；对 username/IP 维度做有界速率限制，不泄露账号枚举信息。
4. 生成高熵随机 session token，只把 hash 存数据库；cookie 设置 HttpOnly、SameSite=Lax/Strict、生产 HTTPS 下 Secure、路径限定、过期时间。登出撤销 session。
5. FastAPI dependency 验证 session，暴露不可由 request body 覆盖的 `current_user`。
6. 对所有私有查询通过 `user_id` 过滤；对象越权统一按 404 处理，避免暴露对象存在性。
7. CORS/CSRF 边界按同源 cookie 设计；有跨站写请求时校验 Origin/CSRF token。

### 前端实施

登录/注册页面、表单校验、重复账号/通用认证错误、登录态恢复、登出与受保护页面跳转。凭证仅经 HTTPS 同源 API 发送，前端不存 token 到 localStorage。

### 异常边界

- DB 唯一冲突、迁移失败、哈希参数错误、session 过期/撤销、限流、cookie 不可用、缺少 HTTPS 配置。
- 不记录密码、session token 或完整认证请求体。
- 未迁移现有单用户数据到某个新账户；如需保留旧库使用，必须提供显式、可备份、可回滚的数据归属流程。

### 验收

单测覆盖账号规范化/重复注册/密码错误/哈希不可逆/session 过期撤销/限流；API 测试验证未登录为 401、越权不可读写；并发同名注册仅一条成功。安全复查搜索日志和 trace 无敏感值。

## 阶段 2：个人论文库

1. 新增 `user_library_entries`，关联 user 与规范 work/source ID；来源 ID 唯一性按 user 约束，保存 added_at、license_state、fulltext_state。
2. 封装 PaperStore 用户作用域方法，避免 API handler 自行拼接无边界 SQL。
3. 新增个人库增删查接口；重复加入幂等或 409，行为固定并记录。
4. 复用已有 OpenAlex/arXiv 搜索/详情接口；搜索结果“打开原文”和“加入个人库”是不同动作。
5. 当前无全文许可时只保存元数据；不让搜索 API 自动触发原文下载。
6. UI 增加个人库视图、过滤、来源跳转、移除和许可/全文状态提示。

**异常边界：** 来源 API 超时/429/畸形数据，重复 DOI/跨源 ID 歧义，删除正在解析的条目，数据库约束冲突。

**验收：** A/B 用户完全隔离；source id 唯一；移除条目不误删其他用户或未关联的源快照；原文链接来源可信且 host 固定；OpenAPI 导出更新。

## 阶段 3：MinerU 解析和混合 RAG

### 文件准入和解析任务

1. 设计全文记录与任务状态：uploaded → license_pending/approved/rejected → queued → processing → indexed/failed/deleted。
2. 共享全文仍需逐篇许可核验。用户私有 PDF 可在上传时逐篇声明拥有版权或已获授权，该声明仅允许该用户空间内处理；不得因此进入共享语料。外部论文 PDF 关联个人库来源；未发表自有稿件以标题独立上传，来源类型为 `personal`，不生成公开来源 URL。记录声明时间、来源（如有）、SHA-256、文件大小、MIME、owner。
3. 上传采用流式限额、PDF magic bytes 校验、随机服务端文件名、隔离存储目录；拒绝路径穿越、超限、加密/损坏文件并返回明确错误。
4. 文件和 DB 状态转换使用事务/补偿，崩溃后任务可恢复；同一内容 hash + parser config 可幂等识别。
5. MinerU 适配器运行在受限子进程/独立 worker，无网络或仅允许所需本地模型资源；设置 CPU/GPU、内存、页数、时限和并发上限。解析文本始终作为不可信输入。
6. 统一输出 PaperTrail element：document/version、page、bbox、element_type、section_path、parent_id、text/structured payload、warnings、parser version/config hash。
7. 输出先校验 schema、坐标范围、重复 ID、缺页和资源限制，再发布为可检索索引版本。失败不切换活动索引。

### 切分和索引

1. 标题/段落/列表按结构边界分块；过长正文在句/段边界再切，保留 section path 和父元素。
2. 表格保持表级或行组级结构化文本，重复必要表头；公式保留 LaTeX/原文表示和页面定位，不杜撰语义描述。
3. 每个 chunk 保存 retrieval_text 与 evidence_text 分离；retrieval_text 可带确定性标题/章节上下文，evidence_text 必须是能映射回原解析元素的原始内容。
4. BM25 + Dense 双路召回；RRF 融合、论文/用户/许可过滤、同文档近重复折叠；命中后有限扩展同 parent/相邻 child。
5. 查询扩展/HyDE/LLM contextualization 暂不默认启用。后续按冻结评测集作为独立实验分支比较，不能把生成查询或假设作为引用证据。
6. 新 parser/index version 完整重建并检查 lineage、计数和 hash 后原子切换；保留旧版本回滚窗口，清理需明确执行且不触及原始许可文件。

### MinerU 质量和异常边界

测试样本覆盖数字 PDF、双栏、复杂跨行表格、行内/展示公式、扫描页、中英混排、旋转页面和损坏 PDF。异常包含 MinerU 不可执行/模型缺失、OOM、超时、空输出、公式/表格异常、坐标越界、输出文件爆量、任务重复和 worker 重启。所有状态可见并有安全重试上限。

**验收：** `TEST-*` synthetic 隔离测试；代表性获准 PDF 的盲审 review pack；MinerU 与现 parser 对比指标；citation 页码/bbox 可回溯；未许可样本不调用 parser；索引失败不破坏旧活动版本。未获准全文不进入测试夹具或报告。

**自有稿件补充验收：** 标题与个人库关联恰选其一；本人可查看、重试、删除自有稿件，其他账号不可读取；Agent 只能依据本轮本人稿件检索片段生成 `personal` 引用，且不得附带公开论文链接。

## 阶段 4：私有会话、Skills 与写作辅助

1. migration 新增 conversations/messages，所有行有 user_id，删除 cascade 规则明确；研究材料关联由 conversation-paper selections 维护，不将整篇论文复制进消息。
2. 会话创建、列表、重命名、清空、删除 API 全部做 ownership filter；消息分页/长度限制。
3. 在固定 skill registry 中注册任务说明和允许工具集合：research_search、evidence_synthesis、paper_compare、draft_revision、citation_check。
4. 后端工具仍只读；文稿修改以返回差异/建议为主，需用户操作保存。默认禁止 Agent 工具自由写论文或许可字段。
5. 研究模式输出结构化 claims + citations；写作模式输出 edit suggestions、原句/改写、证据状态和待核实点。引用必须来自当前 run allow-list。
6. 外部 Skill 文档视为不可信数据；只读取审过并固定版本的本地 skill；skill prompt 与用户论文内容不能改变工具注册表。

**异常边界：** 空会话、超长消息、并发清空与回复、LLM 失败/限流、citation 不在 allow-list、上传草稿超限、跨用户 conversation id。

**验收：** CRUD/并发/API 权限测试；对抗性论文提示注入测试；AI 失败不丢历史；清空历史与删除资料行为分开；研究回答缺证据时拒答或标注缺口。

## 阶段 5：前端双工作区与交互

1. 登录后布局为论文发现、我的论文库、科研助手；窄屏提供可访问导航。
2. 助手界面包含会话列表、消息区、选用文献和引用证据侧栏。
3. 明确加载、空态、网络错误、429、401/session 过期、许可待核、上传中、解析失败和删除状态。
4. 关键操作键盘可达，表单 label、焦点、ARIA 状态和错误提示符合可访问性基础。
5. 使用 frontend-design/humanizer 指导风格和文案，但不添加与功能无关的复杂视觉组件。

**验收：** E2E 完整流程：注册→登录→搜论文→加入库→创建会话→引用→退出→重新登录→清空会话；另测用户隔离、重复账号、解析失败反馈和小屏布局。

## 阶段 6：多 Agent 决策与最终验收

首发默认单 Agent。构建独立对照评测：单 Agent 与候选多 Agent 在同一任务集运行，测证据质量、citation 正确性、成本、时延、超时和失败恢复。仅明确收益且成本上限可接受时再启用；并行仅用于只读独立子任务。worker handoff 使用精简结构化摘要，设定最大 fan-out/depth/retry/token/time，主 Agent校验冲突和引用。

## 全量质量门与执行记录

按照仓库 AGENTS.md 完成后端 Ruff check/format、pytest、OpenAPI 导出；Web format/typecheck/build/e2e；根目录 `git diff --check`。依赖审计按依赖变更情况执行。逐项记录命令、退出码和环境限制；失败不掩盖、不宣称通过。任务完成后更新 `docs/TASKS.md` 和 `docs/PROGRESS.md`。

## 不删除旧测试/研究文件的原则

现存测试和研究材料包含回归保护、数据 lineage 和历史决策，默认继续保留。仅当某文件被新版本完全替代、无外部/历史引用、且删除不会丢失审计证据时才考虑删除；本次实施不批量清理历史报告、fixture、SQLite 或 PDF。
