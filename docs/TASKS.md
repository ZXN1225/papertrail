# 任务台账

状态：done=验收完成；active=当前实施；todo=未开始；blocked=有具体外部阻塞。阶段完成后等待用户确认。

| ID  | 任务                                                    | 前置                    | 状态   |
| --- | ------------------------------------------------------- | ----------------------- | ------ |
| P01 | 项目章程、迁移评估、来源/Agent/评测边界                 | 用户确认方向            | done   |
| P02 | 独立应用骨架、锁文件、CI 与启动说明                     | P01 用户确认            | done   |
| P03 | OpenAlex 固定 API 客户端与契约测试                      | P02                     | done   |
| P04 | 元数据快照、目录、来源 lineage                          | P03                     | done   |
| P05 | BM25 与人工检索金标评测                                 | P04                     | done   |
| P06 | 受限 Agent 工具循环与引用契约                           | P05 BM25 baseline       | done   |
| P07 | OpenAlex 研究 API 能力补全与 Agent Harness 可观测性     | P03、P06                | done   |
| P08 | arXiv 第二来源、ID 归一化与精确 ID 导入                 | P04、P07                | done   |
| P09 | 全文许可登记和开放许可论文 RAG                          | P04、P06、P07           | done   |
| P10 | Embedding、Hybrid 与排序消融                            | P05、P09                | done   |
| P11 | 研究工作区 Web UI 与 E2E                                | P07                     | done   |
| P12 | 端到端 benchmark、工程指标与作品集交付                  | P05、P07、P09、P10、P11 | done   |
| P13 | 扩展论文检索评测集与 AI 标注诊断                        | P05                     | done   |
| P14 | 检索方法对照与失败查询诊断                              | P13、P10                | done   |
| P15 | 简历展示文档、GitHub CI 与收尾回归                      | P14                     | done   |
| P16 | 迁移当前仓库为 PaperTrail 并发布                        | P15                     | done   |
| P17 | 升级 Embedding 模型并完成同集复评                       | P14                     | done   |
| P18 | Agent 离线失败场景矩阵与复现信息                        | P12、P17                | done   |
| P19 | 完整研究工作流与 README 策略/检索质量说明               | P11、P18                | done   |
| P20 | 修正 Web Agent 代理短超时导致的假离线                   | P19                     | done   |
| P21 | 在来源卡片展示引用年份与关系                            | P19                     | done   |
| P22 | Agent 结构化终答格式错误的有界恢复                      | P18、P21                | done   |
| P23 | Citation graph 工作流的离线 Harness benchmark           | P19、P22                | done   |
| P24 | 为离线 benchmark 增加逐场景诊断                         | P12、P23                | done   |
| P25 | 跨 OpenAlex/arXiv 补充检索与 DOI 去重                   | P19、P24                | done   |
| P26 | arXiv 工具失败诊断、避免重复失败请求                    | P25                     | done   |
| P27 | Agent 回答的安全 Markdown 渲染                          | P26                     | done   |
| P28 | 隔离生产构建与依赖安全审计                              | P27                     | done   |
| P29 | 诊断并修复 arXiv HTTPX 请求被 406 拒绝                  | P28                     | done   |
| P30 | 引用扩展回答失败的结构化输出诊断                        | P29                     | done   |
| P31 | 为文献检索增加逐批加载结果                              | P11、P25                | done   |
| P32 | 将年份范围传递到远程来源检索                            | P31                     | done   |
| P33 | 将左侧检索结果与 Agent 多轮对话衔接                     | P19、P31                | done   |
| P34 | 调整首页主标题与说明文案                                | P33                     | done   |
| P35 | 重组 README 检索策略选型与质量迭代证据                  | P14、P17、P19           | done   |
| P36 | 盲审排序候选池与人工相关性复评                          | P14、P17、P35           | done   |
| P37 | 既有助手 qrels 与人工盲审评分一致性诊断                 | P36                     | done   |
| P38 | 最终代码复核：统一 Agent 文献库上下文条数上限           | P37                     | done   |
| P39 | 制定低负担全文 RAG 质量评测协议                         | P38                     | done   |
| P40 | 准备本地许可全文候选文件、导入条件清单与小规模问题草案  | P39、用户提供 PDF       | done   |
| P41 | 复核许可、补齐元数据并导入试点语料，冻结问题和候选池    | P40、论文所有者逐篇复核 | done   |
| P42 | 修复 arXiv 精确 ID 元数据查询（406 与 Atom 页大小校验） | P40                     | done   |
| P43 | 改进 Agent 多论文证据采集与覆盖                         | P41                     | done   |
| P44 | 将 Agent Markdown 比较表安全渲染为可读表格并稳健处理输出 | P43                     | done   |
| P45 | 对齐六阶段路线并复核真实全文 RAG 基线缺口               | P44                     | done   |
| P46 | 在低标注预算内补齐/界定 BM25、Dense、Hybrid 真实全文基线  | P45、用户要求继续        | done   |
| P47 | 按冻结基线做单项 RAG 改进与消融，记录质量/成本/延迟      | P46                     | done   |
| P48 | 实现受控运行时 Agent Skills 注册、调用与安全验收         | P47                     | done   |
| P49 | 汇总可公开评测材料、README 与 GitHub 最终交付             | P46–P48                 | done   |

六阶段路线状态：①能力与证据边界已说明；②10 篇许可全文、8 问题、127 个候选评分和 2 个不可回答判断已完成；③BM25/Dense/Hybrid top-5/10 真实全文基线已完成，仅属单评审探索结果；④P47 已完成一项冻结基线反事实重排试验，但未观察到目标质量改善，默认检索不变；⑤P48 已完成 Skill 目录、激活和工具范围约束的离线实现，并通过一次真实模型现场验收；⑥README 已更新基线表格、完成最终变更审查并推送到 GitHub。E2E 和依赖审计因本机开发服务锁冲突及受限网络/uv 缓存权限未能完成，见进度记录。不得把 P44 的 UI/Agent 修复或 P01–P44 历史任务表视为六阶段路线结束。

P40 当前第 `10` 篇已替换为 arXiv `2310.11511v1`（Self-RAG），对应 TXT 和 manifest 已重建；用户已验收 P42 修复，02 与 10 元数据均解析成功。用户确认完成 02–10 许可复核和全文导入；本机数据库核验 10/10 文档 approved、共 417 个片段且向量全部覆盖。用户完成 40 条盲审评分与 2 条不可回答性判断；P41 的 BM25/Dense/Hybrid 探索性基线已生成。P43 的工具/引用契约测试及用户 live 双论文验收均已完成：两个来源各有成功的全文检索和对应证据摘录，单篇缺证据场景仅有 mock 覆盖。P44 已完成功能实现和用户 live 浏览器验收：表格行列、横向滚动及来源显示正常；输出预算设为 4096，显式 arXiv ID 内容请求直接查许可全文。后端测试 141 项与静态检查通过；Playwright E2E 受隔离副本 pnpm 符号链接解析问题阻塞，未执行。扩展候选池和新增人工判断须先得到用户明确同意。

P46 已按用户授权扩至 129 项人工判断：127 个候选评分 + 2 个不可回答判断。87 行增量盲审与独立 lineage 审计仅在 Git 忽略目录，既有 40 条评分表未改写。用户现已填写完成；评估器校验全部评分、支持说明、来源 lineage 与问题集完整后成功生成报告。宏平均中 Hybrid 的 Hit@1/MRR 较高，Dense 的 NDCG 与候选池内 Recall 较高；Hit@10 三种方法均为 1.000。完整 overall/per-bucket 表已同步 README 和 P39 阶段记录，指标仅属 6 个可回答问题、单评审探索性比较。

P47 已完成一项针对多论文问题的受控反事实检查：来源轮转重排未改善 Q05/Q06 Hybrid top-2 的 grade≥2 来源覆盖（重排前后为 0/2、1/2），top-5 均为 2/2；六题总体指标基本不变。因此不改生产排序，也不声称质量改善。基线评测细节见 [`research/P39-rag-evaluation-protocol.md`](research/P39-rag-evaluation-protocol.md)。

P48 第一版运行时 Skills 已实现并完成现场验收：`backend/app/agent/skills.json` 定义三个提示词工作流和固定工具子集；Harness 以 `activate_skill` 载入目录，激活后只向模型展示已启用且被该 Skill 允许的工具，每次运行最多一个 Skill。目录拒绝未知工具；没有脚本执行、任意 URL、文件、SQL 或写库权限。根 `skills/` 开发工作流与运行时目录明确分离。三项定向安全回归及后端全量 144 项测试通过；Ruff check/format 通过。用户提供的真实模型 trace 显示 `evidence_synthesis` 成功激活并按两个来源 ID 分别检索证据，工具均返回 `ok`，回答附带两条来源证据卡片。结论仅限于此现场样例，不代表普遍模型遵从率。详见 [`research/P48-agent-runtime-skills.md`](research/P48-agent-runtime-skills.md)。

P05 的 80 项 qrels 已由用户导入为 human-reviewed v2，且 BM25 候选/人审对照已完成；小样本报告仍为 exploratory-only。细节见 [`research/P05-acceptance.md`](research/P05-acceptance.md) 与 [`research/P05-qrels-review.md`](research/P05-qrels-review.md)。P09 本机验收记录见 [`research/P09-acceptance.md`](research/P09-acceptance.md)。P10 实现、自动测试和用户本机 live smoke 均已完成。已增加本地 qrels 复核包工具，详见 [`research/P05-review-workflow-acceptance.md`](research/P05-review-workflow-acceptance.md) 与 [`research/P10-acceptance.md`](research/P10-acceptance.md)。P12 离线 benchmark、mock Agent 安全评测和作品集文档已完成，结果及 E2E 清理限制见 [`research/P12-acceptance.md`](research/P12-acceptance.md)。

用户已取得 OpenAlex 与 OpenAI Key；OpenAlex Key 已留在本机 `.env`，P03 完成一次真实搜索验证。Key 不通过聊天传递；本轮没有调用 OpenAI。

P13 已建立 100 篇/30 查询/3,000 pair 的候选评测集；按用户选择，生成了 AI 填分副本和探索性 BM25 诊断报告。原人工复核包保持未审核状态，AI 标签不作为人工金标。验收及指标限制见 [`research/P13-acceptance.md`](research/P13-acceptance.md)。

P14 已完成 BM25/Dense/RRF 的同查询对照、分桶指标和失败查询诊断；使用 `text-embedding-3-small` 产生 23,960 输入 tokens。报告仅作 AI-qrels 探索分析，`quality_claim_allowed=false`。详见 [`research/P14-acceptance.md`](research/P14-acceptance.md)。

P15 的 README、架构/评测介绍、CI、全文 PDF 忽略规则与最终回归已完成。P16 已将仓库改名为 `papertrail`，将完整代码推送到默认 `main`，清理旧项目分支并关闭旧项目 PR；GitHub Actions 最终运行通过。

P17 已验收：Large 复评与 Small 使用相同数据集哈希和 snapshot，指标/费用已核对；AI 标签仍是探索性诊断。报告命令未记录自定义输出路径的问题，以及根目录两个检查脚本缺失的事实，见 [`research/P17-embedding-model-upgrade-acceptance.md`](research/P17-embedding-model-upgrade-acceptance.md)。

P18 已完成：离线 Agent Harness 评测覆盖 8 个失败/安全场景，CLI 记录实际 argv 与输出路径；后端和 Web 静态检查均通过，报告为 `backend/reports/p18-agent-eval-report.json`（本机忽略文件）。详见 [`research/P18-agent-eval-acceptance.md`](research/P18-agent-eval-acceptance.md)。P19 已完成研究工作流闭环与 README 策略/质量说明，不包含演示素材。

P19 已完成：Agent 支持按用户要求应用 OpenAlex 年份/OA 过滤，并沿单篇种子论文做有界一跳引用扩展；README 展示检索策略选择、同集 Small/Large 对照与可信边界。详细验收见 [`research/P19-workflow-readme-acceptance.md`](research/P19-workflow-readme-acceptance.md)。本轮不加入未经校准的 LLM-as-judge 指标。

P35 已完成：README 增加按研究需求说明策略选择、原因和实测边界的矩阵，并将 P05、P14、P17 整理为评测迭代记录；区分流程能力、探索性排序诊断与可支持的质量结论，没有将 AI 标签或模型基准描述为质量提升证据。详见进度记录。

P36 已完成：用户盲审 101 个候选判断，按人工 0–3 分生成池内 top-5 对照报告。Large Dense 在 8 个定向困难查询上分数最高，但样本来自旧 AI 标签分歧筛选且仅一位评审，不支持总体质量声明；报告保持 `exploratory_only=true`、`quality_claim_allowed=false`。完整方法和边界见 [`research/P36-blind-pool-review.md`](research/P36-blind-pool-review.md)。

P37 已完成：离线配对 P13 助手建议和 P36 的 101 个人工评分，完全一致 30.7%、MAE 1.218、二次加权 Kappa 0.310。该挑战集存在选择偏差，不能视为 LLM-as-judge 校准或一般判断质量证明；无需新增 API 调用。分析方法与复现命令见 [`research/P37-assistant-human-grade-agreement.md`](research/P37-assistant-human-grade-agreement.md)。

P20 已修正 Agent 前端代理超时：普通请求仍为 15 秒，Agent 请求与后端最长 120 秒 deadline 对齐到 125 秒。用户随后成功完成种子与引用扩展实测，代理可以返回完整响应。阶段记录见 [`research/P20-agent-proxy-timeout-acceptance.md`](research/P20-agent-proxy-timeout-acceptance.md)。

P21 已完成：来源卡片显示 OpenAlex 候选年份和来自工具观察的引用关系；Harness 合并同一论文的多条引用边。后端 107 项测试、Web 15 项 E2E、格式/类型/生产构建和 OpenAPI 导出通过；见 [`research/P21-citation-provenance-ui-acceptance.md`](research/P21-citation-provenance-ui-acceptance.md)。

P22 已完成：终答格式错误仅在剩余轮数内尝试一次无工具修复，最终回答仍通过同一严格 schema 与引用 allow-list；修复失败仍拒绝。后端 109 项测试、Ruff check/format 通过；验收见 [`research/P22-agent-structured-output-recovery-acceptance.md`](research/P22-agent-structured-output-recovery-acceptance.md)。

P23 已完成：P12 离线 Agent 用例扩展为 9 项并升级报告 v3；新增主题检索到双向引用扩展场景，验证年份/关系 provenance、重复候选合并和 metadata-only 边界。全量后端 109 项测试及 Ruff、OpenAPI 导出通过，见 [`research/P23-citation-graph-benchmark-acceptance.md`](research/P23-citation-graph-benchmark-acceptance.md)。

P24 已完成：P12 报告升级到 v4，逐场景记录状态/授权/指标检查的期望值与实际值、失败 reason code 和失败场景汇总；故障注入测试验证诊断准确。全量后端 110 项测试、Ruff 与 OpenAPI 导出通过，见 [`research/P24-benchmark-diagnostics-acceptance.md`](research/P24-benchmark-diagnostics-acceptance.md)。

P25 已完成：Agent 可结合 OpenAlex 与 arXiv 检索，arXiv 支持按提交年份过滤；仅同 DOI 的来源合并并保留备用 arXiv 链接。P12 v5 离线 benchmark 的 10 个场景全部通过。后端 113 项测试、Ruff、OpenAPI 导出，Web Prettier、TypeScript 和 15 项 Playwright E2E 通过。生产构建未运行，以免覆盖用户正在使用的共享 `.next` 开发服务目录；详见 [`research/P25-cross-source-discovery-acceptance.md`](research/P25-cross-source-discovery-acceptance.md)。

P11 研究工作区及自动验收已完成，结果见 [P11 验收](research/P11-acceptance.md)。用户确认启动的 P12 已完成，阶段报告见 [P12 验收](research/P12-acceptance.md)。P05 qrels 已由用户复核导入并完成 BM25 对照，但数据集规模较小；P13/P14 标签未经人工核验，仅支持探索诊断，不支持对外质量声明。
