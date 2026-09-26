# 进度

更新日期：2026-09-26。PaperTrail 已迁移为仓库根目录项目，并发布至 [GitHub](https://github.com/ZXN1225/papertrail)；默认分支为 `main`，当前工作分支 `codex/paper-research-agent` 已推送至远程。旧电脑推荐项目源码从当前 Git 工作树移除并保存在本机忽略目录 `.local/legacy-computer-project/`。P11 用户本机验收修复并验证 arXiv 检索；P12/P18 离线 Harness 评测完成；P05 80 条人工复核 qrels 已导入；P13/P14/P17 检索结果仅为 AI 标签探索诊断。P19 后端 106 项自动测试、Web 18 项 E2E 及构建检查通过；GitHub Actions 最终运行通过。P29 arXiv 请求修复、P30 元数据回答修复已由用户验收。P31 检索结果分页已实现并通过自动验证。

## 六阶段 RAG 路线复核（2026-09-26）

对照用户确认的路线，当前不是整体收尾状态：

1. **能力/证据边界：已完成。** README 和项目规格区分元数据、合成测试与许可全文评测，并限制结论范围。
2. **可复现全文评测集：已完成本轮标注。** 本地有 10 篇获准全文、8 个问题、127 条人工相关性判断及 2 条不可回答判断；原始全文与逐条标签不进 Git。
3. **BM25/Dense/Hybrid 真实全文基线：已完成探索性 top-5/10 对照。** 结果已按总体和问题桶列入 README；只有 6 个可回答问题和单评审，不能外推为总体质量提升。延迟只作本机运行记录，不作生产基准。
4. **基于错误分析的受控 RAG 改进：已完成一项试验。** 冻结 Hybrid top-10 的来源轮转重排没有改善 Q05/Q06 的相关来源覆盖；不调用外部服务，不改生产策略。结论是该尝试无质量收益，不声称检索质量提升。
5. **运行时 Agent Skills：第一版已通过现场验收。** 三个受控 Skill 已注册并可被激活；用户现场 trace 确认 `evidence_synthesis` 被真实模型选中，随后两次按来源 ID 的授权全文检索均成功，答案展示了对应来源证据。此单次样例不代表模型普遍遵从率。
6. **可信 GitHub 交付：部分完成。** README 已列试点结果与限制；当前还有本地未提交改动，最终审查、适当验证和同步尚未完成。

P44 仅代表最近的回答渲染/Agent 工作流任务完成，不代表上述路线整体完成。用户已授权适当增加人工预算，P46 按完整 top-10 候选并集生成新增盲审表；原 40 条评分和 2 条不可回答判断保留不变。

P46 新增的 top-k 评估器已验证拒绝空表；用户现已完成评分，全部 129 项通过完整性与支持说明校验。完整 top-10 并集为 127 个候选（原评分 40 + 新增 87），再加两项不可回答判断；无第二评审。完整 overall/per-bucket top-5/10 指标已写入 README 和 P39 协议。Dense 在 NDCG/候选池内 Recall 较高，Hybrid 在 Hit@1/MRR 较高；结论仍为小样本探索性且 `quality_claim_allowed=false`。本机报告记录完整逐题指标、输入 SHA、估算嵌入费用和非生产单次延迟。

P47 在冻结 Hybrid top-10 上执行按来源轮转重排，不调用外部服务、不修改运行时代码。Q05/Q06 的 top-2 grade≥2 来源覆盖在重排前后分别保持 0/2、1/2，top-5 都是 2/2；总体 top-10 指标无实质变化。该受控试验没有改善多论文问题的证据完整性，不发布为检索质量提升，也不改变默认策略；记录为无收益的探索消融。

P48 第一版运行时 Skills 已实现并通过现场验收：`backend/app/agent/skills.json` 定义三个提示词工作流和固定工具子集；Harness 以 `activate_skill` 载入目录，激活后只向模型展示当前已启用且被该 Skill 允许的工具，每次运行最多一个 Skill。目录拒绝未登记工具；不执行脚本，也不授予任意 URL、文件、SQL 或写库权限。开发者的根 `skills/` 工作流与运行时目录明确分离。离线安全回归和后端全量 144 项测试通过，Ruff check/format 通过。用户现场真实模型 trace 显示 `evidence_synthesis` 激活成功、两次按来源 ID 检索全文证据均为 `ok`，并展示两篇来源卡片。该单次验收仅证明样例工作流可用，不代表一般模型遵从率。详见 [`research/P48-agent-runtime-skills.md`](research/P48-agent-runtime-skills.md)。

P49 最终审查与交付完成：README 中保留 BM25/Dense/Hybrid 总体及分桶对照表、指标定义和小样本限制；P39/P47/P48 阶段记录与源代码、测试一并推送到当前 GitHub 工作分支。验证结果：后端 Ruff、格式检查、144 项 pytest 和 OpenAPI 导出通过；Web Prettier、TypeScript 与生产构建通过；根 `git diff --check` 通过。E2E 未能启动，因为本机现有 Next dev 服务持有共享 `.next` 开发锁；未停止该进程。依赖审计未能执行：npm registry 请求失败，`uv run` 因本机 uv 缓存权限失败，当前 backend venv 也没有 `pip-audit` 模块。因此依赖漏洞审计仍未验证，不记为通过。GitHub 只包含源代码、文档和汇总结果；本机 `.env`、数据库、全文、PDF 和逐条评分文件未纳入提交。

## P40 本地试点语料准备（文件已就绪；导入待逐篇复核）

- 检测到用户提供的 `backend/paper_doc/01`–`10`；保留 `01` 原有 PDF/TXT/manifest 和既有批准记录，对 `02`–`10` 的 PDF 文字层提取 UTF-8 TXT 与对应 manifest 草稿，共 9 组。第 `10` 篇后来由用户替换为 arXiv `2310.11511v1`（Self-RAG），已重新生成 `10.txt`（30 页）和 manifest；首面标题与正文已抽查。该本机目录被 `.gitignore` 忽略，原文不会进入提交。
- 本地元数据目录已有 `01`、`03`–`10`。用户本机运行 `prepare_import.py --resolve` 后确认 `02` 成功解析为 `2604.14572`、最新 `10` 成功解析为 `2310.11511`；此步骤只导入元数据，不代表许可已复核或全文已导入。
- arXiv `02`、`10` 官方记录提供 CC BY 4.0 许可入口，ACL Anthology 2016 年后材料适用 CC BY 4.0；每篇本地 PDF 与许可依据仍须论文所有者核对，尤其留意第三方材料。新 manifest 的 `reviewer` 保持 `PENDING_HUMAN_REVIEW`；没有运行全文导入命令或启用 Embedding API。
- 在忽略目录保存逐篇导入条件、运行步骤与 8 个问题草案。问题草案尚未冻结，两个不可回答案例和可回答问题的支持片段仍须在批准后的语料内确认；没有新增人工评分或质量结果。

## P41 许可全文盲审与探索性基线（已完成）

- 用户确认完成 `02`–`10` 的许可/来源复核和全文导入；截图及本机只读数据库核验显示 10/10 篇均为 `approved`，共 417 个当前片段。许可复核者为 `local-project-owner`；没有改动全文或许可记录。
- 为 6 个可回答问题生成 8 个 BM25 支持片段候选，存于 Git 忽略目录 `backend/paper_doc/p39-evidence-candidates.draft.json`。它们只是候选，不是人工相关性标签。修正 Q04 的措辞以准确指向 Query2doc 假设文档，并将 Q08 限定为 PaperTrail 本地方法比较，避免与论文自身报告的 citation precision 混淆。
- 用户本机已执行 `uv run --directory backend --frozen python -m app.cli.index_fulltext_embeddings` 成功：417 个片段使用 `text-embedding-3-large` / 3072 维完成索引，输入 157,814 tokens，估算费用约 USD 0.02051852。Codex 环境只读核验确认 417/417 当前片段有匹配向量。
- 新增仅位于 Git 忽略目录的 `backend/paper_doc/build_p39_pool.py`，用于批量嵌入 8 个问题、为 BM25/Dense/Hybrid 各取 top-2、合并去重、注入最多 6 个支持锚点并输出盲审 CSV 和独立审计映射；自动拒绝超过 54 候选的池，评分预算仍不超过 64。脚本不会给候选打分。
- Codex 执行环境生成问题向量遇到 `provider_unavailable`；用户随后在本机成功运行忽略目录生成器，输出 40 个候选。检查确认 8 个问题都有候选、每个候选均有审计 lineage、CSV 留空评分且不含方法/排名/分数/来源 ID 列；审计 CSV 哈希一致。4 个支持锚点被额外注入，仍只视作候选提示而非正例标签。
- 用户已完成全部 40 条候选 0–3 分人工评分及 Q07/Q08 两条语料内不可回答性判断；40 条评分完整，所有 2/3 分均附支持说明，两条不可回答判断均为“否”且附理由。总计 42/64 人工项目，没有第二评审。
- 按冻结审计映射计算探索性 top-2 基线（宏平均，6 个可回答问题；相关阈值 grade≥2，NDCG gain=2^grade−1）：BM25 Hit@1/Hit@2/MRR@2/NDCG@2/候选池内 Recall@2 = 0.333/0.500/0.417/0.287/0.108；Dense = 0.667/1.000/0.833/0.783/0.522；Hybrid = 0.833/1.000/0.917/0.713/0.397。
- 在这组小样本中 Dense 的 NDCG@2 与候选池内 Recall@2 较高，Hybrid 的 Hit@1 与 MRR@2 较高，Dense 和 Hybrid 的六题 Hit@2 均为 1.0。该结果受 8 题/10 篇语料/单评审和候选池构造限制，只是错误分析基线，不能宣称普遍质量提升或方法胜出。Q07/Q08 各只有一例，单独记录判断，不汇总为稳定拒答率。
- 本机忽略目录保存已填写盲审表、回答性判断、检索审计映射和 `p39-baseline-report.draft.json`，报告记录了输入 SHA-256。检索调用耗时没有采集；基线只评测证据检索，不评价生成忠实度或引用精确率。查询向量 265 tokens，估算费用约 USD 0.00003445；全文索引 157,814 tokens，估算费用约 USD 0.02051852。
- 首轮错误定位显示 BM25 在 Q01/Q04/Q06 top-2 未命中相关片段。补充的未预注册双来源覆盖诊断还发现：Q05/Q06 的三种方法都没有在 top-2 同时找齐两篇来源的支持片段。该分析用来确定下一阶段目标，不支持新指标或方法的质量宣传。

## P43 多论文问题的证据集合完整性（已完成）

- 目标是让比较多篇论文的问题在回答前收集到每篇所需的支持证据；目前的 Hit@2 只代表命中至少一段相关内容，不能代表多论文证据完整。
- 已更新 Agent 系统指引：比较多篇论文的方法/发现时，应按每篇论文的确切来源 ID 分别检索许可全文证据；某篇没有支持片段时须说明比较不完整，不能用一篇论文的段落代表另一篇。工具契约不变，没有开放额外权限。
- 新增两篇 synthetic TEST 全文的 Harness 回归：分别按 source ID 检索，检查两条工具观察互不串文，最终引用分别回到对应来源和片段；另测一篇有证据、一篇无证据时，回答明确说明比较不完整，缺证据论文只保留已核验的书目链接且没有全文片段引用。后端全量 `pytest` 138 项通过，Ruff check/format 通过。
- 用户使用两篇已导入且获准全文的论文进行了 live Agent 验收：运行记录显示两次 `retrieve_paper_evidence` 均为 `ok`；来源卡片分别显示 Knowledge-as-Skill 与 Corpus2Skill 的授权全文摘录，内容和论文归属对应。该次验收支持 Agent 能在这组样例中为两篇论文分别取证，不代表普遍模型遵从率，也未验证真实模型的单篇缺证据部分回答场景。
- 没有改变 BM25/Dense/Hybrid 排名实现或默认策略，也不据单次 live 对话宣称检索质量提升。P39 固定盲审已完成；扩池或新增人工判断须先由用户明确同意。

## P44 Agent Markdown 表格与多论文回答（已完成）

- 用户 live Agent 比较答案正确产出 Markdown 表格，但 Web 安全渲染器最初将 `|...|` 表格语法作为普通文字展示。
- 为支持常见 GFM pipe table，增加安全的 React 表格节点解析、横向滚动样式和 E2E 回归；单元格继续经过现有内联格式与允许域名链接过滤，不解释为 HTML。
- 用户现场验收期间发现结构化输出预算不足，Responses API 返回不完整输出。后端现读取 `incomplete_details` 并以不含回答内容的 warning 区分输出上限、内容过滤和未知中断，避免对同一受限响应做无效重试；默认值、模板和本机忽略 `.env` 均设为 4096，并明确要求模型将表格回答保持精简。
- 下一次现场 trace 显示：显式 arXiv ID 的比较题仍先调用不可用的元数据 API，占用 Agent 步数，再因这些错误误判证据不足。现对“显式 arXiv ID + 内容/方法/证据请求”隐藏 arXiv 元数据搜索/详情工具，直接按 ID 检索授权全文；元数据 API 失败不再被视为全文证据缺失。
- 用户最新 live 验收截图确认 Agent 成功返回 `completed`，比较表显示为真实行列，窄栏支持横向滚动，比较依据段落和两条来源卡片均正常显示。后端测试 141 项通过，Ruff check/format、Web TypeScript、Prettier 与 `git diff --check` 通过。Playwright E2E 命令在隔离副本中受 pnpm 符号链接解析问题阻塞，未覆盖；本轮未触碰 `web/.next`。P44 按 live 页面验收完成，自动化 E2E 环境限制已记录。

## P42 arXiv 精确 ID 元数据查询修复

- 用户诊断显示：Python 对 `id_list=2604.14572` 单独请求返回 HTTP 200；相同请求附加 `start=0&max_results=1` 时，httpx 与 urllib 均返回 HTTP 406。此前将其归为传输头差异不准确。
- `ArxivClient.get_work_page()` 对已知 ID 使用不带分页参数的 `id_list` 请求。用户重跑后确认 HTTP 请求已通过，但 02 和 10 都触发 `ArxivProtocolError`；根因是 arXiv 响应将 `itemsPerPage` 声明为 10，而精确 ID 结果仅有 1 条，解析器错误要求二者严格相等。校验现改为允许实际条目数小于声明页容量，同时仍拒绝条目数大于容量；新增回归测试模拟该响应。
- 修复后的后端全量 pytest 136 passed；Ruff check/format 与根目录 `git diff --check` 通过。用户随后在本机确认 02 与替换后的 10 均成功解析并写入元数据快照。没有导入全文、复核许可或变更评测数据。

## P39 全文 RAG 小规模评测协议与基线（已完成）

- 制定小规模全文证据检索试点评测协议：8 个问题、四类各 2 个；BM25/Dense/Hybrid 各取 top-2，盲化候选池最多 54 项（含最多 6 个已知支持片段），最多 8 项双评，两条不可回答性判断；人工评分/判断总量硬上限 64。
- 指标限定 Hit@1/2、MRR@2、NDCG@2 和候选池内 Recall；试点只作探索诊断，不足以支持普遍质量提升声明。检索质量和生成答案忠实度分开评估。
- P41 已在明确批准的 10 篇全文上完成 40 项候选人工评分和两项不可回答性判断，生成 6 个可回答问题的 BM25/Dense/Hybrid top-2 探索性基线；结果和限制见 P41 记录及 [`research/P39-rag-evaluation-protocol.md`](research/P39-rag-evaluation-protocol.md)。全文、片段正文和逐条标签仍仅存本机忽略目录。

P36 已完成人工盲审及候选池内评测：8 个困难查询、101 个候选判断，保持未入池论文为未判断。Large Dense 在该挑战集分数最高，但报告明确 `exploratory_only=true`、`quality_claim_allowed=false`。P37 已在同 101 对候选上完成助手建议与人工评分的一致性诊断：完全一致率 30.7%、MAE 1.218、二次加权 Kappa 0.310；这不是独立 LLM-as-judge 校准，仍为探索分析。

## 最终收尾核验（2026-09-25）

- 实施范围 P01–P38 已完成并提交为 `bde769c`，分支已推送；README 已整理策略选型、检索质量证据和限制，开发说明及阶段记录已同步。
- 后端全量 pytest 133 passed；Ruff check/format、Web Prettier、TypeScript、隔离生产构建、npm/pip 依赖审计及 `git diff --check` 均通过。前端本地依赖目录已按锁文件恢复并确认 Next/Playwright 可执行文件存在。
- 用户提供的最终 E2E 运行结果为 21/21 通过且退出码 0，干净退出确认完成；此前 teardown 异常的重跑不作为通过依据。本轮未更改 Web 应用代码。
- 最终独立复核发现 Agent 读取本地文献库时会将 OpenAlex 与 arXiv 各自的 30 条相加，可能超过界面承诺的 30 条上限。现改为合并后按年份降序排序并截取最多 30 条；新增回归测试。全量后端 pytest 134 passed，Ruff check/format 和根目录 `git diff --check` 通过。`uv run` 被本机 uv 缓存权限拒绝，因此使用已存在的锁定虚拟环境直接运行等效命令。
- P38 复核改动已提交并推送；后续阶段按单独任务推进。

## P37 既有助手标签与人工评分一致性（已完成）

- 重建并核验 P36 的冻结候选池与来源审计，将每个人工 query-paper 对与 P13 `suggested_grade` 配对；不发起模型 API 调用，不生成新标签。
- 101 对评分完全一致率 30.7%，相差不超过 1 级为 64.4%，MAE 1.218，二次加权 Cohen's kappa 0.310。助手给 81 项标 0，人工仅给 20 项标 0，提示明显的等级分布差异。
- 困难查询按旧 AI 标签分歧选择，候选也来自各排序器前五，且仅一位评审；因此结果不能视为一般性 judge 质量、校准或检索质量证据。JSON 报告位于 Git 忽略的 `backend/reports/p37-assistant-human-grade-agreement.json`。
- 详见 [P37 一致性诊断](research/P37-assistant-human-grade-agreement.md)。

## P35 README 策略选型与检索质量迭代（已完成）

- 参考 [car-selection-assistant README](https://github.com/CN-Discretemathematics/car-selection-assistant) 的组织方式，补充 PaperTrail 按研究需求选择元数据检索、BM25、可选 Dense/Hybrid、引用扩展和跨来源 DOI 去重的理由与证据边界。
- 将 P05、P14、P17 整理为评测迭代表，呈现题集范围、当阶段回答的问题与限制；没有虚构 v2/v3/v4 的质量提升，也没有把 AI 生成标签或 Embedding 厂商基准写成 PaperTrail 的质量证明。
- 增补说明：未来质量声明需要人工审核或独立校准的标签、多主题查询与全文证据准确性评估；当前未校准 LLM-as-judge 不计作标注。
- `pnpm run format:check` 与根目录 `git diff --check` 均通过；本轮只验证文档格式与差异空白，不需要运行代码测试。

## P36 盲审候选池与人工相关性复评（已完成）

- 从同一 P13 冻结数据的 P14/P17 结果中，选取 P14 方法分歧较大的查询并按意图桶分层；BM25、Small Dense/Hybrid、Large Dense/Hybrid 各取前 5 名后按 query-paper pair 去重。
- 新增有界池生成器和 CLI，严格检查数据集标签状态、SHA、snapshot、查询 ID 与论文元数据哈希；最大 8 个查询、每种配置前 5 名、总候选判断不超过 200。本次生成 8 个查询、101 个候选项。
- 评审 CSV 及机器 JSON 不含单篇排序来源、名次或 AI 建议等级；来源映射、选择方法和输入报告 SHA 单独保存在本机忽略审计文件。记录明确该样本由旧 AI qrels 的系统分歧选择，只能作为 challenge set。
- 用户完成人工盲审，101 项均有 0–3 等级；导入器验证 row ID、完整性、评分范围、人工审核标记和来源元数据。Excel Windows-936 保存造成的 5 个摘要 codepage 转换已明确记录。
- 仅针对盲审池 top-5 产生 MRR/NDCG 对照，未入池论文保持未判断，不计算全语料 Recall。Large Dense 在这 8 个定向困难查询上领先；单评审和旧 AI 标签分歧抽样使结果只能作为探索诊断，不能声称总体质量提升。
- 全量后端测试 `130 passed`；Ruff check/format、Web 格式检查和 `git diff --check` 通过。`uv run` 因本机 uv 缓存目录权限失败，使用 backend 已存在的 `.venv` 运行相同工具；pytest 临时目录改到仓库内以避开系统 Temp 权限拒绝。

## P34 首页文案调整（已完成）

- 删除眉题“从问题出发，沿证据前进”。
- 首页主标题改为“Agent 文献检索分析系统”；副标题保留“搜索可信学术来源，比较关键研究。”，移除“并让每个回答都能回到原文证据”。
- 仅调整展示文案；Web 格式与类型检查通过。

## P33 研究助理上下文衔接（已完成）

- 根因：Web Agent 代理之前只发送当前问题，未附左侧检索条件，也不保留前序问答；“根据刚才的检索结果”因此没有可引用的上下文。
- 前端现在随 Agent 请求发送最近 4 轮对话和最近一次成功的左侧搜索来源、查询词、年份范围及已载入页数。后端依照这些结构化条件重新从固定来源获取最多 30 篇书目元数据并作为本轮证据；不信任浏览器直接提交的论文文本。对话历史只帮助解析指代，不作为事实证据。
- 新检索开始时先清空旧上下文；若新检索失败，Agent 不会误把上一次成功搜索当作当前结果。
- 运行记录新增 `current_search_context`，界面展示当前附带的来源和范围并允许清空对话。元数据只用于书目型回答；论文结论仍要求许可全文证据。arXiv 多页重读遵守现有限流节奏。
- 后端 118 项测试、Ruff、OpenAPI、Web 格式/类型检查及隔离 Webpack 生产构建通过。Playwright 复用用户已运行的开发服务，三视口 21/21 E2E 通过；具体执行范围见 [P33 Agent 上下文记录](research/P33-agent-context-acceptance.md)。

## P32 远程来源年份检索过滤（已完成）

- 用户截图证明 P31 首版年份筛选只作用于已载入页：例如 OpenAlex 命中总数仍是全年份，已载入 30 条恰好均不在区间内，造成“当前 0 条”的误导。用户质疑正确；不能据此认为范围内没有论文。
- OpenAlex 搜索代理与后端端点现在传递 `from_year/to_year`，由 OpenAlex 按出版日期过滤并返回过滤后的匹配数；arXiv 由 `submittedDate` 按提交日期过滤。翻页请求继续携带相同范围。UI 明确说明远程检索年份语义，并提示改范围后重新搜索；本地库仍只对已载入元数据筛选。
- 后端 API 测试锁定年份参数传递，Web E2E 锁定首批和下一页均携带年份范围。后端 116 项测试、Ruff check/format、Web 18 项 E2E、Prettier/TypeScript 和 OpenAPI 导出均通过。完整验收见 [P32 记录](research/P32-year-filter-acceptance.md)。

## P31 检索结果逐批加载（已完成）

- 初始界面每个远程来源固定查询第一页 10 条，虽然后端来源 API 支持分页，用户无法看到后续结果。新增“加载更多”：OpenAlex 和 arXiv 每次拉取 10 条，本地库按来源 offset 分批拉取并保留已展示记录；跨页按来源 ID 去重。
- 进度信息显示匹配总数与当前列表数。分页受单次最多 10,000 条的现有边界约束，到达上限会提示缩小查询范围。年份仅作用于已载入结果的 P31 初版限制已在 P32 修复。
- arXiv 尾页原有 start 上界与 10 条分页不对齐；已允许最后一个不超过 10,000 范围的请求，并同步 OpenAPI。
- Web Prettier/TypeScript、18/18 三视口 Playwright E2E、隔离 Webpack 生产构建通过；后端 116 项测试、Ruff 与 OpenAPI 导出通过。E2E 复用了用户 3000 端口开发服务，没有停止或改写 `.next`。

## P30 引用扩展终答格式失败诊断（已验收）

- 用户复测截图显示 OpenAlex 检索与引用扩展工具均成功，返回 6 篇来源；首次终答是无效 JSON，单次结构修复得到有效 JSON，但仍将元数据任务标记为 `insufficient_evidence`。当前可见问题是 Agent 对仅要求标题/年份/链接/引用关系的任务过度拒答，不是来源 API 或引用拓展工具故障。
- 系统提示与修复提示现明确：只要至少一部分请求字段由成功工具观察支持，就回答可用子集并标明缺失项；没有全文本身不构成元数据任务证据不足。论文 findings/methods 结论仍须有许可全文证据。
- 本地回归覆盖输出诊断类别和元数据充分性提示；用户确认引用扩展回答已正常，P30 验收完成。

## P29 arXiv HTTPX 406 请求差异（已验收）

- 复现证据：同一个 arXiv 查询 URL、相同的 `Accept: application/atom+xml` 与 `User-Agent: Python/<version>` 下，用户本机 `urllib` 返回 HTTP 200，而 HTTPX 0.28.1 返回 HTTP 406；PaperTrail 将非 2xx（除 429）包装成 502 `arxiv_unavailable`。
- HTTPX 明确发送 `Accept-Encoding: identity` 并由 mock 单测锁定；用户本机确认 arXiv 检索成功，P29 live 验收完成。详情见 [`research/P29-arxiv-http-406-diagnostics.md`](research/P29-arxiv-http-406-diagnostics.md)。
- 定向测试：`tests/test_arxiv_client.py` 8 passed；目标文件 Ruff check/format 通过。未从自动化环境再次请求 arXiv。
- 验收文档：[P29 诊断与验收](research/P29-arxiv-http-406-diagnostics.md)。

## P28 生产构建与依赖安全审计（已完成）

- 为避免影响用户正在使用的 Next 开发服务，在忽略目录 `.local/p28-build-check` 复制 Web 源码，排除 `.env.local`、缓存和测试产物；构建结束后已删除临时副本。
- Turbopack 拒绝了临时副本指向仓库依赖目录的 junction。改用 Webpack 构建后通过：优化生产编译成功、TypeScript 成功、8 个静态页面生成成功、全部 App 路由产物完成。
- 构建检查的是当前 P27 源码，没有覆盖开发服务的 `.next`；详情见 [P28 验收](research/P28-isolated-production-build-acceptance.md)。
- `pnpm audit --audit-level moderate` 与通过 `uvx` 临时启动的 `pip-audit --path .venv\Lib\site-packages` 均报告未发现已知漏洞；`uv.lock` 与 `pnpm-lock.yaml` 未改动。

## P27 Agent 回答安全 Markdown 渲染（已完成）

- P26 本机复验截图显示双来源搜索成功，用户确认进入下一步。
- Agent 回答现支持安全渲染标题、列表、加粗/斜体、行内代码和 HTTPS 链接；链接只允许 OpenAlex、arXiv 与 DOI 官方域名。用 React 节点渲染，不将模型输出当作 HTML。
- E2E 覆盖格式渲染和 `javascript:` 链接不生成可点击元素；15/15 三视口通过。Web format/typecheck 通过。
- 根 `git diff --check` 通过；验收条件与边界见 [P27 验收](research/P27-safe-agent-answer-markdown-acceptance.md)。未引入依赖或调用外部服务。

## P26 arXiv 工具错误诊断（已完成）

- 用户在运行 trace 中观察到两次 `search_arxiv_metadata error`。根因表现为运行中的后端返回 `arxiv_unavailable`；项目客户端在允许外网访问的进程中用同一年份查询可成功，因此检索查询构造有效，当前后端进程出站访问失败。
- Agent trace 现在记录安全白名单错误码，UI 显示例如 `error · arxiv_unavailable`。同一次 Agent 执行中某来源失败后，Harness 拦截该来源后续外呼并记录 `source_unavailable_after_failure`。系统指令要求停止重复调用并说明来源不可用/回答不完整。
- 后端全量 114 passed（2 条上游弃用 warning），Ruff check/format 与 OpenAPI 导出通过；Web Prettier、TypeScript、15 项 E2E 全通过；根 git diff --check 通过。E2E 用例确认 trace 展开后显示错误码。生产构建随后在 P28 隔离目录完成。
- 用户随后在本机重启后端并成功完成 arXiv 检索，运行记录可见成功结果；P26 本机验收完成。实现与诊断记录见 [P26 验收](research/P26-arxiv-tool-diagnostics-acceptance.md)。

## P25 跨来源补充检索（已完成）

- 验收条件见 [P25 验收](research/P25-cross-source-discovery-acceptance.md)。Agent 指引在广泛发现时结合 OpenAlex 与 arXiv；工具仅在各来源客户端启用时提供。OpenAlex 结构化年份/OA 过滤保持原样，arXiv 新增 `submittedDate` 年份范围，二者年份语义不同，且 arXiv 不提供 OpenAlex OA 保证。
- Citation 契约加入 DOI 与 `alternate_sources`；仅规范化 DOI 完全一致才归并，OpenAlex 作为主记录并保留 arXiv 链接。不同 DOI、缺 DOI 记录分开。研究工作区卡片显示 DOI 与备用来源；新增 E2E 覆盖该链接展示。
- P12 benchmark 升至 v5，新增 `cross_source_discovery_deduplicates_only_matching_doi` 场景，报告 10/10 通过；夹具标题使用 `TEST-*` 并标记 `synthetic=true`，来源 ID 保持生产契约所需格式，质量声明仍关闭。
- 验证：后端 113 passed（2 个依赖弃用 warning）、Ruff check/format 与 OpenAPI 导出通过；Web Prettier、TypeScript 与 15/15 E2E 通过；根 `git diff --check` 通过。E2E 复用了用户已运行的 localhost:3000 开发服务。未运行 Next 生产构建，因为它会与该服务共享 `.next` 输出目录。Python 环境未安装 `pip-audit`；`pnpm audit` 访问 npm registry 被 EACCES/fetch failed 拒绝。
- 未调用 OpenAlex/arXiv 或 LLM/embedding API，未读取/更改用户数据库或报告。P25 功能与现有自动化验收已完成；生产构建留待服务停止后执行，依赖审计须在相应工具/网络可用时重试。

## P24 离线评测逐场景诊断（已完成）

- P23 已将引用图检索闭环加入 P12；本阶段补充逐场景的结构化通过检查与明确失败原因，方便从报告直接区分预期状态错误、越权执行及指标不符。验收条件见 [P24 验收](research/P24-benchmark-diagnostics-acceptance.md)。
- P12 schema 升级至 v4。每个 case 会列出 status match、无越权执行、期望指标逐项 expected/actual/passed；若失败，会给出稳定的 `status_mismatch`、`unauthorized_tool_execution` 或 `metric_mismatch:<field>`。Agent 汇总提供 failed count 与场景 ID 列表；`passed` 由这些检查推导。
- 定向测试 4 passed；后端全量 pytest 110 passed，Ruff check/format、OpenAPI 导出与根 `git diff --check` 通过。pytest 有 2 条依赖弃用 warning。Web 源码未改，未重跑 Web 格式/类型/构建/E2E；没有依赖变更，未跑 pip/pnpm 审计。根 foundation/source-review 脚本缺失，未运行。
- 未访问外部 API/模型/真实数据库，未改既有 ignored reports；P24 已完成。README、开发说明、P12/P24 验收记录与任务台账已同步。

## P23 Citation graph 离线 benchmark（已完成）

- 用户已验收引用扩展 UI：种子与候选来源卡片显示年份、OpenAlex ID 和引用方向，回答将 citation links 限定为 discovery metadata；筛选后的参考候选为空时也明确说明。
- 本阶段把上述工作流加入 P12 固定离线评测，使用生产 Harness 与受控工具/模型，不访问 OpenAlex、真实数据库或模型服务。验收条件见 [P23 验收](research/P23-citation-graph-benchmark-acceptance.md)。
- 已升级至 P12 report v3，新增第 9 个 Agent 场景；synthetic W900/W901 只用于满足生产 ID schema，不对应真实作品。重复候选合并成一个 citation，2023/2024 年份和两个方向关系均在报告中保留；回答注明引用边仅为发现元数据。
- 验证：P12 定向测试 3 passed；后端全量 pytest 109 passed，Ruff check/format 与 OpenAPI 导出通过，根 `git diff --check` 通过。Web 源码未改，本阶段未重跑 Web 构建/E2E。根 foundation/source-review 检查脚本在当前检出中不存在，未运行。未访问外部 API/数据库/模型；P12 质量声明关闭、费用未测。
- P23 已完成。README、开发说明及 P12/P23 验收文档已同步；不增加人工审核负担或 LLM-as-judge 标签。

## P20 Agent 请求超时对齐（已完成）

- 用户本机日志显示 `POST /api/agent` 在 15 秒以 503 结束，而后端 Agent 仍在处理；根因是 Web 通用代理固定 15 秒超时，短于 Agent 的默认 45 秒/可配置最高 120 秒期限。
- 保留搜索、健康等 API 的 15 秒超时，只将 Agent 到后端请求上限改为 125 秒，为 Agent 允许的最长运行时间留 5 秒响应编码余量。前端 Agent 调用本身没有更短的客户端 timeout。
- 验证：Web Prettier、TypeScript、生产构建和根 `git diff --check` 通过。E2E 未运行成功：Playwright 启动额外 Next dev 实例时遇到现有用户开发服务占用共享 `.next` dev 锁；未停止用户服务。当前前端状态代理和后端健康接口返回 ready。没有重复发起真实模型请求，以免增加用户 API 费用；需用户本机重试超过 15 秒的 Agent 请求验收代理等待行为。
- 后续用户本机实测成功生成带种子及引用候选的研究回答，超过旧代理限制的 Agent 流程现可完整返回；P20 本机验收完成。

## P21 引用卡片 provenance（已完成）

- 先定义 [P21 验收](research/P21-citation-provenance-ui-acceptance.md)：Agent 引用对象需保留 OpenAlex 元数据中已观察到的出版年份和引用方向；UI 来源卡片展示“参考文献/被引”及年份。
- `Citation` 响应新增年份和有类型的关系字段；Harness 只从工具 observation 采集这些值，并跨重复 observation 合并关系，忽略无效关系，缺失年份保留 null。
- 来源卡片显示可用年份、引用方向与种子 ID。普通搜索/作者条目没有引用关系字段时不生成关系标签。OpenAPI schema 已同步。
- 验证：后端 107 passed；Ruff check/format、OpenAPI 导出通过。Web Prettier、TypeScript、生产构建通过；15 项 E2E 在现有 3000 开发服务上通过三种视口运行。E2E 采用一次性临时配置并已删除，不覆盖用户现有 Playwright 配置。无真实来源/模型 API 调用。

## P22 Agent 结构化终答恢复（已完成）

- P21 后用户本机复验显示 Agent 偶发返回 `invalid_model_output`。Harness 现仅在剩余步数内追加一次格式修复 user turn，并向模型隐藏工具定义；修复结果仍须通过原 JSON schema 和引用 allow-list。若无剩余步数、修复仍错或模型试图调用工具，继续安全拒绝并返回脱敏 warning。
- 增加 FakeModel 测试覆盖修复成功、格式修复二次失败、预算耗尽与修复轮次工具调用拦截。后端 109 passed；Ruff check/format 通过。未调用真实模型、OpenAlex 或 embedding API；验收条件和结果见 [P22 验收](research/P22-agent-structured-output-recovery-acceptance.md)。

## P19 研究闭环与 README（已完成）

- 按 [P19 验收](research/P19-workflow-readme-acceptance.md)实施。用户希望 Agent 从研究问题出发提升文献集合，并可沿论文参考文献/被引关系拓展，完善 README 的策略取舍和检索质量展示；本阶段不制作图片/视频演示素材。
- OpenAlex 官方 API 文档确认 Works 提供 `referenced_works`、`cited_by_api_url` 与 `filter=cites:W…` 路径；已新增固定 Works API 上的受限引用拓展，以及年份范围和 OA 条件的结构化筛选。
- Agent 系统指令指导先检索、再按需扩展一跳并去重比较；引用边只作为发现线索，OA 标记不等于全文许可，论文方法/结论仍需已批准全文证据。
- 新增 API 客户端和 Harness 离线契约测试，涵盖年份/OA 过滤、参考/被引方向、流程决策、参数拒绝和来源引用。后端全量测试 106 passed；Ruff、格式、OpenAPI 导出通过。Web format/typecheck/build 通过；E2E 15/15 通过。根 `scripts/check_foundation.py` 与 `scripts/check_source_review.py` 在当前检出中不存在，未运行；依赖警告仅为 Starlette/httpx 上游弃用提示。
- README 加入 v1 BM25、v2 全文 RAG、v3 Dense/Hybrid、v4 引用图发现能力演进；并列展示 Small 与 Large 同一 100 Works/30 queries 数据对照。指标对应 assistant-labeled qrels，明确仅作探索诊断；Large 的某项指标提升不能称为总体质量改进。未实现 LLM-as-judge，因为没有可校准的 judge 数据集，自动评分不能作为人工标注。
- 本阶段未发起真实 OpenAI/Embedding API 调用，未改动/读取用户私有数据库或新增全文。详细结果见 [P19 验收](research/P19-workflow-readme-acceptance.md)。

## P17 Embedding 模型升级（已验收）

- 验收条件见 [P17 验收](research/P17-embedding-model-upgrade-acceptance.md)。根据论文语料与问题可能中英文混合，选择 OpenAI `text-embedding-3-large` 作为 Dense/Hybrid 可选模型：官方称其为英语和非英语任务中当前能力最强的 Embedding，MTEB 64.6%（Small 62.3%）；标准输入价 `$0.13/百万 tokens`，约为 Small 的 6.5 倍。BM25 继续是默认，不会自动触发 Embedding API。
- 示例配置、开发说明、README 和本机 `.env` 已切换到 Large、3072 维、`$0.13/百万 tokens`；本机 API key 原值保留且未输出。索引按模型/维度隔离；Small 旧索引保留，Large 查询需先重新索引。
- 新增 Large/3072 请求契约测试；后端全测 100 passed，Ruff check/format、OpenAPI 导出、Web Prettier/typecheck、`git diff --check` 通过。测试只用 HTTP mock，没有调用 OpenAI。
- P14 Small 历史结果未覆盖。用户已在独立报告中完成同数据集 Large 复评：100 篇、30 queries、23,960 tokens，估算 `$0.0031148`；数据 SHA/snapshot 一致，报告仍是 AI qrels 探索分析。Dense 的 NDCG@10 提升但 Hit@1/MRR 略降；Hybrid MRR/NDCG 提升。不能宣称 Large 普遍更好。
- 报告的 `reproducibility.command` 未记录自定义输出参数；数据与结果本身无异常。此项在 P18 修复 CLI provenance 时解决，不重复产生 API 费用。根 `scripts/check_foundation.py` / `check_source_review.py` 当前检出缺失，已在 P17 验收记录中如实注明。

## P18 Agent 离线失败场景矩阵（已完成）

- 先定义 [P18 验收](research/P18-agent-eval-acceptance.md)，再扩展 P12 生产 Harness mock 评测：加入参数错误、伪造引用、结构错误终答、模型不可用和工具预算耗尽等场景，并保留提示注入和工具错误恢复。
- 同步修复 P12/P14 CLI 报告中的可复现参数：记录真实 argv 和解析后的输出路径；不改写既有忽略报告，不调用外部模型/API。

- P12 benchmark schema 升级到 v2，使用生产 `AgentHarness` 加受控 mock，8/8 场景通过：保守拒答、提示注入和越权工具拦截、非法参数、工具失败、伪造引用、无效终答 JSON、模型不可用、工具预算耗尽。总越权执行为 0；该结果仅验证确定性 Harness 契约，不代表真实模型回答质量。
- 将含义不准确的 `tool_side_effect_executions` 改为 `registered_tool_executions`。P12/P14 新报告保存实际命令参数、解析后的输出路径、runner 哈希和数据哈希；新增 CLI 定向回归测试。P17 已产生的 Large 报告不修改、不重跑。
- 离线报告在 Git 忽略的 `backend/reports/p18-agent-eval-report.json`，synthetic、无网络/真实数据库/真实模型，费用为 null，质量声明禁用。
- 后端全量测试 101 passed；Ruff check/format、OpenAPI 导出、Web Prettier/typecheck、`git diff --check` 通过。Web build/E2E 未重跑（无 Web 运行代码变更）；根检查脚本因当前检出缺少 `scripts/check_foundation.py` 与 `scripts/check_source_review.py` 而未执行。详见 [P18 验收](research/P18-agent-eval-acceptance.md)。

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
- 首次 GitHub Actions 发现 SQLite 兼容问题：部分 SQL 将 `2_000` 作为数字字面量，CI 使用的 SQLite 不支持该写法；改为 `2000` 后，本机 99 项测试通过，后续 GitHub Actions 全部通过。

## P16 仓库迁移与发布（2026-09-24）

- 将 GitHub 仓库改名为 `papertrail`，更新本机 `origin`，并将已验证的 PaperTrail 根目录版本快进发布到默认分支 `main`。
- 按用户先前要求，删除其余 22 个旧项目远程分支；21 个旧项目开放 PR 已关闭，PR #1 随 `main` 更新显示为已合并。确认远程只剩 `main` 且无开放 PR。
- 更新 GitHub 仓库简介与 topics；最终 Actions 运行通过。旧项目文件只保留在本机 Git 忽略的 `.local/legacy-computer-project/` 归档中，不在发布树中。

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
