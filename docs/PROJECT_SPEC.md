# PaperTrail 项目规格

2026-10-14 人审状态：用户已提供 17 项 v21 标签。复核确认总体观察合理，但 `2610.10204-S2` 的 `iron-phytolankton` 是原 PDF 拼写，不能计作解析缺陷；`2609.39773-S3` 是无解析元素的无效审核样本，排除 pass/fail 分母。v21 标签仅记录于对应包，不迁移到 parser v25。v25 仍需人工核对 16 项后再考虑活动索引升级。

2026-10-14 R04 预算守卫补充：模型输入与 dense/hybrid embedding query 均在 provider 调用前按 UTF-8 字节保守上界预留；剩余额度限制模型输出，provider 回报 usage 超界后停止本轮。该上界不是精确 tokenizer 或账单硬限制。后端 327 项回归通过；测试环境使用捆绑 Python 和既有依赖目录，标准 uv 离线重建受本机缓存缺轮子阻塞。详见 [R04 验收记录](research/R04-agent-runs-acceptance.md)。

2026-10-14 当前改进状态：parser v26 已通过后端 330 项回归；9 篇许可全文的 217 页 v26 草稿机械审计有 3,254 个元素、0 个重复 ID、0 个非法 bbox；16 个审核项映射无误。v26 的 16 项原文核验包待用户检查，活动 SQLite 仍为 v21。v21→v25 BM25 精确映射诊断为 5/6，单篇 top-8 5/6、全库 4/6；这不是 gold recall，v26 需在人工核验后重算。R01–R03 与整体 R08 质量门槛仍进行中；本机交付的既有验收不代表这些质量目标已达成。GitHub 上传未授权。详见 [最新进度](PROGRESS.md)、[PDF 结构核验](research/R02-pdf-structure-acceptance.md)、[BM25 诊断](research/R01-R03-v25-bm25-diagnostic-2026-10-14.md)。

2026-10-13 parser v19 更新：四篇现有许可全文已重解析，活动索引共 1,369 chunks。细线碎片不再作为整图候选；邻接矢量面板可合并成联合 bbox，分离图组不会被聚成一框。2608.02037 第 9 页 Figure 5 联合框为 `[72.31,298.97,519.68,655.65]`，匹配 confidence=0.965，并包含图内子图标签；等待用户确认叠框范围。A1 表格空逻辑行已从 metadata row/header count 中移除，保留物理 row index。许可复核时间保留原人工记录。未覆盖图像像素理解、OCR 或一般解析准确率。后端回归 286 passed、1 条既有 warning；R02 细节见 [PDF 结构验收](research/R02-pdf-structure-acceptance.md)。

2026-10-13 验收补记：用户明确接受当前本机交付版及已披露的探索性结果。R01–R03 的更大真实质量门槛、远端 CI 和 GitHub 发布仍未完成；本机验收不授权上传。后续质量集条件见 [R01–R03 下一门槛](research/R01-R03-next-quality-gate.md)。

2026-10-13 工程回归更新：Harness 对模型/embedding 用量缺失或无效时失败关闭；embedding 用量不可核验会返回 `usage_unavailable` 并终止本轮，避免错误 observation 后继续模型调用。完整后端 **296 passed**、1 条既有 Starlette/AnyIO 弃用 warning；Ruff、84 文件格式检查与 OpenAPI 导出通过。Web Prettier、Next build（集成 TS）和 E2E 18/18 通过。provider 输入/embedding 用量仍是调用后观测、provider 自报无法担保准确，预算不等同账单硬上限，R04 维持进行中。

后续本机数据更新：2026-10-13 四篇许可 PDF 活动索引先统一至 v14，用户核验后反馈 A1/B2 表格错误；parser 已修复并升级为 v15。用户现已确认 v15 两张表的内容修正；A1 raw structured row count 与可见输出行数相差一条全空解析行，说明已加入本机核验包。旧版全文和评测记录保留。

更新日期：2026-10-13。状态：P01—P16 已完成各阶段声明范围内工作；P17、R01—R04、R06—R08 的部分质量门槛仍在推进中，R05 的一个外部 MCP Host 只读烟测已通过；**当前本机交付版已获用户验收**。四篇逐篇许可的 PDF 已进入本机全文索引；其中新三篇的主要正文、Figure 5、Table II/III 和 2609 收紧 bbox 已完成用户抽样核验。R04 支持不落盘的 request-scoped 多轮约束修正并仅记录历史摘要哈希；R07 协调器默认不接入生产。修复后 `gpt-5.6-sol` 六题三臂试运行已完成 18/18 arm、48/48 请求，本地费用估算 USD 1.219042；8 个机器选定答案经用户核对原 PDF 均为 `supported`，但 R4 旧引用缺 `(d)` 标签且把图注续行误标为段落。parser v15 已修复 2607 Table II 表头及 2608 Table 2 列/IVIM 下标问题，并重建四篇活动本机索引；A1/B2 修复内容现已由用户定向复核通过，A1 空解析行计数口径已说明，旧报告与冻结的 R1/R4 直接 chunk 漏命中保留原样。后端最近回归 **253 passed、1 warning**；Ruff check/format 通过。六题一次不足以证明一般质量收益，多 Agent 成本比约 2.20 且只在 R3 形成 consensus，继续默认关闭。48 次调用授权已用尽；远端 Actions 未运行，本轮改进不上传 GitHub。阶段事实与限制见 [进度记录](PROGRESS.md)、[人审结果](research/R06-R07-live-postfix-result.md)和根目录 [current_contexts.md](../current_contexts.md)。

## 1. 产品目标

构建一个可演示、可评测的论文检索与研究助理 Agent。用户以自然语言描述研究问题或兴趣，系统检索真实论文、排序并解释匹配理由；用户可以查看论文元数据、摘要、公开来源、作者、年份、主题与引用关系。后续研究总结必须将事实主张链接到具体论文证据，并对证据不足的内容明确标记。

本项目是学习与简历项目，不宣称替代系统综述、专业同行评审或研究者判断，不自动判断论文结论为真。

## 2. 来源与许可

### 首发来源：OpenAlex

- 首期只接收 API 返回的学术元数据字段；保留 OpenAlex ID、原始记录 URL、查询时间、数据版本/快照时间和映射版本。
- OpenAlex 数据当前以 CC0 发布；每次上线前仍需复核现行 API 条款、字段语义和服务额度。
- API Key 是可选的服务访问凭据，不是论文全文许可，也不进入浏览器、日志或 Git。

### 后续来源：arXiv

- 使用官方 API 查询论文元数据；遵守 API 使用条款、请求节流和指定署名要求。
- arXiv API 元数据、论文文件和论文内图表的许可不是同一概念。未经记录并核对具体许可，不下载、保存、切分或展示全文。
- P08 已接入官方 arXiv Atom API，支持有界搜索、精确 ID 查询、SQLite 快照和不可变版本；单进程请求间隔至少 3 秒，默认每页不超过 25 条。元数据自动跨源关联只采用唯一精确 DOI，歧义或冲突不自动合并。

### 全文边界

- 只有能解析到明确许可且许可允许本项目拟定处理方式的全文，才可进入全文索引。
- 许可未知、仅有开放访问标识、或只有可读网页，不自动视为允许保存和重展示。
- 保留原始来源 URL、许可名称/URL、许可检查时间、内容哈希、抓取时间和处理版本；权限不明确时仅保留元数据与外链。
- 本地全文导入采用人工核对确认，仅白名单 `CC0-1.0` 与 `CC-BY-4.0`；支持 UTF-8 `.txt` 与显式提供的本地 PDF，不自动下载或抓取。PDF 以 pdfplumber 进行本地版面文本提取和表格提取，保存解析器版本、源文件哈希、页码、元素类型及页面区域；双栏分段使用几何启发式，并保留阅读顺序不确定/旋转文字排除等解析 warning，不能把无 warning 当作普遍质量保证。图表以原文图注和图像区域定位支持检索，不生成未经核验的图像语义描述。扫描 PDF/OCR 与复杂图表视觉理解仍未覆盖。具体文件版权仍由导入者逐篇确认；系统白名单不是法律意见。

## 3. 用户流程

1. 输入研究问题，可补充年份、学科、作者、开放许可等过滤条件。
2. 系统确定性解析硬过滤条件，检索论文并返回排序结果和可解释字段。
3. 用户选择论文进行摘要、主题比较或延伸阅读。
4. Agent 在只读工具白名单内查询论文、引用关系和许可允许的证据片段。
5. 输出逐条引用来源、发布日期、证据片段定位、缺失信息和不确定性；无支持证据时拒答或说明缺口。

## 4. Agent 与工具边界

计划工具：

- `search_papers`：搜索与过滤作品元数据。
- `get_paper_details`：读取单篇作品的规范化详情。
- `find_related_papers`：通过作者、主题、引用关系或已检索作品发现相关文献。
- `retrieve_paper_evidence`：只检索许可准入的全文片段；全文功能未实现时明确返回不可用。
- `compare_papers`：由后端确定性汇总选定作品的结构化字段，再由模型组织文字。

模型不得自由访问任意 URL、任意文件、SQL 或 shell，不得直接写数据库、发起下载、改变许可状态或生成虚构论文/引用。所有工具使用 Pydantic 契约、次数与时间上限；最终论文列表和引用必须来自已执行工具的结构化结果。

### 4.1 Harness 组件与当前工具面

Harness 按职责拆分为：模型适配器（Responses API 与可替换 mock）、决策循环/步数预算、严格工具注册表、Pydantic 参数与返回契约、只读执行层、有界 observation、逐 claim 的证据类型/来源字段绑定、终答验证、deadline/token 统计、任务运行 ledger、脱敏 run trace、离线 eval 接口。Skills 选择和正文完整性由固定 registry 管理；Skill 只提供任务指导，并通过同一白名单限制模型可见工具和实际执行工具。

当前生产模型运行实际注册最多 12 项受限只读工具：本地 BM25 搜索、精确作品详情、词法相似作品、2—5 篇元数据对比、全文证据 unavailable；OpenAlex Works 搜索/详情、Authors 搜索/详情、作者作品列表；arXiv 元数据搜索/精确读取。来源工具仅在对应客户端启用时展示；固定官方 host，ID/查询/页大小有界。arXiv 工具只读元数据，不开放论文文件请求、任意网页抓取或数据库写入。

独立 MCP stdio Server 只公开 5 个本地只读工具，全文检索固定使用 BM25。其 SQLite 连接使用 `mode=ro`；缺失数据库、旧 schema 或 migration checksum 不符都会失败关闭，不在 MCP 调用期间创建或升级数据。MCP Host 启动前由 PaperTrail 后端初始化并迁移数据库；用户已完成一个外部 Host 的只读实际调用，详见 [R05 验收](research/R05-mcp-acceptance.md)。

Harness 强制结构化终答；候选论文、摘要与引用只能来自本轮已执行工具观察，引用由 allow-list 校验。答案正文必须精确等于逐 claim 的规范拼接；全文 claim 必须引用当前 run 返回的 excerpt/chunk，metadata claim 只能引用白名单书目字段（不含 abstract）。另外对有限词表可识别的数字、单位、方向词和实验组标签做确定性一致性筛查；数字须与同一条件标签对应，简单否定词也参与方向核验。该规则只拒绝部分可检测错配，不验证完整语义蕴含、通用单位换算或跨论文实验可比性。

SQLite run ledger 持久化 run UUID、问题 SHA-256、状态、模型/embedding token、工具调用/步骤、耗时与脱敏 trace；不持久化原始问题、答案、工具参数或全文摘录。重复 run UUID 返回冲突，`GET /api/v1/agent/runs/{run_id}` 查询状态，`POST /api/v1/agent/runs/{run_id}/cancel` 请求协作取消。非活动进程留下的 `running` 记录在查询时改为 `interrupted`；系统不会自动重放外部模型调用，不提供持久化多轮问答正文。总 token 限额按 provider 返回 usage 计入模型与 embedding；缺失或格式错误的 usage 不再按零计，embedding 请求错误会以 `usage_unavailable` 终止当前 run；单次在途请求仍可能超出一次，context 上限按字符近似而非精确模型 tokenizer。PDF/plain-text chunks 以 1,800 UTF-8 bytes 作为 byte-level BPE token 数保守上界；migration 0009 将 retrieval_text 与 evidence_text 分离，且用 parent_element_id 记录 PDF child chunk 的父级解析元素，命中时受限扩展相邻 child 证据（同解析元素或同 section path）。未扩展整个 section 或跨多个 section，语义蕴含仍未验证。

生产路径仍是单 Agent。额外 `MultiAgentExperiment` 仅作为默认不接入 `/agent/ask` 的评测框架；顺序 worker 共用观测 token/tool/deadline/cancel budget。至少两 worker 的结构化 claims 与 citation IDs 完全一致才返回 consensus，分歧时不合并答案。合成测试证明状态/预算/冲突处理契约，不证明真实质量收益。

`retrieve_paper_evidence` 仅查询当前人工批准的本地全文版本，最多返回 8 个片段；citation 包含许可署名与命中证据定位。未获准文本不进入索引；撤销命令清除文档全部全文版本/切片，并留存不含正文的哈希删除审计。

## 5. 检索与评测

先用可冻结的 OpenAlex 元数据/摘要快照建立 overlap 与 BM25 基线。每条评测查询具有稳定 ID、意图桶、相关论文 ID 与 graded relevance；评测数据不能因在线查询结果变化而静默改变。

检索指标至少包括 Hit@k、MRR@k、NDCG@k、分桶指标、查询均值/P95 延迟、空结果率与数据集哈希。后续答案评测单独量化引用精确率/召回率、可验证主张比例、不可回答问题拒答正确率、工具选择/参数合规率、端到端延迟和模型/API 成本。LLM-as-judge 只能作为补充，需与人工样本校准，不取代确定性指标。

Synthetic 查询和文献只用于代码单元测试及离线评测管线验证，统一 `synthetic=true`、`TEST-*` 标识并与真实来源快照隔离；不能用于报告真实数据质量。P05 qrels 在人工逐项复核完成前不能称为 gold。

Embedding/Hybrid 已完成初版；固定 TEST 向量报告只验证 BM25、Dense、RRF 管线，不代表真实语料/模型质量。真实同题 A/B 需等待许可语料与人工核验 qrels。

## 6. 数据模型原则

- 作品使用来源稳定 ID；跨来源匹配 DOI、arXiv ID 等只保存可验证的匹配依据，不靠标题相似度静默合并。
- 日期、作者、venue、主题、引用、摘要保留原始来源字段与规范化字段。
- 缺失字段保持 null；不从模型记忆补足出版事实、实验结果或引用。
- 每次导入保留来源快照、采集时间、解析器版本与内容哈希，支持增量重跑和差异审查。
- 全文与元数据许可分开建模；索引记录能追溯到作品、来源位置和许可检查。

## 7. 非功能与安全要求

- OpenAlex/arXiv Key、LLM Key 和数据库凭据仅由服务端读取，示例文件不含真实密钥。
- 固定官方 API 基址、超时、并发和退避；不实现通用网页抓取工具。
- 对提示注入与外部文档指令采用不可信数据处理；论文正文不得提升工具权限。
- API 错误、来源限流或 LLM 不可用时降级到可用的确定性搜索，不伪造成功。
- 记录每次检索和 Agent 运行使用的数据快照与配置版本，便于复现。

## 8. 项目验收愿景

- 能从批准来源检索可核验的真实论文记录，并逐条显示来源链接。
- 元数据搜索、过滤、相关论文与 citation 输出均有稳定测试。
- Agent 不能调用未登记工具，不能编造检索结果，工具失败与无结果状态可见。
- BM25 结果可复现；后续检索增强须用同一冻结题集展示量化差异。
- 全文流程在无许可/未知许可时明确拒绝入库；明确许可内容能够保留许可和证据 lineage。
- 清楚报告测试环境、数据快照、API/模型成本、未覆盖场景和失败项。

## 9. 当前核验的官方来源入口

- [OpenAlex API 认证与限额](https://help.openalex.org/api/authentication/)：免费 Key、配额观测与请求限制。
- [OpenAlex 数据来源与 CC0 发布说明](https://help.openalex.org/data/how-its-built/)：元数据可再利用范围。
- [OpenAlex 价格/免费额度](https://help.openalex.org/access/pricing/)：请求服务额度可能调整，P03 实施时重新核验。
- [arXiv API User Manual](https://github.com/arXiv/arxiv-docs/blob/develop/source/help/api/user-manual.md)：查询格式、分页与请求间隔建议。
- [arXiv API Access](https://github.com/arXiv/arxiv-docs/blob/develop/source/help/api/index.md)：教育/非商业项目说明、署名和品牌限制。
- [arXiv API Terms of Use](https://info.arxiv.org/help/api/tou.html)：具体全文/API 处理仍须以现行条款与作品自身许可为准。

以上只用于规划候选来源；接入前必须重新核对平台最新条款和项目实际字段用途。
