# 任务台账

## 2026-11-12 Rerank 预检与全文向量索引预算门（PR #41 Draft，CI 通过）

- rerank dry-run 已在本机隔离 schema-23 副本核对 9 篇 / 3,294 chunks：3294 缺向量，活动索引不完整；6 条查询仅需 404 UTF-8 bytes、估算 `$0.00000808`；生成全文向量需传输约 825,894 UTF-8 bytes，按配置价字节上限估算 `$0.01651788`。0 provider calls、0 报告写入，原 DB SHA 不变。
- 全文索引 CLI 现在要求 `--max-chunks` 和 `--max-cost-usd`，真实执行再要求 `--confirm-data-transfer`；dry-run 不创建 provider，限定只补缺失向量，并拒绝超预算/超 chunk/过长 chunk。查询预览的维度未配置会显示未验证，真实 rerank 在请求前失败关闭。
- 用户授权指定语料外传后，初次及本机 key 更新后的重试均在首批 embedding 请求返回 `authentication_failed`；没有向量/usage，也未写本地索引。两库 SHA 均未变化；当前凭据仍不可用于 embeddings endpoint，需本机配置有效且有权限的 key，凭据不得发到聊天。
- `embedding client` 现将 HTTP 401 和 403 分别归类为 `authentication_failed` 与 `permission_denied`，Harness 会以安全 warning 保留这两个具体错误；补充客户端分类与 Harness 传播回归，当前没有再次调用 Provider。
- 再次本机配置后的同范围索引尝试确认是 HTTP 401，不是 403；尚无向量或 usage。此次评测在进程内显式固定已授权的 small 模型；`.env` 当前模型为 large、手工价格仍为 `$0.02`/百万 tokens，不能直接沿用本次费用预览。需有效的官方 OpenAI embeddings key 后再做真实 rerank。
- 401/403 映射与 Harness 传播回归共 95 passed、全后端 `580 passed`（1 条既有 Starlette 弃用 warning）；Ruff check/format、OpenAPI（SHA 未变）、pip-audit、diff check 均通过。PR #40 和 PR #41 最新 Harness 集成修复的 backend/web/Browser E2E/container CI 均全绿。PR #41 保持 Draft、未合并。
- Rerank 质量效果仍待有效凭据、索引完成和足量 held-out 人审任务；尚不能据此评选策略。

## 2026-11-12 Chunk size/overlap 配置对照（PR #40 实现中）

- 将 0%/最高 10% overlap target × 900/1200/1800-byte 作为离线 BM25 配置臂；生产 chunk 默认保持原行为，表格结构不重叠；报告版本升级为 v3。
- 9 篇获准本机来源、6 条 single-reviewer selected-span 的六臂对照已跑完，0 provider calls，原数据库 hash 不变。1800-byte 两臂 span coverage 均 100%；overlap 只小幅提升 MRR/NDCG。900-byte+overlap 指标低于零重叠，1200-byte 两臂相近。小样本不能选生产默认。parent-embedding proxy rerank 没有 query embedding，故未执行。
- 全后端 `577 passed`（1 条既有 Starlette 弃用 warning），Ruff/OpenAPI/pip-audit/diff check 通过。独立 reviewer 对原 overlap 算法无 blocker；新增 1200-byte arm 的复核待回。PR #40 初始版本的 backend、web/Browser E2E 与 container CI 全绿，最新矩阵更新待 CI。

## 2026-11-12 MinerU 图表 LLM-as-judge（PR #39 实现中）

- 新增只读 judge runner/CLI：仅 human-reviewed held-out test 的 adjudicated tasks；candidate/judge 必须不同；结果 schema 校验 fact matching 完整性并保留 prompt/dataset/review-pack lineage、token/cost estimates。
- 必须显式 `--execute` 与 `--confirm-data-transfer`；dry-run 0 provider calls，展示整批保守预算估计，执行前若超过费用 cap 则拒绝。逐请求预留仍作为执行保护；成本预算是估计值而不是服务端硬上限。仅传 chart question、candidate facts、human reference facts，不传图像/PDF。Judge 将任务 JSON 视为不可信数据，并使用统一的 1/3/5 评分锚点；AI judge 不得写回或替换人审参考，质量声明恒为 false。
- 7 个 TEST fake-model/CLI smoke 通过（实际 provider 故障模拟确认 partial 写盘、非零退出，且预算触顶保留具体原因与 0 provider calls）；全后端 `576 passed`，Ruff check/format 通过，OpenAPI/pip-audit 在上一版本通过且此次未改契约/依赖。PR #39 最新 commit backend、web/Browser E2E 与 container CI 全绿。真实题集尚未做人审，无法声称 chart judge 得分或 MinerU 质量达标。

## 2026-11-12 MinerU 图表事实评测协议（PR #38 实现中）

- 新增本地 chart-task review/export/import/evaluate：固定 PDF、解析报告、图像与区域 provenance；逐篇 rights attestation；来源/PDF hash 级 dev/test 防泄漏；reviewer 可标 answerable/unanswerable/uncertain；按轴名、series/legend、数值+容差、趋势和比较生成分桶指标；page audit 需要包含零预测页样本并与人审图表数量对照，以测漏图。抽样策略由数据准备流程记录，本 CLI 不自动抽样。
- Import 仅在完整逐任务与页面审阅并显式确认后可写 `human_reviewed`；输出仍不称 gold、不开放质量结论；评分内容 hash 可检测导入后数据漂移，相同输入只写新文件。此 CLI 离线，不发 provider 请求。
- 8 个 synthetic 定向测试通过；全后端 569 passed，Ruff check/format、OpenAPI export、pip-audit、CLI help、diff check 通过；独立代码复核对内容 hash 与 split 校验无 blocker。page count 指标不评价图框 localization。无真实人工复核 MinerU chart set，因此没有解析/事实准确率数值或策略胜者；PR CI 待运行。协议说明见 [MinerU 图表事实评测](research/mineru-chart-fact-evaluation.md)。

## 2026-11-12 私有论文图注检索修复（PR #37 Draft，CI 通过）

- 真实回放发现私有检索同时排除 table 与 figure；16 个 MinerU v11 图注 chunk 已解析入库但无 advanced visual evidence，exact-caption query 原路径为 0/16 命中。
- 修复只开放 figure caption source-exact chunks 进入 BM25；table 继续排除，账号过滤和 rights attestation 沿用原边界。定向 TEST 覆盖 caption 原文检索、table 拒绝及跨账号隔离；全后端 561 passed，Ruff/OpenAPI/pip-audit/diff check 通过。
- 同 ignored 只读 schema-23 副本 16/16 caption self-query 在 top-5/top-8 命中，0 provider calls；原 DB SHA 未变。仅证明图注链路恢复，不证明一般相关性或图表事实解析质量。新增高级 MinerU caption-only 回归验证 exact caption 与未核验视觉解读作为不同记录返回，且跨账号隔离；独立 reviewer 未发现阻断项。PR #37 已创建为 Draft，backend、Web Browser E2E、container CI 全绿，未合并。

## 2026-11-12 Chunk × Parent Embedding Proxy Rerank 配对评测（PR #36 Draft，CI 通过）

- 增加 900/1,800-byte × BM25/父 chunk embedding proxy rerank 四臂只读评测；子 chunk 到当前向量父项必须按来源 hash、page、element/type 和半开 span 唯一严格映射，按唯一父 chunk 计算候选预算，缺向量时整臂显式不可用。
- rerank 只借用当前 1,800-byte chunk 向量，不是 child dense 或 cross-encoder；BM25 继续零 provider 默认。只有显式确认数据外传、query 数和费用上限时，才发送 query 给 embedding provider；不发送论文全文/替代 chunk。
- 合成 paired-rerank、唯一映射/缺向量失败关闭、只读向量加载、预算预检及已有输出防 provider 费用回归已验证；全后端 561 passed，Ruff check/format、OpenAPI、pip-audit、diff check 通过。PR #35 f23a0a7 和 PR #36 `5935b9b` 的 backend/web/container CI 全绿；均保持 Draft、未合并 main。
- 真实 v27 的两条 BM25 臂已在 9 篇、6 条 selected-span 任务上跑完；未确认 query 数据外传，因此两条 embedding proxy rerank 臂未执行。独立 reviewer agent 对 3 篇 rights-attested 私有 MinerU v11 文档的 9 个图页、16 个 figure chunks 做了本地 spot check，未发现明显错页/漏检；这不是人工复核或金标。尚无图表事实 qrels，MinerU chart set 与 parser/index 同源评测仍未闭环。

## 2026-11-12 真实获准语料 Chunk 策略对照（PR #35 Draft，CI 通过）

- 对冻结 v27 9 篇 CC-BY-4.0 corpus / 6 个 selected-reference tasks 真实跑通 900/1,800-byte BM25 对照；原数据库 schema 22，仅在 ignored 临时副本迁移，原库 hash 不变。报告不可作 gold/通用质量声明，真实 MinerU 和 Chunk×Rerank 尚未覆盖。
- 1,800-byte：Hit@1 .500、MRR@8 .622、NDCG@5 .712、Recall@5 1.0、span coverage 1.0；900-byte：.333、.561、.620、.917、.833。900-byte 在 @3 指标较高，样本小且单 reviewer，保持线上默认 1,800，不选胜者。
- 修复真实 run 中发现的 anchor 过期：只对同一源 PDF、历史 span exact text 在当前同页同类型唯一匹配时重定位；其他失败关闭。PR #35 backend/web/container CI 通过，Draft 未合并 main。

## 2026-11-12 Harness 外部检索授权边界（PR #34 Draft）

- `prepare_task` 将联网否定短语当作正向检索指令；ResearchRuntime 也仅校验计划引用原句，存在“明确拒绝联网却调用公开检索”风险。两处现共享肯定意图规则，执行前还限制到用户明确指定的公开来源。
- 回归涵盖中文/英文否定、拒绝 OpenAlex 但正向授权 arXiv、计划超出来源授权时对外部 Registry 调用数为零。全后端 552 passed；Ruff、OpenAPI、pip-audit 通过。
- PR #34 最新提交的 backend/web/container CI 均通过，保持 Draft、未合并。无 UI 代码变更，web 路径由现有 CI 覆盖。

## 2026-11-12 Chunk 策略只读对照（PR #33 Draft，CI 通过）

- 新增 900/1,800 UTF-8 bytes 的结构保留 chunk ablation；原生产 chunker 默认不变。只读 frozen approved corpus + manifest，经 page/element/type/char interval 投影旧 selected-span 锚点；报告 exact span coverage、Hit/MRR/NDCG/Precision/Recall、切块/索引构建/搜索时延。记录与 MinerU 图表生成文本隔离。
- TEST 合成回归和只读 DB 快照验证；全后端 542 passed、Ruff check/format、OpenAPI、pip-audit 通过。
- 未完成：真实获准全文库不可用，尚未执行真实 A/B，chunk/Rerank 联合选型、人工 gold/人工复核图表集和质量门仍待完成。报告保留 `quality_claim_allowed=false`。
- 最新修复让超宽结构化表头只使 900-byte 候选臂不可用，不再阻断 1,800-byte 基线。PR #33 backend/web/container 检查均通过；Draft 堆叠于 PR #32，未合并。

## 2026-11-12 检索 rerank 实验臂（PR #32 Draft，CI 通过）

- 新增只读 `bm25_dense_rerank` 评测臂：BM25 前 128 候选由现有 embedding cosine 重排；Agent 线上默认及 function-call schema 不变，不冒称 cross-encoder，不新增 provider 调用。报告加入 reranker 配置和本地 retrieval latency（不含 query embedding 请求时间）。
- 定向回归 37 passed；全后端 534 passed（需指定 `--basetemp=.local/pytest-rerank-full-20261112-01` 绕过系统 temp ACL），Ruff check/format、OpenAPI、pip-audit 通过。
- 未完成：当前 worktree 无本地授权全文数据库，不能对真实 licensed taskset 报策略收益；chunker side-by-side 现由 PR #33 实现；真实 MinerU 图表准确率和 MinerU/pdfplumber 对照仍需许可样本与逐项核验。synthetic regression 只验证方法实现，不代表检索质量。

## 2026-11-12 MinerU 视觉证据接入（PR #31 Draft，CI 通过）

- 将 advanced 图像/图表模型描述独立于逐字全文切片存储，并限制来源为 adapter 明确标注的 MinerU generated description 字段；私有 BM25 可检索，Harness 与引用 UI 必须显式标“未核验”，精确图注仍单独展示。账号/文档权限和删除级联沿用现有私有文档边界；每份文档最多 128 项、账号最多 2,560 项；表格仍保持排除。解析器元素和文档级 warning 均保留未核验标记。
- 合成测试覆盖数据提取白名单、检索、类型化最终 claim/citation、租户隔离和删除。全后端 533 passed、Ruff check/format、OpenAPI export、pip-audit 均通过；Web 修改文件 Prettier、typecheck、production build、E2E 66/66 均通过，新增未核验视觉证据用例在 375/768/1440px 单独复跑通过。
- 本机全局 `pnpm run format:check` 报告 26 个未修改文件格式不符；本次修改的三个 Web 文件单独检查通过。PR #31 后端、Web、container GitHub CI 均通过，保持 Draft、未合并。真实授权图表与逐图人工校核集、chunk/Rerank A/B、MinerU 与 pdfplumber 图表/正文分桶对照，以及真实解析/检索质量结论仍未完成；合成测试不测量视觉识读质量。
- Firecrawl 外部设计摘录已记录在 `docs/research/agent-and-evidence-design-references-2026-11-12.md`：NatureSkills 的 source-boundary/source inventory 与按需 skill fragments，以及 AI Research Writing Skill 的 claim-evidence map、生成图与确定性图分离和可执行质量门；只借鉴设计原则，PaperTrail 仍保持固定只读工具权限。

## 2026-11-12 MinerU advanced 图表分析开关（PR #30 草稿，CI 通过）

- 修复 `image_analysis=False` 硬编码；仅 `PAPERTRAIL_MINERU_TIER=advanced` 向本地 MinerU 开启 image/chart analysis，standard 默认保持关闭。私有 PDF worker 现在读取该 tier 配置。
- 解析器返回将视觉模型输出保留在结构化内容并标为 `model_generated_unverified`；advanced 的 figure/chart chunk 文本限定为来源 caption，模型生成内容不会变成逐字原文证据。私有索引尚不持久化或检索这些视觉描述。
- 定向 81 项通过，Ruff check/format 通过。未完成：Agent 尚未检索这些结构化视觉输出；缺真实获准 MinerU 图表评测集；解析性能/内存/耗时和图表数值准确率未测，因此不可称图表问答已实现或质量达标。
- 全后端 532 passed；OpenAPI、pip-audit 和 diff check 通过；PR #30 backend/web Browser E2E/container 全绿，Draft 堆叠 PR #29、未合并。

## 2026-11-12 MinerU 评测解析器版本解锁（PR #29 草稿，CI 通过）

- 已移除全文检索诊断和 AI 标注评测只接受 pdfplumber 的阻断：现在仅接受 `pdfplumber-layout-vN` 与 `mineru-<version>-papertrail-vN` 两类明确版本化解析器，并继续要求 manifest 和活动索引的版本/来源/许可/hash 完全一致；未知 parser 测试为拒绝。
- 后端全量 530 passed；Ruff check/format、OpenAPI 导出、pip-audit、diff check 通过。pytest 使用忽略目录 `backend/.local`，绕过 Windows 系统临时目录 ACL。PR #29 backend、web Browser E2E、container 全绿，堆叠 PR #28、未合并。
- 未完成：无真实获准 MinerU 语料可在当前 worktree 复跑；图表视觉内容抽取与评测缺少真实复核集；MinerU 与 pdfplumber 解析对照、检索 reranker ablation、chunk 策略对照均未完成。现有 BM25/Dense/RRF 和单 reviewer anchor 任务不可替代上述评测，也不构成通用质量声明。

## 2026-11-12 PR #28 公开发现有界分页（进行中）

- OpenAlex/arXiv 发现支持每次最多 25 条结果，按不超过 10 条的页大小执行；每页消耗独立工具预算和 trace，精确 arXiv ID 不做无效分页。
- 已验证 OpenAlex 多页合并、arXiv 空页、中页失败、工具预算耗尽及超过 25 条时的结果上限披露；预算耗尽保留已检索记录并返回 `insufficient_evidence`。后端 526 passed，Ruff/OpenAPI/pip-audit 通过，PR #28 backend/web Browser E2E/container CI 全绿；Draft 基于 PR #27、未合并 main。

## 2026-11-12 PR #27 同题检索方法比较（完成，Draft）

- 扩展 AI 标注评测 CLI，同一题集支持 BM25/Dense/Hybrid；BM25 默认保持零 Provider 调用，Dense/Hybrid 必须显式确认查询数据外传并设置题数与费用预算，生成包含各方法指标及 embedding 用量的对比报告。
- 独立复核无 blocker；后端 521 passed，Ruff/OpenAPI/pip-audit 通过；GitHub backend/web Browser E2E/container CI 全绿。PR #27 基于 PR #26 分支，保持 Draft 且未合并 main。标签仍非人工金标，查询 embedding 会传给配置的 OpenAI 服务，实际检索质量/泛化能力未由本项证明。

## 2026-11-12 PR #26 检索评测更正

- 修复共享 `MRR@k` 把 cutoff 后命中计分的问题；AI 标签构建器逐个验证多证据锚点，AI 任务评测新增完整 evidence coverage、MRR/NDCG/precision/recall@k，并将未答题的词法候选计数改为不误导的名称。
- 旧 multi-hop 题没有全证据 qrels 时明确报告“未测量”，不会补造标签；任务和报告仍标记 AI 标注、非金标、不可作通用质量声明。
- 后端 516 passed，Ruff check/format、OpenAPI、pip-audit 通过；独立复核确认 MRR/多证据语义正确，NaN 和非法 cutoff 均失败关闭。PR #26 GitHub backend/web Browser E2E/container CI 全绿；当前多锚点限定在单篇论文内，跨论文多跳仍需后续设计。分支 `codex/rag-evaluation-v2` 堆叠在 PR #25 上，不合并 main。

## 2026-11-12 PR #23/#24 与 Agent workspace 批次

- PR #23：弱监督候选与多口径 BM25 回放，修复 GitHub Actions apt DNS 脆弱点；backend、web/E2E、container 全通过，保持 draft。
- PR #24：安全边界内的 LLM-as-judge 诊断；361 项后端测试及 GitHub 全部检查通过，保持 draft。
- PR #25：账号/会话/个人论文工作区和自适应 Agent Harness。Coverage 缺口、预算跳过、重复补查由服务端最终披露并阻止误报完成。PR 分支后端 506 passed，Ruff/OpenAPI/pip-audit 和 Web format/typecheck/build/E2E 66/66/audit 通过；上传并发额度有回归覆盖，删除事务失败可恢复且启动时清理中断删除。GitHub backend/web Browser E2E/container CI 全绿，保持 draft、未合并。
- 三个 PR 均未合并 main；原工作区未暂存改动及本机数据仍保留。

## 2026-11-11 Agent/RAG 架构与零标注评测启动

- 已审阅参考项目文档与 PaperTrail GitHub 历史 PR；新增架构复核报告，记录框架决策和评测边界。
- 已实施 coverage 评估/受限补查和弱监督 query candidate/多指标的起始实现；仍待：按文档拆分训练/dev/held-out，增加不可回答/改写/多约束/章节桶，完善 parser/index 版本对比，开发结构化双 judge 报告并验证校准。
- 持续使用隔离 worktree 与明确文件白名单提交；不纳入私人数据、缓存或生成式复核报告。

## 2026-11-11 分析任务自适应补查

- 已加入初次检索后 Coverage→定向补查，限定原计划内文档、剩余调用预算及一轮补查。未解决缺口、Coverage 因预算跳过、重复补查被去重均由服务端强制披露并阻止 completed；37 项 runtime 定向回归通过。
- 待进一步验收：截图真实比较任务的全文覆盖率、按章节/页读取、表格证据准入，以及长文多轮补查。不得将当前补查能力描述为完整全文阅读或任意任务自主规划。

## 2026-11-11 搜索误判证据不足

- 已分离纯发现与科研分析的完成条件：发现返回实际标题/链接，成功取得指定数量且来源无失败则 completed；不再执行无必要的草稿主张复核。空结果或来源故障仍说明原因。
- 截图原句真实复测 completed / 2 citations；32 项 runtime 回归及 Ruff 通过。复杂筛选、多来源排序和超过 10 条的分页发现仍需后续扩展。

## 2026-11-11 模型调用复查

- 已真实执行截图查询，Plan/公开检索/Draft/Review 均成功；结果为证据不足，未宣称回答质量通过。
- 已重启无热重载的本机后端加载新代码，健康检查正常；新增明确模型错误提示及 Skill 加载失败受控停止。45 项定向测试及 Ruff 通过。
- 历史 model_unavailable 未保留 provider 错误分类，无法确定其历史原因；新请求可区分网络、认证、限流、请求契约及响应错误。

## 2026-11-11 Agent 搜索与运行中断复查

- 已将 Agent OpenAlex 客户端由 4 秒无重试改为 12 秒、最多 1 次重试；与论文发现页的请求配置对齐，并针对截图查询完成 live 工具 smoke test（返回 5 条）。需在新运行中继续观察慢网下的超时率。
- 已为新发生的通用中断日志加入脱敏 traceback 帧（仅文件、行号、函数）；历史稿件运行没有保存栈信息，无法追溯确切异常。下次复现后需根据服务日志继续修复根因。
- 现场健康检查：后端 ready、SQLite 可用；公开论文搜索可用；当前 OpenAlex Agent 工具查询成功。相关 Harness/运行接口测试 105 passed，Ruff check/format check 通过（既有弃用提示及 cache 权限 warning）。个人稿件截图中的间歇性中断尚未被当前可复用数据复现，不能据此宣称已修复。

## 2026-11-11 Harness 与 Skills 改进

- 已将显式文档 ID/标题覆盖和明确比较意图/多篇本地比较数量约束移至服务端计划校验；比较任务只有取得两个不同来源证据才进入草稿阶段；新增 citation-check intent→skill 映射并加回归。
- 五个 Skills 1.1.0 补入 scope、前置条件、阶段产物/检查点与停止/输出条件；比较矩阵和引用核验状态结构更明确，权限保持只读白名单交集。哈希校验测试通过。
- citation-check 现有专用结构化契约可保留 unsupported 原主张；每条 evidence 与主张 source_key 必须一致，若用户明确给 ID/标题，支持判定必须绑定到该指定来源；只有绑定证据且通过复核的主张进入支持 claim 列表。
- 新增独立 AI 辅助复核协议及 TEST 合成样例，标签 `ai_assisted_unverified`/`synthetic=true`；真实语义准确率仍需人工许可语料盲审，当前样例不能充当金标。
- 定向 runtime/skills 测试 45 项通过；全后端 487 项及 Ruff check/format 通过。存在既有 Starlette 弃用提示和本机 pytest cache 权限 warning。

## 2026-11-11 审计后代码改进

- 已修复发现工作区过期搜索/详情响应覆盖，文档请求失败不再伪装成空列表；Agent 取消需服务端 run 状态确认。取消确认三视口测试通过。
- 登录/注册限速已共享持久化到 SQLite，跨 app 实例测试通过；schema 版本预期同步至迁移 0022。
- Web E2E 66/66，类型/格式/生产构建通过；后端 Ruff check/format 与 pytest 467 项通过（存在既有 Starlette 弃用和本机 pytest cache 权限 warning）。已覆盖取消成功/失败和旧搜索响应竞态。
- 未闭环：搜索/详情竞态专用 E2E、取消失败专用场景、双账号越权全路径、重启/断网恢复、独立人工科研质量集、真实生产拓扑与成本/数据保留验证。

## 2026-11-11 认证限速跨实例共享

- 已将账号/IP 15 分钟失败尝试计数持久化到 SQLite，事务化计数避免多 worker 同时绕过；迁移 0022 仅新增表/索引。仅信任 socket peer 地址，不采信客户端可伪造的转发头。
- 已添加同一 SQLite 文件上的双 app 实例限速测试；定向测试 5 passed，Ruff check/format 通过。生产部署仍需在受控反向代理下正确限制入口，不应把任意 forwarded header 当可信客户端地址。

## 2026-11-11 整体项目审计

- 已审阅 Harness、后端账号/私有文档/run 边界，以及发现和助手工作区主要路径；审计记录：`docs/research/project-audit-2026-11-11.md`。
- 已修复发现工作区搜索/详情旧响应覆盖、文档请求失败被当作空列表；Web typecheck、格式和 E2E 57 项通过。
- 继续待办：取消状态须由服务端 run 状态确认；增加双账号资源交叉访问与重启/断网恢复 E2E；建立独立人工复核科研任务集；生产部署需共享登录限速和成本/数据保留验收。

## 2026-11-11 结构化运行时改造

已替换生产调度入口、加入文档身份约束、服务器证据绑定、语义复核及持久会话摘要。后端 466 项、Web 57 项通过；真实比较和混合修改均仅调用本地全文检索并输出带证据的部分回答。详见 [改造与未完成项](research/harness-runtime-v2.md)。不将仍有证据缺口的运行标为完全通过。

## 即时消息与来源识别回归

- 已修复发送后等待回答才显示用户消息的问题，并合并本地文档来源识别规则，覆盖截图原句。
- 整体架构改造、引用精确匹配失败的完整诊断、持久化任务规划和语义质量评测仍未完成。

## 2026-11-11 文档目标及跨来源（进行中）

- 完成账号内已索引文档的明确标题/编号匹配、单篇限定、模糊目标询问、有限上下文指代，以及论文库和公开来源联合任务的初步约束。
- 仍需：验证混合来源在真实网络和 embedding 服务波动下的稳定性；建设带独立标注或可复核依据的多轮语义评测集；评估任务规划、长对话状态和引用语义是否可靠。混合来源修复后一次真实运行完成，早期多次证据不足或 embedding 失败，因此不能宣称全面验收通过。

## 2026-11-11 Harness 改进（未完成）

- 已完成输入框键盘操作、清空及请求失败恢复，以及个人论文追问范围和回答格式的局部修正。
- 待完成：对话文档身份与消歧、结构化任务规划和多来源约束、长上下文管理、事实与建议区分及多场景质量评测。现有规则仍不能保障所有表达和追问的正确路由。

## 2026-11-10 双来源搜索与代码审查

- 已修复明确指定 OpenAlex/arXiv 搜索的路由、有限轮次下的收尾和 arXiv 短末页处理，并覆盖成功、空结果、单来源故障等测试；真实双来源查询返回三条引用。
- 已修复对话消息同时间戳排序及切换时的异步竞争；后端 443 项、前端端到端 51 项通过。任务路由仍为规则匹配，引用验证不能保证语义蕴含，复杂输入仍需持续评测。

## 2026-11-10 响应截断与延迟

- 输出预算提升至 8,192，本机支持模型配置 low 推理强度；混合来源与论文库任务不再重复生成正文。针对确定的输出 token 截断增加有界简洁重试，保留来源及精确证据检查。
- 同一问题真实复测完成：约 30 秒、31,707 tokens、3 个来源、5 条主张；截图旧失败约 60.6 秒、35,542 tokens。样本只有一次且上下文与网络不一定完全相同，不作为整体质量或延迟保证。
- 运行 trace 区分 incomplete 与 ok，并在页面显示“输出未完成”；状态契约已导出 OpenAPI。

## 2026-11-10 混合来源 Harness 修正

- 实现论文库与个人稿件的混合写作任务，明确联网时才开放公开检索工具；本轮必须分别引用账号内两类私有全文，必要时至少两篇论文。历史对话用于理解任务，不充当证据。
- no_results 不再标为 ok；真实截图问题完成一次模型复测，3 个私有来源，2 条主张。静态任务规则和语义支持质量仍有局限，详见 Harness 架构文档。

## 2026-11-10 论文库多轮追问路由

- 最新问题提及当前账号已保存论文编号，或明确追问最近一轮论文库问题时，限制为账号论文库全文检索；明确联网请求继续允许外部检索。历史不作为证据；运行元数据和执行任务保持一致。
- 真实模拟多轮追问返回 completed，引用目标论文，工具仅为本地全文检索；添加编号边界、联网覆盖与工具白名单检查。

## 2026-11-10 论文库 Agent 修复

- 增加账号限定的论文库全文任务，禁用远程 arXiv/OpenAlex 工具；比较至少需要两个本轮核验来源。修正任务与 skill 的一致性，确保仅展示逐条校验过的 claims。
- 196 个缺失向量已补建。真实复测指定论文总结及两篇比较均 completed；后端 424 项通过。模型语义推断质量仍需独立验证。

## 2026-11-10 模型不可用排查

- 两次失败与原 20 秒模型等待上限一致；提高单次等待和任务期限，代理超时相应提高。细分并安全显示模型连接、超时、认证、限流及服务端错误；去除工具结果中重复的索引上下文。短连接探测成功，用户比较问题真实重跑未再超时，但因比较工作流必需工具未完成而中止，比较功能仍需修复。

## 2026-11-10 单轮预算与证据面板

- 将单轮预算提升至 300,000、允许配置至 1,000,000；保留预留检查和资源边界。证据面板不再重复显示回答和主张正文。
- 正文保持校验后展示，避免流式展示尚未核验的内容；回归检查覆盖现有对话与证据。

## 2026-11-10 Hybrid 检索与输出修复

- 完成私有向量迁移、按账号的索引 CLI、BM25+dense RRF、查询预算核算和失效向量过滤；用户授权账号 544 块已建索引，原中文查询命中 8 条。
- 单次输出上限提升到 4096，识别 incomplete 输出；修复同向比较误拒绝，增加有界私有证据修正。真实原问题返回 completed，1 来源/3 主张；全后端 416 passed。
- 新上传或重新解析的文档仍需显式运行向量索引 CLI；缺失向量时保留 BM25，不能宣称已经具备语义召回。

## 2026-11-10 私有块链路修复

- 已确认当前账号 544 个可检索块与 Agent 引用收集器相连；中文泛化问题零命中，英文概述关键词命中 8 个。
- 修复长 locator 导致引用对象校验异常，保持数据库原文及页码不变；新增越界回归。强化任务中的英文关键词检索与未知 UUID 使用 null 的要求。
- 本地真实块检索→引用收集→逐字证据最终校验已通过；真实模型生成仍需实际使用验证。

## 2026-11-10 私有论文引用校验恢复

- 用户截图运行已完成检索，但最终引用 ID 未匹配本轮证据，触发 `unverified_citations`。首个检索调用状态为 error、第二次成功；历史 trace 未留错误码和原始输出，无法追认其具体失败原因。
- Harness 在可恢复的引用 ID 校验失败时，增加一次受 max_steps/token/deadline 约束的修正机会；修正轮仅允许使用本轮验证来源 ID，禁用工具；无来源或仍失败则保持拒答。
- 加入个人论文 UUID 与 arXiv 修正用例，并验证伪造引用仍被拒绝。
- 验收通过：后端全量 414 项、Ruff check/format 与 `git diff --check`。

## 2026-11-10 Agent 中断诊断与会话删除

- 后端 Agent 运行异常仍以 503 返回，但增加仅含异常模块/类型和 run ID 的安全日志；不落提示词、证据、异常消息或 traceback。Web 将 `agent_run_interrupted` 显示为带运行编号的可操作错误提示。
- 新增会话 DELETE Web 代理和侧栏逐条确认删除；删除当前会话后切换到现有会话，删除最后一个时创建空白会话。
- “服务可用”状态表示 API/数据库/模型配置检查就绪，不保证 Provider 单次调用成功。若复现失败，按界面 run ID 对照后端日志中的异常类型继续定位。
- 验收通过：后端 413 项、Web E2E 45 项、Ruff、Prettier、TypeScript、Next build 与 `git diff --check`。真实 Provider 调用未触发。

## 2026-11-10 新对话创建与个人 RAG 预算修复

- 修复 Web 后端代理未保留 `Headers` 内容导致 JSON 请求变成字符串；新对话创建请求恢复正确 Content-Type 与登录 Cookie。
- 修正 personal RAG 工具允许不指定文档 UUID 的校验；本地个人检索可覆盖账号内所有个人稿件，不再因只提供标题而重复报 `invalid_arguments`。
- 单轮 token 上限和示例配置提升到 100,000（当前配置允许的最高值）；日预算 0 继续表示关闭。保留有限上限以控制单次请求成本。
- 加回归检查并用当前本地索引直接验证：`Master Thesis` 私有 BM25 返回 8 条结果、扫描 544 个片段。

## 2026-11-10 个人论文检索与对话管理

- 对明确指向“已入库/我的稿件/本地论文”的问句，Harness 固定到 personal-paper-qa 工作流，只开放个人全文证据检索并要求先检索；无个人证据时不能改用 arXiv/OpenAlex 补猜。
- 科研助手加入左侧常驻对话栏；可新建、切换和重命名对话。每条对话继续使用账号隔离的持久消息记录。
- 新增会话改名 API，按 owner 校验；补充本地论文工具限制、会话创建/重命名/切换与跨用户改名拒绝回归测试。

## 2026-11-10 Agent 请求超时与个人库操作修正

- Agent 专用 Web 代理超时设为 60 秒，覆盖后端 45 秒运行期限；其他后端请求仍为 15 秒。Agent 模型不可用等后端状态现在显示后端提供的具体说明。
- “我的文献库”来源搜索结果隐藏“加入个人库”操作，详情入口保留。
- 新增 E2E 回归检查：个人库搜索不显示重复加入按钮，Agent 503 模型错误显示可读错误。

## 2026-11-10 个人库检索与单轮预算

- 个人库 API 将查询拆成词项并对每个词做大小写无关匹配，修复连字符标题搜索不到；列表卡片将元数据和操作按钮分组并添加间距。
- Agent 单轮默认预算提高到 30,000 token，未能容纳首次请求时提供 `.env` 配置提示。截图中 12,000 上限低于该问题的 12,164 保守输入上界；用户现有 `.env` 未改动。

## 2026-11-10 Web 工作区改版

- 发现论文页移除右侧科研助手；科研助手页改为对话与按需证据双栏布局，窄屏证据移至对话下方。精简多余导航/区块装饰，新增可展开的使用说明。
- E2E 增加发现页隔离、说明面板与助手入口检查；真实模型网页烟测步骤写入 `docs/development.md`。当前仅做前端自动化验收，未配置或调用付费模型。

## 2026-11-09 JAMA 扫描卷 v9 全量解析与 v10 图注关联修复

- 前 250 页 MinerU 4.1.7 standard/auto 全量成功：250 页、249 页含元素、第 2 页空；4,792 元素、5,360 chunks、123 warnings，耗时 50.6 分钟。v5 基线保留；全量 v9 报告位于忽略目录。
- p52 DIAGRAM 15 现归类 figure；p66 Fig.3/Fig.4 的说明关联与 p183 图注位置符合样例。全量 v9 页面检查发现 p241 Fig.33 caption 被误挂到左栏 Fig.31。先添加并确认合成回归失败，再修正候选排序，adapter 升为 `papertrail-v10`。
- v10 对 p241 单页 standard 重跑：1/1 页、21 元素、21 chunks；图注进入对应图块，不再挂 Fig.31。OCR 标签及 `outer` 仍有误识，记录为关联修复，不记作 OCR 准确。
- 警告：86 figure、15 table 未核验；15 caption-native 与 7 table-native 差异。图/表内容继续排除 Agent 证据；AI 目视检查不是真值集/准确率。
- 验收：后端全量 **407 passed**（1 条既有 Starlette/AnyIO 弃用提示）；Ruff check/format、OpenAPI 导出、根目录 `git diff --check` 通过。未修改用户原 PDF，未向外部发送全文或图片。

## 2026-11-09 MinerU 风险候选复核与 v11 适配器修正

- 自动分层、固定 seed 从 v9 250 页结果生成 16 页本机复核包；逐页视觉对照后按协议登记 25 项 `ai_assisted_unverified`（修订后为 5 `possible_issue`、7 `no_issue_observed`、13 `uncertain`），accuracy metric=null。观察重点：p3 空白页自描述、p51 caption OCR 误字、公式文本块误分类、图组关系和小字表格不确定。无远程调用，无人工金标。
- v11 修复：抑制空白页自描述 filler 幻觉，并将短 prose equation 降为 paragraph； warning 记录两种纠正。真实四页样本 v11 运行 438.1 秒，p3 空页输出不再产生正文，p88/p114 continuation footer 归为 paragraph；p51 单页重跑 30.3 秒后 `COURSE OF STUDY` 归为 paragraph。完整 250 页报告仍为 v9；未因局部修复改写其统计。
- v10 的 p241 修复仍有效：唯一近邻编号图注优先绑定正下方图体；真实单页重跑通过，OCR caption 字符错误仍保留并记录。
- 验收：后端全量 **409 passed**（1 条既有弃用警告）；Ruff check/format、OpenAPI 导出及 `git diff --check` 通过。原始论文未修改，所有派生 PDF/图片/评测报告留在忽略目录。

## 2026-11-09 p243/p51 定向复核

- p243 v11 单页复跑仍为一个图像块，不能从扫描图可靠分割 Fig.36/Fig.37；不添加猜测性拆分。相应 v9 视觉观察降为 `uncertain` 并重新按协议登记。
- p51 图注在 600/900 DPI 放大、对比增强后重跑本机 MinerU，仍将 “Showing” 误读；尚无安全的自动修正方法，图表 warning 与 Agent 证据隔离继续生效。后续方向是评估独立 OCR 引擎，再用页面级差异审计决定是否融合。
- 隔离环境试跑 RapidOCR PP-OCRv6 small/medium 和 PP-OCRv5 English/mobile；均未读对历史印刷体图注（置信分数约 0.76–0.88）。未改项目依赖/锁文件；当前不融合 OCR 输出。下一步需评估历史印刷体模型或多页、可审计的复核结果，并保留逐块差异审计。
- 用户授权后，仅将图注紧裁切提交给 OpenAI GPT-5.4 mini 一次，`store=false`，445 input / 29 output tokens；未发送整页/PDF，没有修改 provider 配置或锁文件。模型与本机视觉均读为 “Showing”，但模型给出年份 `1880-90`，与 MinerU v9 `1856-90` 有冲突，故不自动覆盖。原响应/crop SHA 仅留在忽略目录 `TEST-jama-p51-openai-vision-crosscheck.json`。

## 2026-11-10 RapidOCR PP-OCRv6 medium 16 页候选复核

- 对固定 seed 的 16 页本机风险样本运行 PP-OCRv6 medium：共 2,979 OCR 行、平均约 19.5 秒/页。输出仅作模型差异候选，无人工/模型真值，不形成准确率指标；不进入生产索引或 Agent 证据。
- p51 图注仍错读 `Shoncing`，p243 Fig.36/37/38 输出与 MinerU 接近。没有证据证明换引擎可稳定改善，不集成 RapidOCR。机器可读对照留在忽略目录 `TEST-jama-pages-001-250-papertrail-v9-rapidocr-medium-review.json`。

## 2026-11-10 Kraken 英文旧印刷体候选复核

- 在 WSL2 独立用户缓存安装 Kraken 7.1.1、CPU-only PyTorch 和官方 `en_best.mlmodel`（2.9 MB）；没有改项目依赖或上传图像。模型说明及下载见 [Zenodo 2577813](https://zenodo.org/records/2577813)。
- 自动版面分割识别 p51 图注时 OOM，内核记录该进程 RSS 峰值约 6.1 GiB。用手工 bbox 绕过分割后，识别结果仍为乱码。因此 Kraken 未形成可用候选、不接入生产路径；本次试验不构成 OCR 准确率评估。

## 2026-11-09 五篇论文复核与解析器定向修复（追加）

- 自动选定五篇论文共 10 页并完成结构化 AI 辅助视觉复核登记，17 项全部标记 `ai_assisted_unverified`；图 4 项、表 1 项为可能问题。无人工金标、无准确率指标。
- 修正表格 caption 与表体的关联距离：按 bbox 边界距离重配。论文 2611.08390 p12 本机 MinerU standard 重解析中，Table 5/6 标题分别落到正确表体；表格 cells 继续隔离于 Agent 证据。
- `papertrail-v9` 总图注保留为独立 caption，并记录 ambiguous 候选关系。五篇 PDF 均完整本机 standard 重解析；07517 p4、07928 p10、08390 p12、08483 p18、08054 p10/p13 通过相应结构/关联局部检查。08483 的侧置 caption 曾触发空候选异常，现有保护并经重跑验证。没有外部调用。
- 对原自动选定的相同 10 页重新绑定 v9 报告并本机查看，严格登记 16 项 `ai_assisted_unverified`（figure 7、formula 3、layout 2 项 no issue observed；table 4 项未逐格核验，记 uncertain）；无准确率或金标声明，无外发调用。
- 后端最终全量 **406 passed**（1 条既有弃用提示）；Ruff check/format、OpenAPI 导出和根 `git diff --check` 通过。Web format/type/build 通过，本机 Chrome E2E **36/36**；两端依赖审计无已知漏洞。账号日 token 限额默认关闭且可配置；美元 Provider 账单硬上限尚未实现。

## 2026-11-09 自动 PDF 评测候选与 Harness 架构

- 新增 MinerU 分层候选生成器和 CLI；从 250 页旧 v5 解析报告自动选出 33 个未核验候选页，按 layout、figure/table/formula、warning 分层，固定 seed。manifest 绑定 PDF SHA 与 parse report SHA；默认清单不含 PDF 文本或图像，候选集不是金标准。
- 新增 MinerU 本机复核协议与 CLI：对自动候选页渲染本地输入包，绑定 source/report/candidate/page image SHA 和固定 prompt 版本；结构化登记严格校验当前页和 element provenance，结果标记 `ai_assisted_unverified`。已从 250 页解析结果抽出 18 页本机包，图片/正文留在 Git 忽略目录；没有调用模型或声称准确率。
- 新增 [Agent Harness 架构文档](AGENT_HARNESS_ARCHITECTURE.md)：四层分工、既有代码评估、状态机/预算/trace、安全约束及 H1–H5 可验收实施阶段。
- 验收：本轮后端 398 passed；Ruff check/format 通过。Web 格式/类型/生产构建通过；正式 Playwright Chromium 缺失且 CDN 无响应，使用本机 Chrome 临时配置后 E2E **33/33 通过**（375/768/1440px），正式配置未改。
- H1：五类任务已有固定 `TaskSpec`；compare/research brief/citation check 的必需工具阶段由 Harness 强制；H2：owner-scoped 持久取消、30 秒 worker lease/5 秒续租和过期状态处理；H3：per-run token 上限/预留/实际用量及逐调用 trace/heartbeat；H4 的版本证据在运行开始即落账，结束时补 prompt/model usage。可选的每账号 UTC 创建日 token 预算由 `AGENT_DAILY_USER_TOKEN_BUDGET` 配置，默认关闭；账号日预算并发准入有隔离测试。真实子进程退出恢复、取消与恢复并发竞争已通过隔离测试，任何模型调用中断均不自动重放。美元账单硬上限仍未实现。

## 2026-11-08 MinerU 扫描页定向修复（完成，整体 OCR 质量复核仍进行）

- `papertrail-v7` 针对真实 p52/p241 输出修复两项关联问题：受邻近正文 Diagram/Chart 明确指代的伪 table 重分类为 figure；OCR 丢失 Fig. 标签时，紧贴唯一图体且横向重叠的短段落补关联到 figure，保留原 paragraph。
- `papertrail-v8` 对同页图块与说明段中相同且唯一的 `Fig. n` 编号做远距离关联。真实 p66 `auto` OCR 样本中两条长说明与 Fig.3/Fig.4 图块正确配对；`txt` 模式识别不到图块号时规则不触发。
- 补齐本机官方 MinerU standard 模型包并通过 `mineru-kit models verify`；实际样本保持完全本地解析。
- 重跑两页样本：2/2 页、33 元素、60 chunks；确认 DIAGRAM 15 为 figure，Fig.33 图注挂接正确；9 个未核验图表警告继续阻止它们成为 Agent 证据。
- p52/p241 与 p1/p66 两组真实定向样本均通过；后端全量 **371 passed**；Ruff check、format、OpenAPI 导出和根 `git diff --check` 通过。
- 未重跑完整 250 页（约 37 分钟）。右上真表竖排列头漏失仍是已知缺陷，不能宣称扫描版解析通过。

## 2026-11-06 多用户科研助手总体改造（首版完成，真实解析复核继续）

- 新增 `docs/General_Plan.md`：双工作区、账号隔离、MinerU 目标解析、结构感知 Hybrid RAG、任务型 Skills 与安全边界。
- 新增 `docs/IMPLEMENTATION_PLAN.md`：代码步骤、技术栈、异常边界、多 Agent 分工、验收计划及旧材料保留原则。
- 已实现账号注册/登录/登出、Argon2id 密码哈希、session hash/过期、唯一账号、速率限制与用户隔离；SQLite 迁移到 0017。
- 已实现个人论文元数据快照、来源 ID 校验、快照 SHA-256、按标题/ID 搜索、移除与原始来源链接；Agent 每轮收到当前用户最多 50 个来源 ID 作为不可信检索线索。
- 已实现会话创建/列表/读取/清空/删除、页面切换与历史展示；成功 Agent 对话持久化并更新标题。新增 `draft-revision`、`citation-check` 两个固定 hash Skills，Agent 工具权限仍只读。
- 已接入 MinerU 4.1 SDK 解析适配、结构块/bbox 验证、模型本机下载/校验说明及 Docker 可选依赖；个人库 PDF 与未发表自有稿件均支持逐篇声明版权/授权后私有上传、MinerU 异步索引、用户隔离 BM25 检索、失败重试和删除清理。私有解析已移至本机子进程，30 分钟超时，远程 VLM 配置拒绝运行；共享全文导入仍遵循逐篇许可白名单。
- Web 已有“发现论文 / 科研助手”工作区切换、个人库检索、未发表“我的稿件”独立入口和会话选择；视觉系统切换为冷色文献目录风格，并重写首页主文案。私有 PDF 失败状态显示版本更新、超时、远程配置、文件校验等具体原因。
- **当前验证状态：** 后端全量 364 passed；Ruff check/format、OpenAPI 导出通过。Web Prettier、TypeScript、生产构建、E2E（33/33，含 375/768/1440px，覆盖个人稿件上传/失败重试/私有引用）通过。`pip-audit` 与 `pnpm audit --audit-level moderate` 在前次依赖变更后均无已知漏洞；本轮未改变依赖。Next.js 从 16.3.8 定向更新到 16.4.1 以修复审计报告的 2 项 critical 和 1 项 high advisories。
- **个人稿件与隐私：** 迁移 0017 保留旧文档/片段及级联关系，允许本人用标题直接上传未发表 PDF；`personal` 引用必须来自本轮本人私有检索，来源 URL 为空，伪造 UUID/公开链接会被拒。登录态 Agent 证据检索统一使用本地 BM25，不向 embedding provider 发送用户查询；共享与个人结果仍可做 RRF。A/B 隔离与 provider 零调用均有测试。
- **真实解析试验：** 五篇数字 PDF 使用按页判断的 `ocr_mode=txt`/`auto`；定向试跑修正 2611.08054 第 10、24 页 `macro` 下标。新增文字层差异告警；Table 5 裁图重解析仍未恢复可靠列结构，图表片段继续从 Agent 检索排除。扫描版 JAMA 整卷（72.7 MiB、726 页）前 250 页完成 v6 解析，4,791 个元素/5,367 个 chunks/123 条警告，约 36.9 分钟。v8 的 `auto` OCR 定向复核确认 p52 DIAGRAM 15 转为 figure，右上表四个地区列头和数值恢复；此前“地区列头丢失”判断更正为一处拼写错误。p66 Fig.3/Fig.4 长说明与 p241 Fig.33 图注均经定向重解析验证关联。尝试完整 250 页 v8 重跑时 VLM 批次明显变慢（约 3 分钟处理 127/1204 块）而中止，故 v6 仍是最近全量基线。表格/图仍隔离且带未核验警告；AI 抽查非人工金标，未逐格核验，不宣称整体准确率通过。详见 [试验记录](research/mineru-five-paper-pilot-2026-11-06.md)。私有全文证据携带来源、位置、内容哈希和私有处理标记。
- 当前本地状态 `docs/portfolio/resume-facts.md`、`.tmp_fetch/`、`interview_prep/` 均为既有改动，必须保留。未删除旧测试/研究报告或触碰现有 SQLite/PDF。

## 2026-10-15 AI 标注真实语料评测（R01/R03）与简历材料刷新（追加）

- **A1 评测集**：新增 `tools/export_labeling_candidates.py`（抽 108 候选）、`tools/build_ai_labeled_dataset.py`（组装 + 机械校验）、`app/evaluation/ai_labeled_tasks.py` + CLI（只读、0 provider 调用、强制拒绝人工/金标声明）、`tests/test_ai_labeled_tasks.py`（8 项）。
- 三个独立 Agent 各读 3 篇产出标签；构建器**丢弃 1 条 `quote_not_verbatim`** 不合格标签后入库 **44 可答 + 9 不可答**。
- **结果**：全库 3,294 chunks/查询下证据命中 **@1 59.1% / @8 88.6%**；`figure_caption` 5/5、`single_fact` 22/24、`multi_hop` 11/12、**`table_lookup` 1/3（短板，与 R02 表格缺陷一致）**；top-1 分数可答 32.5 vs 不可答 18.3。数据集 SHA `72e22a26…`。详见 [评测记录](research/R01-R03-ai-labeled-evaluation.md)。**AI 标注，非人工金标。**
- **A3 简历刷新**：`resume-facts.md` 从"四篇/1,369/281 passed"更新为 **9 篇/3,294 chunks/291 passed**，并新增可直接粘贴的简历条目；`demo-script.md`、`failure-postmortem.md` 同步（复盘新增 4 条本轮真实排障）。
- 验收：后端全量 291 passed / 0 failed；Ruff check + format 通过；未调用付费模型；未推送。
- **A2（R04 账单硬上限/重启续跑）暂缓**：开放式工程，简历价值低于评测结果，用户已同意优先产出可写进简历的整块成果。

## 2026-10-15 v27：修掉两个静默解析缺陷，建立可复现复核包生成器（追加）

用户改为由 AI Agent 复核（记录为 AI 复核，不冒充人工金标）。据此修掉 v26 核验认定的两个**内容正确性**缺陷：

- `_reattach_grid_dropped_words`：网格推断列边界落在表头字形之外时 `Table.extract()` 会静默丢词（`2609.39773` p39 表 8 丢 `UMA`、表 10 丢 `max_k p_k`）。现以**整张表**的文本为参照集（首版按单行判定，会把已在邻行的表头词复制进空行；全语料版本对比抓到后已改）回挂缺失词，并限制在表格水平跨度与纵向范围内，不重写既有文本。
- `_merge_continuation_rows`：多视觉行单元格的续行被当成独立行（`2610.12662` p14 表 1 的 Qwen "Level loop" 单元格）。现只并入同列留空的相邻行，并强制列宽与行距约束，避免误并跨列行。
- 新增 `backend/tools/generate_parse_review.py`：此前复核包由一次性脚本生成、换 parser 版本无法复现；现草稿/复核包/manifest 一条命令可重建（只读，不碰 SQLite）。
- 表头碎片化（`2610.12662` p17 表 4 等）**未修**，继续由 `table_header_geometry_unreliable` + `row_semantics=grid_body_rows_header_uncertain` 披露；这些元素无丢词、数据行正确。
- 验收：新增 6 个合成用例；parser/table 定向 41 passed / 0 failed / 22 errors（22 个 error 全为沙箱临时目录环境问题）；全语料版本对比 v27 保留 24 张合法表、**0 张表丢词**、回收 36 个被丢弃的词；全量后端 **291 passed / 0 failed / 45 errors**（环境 teardown）；Ruff check 通过、87 files format 通过。
- **独立 AI 复核两轮**：第一轮 10 supported / 6 unsupported（`data/storage/reviewer-v27b/`）；第二轮复核实际发布构建，**8 supported / 7 unsupported / 1 uncertain**（`data/storage/reviewer-v27c/`），确认 **字符丢失只剩 1 处、全样本 0 重复**、S6/S10 丢字已修好，并新发现 `2610.12662` p15 图形文字层假表。
- 据此追加两处修复：单字符按目标单元格字符预算判定；无 `Table N:` 标题且 bbox 完全落在图形区域内的表格候选一律拒绝并记 `table_inside_figure_region_rejected`（`2610.12662` 表格 6→4）。被否决的两条路线已记入 [升级记录](research/R02-v27-parse-upgrade.md)。
- **唯一残留**：`2610.06874` p14 被列线切掉的 1 个 `s`，如实记录未修。
- **活动 SQLite 已升级到 v27**：9 篇全部 `pdfplumber-layout-v27`、**3,294 chunks**、lineage **9/9 verified**、活动库六题检索诊断 **top-8 5/6**、`provider_calls=0`。v27 草稿/复核包/manifest/两份 reviewer 报告已归档到 `backend/reports/live_eval/`。备份保留 `data/storage/papertrail-pre-v27.sqlite3`。
- 未调用模型/embedding；记录一律标为 **AI 复核**，不冒充人工金标；未暂存/提交/推送。

## 2026-10-15 DSH 接手：规范命令修复、v26 独立核验与解析版本循环冻结（追加）

- **规范命令修复**：`backend/tests/tmp*`、`backend/tmp/*`、`backend/.pytest-tmp/`、`backend/.pytest_cache/` 等历史临时目录不可访问，
  使 `pytest -q` 收集阶段 57 个 `PermissionError` 中断、`ruff format --check .` panic、`backend/.ruff_cache` 不可写。
  已在 `backend/pyproject.toml` 加 `norecursedirs`/`extend-exclude`/`cache-dir = ".ruff-cache"`，`.gitignore` 加 `.ruff-cache/`；
  **未删除任何既有文件**（用户选择只加配置忽略）。修好后：收集 330 项 0 错误、`ruff check .` 通过、`ruff format --check .` 86 文件通过、
  `git diff --check` 退出 0、OpenAPI SHA 未变。
- **全量后端回归**：`pytest -q` → **285 passed，0 failed，45 errors，3 warnings（10.25s）**。45 个 error 全部是 teardown 环境错误：
  本沙箱下 `os.mkdir(p, 0o700)` 创建的目录无法再列目录或删除，而 `tempfile.mkdtemp` 固定用 `0o700`，因此约 30 处
  `tempfile.TemporaryDirectory(dir=Path(__file__).parent)` 的 cleanup 必失败。未改测试代码迁就沙箱；`tests/` 下因此堆积 245 个
  已被 `.gitignore` 覆盖、本环境无法删除的 `tmp*` 残留目录。
- **v26 独立核验（AI 辅助）**：16 项逐项视觉/坐标对照 → **supported 11 / unsupported 4 / uncertain 1**，并归纳出四个通用缺陷模式
  （多行表头被列线切穿并丢词、两行表头被拆成两行、双行单元格被拆到相邻行、纯矢量图 caption 关联失败）。记录见
  [R02 v26 独立核验](research/R02-v26-independent-review.md)。**AI 标签不等于用户标签，v26 人工验收仍未完成。**
- **解析版本循环冻结**：v20→v26 连续 7 版各自重出复核包却始终没有 v25/v26 人工标签；本轮不再新增 parser 版本。
- **Web**：Prettier `format:check`、`tsc --noEmit --incremental false`、Next 生产构建均通过；构建对 `web/next-env.d.ts` 的改动已恢复。
  `pnpm run *` 在本沙箱无法启动，改用锁定 CLI 直连；Playwright 浏览器未安装，`test:e2e` 本轮未执行。Web 源码本轮未改。
- 无活动 SQLite 写入（仍 v21）、无模型/embedding 调用、未暂存/提交/推送/上传。

## 2026-10-14 v26 表格恢复与复核包（追加）

- 新增保守表头锚点回退：列起点须由表头和多数正文行共同支持，词框不得被边界切开；Captioned table 的正文列线也纳入切词检查。parser 现为 `pdfplumber-layout-v26`。原 PDF 第 5 页 Table 1 的三列和数值恢复正确；语义按视觉行保留，不推断逻辑关系。
- 基于 9 篇/217 页生成 16 项 v26 人审包，SHA-256 `f8bd20fac4b478ee6bc626d5dcaaf2a5a2c9739c4fdd3f5961be504dd59a98d5`；v25 草稿/复核包保留。人工核对 v26，不迁移 v25/v21 标签；活动 SQLite 仍是 v21。
- 验收：parser/table 57 passed；全后端 330 passed、1 个既有 Starlette/AnyIO 弃用 warning；三目标 Python 文件 Ruff check/format 与根 `git diff --check` 通过。机械核对 3,254 元素，duplicate ID/非法 bbox/16 样本映射错误/缺页图均为 0；不作为语义准确率证据。
- 停止前用量查询已用 84%、约余 16%；本轮在需要用户验收的完整交接点停止。无活动 DB 写入、真实模型调用、暂存、提交、GitHub 上传。

## 2026-10-14 R01 语料状态核准（追加）

- 路线图与 R01 验收页已纠正过期“候选论文未批准/未导入”记录：目前 9 篇许可全文、217 页；第十篇 `2610.13595` 是 CC BY-NC-SA 4.0，按现行白名单排除。
- 已有 10 个候选问题（旧单篇 4 + 新增三篇 6）和六题 live 试验的五组所选回答由用户单人核验；不能代表 40 道任务集、不可答能力、独立 holdout 或双人金标。R01 维持 in progress。

## 2026-10-14 v25 复查交接（追加）

- 对 2610.09789 第 5 页 Table 1 做只读复核：v25 文本仍在，但 `visual_lines_only_unstructured` 输出是 10 条单列视觉行，不能验收三列语义映射。显示行整理能合成 `K_{min}`，但 gutter 重建器对原始词坐标按 3 pt 分行，底标约偏移 4 pt；临时强制底标对齐的只读探针仍未得出可靠列。拒绝比伪造列结构更安全；只加同行容差不足。这里只是 AI 诊断，不替代用户标签。
- 下一步必须用户核对 v2 人审包 16 项并标 `supported` / `unsupported` / `uncertain`。收到前不基于旧版标签修复、不升级活动索引（仍为 v21），不得将这一复核写成已通过。其余状态见 `docs/PROGRESS.md` 顶部。
- 停止前额度检查：Codex 已用 74%，约余 26%；在有明确人工门槛的安全检查点停下。无代码改动、测试运行、数据库/模型调用、暂存、提交或上传。

## 2026-10-14 v25 BM25 R2 映射核查（追加）

- v25 页 2 草稿保留了“决策支持工具，不执行控制操作”的原文。R2 `no_exact_text_match` 是 v21→v25 精确 chunk lineage 映射失败，不等于解析漏字或检索失败；由于没有稳定的新 locator，当前不为 R2 计新版本命中。
- 不修改原报告指标（5/6 exact-mapped、全库 selected-reference top-8 4/6，未映射按 miss）。待 v25 人审确认原文和元素边界后再冻结新 locator 并重跑诊断。
- 当前需人工审阅 v25 包 16 项；活动 SQLite 仍是 v21。无模型调用或数据库写入。

## 2026-10-14 v21 用户人审复核（追加）

- 17 条 v21 用户标签已与原 PDF 页图和解析输出做只读交叉检查。多数观察一致；2609.39773-S3 为审核包无解析元素/截图错配，保持 uncertain 并排除解析器通过率分母。2610.06874-S3 是 caption-image unmatched 能力缺口。
- 归因更正：2610.10204-S2 的 `iron-phytolankton` 拼法也在 PDF 原图注中，v21/v25 解析忠实保留；用户 `unsupported` 标签照原样保存，但该项不计为 parser transcription defect。此项和其他 v21 标签不得迁移到 v25。
- 下一人工验收：v25 review pack 16 项；活动 SQLite 保持 v21，直到新版本有人工验收与 lineage 检查。
- 用户要求关注模型 token 余量；若本轮无法完成整体目标，只在进度、验收、限制、下一步已同步并可恢复的节点停止。

## 2026-10-14 R04 模型输入预算预留（追加）

- Harness 发起模型请求前计算保守输入 token 上界并从共享预算扣留，剩余值用于限制输出额度；若 provider 回报输入量超过预估上界则失败关闭。
- dense/hybrid embedding query 也在调用前按 UTF-8 byte 上界 + 1,024 字节预留；预算不足不发请求，provider usage 超界后中止。R04/Harness 定向 55 passed；live-eval/P12 兼容 14 passed；全后端 327 passed、1 条既有弃用提示。Ruff check 与三个目标文件 format check 通过。
- 由于项目旧 `.venv` 指向失效 Python、uv 离线缓存缺少轮子，使用捆绑 Python 加既有项目依赖执行全套回归，未更改 `.venv`。这是 token 守卫，不是精确 tokenizer 或 provider 账单上限；单个在途调用仍可能超额。R04 未完成，OpenAPI 无变化。

## 2026-10-14 v25 页外文字过滤、表格结构保留与复核包（进行中；最新）

- v25 延续正文词语不被列线切开的结构保留规则，并过滤页边界之外的定位词，记录 `out_of_page_text_excluded`。不恢复表头语义，也不隐藏文档坐标异常。活动索引仍为 v21。
- 新增相关合成测试：parser/table 定向 **54 passed**；后端全量 **322 passed、1 条既有弃用警告**。改动文件 Ruff check/format 通过。
- 9 篇白名单 PDF/217 页 v25 草稿与 16 项复核包 v2 已生成；manifest SHA `1548235e8e173296c37d5dabb0050a2747c0d2d6bd77cb0c3ad39cf44fef0b78`。结构审计 3,254 个元素，0 个重复 ID/越界 bbox；36 页页外文字被过滤并警告。v1 将 2610.09789-S2 错选为 table，v2 已改为 Figure 3 caption，包含完整图注和已匹配 vector-boundary image relation；v1 保留。
- v21→v25 只读 BM25 版本诊断：精确原文/来源/页/类型映射 5/6，单篇 top-8 5/6、全九篇 top-8 4/6，R2 未映射按 miss；非 gold recall，见 `research/R01-R03-v25-bm25-diagnostic-2026-10-14.md`。
- **当前人工门槛：** 核对 `backend/reports/live_eval/corpus-expansion-v25-human-review.md`；旧版本标签不迁移。无数据库改写、无模型费用、无 Git 暂存/提交/上传。


## 2026-10-13 全库扫描修复与真实诊断（历史）

- 当前许可全文为 9 篇、217 页、4,871 chunks，parser v21；第十份 2610.13595 是 CC BY-NC-SA 4.0，未满足当前全文白名单，未导入全文。
- 修复 repository 的 SQL LIMIT 2000 静默截断：现对选定范围完整扫描，最多 50,000 chunks；超过返回 corpus_limit_exceeded 且不返回部分排名。索引枚举同样拒绝截断。50,000 是资源保护值，不是性能验收结论。
- 新全库评测清单冻结 9 篇 lineage，校验活动来源集合、每个结果来源/hash、完整扫描数量及 truncated 标志；源内与全库报告明确区分。公共 API 继续要求 source_type/source_id 成对提供。
- 全库六题全部 scanned_chunks=4871、truncated=false；参考 top-8 命中 4/6，R1/R2 未命中，R3–R6 排名 1/2/4/3。原单篇限定诊断为 6/6。两次全库重放报告 SHA 相同：eccc6fd5f8f5e4cf0ab552686d05577ff709ee51531c54bbd3a612ae386d95ff。非 gold、非独立 holdout，不宣称一般质量或扩库收益。
- 验收：项目 venv 全后端 304 passed、1 条既有 Starlette/AnyIO 弃用 warning；Ruff check 与 84 文件格式检查通过；OpenAPI 导出 SHA 未变。首次全回归暴露公共 API 部分过滤参数行为变化（303 passed/1 failed），已恢复契约后全量复验通过。新增 2,001 chunk 合成测试覆盖旧截断缺陷及超限拒绝。
- 未调用模型/embedding，未暂存、提交或上传。Web 未改，本轮未重复运行 Web 测试。仍待 v21 抽查包 17 项人审、Figure 5 叠框确认、第十篇兼容许可全文和独立评测集；R1/R2 全库漏命中仍待进一步泛化诊断。
- 详情见 `docs/research/R01-R03-current-v21-full-corpus-2026-10-13.md`；人工材料在 `backend/reports/live_eval/corpus-expansion-v21-human-review.md`。


最新更新（2026-10-13）：PDF parser 已升至 v21。真实表格坐标不完整时保留单列视觉行并显式警告，避免误报列关系或把文本丢回双栏正文排序；完整后端 298 passed，Ruff check/format 通过。10 份候选 PDF 中 9 篇通过 CC0/CC BY 4.0 白名单并建成活动全文，lineage 9/9 verified、4,871 chunks/217 页；另 1 篇 arXiv:2610.13595 实为 CC BY-NC-SA 4.0，全文排除且元数据 API 导入超时，不能称 10 篇活动全文。用户待核验 v21 的 17 项原 PDF 抽查包，以及独立 Figure 5 v20 bbox 图片。无模型调用、提交或上传。详见 [当前进度](PROGRESS.md) 与 [语料扩充验收记录](research/R01-R03-corpus-expansion-2026-10-13.md)。

离线 R01/R03 版本 smoke 另以唯一 exact-text/page/type/source mapping 将六条历史选定参考映射到 v21，当前源内 BM25 top-8 命中 6/6，rank 5/1/1/1/2/3，locator 6/6，provider calls 0；该小样本非 gold，未跨整个 9 篇语料，也未把旧语义人审标签迁移。见 [v21 诊断记录](research/R01-R03-current-v21-bm25-smoke-2026-10-13.md)。

PDF 解析现为 v20：矢量图 bbox 左右各增加 2 pt padding 并限制在页面内，修复 Figure 5 `(d)` 标题末尾 `nm` 被右框切过 1.27 pt 的问题；第 9 页 bbox `[70.31,298.97,521.68,655.65]`。A1 v18 逻辑行修复继续有效，v20 为 8 行/3 个表头、物理 row_index 1–8；B2 三列和 IVIM 下标 supported。旧内容标签仍绑定 v15 SHA，不视作 v20 structured-output 人审。四篇许可全文统一到 v20，共 1,369 chunks；PDF SHA/许可审核时间未变，lineage 4/4 verified。Parser 定向 35 passed；全文检索诊断/lineage 25 passed；全后端 **297 passed、1 条既有 Starlette/AnyIO 弃用 warning**。Ruff check/84 文件格式与 OpenAPI 导出通过。六题 BM25 v20 诊断 top-8 6/6、locator 6/6、排名 5/1/1/1/2/3、0 provider calls，但仍是单人选择参考，非 gold recall。当前人工门槛是核对 Figure 5 红框范围，不得据抽样宣称通用解析准确率。

R04 新增 provider token usage fail-closed 校验：模型和 embedding adapter 不再把缺失/非法 usage 静默记为 0，避免低报共享预算；完整后端现 **294 passed**、1 条既有 warning，Ruff、84 文件格式检查、OpenAPI SHA 未变。账单硬上限和在途单次超额仍未解决，R04 继续 `in progress`。Figure 5 bbox 用户核验仍是当前人工门槛。

修复了 embedding 错误路径仍继续调用 LLM 的预算缺口：无可核验用量时新增 `usage_unavailable`，立即停本轮并作为 failed 记账；Harness 与 API/ledger 集成回归通过。当前完整后端 **296 passed**，OpenAPI SHA `be007df662be75f9df7e1d480baee2c7284cd02714227d504d57d20324e0c258`；Web Prettier/build/E2E **18/18** 通过。账单硬上限仍未解决。

同轮 Web 只读回归：Prettier 通过，Next production build（含集成 TS 检查）通过，Playwright E2E **18/18**。独立 tsc 命令在当前 pnpm junction 拓扑未解析 `playwright/test`，标准 pnpm 在沙箱无法读取 `node_modules`；见 [进度记录](PROGRESS.md)。Web 源码未改。

PDF 解析历史修订 v18：在 A1 表头归一后丢弃空逻辑表行；Table II row_count/header_row_count 为 8/3，物理 row_index 保持 1–8。四篇许可全文现已统一到 v19。v18 全后端为 **286 passed**、1 条既有 warning；v19 验收状态见顶部。新增语料继续暂缓。

此前 lineage 阶段回归为 **281 passed**、v16 阶段为 **282 passed**、v17/v18 阶段分别为 **285/286 passed**；v19 全后端回归结果见顶部最新进度。四篇活动许可全文当前为 v19；最新 `pip-audit` 与 `pnpm audit --audit-level moderate` 均报告无已知漏洞。Harness 每次模型请求有剩余 token 输出封顶；但 input/embedding 用量仍为事后观测，所以 provider 单次调用可能超额，R04 总预算保证尚未达到“账单硬上限”级别，维持 `in_progress`。详见 [R04 验收](research/R04-agent-runs-acceptance.md)和[语料版本审计](research/R01-R03-current-corpus-lineage-2026-10-13.md)。

最新检索诊断实现为 BM25 v3：v2 审查发现少数单数词误截尾，已加入保护与显式复数映射。相同六题的 top-8 chunk ID 和目标名次均与 v2 一致；定向 37 项通过，BM25 阶段完整后端 255 项通过，后续 Harness 预算改动后的完整后端 256 项通过（各有一条既有 Starlette/AnyIO 弃用 warning）。Ruff、范围内格式检查、OpenAPI 导出与 diff whitespace 检查通过。详情见 [BM25 v3 回归记录](research/R01-R03-current-v15-bm25-v3-smoke-2026-10-13.md)及当前 [Harness 预算记录](research/R04-agent-runs-acceptance.md)。

历史 v15/v17/v18/v19 版本分别冻结自己的许可及内容哈希。当前 v20 同题报告见 [v20 BM25 诊断](research/R01-R03-current-v20-bm25-smoke-2026-10-13.md)，六个精确映射参考均进入 top 8、locator 6/6；该窄报告不是 gold recall。Figure 5 几何关系为 vector boundary matched。定向验收见 [全文检索诊断测试](../backend/tests/test_fulltext_retrieval_evaluation.py)。

四篇当前活动全文 lineage 已只读审计并记入 [当前 corpus 版本表](research/R01-R03-current-corpus-lineage-2026-10-13.md)：全部 approved、CC-BY-4.0、parser v19；本机 PDF SHA 与活动 `source_document_sha256` 一致，metadata/chunk 查询数量一致，总计 1,369 chunks。v13/v15/v17/v18 评测 labels/排名均不迁移到 v19。

最新用户选择：暂缓新增语料。当前只在现有四篇许可 PDF 和本机索引上做离线审查，不下载/导入候选论文、不调用付费模型。候选清单是延后的人工作项，不是当前停止工作的理由。

最新离线诊断：旧版 `bm25_fulltext_v1` 对冻结六题的 top-8 定位为 5/6，R1 全库排名 47/48；升级 `bm25_fulltext_v2` 并做单复数归一后，同题六个目标定位均进 top 8，R1 排名第 5，其余排名不变。详情见 [BM25 v1 基线](research/R01-R03-current-v15-bm25-smoke-2026-10-13.md)与 [BM25 v2 重放](research/R01-R03-current-v15-bm25-v2-smoke-2026-10-13.md)。这是小样本回归，不是普遍检索质量证明。

本次检索器改动已通过完整锁定后端/API 回归（255 passed、1 条既有 warning）、Ruff check、79 个 `app/tests/tools` Python 文件格式检查及 OpenAPI 导出（SHA 未变）。全仓格式扫描因原有不可读 `backend/.pytest-tmp` 退出非零，但显示其余可枚举的 96 个文件均格式正确。

2026-10-13 最新：用户已复核 v15 A1/B2：表头、三列结构、类别文本和 IVIM 下标均 supported；A1 元数据与展示行数差异已解释为原始解析中一个全空行，并在本机忽略包中标明。人审按版本/哈希记录于 [R02-v15 人审 JSON](research/R02-v15-human-review.json)。候选许可论文清单见 [R01–R03 语料候选](research/R01-R03-corpus-candidates-2026-10.md)，6 篇经 arXiv 页面许可入口初筛，未下载/导入，需用户逐篇选择确认。后端最近回归 **253 passed、1 条既有 warning**，Ruff check/format 通过；本轮未重跑测试。无模型调用；旧标签不迁移。过程见 [R01–R03 下一质量门槛](research/R01-R03-next-quality-gate.md)。

2026-10-13 用户明确回复“本机验收通过，请你继续任务”。当前交付版、Figure 5 修复、六题探索报告与工程记录的**本机用户验收已完成**；不等于 R01–R03 的大样本质量目标已达到，也不授权提交或上传 GitHub。R08 保持 `in progress`，因为其路线图验收还依赖未完成的必选质量阶段；本机用户验收子项已完成。下一阶段按 [真实质量门槛缺口](research/R01-R03-next-quality-gate.md)推进。

2026-10-13 用户首页截图补充：本机首屏无明显错位，导航、搜索区和研究助理面板可见；记录为视觉 smoke，不将单张截图等同完整功能验收。用户随后明确验收当前本机交付版；既有 Web E2E 18/18 是自动功能验收依据。本机 LLM/embedding 预览配置为 disabled。

2026-10-13 本机验收交接补充（已完成）：用户核验 Figure 5、阅读六题/工程核对材料并浏览 UI 后明确通过。预览首页和 `/api/status` 返回 200/ready，LLM/embedding disabled。R08 的本机用户验收子项完成；路线图整体仍在进行，远端 CI/GitHub 上传未进行。

2026-10-13 最新门槛：用户已逐一核验修复后真实六题的 A–E 五组，答案均 `supported`，对应 8 个机器选定答案；D 的旧引用缺 `(d)` 且类型误标为 `paragraph`，E 的视觉空白/换行严格同形未独立确认。无模型正文的 [人审记录](research/R06-R07-postfix-human-review-v1.json)与 [结果说明](research/R06-R07-live-postfix-result.md)已登记，原 18 项空白审阅模板和运行报告保留不变。parser v14 修复跨行图注并重导入 2608.02037，本机新 BM25 R4 查询完整图注排名第 1；原冻结漏命中不回填。18/18 arm、48/48 请求，本地费用估算 USD 1.219042，实际账单未知；调用次数已用尽。最新后端 **250 passed、1 warning**；Web format/type/build 与 E2E **18/18**、两端依赖审计通过。多 Agent 仅 R3 consensus、成本比 2.20，继续不进生产；六题一次不足以证明 Skills/多 Agent 一般收益。下一个人工门槛为最终项目验收；远端 CI 和 GitHub 上传未获授权。

状态：done=该阶段声明范围内验收完成；todo=未开始；in progress=已有实现但验收未完成；blocked=有具体外部阻塞。真实质量、用户验收与历史探索性结果须分别阅读阶段记录。

2026-10-11：用户恢复并授权本地改进工作，明确要求到项目闭环和验收；不推送 GitHub。当前状态与过程见根目录 [current_contexts.md](../current_contexts.md)。实施范围按 [Agent 岗位评审](reviews/2026-10-11-agent-hiring-review.md) 与 [改进路线](reviews/2026-10-11-refinement-roadmap.md)。

| ID  | 任务                                                | 前置                    | 状态                                                                                                                                                                                                                                 |
| --- | --------------------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| P01 | 项目章程、迁移评估、来源/Agent/评测边界             | 用户确认方向            | done                                                                                                                                                                                                                                 |
| P02 | 独立应用骨架、锁文件、CI 与启动说明                 | P01 用户确认            | done                                                                                                                                                                                                                                 |
| P03 | OpenAlex 固定 API 客户端与契约测试                  | P02                     | done                                                                                                                                                                                                                                 |
| P04 | 元数据快照、目录、来源 lineage                      | P03                     | done                                                                                                                                                                                                                                 |
| P05 | BM25 与人工检索金标评测                             | P04                     | done                                                                                                                                                                                                                                 |
| P06 | 受限 Agent 工具循环与引用契约                       | P05 BM25 baseline       | done                                                                                                                                                                                                                                 |
| P07 | OpenAlex 研究 API 能力补全与 Agent Harness 可观测性 | P03、P06                | done                                                                                                                                                                                                                                 |
| P08 | arXiv 第二来源、ID 归一化与精确 ID 导入             | P04、P07                | done                                                                                                                                                                                                                                 |
| P09 | 全文许可登记和开放许可论文 RAG                      | P04、P06、P07           | done                                                                                                                                                                                                                                 |
| P10 | Embedding、Hybrid 与排序消融                        | P05、P09                | done                                                                                                                                                                                                                                 |
| P11 | 研究工作区 Web UI 与 E2E                            | P07                     | done                                                                                                                                                                                                                                 |
| P12 | 端到端 benchmark、工程指标与作品集交付              | P05、P07、P09、P10、P11 | done                                                                                                                                                                                                                                 |
| P13 | 扩展论文检索评测集与 AI 标注诊断                    | P05                     | done                                                                                                                                                                                                                                 |
| P14 | 检索方法对照与失败查询诊断                          | P13、P10                | done                                                                                                                                                                                                                                 |
| P15 | 简历展示文档、GitHub CI 与收尾回归                  | P14                     | done                                                                                                                                                                                                                                 |
| P16 | 迁移当前仓库为 PaperTrail 并发布                    | P15                     | done                                                                                                                                                                                                                                 |
| P17 | 许可准入 PDF 结构解析、表格/图注检索与页级证据定位  | P09、P10                | in progress（三篇主要摘录、Figure 5、Table II、2609 收紧 bbox 与 Table III 裁剪均获用户核验；跨布局通用质量未证明） |
| R00 | 复现当前工程基线与验收口径                          | 用户恢复开发            | done（隔离锁定安装、全量本机等价检查与依赖审计完成；远端 Actions 待提交后触发）                                                                                                                                                      |
| R01 | 研究任务与可复现评测集                              | R00                     | in progress（旧单篇 4 题与新增三篇 6 题已获单人标签；六题候选/任务 SHA 已冻结；真实系统输出盲评尚缺） |
| R02 | 结构化 PDF 解析与版面证据                           | R01                     | in progress（parser v27 已上线活动索引：9 篇/3,294 chunks、lineage 9/9 verified；v26 确认的丢词与错行缺陷已修并有 6 个合成用例；两轮独立 AI 复核为 8 supported / 7 unsupported / 1 uncertain，仅剩 1 处单字符丢失；表头切词/错列与 `section_path` 元数据问题仍未修，OCR/跨布局准确率未建立） |
| R03 | 结构分块、检索和逐主张证据契约                      | R02                     | in progress（证据契约与机械一致性校验已实现；v21→v25 BM25 版本诊断 source-scoped top-8 5/6、九篇全库 4/6，参考非独立 gold；历史直接 chunk 漏检不回填，扩大语料及盲评待完成） |
| R04 | 任务运行状态与共享预算 Harness                      | R01、R03                | in progress（有界 request-scoped 约束、owner-scoped 持久取消、worker lease、增量脱敏 trace/token 账本、run 起始版本快照及可选的账号 UTC 创建日 token 预算已实现；日预算默认关闭，美元硬上限、后台队列/自动续跑及任务中断后的完整恢复未完成） |
| R05 | 只读 MCP Server                                     | R03、R04                | done（SQLite mode=ro、SDK/stdio 契约及用户桌面 Host 实际只读检索通过；单篇结果含 arXiv ID、CC-BY-4.0、Table 3 页/节/结构化表格定位；未覆盖其他 Host/总体检索质量） |
| R06 | 产品运行时 Skills                                   | R03、R04                | in progress（真实六题单次 Skills off/on 对照及用户 PDF 人审完成：机器选定且答案获支持 3/6 vs 4/6；D 旧引用不完整；样本小，未证明一般收益） |
| R07 | Multi-agent 对照实验框架与配对评估                  | R03、R04                | in progress（真实双 worker 六题完成，仅 R3 consensus 且获人审支持；成本比 2.20 超建议门槛，默认不进生产；未证明收益） |
| R08 | 全流程质量与作品集交付                              | R03、R04                | in progress（旧交付版本机验收已通过；当前 v25 parser 更新等待 PDF 人审，R01–R03 真实质量证据未闭环；远程 CI 未运行） |
| R09 | 用户验收后的发布                                    | R08                     | requires_future_authorization                                                                                                                                                                                                        |

2026-10-13 最新数据更新：用户新增的 6 份 PDF 经逐篇 arXiv 页面核验，其中 5 篇 CC BY 4.0 已导入 v20；1 篇 CC BY-NC-SA 4.0 未进入全文索引，因为不在当前白名单。当前共有 9 篇 approved 全文、4,881 chunks，9/9 lineage verified。新增论文人工解析验收未完成；本机忽略 review pack 发现 2610.09789 p.5 Table 1 的输出存在拆词/错列候选，待修复和用户复核。语料许可记录见 [扩充报告](research/R01-R03-corpus-expansion-2026-10-13.md)。

P17/R02 当前抽样：既有 2608.20519v1 和新增三篇许可全文均在本机 host SQLite，用户已核验 2609 右栏及收紧 bbox、2608 Figure 5、2607 Table II/III。真实模型人审发现 2608 旧图注续行类型错误；parser v14 已修复并重导入，完整图注在 R4 问题 BM25 前 8 条排名第 1。PDF 图像语义、OCR 与跨布局通用准确率仍未覆盖，不能以这些抽样外推。当前后端/Web 回归见本文件顶部及 [R08 验收](research/R08-acceptance.md)。

P05 的 80 项 qrels 已由用户导入为 human-reviewed v2，且 BM25 候选/人审对照已完成；小样本报告仍为 exploratory-only。细节见 [`research/P05-acceptance.md`](research/P05-acceptance.md) 与 [`research/P05-qrels-review.md`](research/P05-qrels-review.md)。P09 本机验收记录见 [`research/P09-acceptance.md`](research/P09-acceptance.md)。P10 实现、自动测试和用户本机 live smoke 均已完成。已增加本地 qrels 复核包工具，详见 [`research/P05-review-workflow-acceptance.md`](research/P05-review-workflow-acceptance.md) 与 [`research/P10-acceptance.md`](research/P10-acceptance.md)。P12 离线 benchmark、mock Agent 安全评测和作品集文档已完成，结果及 E2E 清理限制见 [`research/P12-acceptance.md`](research/P12-acceptance.md)。

历史阶段用户曾取得 OpenAlex 与 OpenAI Key 并完成 OpenAlex 搜索验证；本次根 `.env` 已由用户在本机配置且 OpenAI 模型可达。Key 不通过聊天传递。R06/R07 当前已有完整六题一次的机器结果和用户对选定答案的人审记录；若再做付费试验，须新的明确模型/题数/调用数/费用上限。

P13 已建立 100 篇/30 查询/3,000 pair 的候选评测集；按用户选择，生成了 AI 填分副本和探索性 BM25 诊断报告。原人工复核包保持未审核状态，AI 标签不作为人工金标。验收及指标限制见 [`research/P13-acceptance.md`](research/P13-acceptance.md)。

P14 已完成 BM25/Dense/RRF 的同查询对照、分桶指标和失败查询诊断；使用 `text-embedding-3-small` 产生 23,960 输入 tokens。报告仅作 AI-qrels 探索分析，`quality_claim_allowed=false`。详见 [`research/P14-acceptance.md`](research/P14-acceptance.md)。

P15 的 README、架构/评测介绍、CI、全文 PDF 忽略规则与最终回归已完成。P16 已将仓库改名为 `papertrail`，将完整代码推送到默认 `main`，清理旧项目分支并关闭旧项目 PR；GitHub Actions 最终运行通过。

P11 研究工作区及自动验收已完成，结果见 [P11 验收](research/P11-acceptance.md)。用户确认启动的 P12 已完成，阶段报告见 [P12 验收](research/P12-acceptance.md)。P05 qrels 已由用户复核导入并完成 BM25 对照，但数据集规模较小；P13/P14 标签未经人工核验，仅支持探索诊断，不支持对外质量声明。
