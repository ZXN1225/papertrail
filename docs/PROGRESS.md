# 进度

更新日期：2026-09-24。PaperTrail 已迁移为仓库根目录项目，旧电脑推荐项目源码从当前 Git 工作树移除并保存在本机忽略目录 `.local/legacy-computer-project/`。P11 用户本机验收修复并验证 arXiv 检索；P12 离线评测与展示资料完成；P05 80 条人工复核 qrels 已导入；P13/P14 结果仅为 AI 标签探索性诊断。后端 99 项自动测试、Web 15 项 E2E 及静态检查通过。当前 GitHub 凭据无效，无法进行远程仓库改名与推送。
## P01 已完成

- 用户确认将项目方向改为论文检索与研究助理 Agent。
- 确立 OpenAlex 为首个元数据源、arXiv 为后续补充源；全文仅对明确允许本项目用途的许可开放论文处理。
- 定义 Agent 只读工具、引用 lineage、BM25 优先和同题评测策略。
- 将新项目置于独立子目录，避免改写旧电脑项目；独立仓库拆分留待后续确认。
- 本轮没有调用 OpenAlex/arXiv，没有发起 LLM 请求，没有下载全文或添加密钥。

## P02 本轮实施

- 验收条件见 [P02 验收](research/P02-acceptance.md)，全部通过。
- 新增 FastAPI 应用工厂、存活/就绪接口、服务端设置校验、uv 锁文件、GitHub Actions CI、PowerShell/Unix 启动说明。
- 本轮不连接数据库、OpenAlex、LLM 或 embedding 服务；Key 缺失时可启动，状态接口不回传配置秘密。
- 实际验证：`uv sync --locked --all-groups` 成功；Uvicorn 本地启动后 `GET /api/health/ready` 返回 HTTP 200；pytest 3 passed；ruff check、ruff format --check、根 `check_foundation.py`、`check_source_review.py`、`git diff --check` 通过。测试输出有 Starlette/httpx 弃用提示，不影响结果。
- 旧电脑推荐项目源码已从工作树迁至本机 `.local/legacy-computer-project/` 归档，不再属于 PaperTrail 发布树。

## P03 本轮实施

- 开始前验收条件见 [P03 验收](research/P03-acceptance.md)。
- 已核对 OpenAlex 当前官方认证、搜索、字段选择、分页与错误/额度说明；新增固定 Works 端点客户端、限定查询 API、响应校验、短重试/错误分类与额度观测字段。
- 20 项 mock/route/配置测试通过。用户已取得 OpenAlex 和 OpenAI Key；OpenAlex Key 只由服务端从本机 `.env` 读取，不输出密钥。一次真实查询返回 3 条记录、meta.count=191142、credits_used=10、额度剩余 9981/10000。
- 首次真实调用发现模板中的空可选整数变量导致配置解析失败；已启用空环境值忽略，并加回归测试。之后使用 Key 成功查询。

## P04 本轮实施与验证

- 使用 SQLite 保存 OpenAlex Works 元数据；迁移含版本与校验和，首次就绪检查自动建库。健康接口只有 SQLite 可打开才报 ready，失败返回 503。
- 单页导入 CLI 默认 10 条、上限 25 条；保存查询/分页、source/license、获取时间、结果计数、内容哈希与快照条目。稳定 OpenAlex ID 幂等更新，修改内容追加不可变版本，旧快照可读回当时字段。
- 新增只读本地论文列表、详情和快照 API；空库不造样例。摘要只从 OpenAlex inverted index 确定性重建，全文不下载。
- 一次真实 OpenAlex 请求导入 10 条元数据，创建 10 个新作品版本；库内共 10 条、1 个快照，许可证记录为 CC0-1.0。数据库位于 `data/papertrail.sqlite3` 且被 Git 忽略，未暂存。
- Ruff 检查/格式检查通过，后端测试 31 passed（仅有 Starlette/httpx 两条上游弃用提示）。

## 尚待完成的质量工作

- P05 的 80 项 qrels 已完成人工复核，但 8 queries / 10 papers 仍属小样本探索评测。
- P13 的 3,000 项采用 AI 候选分数，未人工核验；用户决定不进行全量人工审核。P14 结果不作为金标准或检索质量声明。
- P12 合成离线评测不代表真实模型回答质量或线上表现。真实 Agent 回答质量尚未在大规模、经人工确认的题集上系统测量。

## P11 研究工作区 Web UI 与 E2E

- 在独立 `web/` 创建中文论文研究工作区：OpenAlex/arXiv/本地文献库检索、当前结果页年份筛选、论文详情与 2—3 篇元数据比较；Agent 面板显示状态、回答、引用、许可/署名、原文证据、运行 ID、token/耗时与脱敏 trace。
- 浏览器只访问同源 Next Route Handlers；服务端代理固定到 `PAPERTRAIL_API_BASE_URL`，限制路径、方法、参数、响应编码/体积和超时。来源 API Key 与 LLM Key 不进入浏览器；全文仍只从已批准的后端资料读取。
- 新增 `TEST-*` 合成夹具 E2E，三种视口分别覆盖检索/详情/比较、Agent 引用证据、失败重试/空结果和键盘操作，并验证 Agent 代理拒绝多余字段与超大请求体，共 15 项通过。格式检查、TypeScript、Next 生产构建均通过。
- npm 与 Python 依赖审计均未发现已知漏洞。审计发现测试依赖 pytest 8.4.2 的公告后，已提升到 9.1.1 并更新锁文件；Ruff、80 项后端测试和二次依赖审计通过。
- 用户本机页面先显示 arXiv API 不可用。排查发现 `python-httpx/0.28.1` 的 10 条短语搜索被 arXiv export gateway 返回 406；同 URL 的 `Python/3.12` 客户端返回 200。客户端现使用准确反映 Python 运行时的 User-Agent（不伪装浏览器/其他库），查询参数空格用 `%20` 编码。
- live 验证：PaperTrail `ArxivClient` 查询 `retrieval augmented generation` 返回 total=5985、10 条 Atom 记录；用户运行中的后端 `/api/v1/arxiv/search` 与 Web `/api/search?source=arxiv` 均返回 10 条、HTTP 200。遵守 arXiv 最低请求间隔。P11 自动和本机验收现已完成。
- 未触发真实 OpenAlex、OpenAI 或本机 SQLite 的 Web 联调；E2E 是前端交互与 mock 契约验证，不是在线可用性或 Agent 质量评测。运行步骤见 [本地开发说明](development.md)，验收标准见 [P11 验收](research/P11-acceptance.md)。
- P11 阶段完成并已由用户验收；P12 也已实施完成，现暂停等待用户检查。

## P12 离线端到端 benchmark 与作品集交付

- 新增 `python -m app.cli.evaluate_p12`，将 P10 冻结 TEST 检索夹具（BM25、固定向量 Dense、RRF）与真实 `AgentHarness` 离线 mock 安全用例汇总成单份 JSON。报告记录数据/runner SHA-256、Python 版本、配置、查询/文档数、Hit/MRR/NDCG、Agent 状态、工具调用、被拦截的越权尝试、Mock tokens 和仅供观察的本机耗时。
- Agent 用例覆盖保守拒答、工具返回错误、安全恢复、注入要求调用 shell；未授权执行 0 次，越权尝试被拦截 1 次，3/3 场景符合预期。TEST RAG span 校验精确位置、chunk ID、片段中 claim 字符串与 evidence precision/recall；所有质量声明都显式禁用。
- 默认报告写入被 Git 忽略的 `backend/reports/p12-offline-report.json`。报告标明无网络、无真实数据库、无真实模型调用；成本 `null/not_measured_mock_mode`，模拟 token 与本机耗时不是账单或线上服务表现。
- README、开发手册、项目规格和 P12 验收记录已同步。人工复核 P05 qrels 与真实小批量 OpenAI 评测仍未完成，不能据此宣传真实检索/Agent 质量或成本。
- 验证：当时 Ruff check/format、后端 83 tests、OpenAPI 生成、根 foundation/source-review、Web Prettier/TypeScript/生产构建通过。Playwright 收尾问题已在 P14 收尾时解决：Windows 预先启动 3001 Next 服务、让 Playwright 复用后，15/15 passed 且退出码 0。当前完整验证记录见本轮收尾和 [P12 验收](research/P12-acceptance.md)。
- P12 离线流程已完成；P05 80 项人工 qrels 后续已验收。P13 AI 标签与 P14 指标只作探索性分析。

## P05 候选标签人工复核工具

- 由于候选 qrels 必须由人判断，不将助手初稿自行变更为 `human_reviewed`。新增导出/导入 CLI：导出需本机已有与冻结 OpenAlex ID、内容哈希一致的快照；复核包包含全部 80 个 query-paper pair、标题/年份/摘要、建议分数、人工分数、checked 标志和备注。
- 导入要求数据集哈希、当前 SQLite 快照、文档元数据、全部唯一 pair、0—3 分数、每项 `reviewed=true`、审核者和显式 `--confirm-human-review`；输出到新版本文件，拒绝覆盖候选 JSON 与复核包。
- 新增 11 项定向测试覆盖往返、完整性、重复/缺失、越界、未审阅、过期数据和禁止覆盖输入。此工具没有访问用户 SQLite、密钥或本机 PDF；尚无实际 review pack，需用户在本机命令行导出。具体命令见 `docs/development.md` 的“P05 人工复核候选标签”。

## P05 人审 qrels 复评（2026-09-24）

- 用户已将 80 个 query-paper pair 导入 `data/evaluation/p05_human_reviewed_v2.json`；数据记录 `judgment_status=human_reviewed`、reviewer=`me`，原始候选数据集保持不变。
- 分别以人审 v2 和原候选数据集重跑 BM25，确认语料快照和检索排名相同。Hit@1=0.75、MRR@10=0.875；人审标签 NDCG@10=0.884906，候选标签为 0.875894。分差来自 qrels 变更，排名没有变化。
- 人审报告为 `backend/reports/p05-human-reviewed-bm25-report.json`，候选对照为 `backend/reports/p05-candidate-bm25-report.json`，均在本机忽略目录。修复了报告在 `human_reviewed` 数据集下仍错误列出“qrels 尚待复核”的限制说明，并增加回归测试。
- 后端定向测试 5 passed，Ruff check/format 通过。benchmark 只有 8 个查询和 10 篇文献，报告继续为 `exploratory_only=true`；P05 流程完成，但规模扩充前不对外宣称统计性检索质量。

## P13 扩展检索评测集（2026-09-24）

- 经 OpenAlex 官方 Works 客户端单次请求导入 100 条元数据；单页安全上限从 25 调整至官方支持的 100。新增 SQLite 0005 迁移重建 OpenAlex 快照页大小约束；历史行与关联版本经迁移测试保留。数据库升级到 schema 5，外键检查无违规。
- 在同一冻结快照上建立 `p13_rag_retrieval_v1.json`：100 个唯一 OpenAlex ID、30 个问题、14 个意图桶、3,000 个 query-paper pair。候选 qrels 有 127 个非零建议；完整的 3,000 项均未标为人工审核。
- 复核包 `reports/p13-review-pack.json` 导出成功，状态 `awaiting_human_review`。候选 BM25 报告已生成但 `exploratory_only=true`；当前数据只验证扩展管线，不宣称检索质量。
- 每页上限使用 OpenAlex 官方现行 Works API 支持范围；本阶段仅导入元数据，不下载或处理全文，不调用 OpenAI。
- 后端全套 96 tests、Ruff check/format、OpenAPI 导出通过；迁移前后数据/外键验证通过。其余基础/来源一致性/diff 检查在本轮结束前执行。

## P13 AI 标注副本与离线诊断（2026-09-24）

- 用户不希望逐条手工审核，故将 3,000 个 review-pack `suggested_grade` 复制到独立 AI 标注副本；分布为 0: 2,873、1: 31、2: 47、3: 49。该操作没有重新逐条核读论文，也没有将任何行设为 `reviewed=true`。
- 原始候选数据集和 `p13-review-pack.json` 保持原状。新增 `data/evaluation/p13_ai_labeled_v1.json` 及 `reports/p13-ai-labeled-pack.json`，记录 `assistant_labeled` / `human_reviewed=false`，并保留源数据集哈希。
- 用本机匹配的 100 篇 SQLite 快照重跑 BM25：30 查询，Hit@1=0.533333、Hit@3=0.733333、Hit@5=0.866667、Hit@10=0.9、MRR@10=0.644444、NDCG@10=0.522229；报告仍为 `exploratory_only=true`，限制明确标注标签由助手生成且未人工核验。
- 自动回归 96 passed；Ruff check/format 通过。报告不构成 gold、人工验证或检索质量改善证据。

## P14 验收与实施

- 用户决定跳过 P13 逐条人工核验，开始检索方法对照。验收先验要求显式启用付费 embedding 调用、绑定固定 CC0 快照、比较 BM25/Dense/RRF，并将 AI qrels 限制贯穿报告。
- 已实现 `app.cli.evaluate_p14`，要求 `--allow-provider-call` 才能调用固定 OpenAI Embeddings API。校验 assistant-labeled 数据集、固定 100 Work snapshot / 内容哈希和 30 个查询；130 个标题摘要/问题分 3 批嵌入，使用 cosine Dense 与 RRF@60 对比 BM25。报告输出每方法总体/14 桶指标、每查询 top-10、方法分歧、数据集/runner 哈希、模型、tokens 和成本估算；不保存向量。
- P14 报告 `backend/reports/p14-retrieval-comparison.json`：BM25 / Dense / Hybrid 的 Hit@1 分别 0.5333 / 0.8333 / 0.7000；MRR@10 分别 0.6444 / 0.8562 / 0.8208；NDCG@10 分别 0.5222 / 0.6464 / 0.6321。Dense 在此 AI 标签诊断集上较高，Hybrid Hit@3/5/10 较高。错误诊断优先指向 graph RAG、检索质量控制和隐私风险查询。
- 单次 23,960 embedding tokens，估算 USD 0.0004792；修正 MRR@10 截断后重跑，总估算约 USD 0.0009584。后端测试、Ruff 与全仓检查在本轮最终验证后登记。qrels 未人工审核，语料有主题偏差，报告严格标 `quality_claim_allowed=false`；不得作为检索质量结论。完整边界见 [P14 验收](research/P14-acceptance.md)。

## P15 简历展示与最终回归（2026-09-24）

- 重写 PaperTrail 与仓库根 README，按作品集顺序展示问题/功能、架构图、技术栈、Agent/RAG 能力、P14 对照结果、适用限制和本地启动步骤。明确项目是学习/简历项目，AI qrels 未人工核验且不能支撑检索质量声明。
- 新增根目录 `.github/workflows/ci.yml`；根仓库 GitHub Actions 将执行后端锁定安装/Ruff/pytest/OpenAPI 校验，以及 Web 格式、TypeScript、生产构建和 Playwright E2E。由于旧 workflow 位于子目录而 GitHub 不会发现它，根 workflow 才是可运行入口。
- 将真实论文 PDF 加入忽略规则；README 明确全文不随仓库分发、代码复用许可证尚未选择。旧电脑项目源码已在本轮从发布树移除。
- 后端：99 passed；Ruff check/format、OpenAPI 导出通过。Web：format、typecheck、production build 全通过；Playwright 15/15 passed、退出码 0（Windows 下先启动 3001 开发服务，Playwright 复用该服务）。根 foundation/source-review、diff 检查通过；npm 与 Python 依赖审计均未发现已知漏洞。
- 发布尚未执行：用户已确认将当前仓库改作 PaperTrail；本机 GitHub 凭据失效且网络请求受限，等待重新登录后执行远程改名与推送。

## P05 本轮实施进度

- 已加入无外部运行依赖的 Okapi BM25，固定 k1=1.5、b=0.75、标题权重 2，提供英文词项与中文 Han 字符二元词切分；分数相同按 OpenAlex ID 稳定排序。
- 新增 Hit@k、MRR@k、基于 2^rel-1 gain 的 NDCG@k，以及整体/意图桶宏平均、空结果率、ranker 单次检索均值/P95 延迟和哈希/配置报告。
- 评测只从本地导入中找与固定 10 个 Work ID 及 metadata SHA-256 完全一致的快照；找不到或变更时拒绝执行。CLI 报告写到被 Git 忽略的 `backend/reports/`。
- 固定 8 条 query、10 篇 CC0 元数据记录；当前宏平均为 Hit@1=0.75、MRR@10=0.875、NDCG@10=0.875894。两次重跑的 corpus/dataset 哈希、结果 ID/分数和指标相同；延迟是运行时测量值，会自然波动。
- 报告标记 `exploratory_only=true`。qrels 为助手依据标题和可用摘要起草、仍待用户逐条复核的候选标签；尚未宣称人工金标或检索质量结论，P05 暂保持 in_progress。
- 测试 36 passed；ruff check 和 format check 通过（仍有两条上游 Starlette/httpx 弃用警告）。OpenAI、embedding、全文未调用。

## P06 本轮实施

- P05 的 BM25 baseline 已满足 Agent 检索工具依赖；候选相关性标注仍明确保持待复核状态。
- 新增 `POST /api/v1/agent/ask` 和五个只读工具：本地 BM25 search、按 ID 读取、词法相似作品、元数据对比、全文未实现时明确返回 unavailable。
- Harness 默认最多 4 轮、8 次工具调用、45 秒；Observation 有界，模型异常、拒答、格式错误、预算耗尽、无证据都有明确状态。
- OpenAI Provider 按官方 Responses API function calling / JSON structured output 实现。服务器只发送严格工具 schema；本地执行固定工具后回传 `function_call_output`；未核验的 OpenAlex ID 引用会被拒绝。请求设为 `store=false`，API Key 仅在 Authorization header。
- 全后端测试 47 passed，ruff 检查/格式检查通过。测试使用 fake model 和 HTTP mock，不会调用 OpenAI 或消耗 API 额度；本轮无 live GPT 质量结果。
- P05 候选 qrels 继续待人工复核。P12 已完成离线 mock 评测；真实模型试跑和人工 gold 评估仍待条件满足后另行安排。

## P07 本轮实施

- 验收记录见 [P07 验收](research/P07-acceptance.md)。
- OpenAlex 增加 Works 精确详情、Authors 搜索/详情和作者作品列表能力；扩充论文字段选择并保留引用数与最多 50 个参考 Works ID。增加对应只读 HTTP 路由。
- Agent 可调用 5 个本地只读工具和 5 个固定 OpenAlex 在线只读工具：本地 BM25、精确作品详情、词法相关、元数据对比、全文 unavailable；OpenAlex Works 搜索/详情、Authors 搜索/详情、作者作品列表。OpenAlex 工具仅在有 client 时注册。
- 在线 OpenAlex 工具固定 api.openalex.org，并在 Agent 路径用 4 秒 timeout/不重试；Key 不进入 query、trace 或工具 observation。
- Agent Response 附 run ID、总耗时和脱敏模型/工具 span（状态、耗时、token）；不记录问题、工具参数或论文摘要。尚未持久化 trace。
- Mock 后端测试 51 passed；ruff check/format 通过；根 foundation 与 diff check 通过。两条第三方 deprecation warning 保留。
- 本轮没有发起 OpenAlex/OpenAI 真实请求。OpenAlex Key 已配置，后续可单独进行受控 smoke test；模型调用仍需确保 OpenAI Key/模型配置正确，并由用户启动/确认 live eval。
- 完整验证项目曾规划在 P12：本轮已完成 TEST-only BM25/dense/hybrid 管线、RAG 固定 span 合约断言、Agent 拒答/错误/注入 mock 和工程观测报告。真实语料/模型质量、真实账单、服务端负载与限流/超时率仍未测；P05 qrels 先经人工审核才能作为 gold。

## P08 本轮实施

- 验收条件见 [P08 验收](research/P08-acceptance.md)。接入 arXiv 官方 Atom 元数据 API：有界搜索、精确 ID 查询与版本后缀归一化，固定官方主机，不请求论文文件。
- 新增 SQLite v2 迁移、导入快照/不可变版本、ArXiv 目录读接口及单页 CLI。只有唯一精确 DOI 才建立 OpenAlex ↔ arXiv crosswalk；歧义、缺 DOI 和冲突均不自动合并。
- Agent 新增两个元数据工具；在线来源工具全部接入后生产模型运行注册 12 个白名单工具。终答引用契约扩展为可明确引用 OpenAlex 或 arXiv ID，仍只接受本轮工具观察中的论文。
- 按官方条款实施单进程全局至少 3 秒间隔；多进程部署尚无共享限流器。arXiv 元数据可按 CC0 保存，全文和图表许可仍需逐篇判断，并需展示 arXiv 指定致谢。
- 后端测试 59 passed；Ruff check/format、根目录 foundation/source-review 与 diff 检查结果以本步最终验证记录为准。使用 fake HTTP/model，无真实 arXiv/OpenAI 请求。
- 限制：未完成全文许可登记、全文 RAG、向量检索、人工 qrels 复核与完整 Agent benchmark；继续安排在 P09—P12。阶段完成后等待用户检查。

## P09 本轮实施

- 验收条件见 [P09 验收](research/P09-acceptance.md)。逐篇许可需人工核对并显式确认；仅接受 CC0-1.0 与 CC-BY-4.0。OpenAlex 的 `is_oa` 或 license 字段不自动授予全文处理权限。
- 只允许本地 UTF-8 `.txt` 入库，不自动下载 PDF、请求任意文本来源 URL、读 PDF/DOCX 或让模型判断许可。保留原论文 ID/URL、文本来源 URL、许可与证据 URL、署名、reviewer、检查时间、源文本/内容哈希、分块版本和字符范围。
- 新增 migration 0003、内容版本、字符定位分块、当前批准版本 BM25 证据搜索、HTTP 只读检索、Agent `retrieve_paper_evidence` 和 CLI 导入/删除。撤销全文会级联清除正文与所有块，只留无正文的哈希审计。
- Agent citation 只由本轮实际工具观察建立，并带许可署名与片段 ID/定位/摘录；全文和元数据均视为不可信数据，不能改变 Agent 权限。
- 后端测试 66 passed，Ruff check/format 通过；所有全文测试使用本地测试库和 fake data，没有下载或提交真实论文内容、没有真实 OpenAI 请求。
- 边界：没有现场核验任何具体真实论文许可证，没有代表用户判定版权，也没有报告真实文献 QA/RAG 质量。P10—P12 尚未完成。阶段完成后等待用户检查。

## arXiv 初期导入联调修复（后续已补充）

- 初期本地 PowerShell 请求 arXiv API 成功，但 PaperTrail 客户端返回 HTTP 406；当时判断网关拒绝项目自定义 `PaperTrail/0.1` User-Agent，因此改用 httpx 默认 UA。P11 用户本机验收证实 httpx 默认 `python-httpx/0.28.1` 仍会对常规 10 条短语搜索返回 406，已在 P11 改为 `Python/{runtime_version}` 并做真实 Web 联调，详见上方 P11 记录。
- arXiv 导入 CLI 的 `--query` 原先总会把输入包装为 `all:"..."`；现已支持 `id:<arxiv-id>` 精确查询并去除版本后缀。此前建议直接传 `id:...` 未考虑包装行为，现由回归测试覆盖。
- 有效 arXiv ID `2609.25991` 的 CC BY 4.0 许可 manifest 已在本地创建；元数据导入与全文测试待 HTTP 客户端修复后进行。

## P09 本机验收补充

- 用户导入 `arXiv:2609.25991` 的 CC BY 4.0 UTF-8 文本：18 个 chunks，`content_sha256=07ba6f68dc9ad4c1330ff9441f50360685591f27abfa3d461304bffb635af29e`。同一文本重复导入返回 `unchanged`，哈希和 chunk 数一致。
- 用户实际运行 Agent 的可复现性负例：询问虚构标识 `PAPERTRAIL-NEGATIVE-CONTROL-92741` 后得到 `insufficient_evidence`，trace 为模型→`retrieve_paper_evidence`→模型，未产生 citation。用户实际运行的正向事实问答也返回 `It is not reported.` 并引用当前工具观察到的论文证据。
- 本机撤回/恢复验收使用 SQLite 备份保护原数据：撤回后 API 与 Agent 全文工具均为 `no_results`、`scanned_chunks=0`，全文版本与 chunks 为 0，删除审计为 1，arXiv 元数据保留。使用原 manifest/text 恢复后 API 与 Agent 工具均重新命中，18 个 chunks 恢复，内容哈希不变，删除审计仍保留。
- 后端回归 `67 passed`；Ruff check 与 format check 通过；OpenAPI 当前生成值与已保存契约一致。根目录 foundation/source-review 和 `git diff --check` 通过。Starlette/httpx 有两条上游弃用警告。BM25 本机报告可重跑：8 queries、10 篇元数据，Hit@1=0.75、MRR@10=0.875、NDCG@10=0.875894；仍标记 `exploratory_only=true`，不能作为人工金标或泛化质量结论。
- `uv run` 受本机 uv 缓存目录权限拒绝，改用项目已存在的 `.venv` 直接运行相同 pytest/Ruff 工具，结果通过。OpenAI 请求未由本轮验收触发；用户此前提供的实时 Agent 输出作为 live smoke evidence，不等于完整模型质量评测。
- P09 本机验收完成。下一步建议开始 P10：先冻结可重复数据/查询集，选择可用 embedding 后端与向量存储方案，再实现 BM25、dense、hybrid 的同题对照；P05 qrels 人工复核仍是质量结论的前置条件。
## P10 本轮实施

- 按 [P10 验收](research/P10-acceptance.md) 增加 OpenAI Embedding Provider、approved/current 全文分块向量索引、Dense cosine、RRF@60 Hybrid 和 BM25/Dense/Hybrid 检索选择；默认 Provider 关闭，BM25 仍为默认，不自动访问付费 API。
- 新增迁移 0004。向量绑定当前批准全文块、模型、维数与内容版本；索引命令有界且幂等。全文撤销/换版沿用当前版本过滤，不允许旧片段进入检索。HTTP API 和 Agent 工具支持显式 dense/hybrid；缺向量、provider 关闭和 provider 错误均明确报告，不伪装成 BM25 成功。
- 新增 `TEST-P10-*` 合成语料/固定向量评测及隔离 CLI。离线报告验证 Hit/MRR/NDCG 和延迟管线，但 `quality_claim_allowed=false`；该夹具不能说明真实 Embedding 质量。OpenAI 官方候选为 `text-embedding-3-small`、1536 维；按官方页面当时价格估算约 $0.02/百万输入 token，实际账单以账户价格为准。[OpenAI Embeddings 指南](https://developers.openai.com/api/docs/guides/embeddings)
- 自动回归 79 passed；之后用户在本机应用 0004 并完成 live smoke：18 个当前全文 chunks 成功建 1536 维索引（5782 input tokens，CLI 估算 USD 0.00011564）；BM25、Dense cosine 与 Hybrid RRF API 均正常返回，Dense/Hybrid 查询各计 12 tokens；Agent `retrieve_paper_evidence` 端到端返回 completed 和引用。PowerShell 原始 JSON UTF-8 解析后与本地 `.txt` 精确片段比较为 True，确认数据正常、仅自动响应解码路径显示乱码，无需重新导入或建索引。

P02 本地启动与配置见 [开发说明](development.md)；验收依据见 [执行计划](EXECUTION_PLAN.md) 的 P02 验收部分。

## P04 本轮实施

- 开始前验收条件见 [P04 验收](research/P04-acceptance.md)。
- 选择 SQLite 本地存储，避免为学习版引入 PostgreSQL 服务；数据库文件和原始数据严格留在本地并被 Git 忽略。
- 采用迁移 SQL、不可变元数据版本、导入快照/内容哈希、只读目录和受限单页导入 CLI；实施中。
- 仅使用 OpenAlex CC0 元数据，不请求全文；计划最多导入一页小样本用于真实本地闭环。
