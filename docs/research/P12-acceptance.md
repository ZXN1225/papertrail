# P12 验收：端到端评测与作品集交付

## 范围与边界

本阶段交付一个一键可重复的离线 benchmark、可审查的 Agent/RAG mock 场景、工程观测报告和面向读者的 README 评测说明。所有离线夹具都必须显式 `synthetic=true` 且使用 `TEST-*` 标识；合成结果只证明评测管线与安全契约可运行，`quality_claim_allowed` 必须为 `false`。P05 qrels 尚未完成人工复核，因此不纳入金标质量声明。

本阶段不发起 OpenAI/OpenAlex/arXiv 网络请求，不使用真实用户数据库或其 PDF，不计算虚构的美元成本。Mock token 数和本机耗时须标明为模拟/本机测量，不得代表真实模型费用或线上延迟。真实模型小批量评估留待单独确认。

## 验收标准

1. 提供一个命令生成 JSON 报告，包含输入夹具 SHA-256、评测代码/模式版本、数据规模、运行时间、固定配置和重现命令；连续运行时排名与质量指标相同，只有运行环境时间戳/延迟可变化。
2. 在固定合成集合上并列运行 BM25、固定向量 dense 与 RRF hybrid，报告 Hit@k、MRR、NDCG 及每种方式的本机 p50/p95；清楚声明不是研究质量结论。
3. 通过真实 `AgentHarness` 和完全离线的受控模型/工具端口执行证据不足拒答、工具错误恢复、未知工具/提示注入负例；核对工具白名单、参数、未登记工具没有副作用，且注入后 Agent 安全收敛。TEST 标识不伪装成可引用的 OpenAlex/arXiv ID。
4. 对固定 `TEST-*` RAG span 做精确字符位置、证据 ID precision/recall 和 claim-in-excerpt 断言；生产存储、许可和引用 lineage 仍由全文集成测试覆盖。这些固定检查只验证 harness，不声称端到端生成质量。
5. 报告 Agent 用例通过率、被拦截的未登记工具尝试、未授权执行数、工具调用数、Mock token 计数、mock 流程 p50/p95 与错误数。费用标为 `not_measured`；不得以 Mock 数据推断线上表现。
6. 红队夹具中的论文文字/工具 observation 按不可信数据处理，不允许调用 fixture 允许集以外的工具或执行副作用。
7. 给出从干净本地 checkout 运行 benchmark 与测试的 Windows 命令；报告输出位于 Git 忽略的 `backend/reports/`，不得携带全文、密钥或本机数据。
8. README 和阶段记录说明真实评测尚缺的前置条件：人工复核 P05 qrels、确认真实模型小批量运行、明确实时价格/成本表与硬件环境。
9. 运行项目规定的后端 Ruff/pytest/OpenAPI、Web format/typecheck/build/E2E（如环境具备）、根目录基础检查与 `git diff --check`。未能运行的检查逐项记录原因，不能算通过。

## 完成本阶段后

同步 `docs/TASKS.md`、`docs/PROGRESS.md` 及 README，保留未解决条件，不自动开始下一阶段。

## 执行结果（2026-09-24）

- `python -m app.cli.evaluate_p12` 成功；离线报告位于被忽略的 `backend/reports/p12-offline-report.json`。检索方法为 BM25、Dense 与 RRF，Agent 场景 3/3 通过，提示注入中的越权工具尝试被拒绝，未授权执行 0 次；无网络、真实模型、真实数据库或费用。
- 后端 Ruff 检查与格式检查、全量 pytest（83 passed）、OpenAPI 导出、根目录 foundation/source-review 检查和 `git diff --check` 通过。Web Prettier、TypeScript、生产 build 通过。
- Playwright 三视口 15/15 用例均输出成功；但测试摘要之后 Windows 下 Next/Playwright 子进程未退出，停止进程后未获得正常退出码。因此这里只确认 15 条断言成功，不声称 E2E 命令以退出码 0 完成。
- 当时保留待办：人工复核 P05 qrels；真实 OpenAI 小样本评测需用户另行确认；没有真实模型费用、Agent 质量或线上延迟结论。后续状态见下方收尾复验。

## 收尾复验（2026-09-24）

- 发现 Windows 下由 Playwright 自己启动 Next dev server 时，所有断言结束后 runner 会挂起。开发说明现采用本机先启动 3001 服务、Playwright 复用已有 server 的方式。
- 按该方式重新运行 `pnpm run test:e2e`，15/15 passed，命令正常以退出码 0 结束。GitHub Actions 在 Linux 设置 CI 环境变量，会独立启动并回收 web server。
- P05 的 80 个 qrels 已于后续由用户审核；P13 的 3,000 个标签按用户决定保留 AI 标注、未人工核验。以上变化不改变本阶段离线测试结论或回答质量限制。

## P18 离线场景矩阵扩展（2026-09-24）

- 评测报告升级到 `papertrail-p12-offline-benchmark-v2`，Agent 场景扩为 8 项并全部通过：保守拒答、提示注入拒绝越权工具、错误参数、工具故障、未观察引用、格式错误终答、模型服务不可用、工具预算耗尽。
- 统一字段为 `registered_tool_executions`；只读 synthetic 检索不再误称为“副作用执行”。越权尝试计数为 1，越权执行数为 0；参数错误/工具错误/模型错误均在单场景 trace 计数中体现。
- P12/P14 CLI 报告现保存确切 `command_args`、解析后的 `output_path`、数据和 runner 哈希，便于保留多个运行结果。既有 P17 Large 报告不重跑、不改写；其输出路径由文件名可见，但其旧 reproduction 元数据没有 `output_path`。
- 全部数据仍为 `TEST-*` synthetic、无网络/真实数据库/真实模型，质量声明禁用、费用未测量。该矩阵只验证 Harness 的确定性契约与失败边界。

## P23 引用图发现工作流（2026-09-25）

- 报告 schema 升级为 `papertrail-p12-offline-benchmark-v3`，增加第 9 个 Agent 场景：OpenAlex 主题检索、按约束双向扩展引用图，再生成带来源的 metadata-only 回答。
- 合成 W900/W901 满足生产 OpenAlex Citation ID 校验；记录标题使用 `TEST-P23` 且 fixture 标记 `synthetic=true`，不对应实际作品。无网络、真实数据库或模型。
- 用例断言仅引用本轮观察到的 seed/candidate，年份分别为 2023/2024，重复候选合并为一个 citation，`references` 与 `cited_by` 两条关系均保留 seed provenance；回答明确引用边不证明 findings 或 agreement。
- P12 质量声明仍禁用、费用未测量。本场景测试生产 Harness 的引用校验与合成关系数据，不评估真实检索召回或回答质量。
- P23 全量验证结果见 [P23 验收](P23-citation-graph-benchmark-acceptance.md)。

## P24 逐场景诊断（2026-09-25）

- P12 报告 schema 升级为 `papertrail-p12-offline-benchmark-v4`。每个场景现在列出 status 匹配、越权执行检查及每项期望指标的 expected/actual/passed；失败列表提供稳定 reason code。汇总含 `failed_case_count` 与 `failed_scenario_ids`。
- 成功场景的 `failure_reasons` 是空列表。定向单元测试故意设置状态和执行数不匹配，验证分别生成 `status_mismatch` 和 `metric_mismatch:registered_tool_executions`。
- 这一变化只作用于离线 CLI JSON 报告，不修改 API、OpenAPI、数据库或网络行为。全量验证及限制见 [P24 验收](P24-benchmark-diagnostics-acceptance.md)。

## P25 跨来源发现与 DOI 归并（2026-09-25）

- 报告 schema 升级到 `papertrail-p12-offline-benchmark-v5`，新增第 10 个 Agent 场景：模型按年份分别调用 OpenAlex 与 arXiv 搜索，同 DOI 记录合并为 OpenAlex 主引用并保留 arXiv 备用链接。
- fixture 使用 `TEST-*` 标题、synthetic DOI 和 `synthetic=true`；来源 ID 保持生产 schema 要求的格式。10/10 场景通过，无网络、真实模型或数据库。不同 DOI/缺 DOI 时不跨源合并的策略由 Harness 单元测试覆盖。
- `quality_claim_allowed=false` 与成本未测量保持不变；该场景只验证工具编排与引用契约，不代表来源检索质量。
- 实施及完整检查结果见 [P25 验收](P25-cross-source-discovery-acceptance.md)。
