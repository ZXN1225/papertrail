# R08：工程交付与作品集验收

日期：2026-10-11。最新状态（2026-10-13）：当前本机交付版经用户明确验收；真实论文小样本人审与 Figure 5 修复完成。路线图更大质量集与远端 CI 尚未完成，本机验收不等于发布授权。

## 2026-10-13 用户最终本机验收

- 用户在检查[核对包](R08-local-acceptance-review-pack.md)及本机页面后回复“本机验收通过，请你继续任务”。已将这一人工结论绑定到当前交接版和既有测试/报告；之前“待用户验收”的段落均是当时历史状态。
- R01–R03 的 10–12 篇真实文献/40 题与独立人审 holdout、建议质量门槛仍无足够证据；R07 仍保持生产默认关闭。R08 本机用户接受与路线图整体完成分别记录。未提交/上传 GitHub，远端 Actions 未运行。
- 验收之后按“继续任务”更新本机索引。v14 样本已由用户核验：A2/B1/B3/C supported，A1/B2 unsupported；针对两项反馈实现 parser v15 并在本机重建四篇活动全文。用户后续确认 v15 修复包 A1/B2 内容均 supported；A1 raw row count 包含一条不呈现的全空解析行，口径已说明。此数据质量步骤不撤销此前对 UI/代码交付的验收。
- v15 parser 定向测试 30 passed，全后端 253 passed、1 条既有 Starlette/AnyIO warning；Ruff check 与 `app/tests/tools` format check 通过。未修改 Web/API，也未运行新模型调用。v15 指定两表样本已人工复核，但解析器整体准确率仍未测。

## 2026-10-13 最新补充

- **较早的待用户验收快照，已完成：** 当时用户已核验 parser v14 Figure 5 完整图注，页面与材料仍待检查；随后已提供[一页验收核对包](R08-local-acceptance-review-pack.md)，用户检查本机页面后明确回复“本机验收通过，请你继续任务”。因此本机用户验收子项已完成；路线图整体仍受 R01–R03 大样本真实质量证据限制。首页和 `/api/status` 当时均返回 HTTP 200，状态 ready、数据库可用，LLM/embedding disabled。
- 用户已对真实模型 A–E 五组答案逐一核对原 PDF，均判 `supported`；D 的旧引用缺 `(d)` 且误标段落，E 的视觉空白/换行严格同形未独立确认。人审事实与旧运行状态分开保存于 [结果说明](R06-R07-live-postfix-result.md)。parser v14 修复跨行图注并重建 2608.02037 的本机索引，R4 问题当前 BM25 第 1 条为完整图注；旧冻结检索漏命中不回填。六题一次不足以宣称一般质量或 Skills/多 Agent 收益。
- 当前本机后端全量 `uv run --locked pytest` 250 passed、1 个既有上游弃用 warning；Ruff check、源目录格式检查、OpenAPI 导出通过。Web 锁定包的格式/类型/构建及 Playwright E2E 18/18 通过，后端/Web 依赖审计均无已知漏洞。Web 本机 pnpm `.bin` 缺失，使用同一锁定包的直接 Node 入口运行；根 Ruff format `.` 受既有不可读 `.pytest-tmp` 目录影响，限定 `app tests tools` 通过。远端 Actions 尚未运行，本轮不上传 GitHub。

- **当前离线检索与 Harness 复核：** BM25 v3 修复了少数单数词被宽泛 `-s` 规则错误截尾的问题；同组六题在 v15 活动索引的 top-8 chunk IDs 与目标排名保持稳定。随后加入 Harness 动态输出 token 限额；完整后端现为 **256 passed、1 条既有弃用 warning**，Ruff、`app/tests/tools` format、OpenAPI 导出通过。记录见 [BM25 v3 回归](R01-R03-current-v15-bm25-v3-smoke-2026-10-13.md) 与 [R04 验收](R04-agent-runs-acceptance.md)。这些本机检查不改变 R01–R03 的真实质量验收结论。

## 2026-10-12 最新补充

- **2026-10-13 修复后真实试运行**：六题三臂完成 18/18 arm、48/48 模型请求，本地估算 USD 1.219042；8 个选定答案机械通过，仅 R3 多 Agent consensus。一次性本机审阅包和 A–E 五组 PDF 核验清单已生成，人工语义标签仍为空，不能宣布 Skills/多 Agent 效果或最终项目验收。报告 SHA、状态和成本见 [试运行结果](R06-R07-live-postfix-result.md)。代码未变，最近后端 248 passed、Web clean E2E 18/18；远端 Actions 未运行。

- **2026-10-13 离线人审交接与完整回归**：新增固定 post-fix 试验报告的本机一次性审阅包工具；5 项 TEST 合成检查通过，生成内容仍留 Git 忽略目录，人工标签保持空白。当前后端完整回归 **248 passed、1 条现有 Starlette/AnyIO 弃用 warning**，Ruff check/format 通过（79 files）。新真实模型报告尚不存在、付费运行待授权；Web/远端 CI/最终用户验收状态未变。

- **2026-10-13 六题重跑前完整复核**：当前后端工作树显式枚举 `test_*.py` 完整回归 **243 passed、1 条现有 Starlette/AnyIO 弃用 warning**；Ruff check/format 通过（77 files）。新增完整六题三臂模式只做 dry-run，付费调用仍待明确授权。Web 本轮未改，最近 clean E2E 18/18；远端 CI 与最终用户验收未完成。以下旧测试数字保留为阶段记录。

- **2026-10-13 最新适配器回归与 R1 人审**：修订版 R1 两请求生成结果因两份完全相同的完整 JSON 被拼接而 `invalid_model_output`；适配器现只折叠逐字相同的完整重复，原报告离线回放机械通过。用户已核对 PDF 第 3 页并将该模型答案标为 `supported`；原运行失败状态保留，单题标签不证明六题收益。完整后端 **242 passed、1 条既有上游弃用 warning**，新增六题 CLI 模式的定向 11 项与 dry-run 通过；新付费运行待明确授权。Web 源码本轮未改，之前 clean E2E 18/18 为最近记录。远端 CI 与最终用户验收未完成，下文旧数字是历史快照。

- **2026-10-13 后端最新回归与 R1 诊断**：新增最多 USD 0.50 的 R1 两请求诊断已完成，报告本地估算 `$0.040386`、真实模型答案仍因字段和换行引用契约被拒；已修订 schema/指令并用离线反事实回放和 4 项新 `TEST-*` 用例检查。后端全量 **237 passed、1 条既有上游弃用 warning**，Ruff check/format 通过；测试需本机 socketpair 权限和独立的项目内 pytest 临时目录。Web 本轮未改。修订后真实模型、六题配对收益、最终用户验收和远端 CI 仍未完成；下文旧测试数字为历史快照。

- **最新真实模型与后端复核**：五次 `gpt-5.6-sol` 受限试运行后，第 5 次完成 R1–R5 的 15 个 arm、39 次请求，但无有效答案通过证据校验，R6 未运行；下一请求费用预检超限停机。不能作为 Skills/多 Agent 质量收益证明；见 [试运行记录](R06-R07-live-pilot-interruption.md)。新增本地模型原始输出审计字段及独立 R1 诊断模式（尚未付费执行）后，Ruff check/format 与显式枚举的后端完整测试 **233 passed、1 条既有上游弃用 warning**；诊断 dry-run 通过。Web 本轮未改，之前 clean E2E 18/18 仍为最近记录。远端 CI 与最终用户验收仍待完成；下文 229/224 等为历史快照。

- **六题人审及 live 运行器后的最新后端复核**：三篇许可 PDF 六题与 Table III/收紧 bbox 已获用户单人抽样核验，R1/R4 的指定直接 chunk 未进 BM25 前 8。新增限额试运行器及 5 项 TEST 守卫后，显式枚举真实测试文件复跑后端 **229 passed、1 条既有上游弃用 warning**；Ruff check/format 通过，OpenAPI SHA 不变。一次直接 `pytest -q` 在收集阶段因本机 pywin32 路径及旧 `tests/tmp*` 权限失败，随后加入既有 pywin32 路径、只枚举 `test_*.py` 复核通过。没有模型调用；本机缺少 LLM Key，R06/R07 真实收益与最终用户验收仍未完成。此前 224/219 的数字是旧阶段记录。

- **Web E2E 退出复核**：parser v13 阶段曾出现 18 个用例均通过但 Playwright runner 未正常退出。本轮修复本机忽略的 `node_modules` 依赖 junction 后，以 bundled Node 24.19.0 单独启动 Next 16.3.8 的 3001 开发服务，另以 `node node_modules/@playwright/test/cli.js test` 运行；18/18 通过且测试进程退出码 0（15.5 秒），服务随后停止，3001 端口无监听。未更改产品代码/锁文件，未触发远程 CI。此前的异常仍作为历史记录，不再代表当前本机 E2E 结论。
- **当前代码回归口径**：parser v13 阶段全后端 `224 passed, 1 warning`；本轮只改文档和候选集，未重跑后端。六题真实论文核验和 Table III 裁剪独立复核仍未完成，不能将 E2E 结果用于 RAG 准确率声明。

- **用户本机 Docker Compose 验收（续）**：用户于 Windows PowerShell 执行 `docker compose up --build -d` 成功，backend/web 两个镜像均完成构建，Compose 显示 6/6 资源处理完成，backend `Healthy`、web `Started`；随后 `docker compose ps` 显示两个容器均 `Up` 且 `(healthy)`，Web 绑定 `127.0.0.1:3000`。本执行会话的 PowerShell 进程找不到 `docker` 命令，故容器清单和生命周期证据取自用户截图；同会话对 `http://127.0.0.1:3000/api/status` 的实测返回 `status=ready`（application/database available，模型/embedding disabled），首页返回 HTTP 200 且包含 PaperTrail 标题。Compose 本机 build/up/readiness smoke 通过。没有配置或触发 LLM/Embedding API。
- **本轮最终本机回归**：后端 `219 passed, 1 warning`（Starlette/AnyIO 上游弃用）；Ruff check、format check 与 OpenAPI 导出通过，契约 SHA-256 `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`。Web format check、typecheck、production build 通过，Playwright E2E `18/18 passed`。后端测试通过 Codex bundled Python + 项目 `.venv` 锁定 site-packages 执行，并将 pywin32 目录加入导入/DLL 搜索路径；本机 `uv` launcher 目标无法启动，故不表述为 `uv run --locked`。

- **后续状态**：旧记录中“未导入活动数据库”“等待用户重试”为当时历史状态，已由本段成功导入结果替代。用户 CLI 成功导入 arXiv:2608.20519 元数据（1 条记录、1 个新版本，snapshot `934cc269-9175-4cb7-abda-89713fa00864`）。用户确认 CC BY 4.0 后，许可 manifest 预检通过，全文导入本机根目录 `data/papertrail.sqlite3`，parser v6、209 chunks；重复导入返回 `unchanged`。
- v6 将 `x_tolerance=2` 用于定位文字抽取，Figure 7 与 Table 3 caption 词间空格恢复。本机 BM25 smoke 针对 Table 1/2/3 和 Figure 7 查询返回对应表格/图注及页级 locator。该检查只证明单篇索引检索链路，不证明语义支持或一般 RAG 质量；没有调用 LLM/Embedding API。
- v6 当前全后端回归 `219 passed, 1` 个 Starlette/AnyIO 上游弃用 warning；Ruff check 与 format check 通过。用 Codex bundled Python 加项目 venv 锁定 site-packages 执行 `pytest tests --ignore-glob='**/tmp*'`，不是 `uv run --locked pytest`。OpenAPI 未变化。

- R02 parser/chunker v5 补强后，后端全量回归 `212 passed, 1` 个 Starlette/AnyIO 上游弃用 warning；全量 Ruff check 通过，72 个 Python 文件格式检查通过；OpenAPI 导出 SHA 仍为 `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`。使用 Codex bundled Python 加项目 venv 锁定 site-packages，运行 `pytest tests --ignore-glob='**/tmp*'`；不是 `uv run --locked pytest`。
- 当时本机许可论文解析为 211 elements、3 tables、7 image regions（5 raster + 2 vector boundary）、7 captions。Table 1/2 chunk 及 Figure 6/7 定位抽样见后续状态；当时全文尚未导入活动数据库，现已由本节顶部的 v6 导入结果替代。
- parser/fulltext/store 定向回归 `50 passed, 1` 个弃用 warning；全量 Ruff check/format、OpenAPI 导出通过。当前机器无 `uv`，测试忽略已有无权访问的 `tmp*` 目录；未声称使用 `uv run --locked`。
- 用户于 2026-10-12 接受 R02 对照包展示的单篇抽样结果；Table 2 的 IVIM 下标缺陷已如实披露。该单篇验收不证明通用 PDF 准确率，真实 PDF 的图表语义/矢量图像理解未宣称通过。Table 3 的 ± 已确认为 U+00B1。
- 历史阻塞记录：当时 arXiv 元数据导入受限流影响，后由用户重试成功；当前数据库与导入状态见本节顶部。
- 用户按步骤运行同一 CLI 也遇到上游 429。现已增强限流错误输出：只显示经过范围校验的 `Retry-After` 秒数，缺少有效头时建议至少等待 5 分钟；限流解析及极端/非法值、CLI 错误输出测试覆盖。当前全后端回归 `218 passed, 1` 个上游弃用 warning，Ruff check/format 通过。等待限流窗口后再做一次本机 API 尝试。

## 本机可复现检查

- 后端此前在锁定隔离环境完成 `176 passed`；R07/R03/R06、R04 request-scoped history 与 R05 引擎只读回归完成后，项目本机虚拟环境全量回归 `192 passed, 1` 个 Starlette/AnyIO 上游弃用 warning；R07 manifest 绑定补强后为 `195 passed, 1` 个弃用 warning。R02/R04 补强曾达到 `198 passed`；后续加入 R03 claim 机械一致性 gate 与否定词检查后，当时阶段回归为 `205 passed, 1` 个弃用 warning。Ruff check/format 与 OpenAPI 导出通过。当前结果见 2026-10-12 最新补充。
- 当前锁定依赖复核：本轮重新执行后端 `pip-audit --progress-spinner off` 与 Web `pnpm audit --audit-level moderate`，均退出码 0、无已知漏洞；pnpm `11.25.0` 与 Web packageManager/锁文件版本一致。沙箱网络失败后，在获准的本机网络环境运行。当前主机无 `uv` 命令，所以后端通过项目 `.venv` 中的锁定 `pip-audit` 执行；严格 `uv run --locked ...` 的本轮复核未执行。
- Web 使用 Node 24.19.0 / pnpm 11.25.0 完成 format、typecheck、production build、Playwright E2E `18/18`；该轮未变更依赖锁文件。
- R02/R04 补强时的回归为 `198 passed, 1` 个 Starlette/AnyIO 上游弃用 warning；新增验证覆盖真实 pdfplumber 合成 PDF 输入、未知模型工具名不进入返回/持久化 Trace，以及 ask→cancel→terminal ledger 的 API 级模拟链路。后续最新回归见下条。
- 再增加 R03 claim 显式数量/单位/方向和实验组关联筛查后，当时后端为 `205 passed, 1` 个 Starlette/AnyIO 上游弃用 warning；Ruff 全量 check/format 通过。7 个 TEST 合成端到端情形通过；该确定性 gate 不替代真实语义支持评测。
- 另从 `web/package.json` 和锁文件在隔离临时目录完成 `pnpm install --offline --frozen-lockfile --ignore-scripts` clean install：31 个依赖全部命中本机 store，Prettier、TypeScript、Next、Playwright 入口版本分别为 `3.9.8`、`5.9.3`、`16.3.8`、`1.63.0`；临时目录已校验路径后清理，锁文件未变。
- 新增后端/Next.js 多阶段 Dockerfile、Compose 持久 SQLite volume、后端健康依赖、非 root 运行、回环默认端口和排除本地数据库/PDF的 build context。Next standalone production build 后，使用镜像同入口 `node server.js` 在本机启动；再与临时 SQLite 后端组合，Web `/api/status` 经服务端代理读到后端 `ready` 并返回 HTTP 200。独立跨沙箱进程 loopback 探测受系统隔离限制，改由同一受控本机测试进程启动/请求后成功；临时 DB 已按路径校验后清理。
- GitHub Actions 新增 `container` job，依赖后端与 Web CI jobs；执行 Compose schema/config check、build、up、首页/readiness smoke，并在 `always()` 清理只用于该 job 的 named volume。该 job 只通过 Prettier/YAML 语法本地检查，未推送，因此远程 job 尚未运行。
- OpenAPI 导出 SHA-256：`3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`；与仓库规范文件一致。
- 根 `git diff --check` 退出码 0；路线图 JSON 可解析。Git 仅报告用户已有工作树文件的 LF→CRLF 提示，没有 whitespace error。远程 GitHub Actions 因改动未提交而未运行。

## 交付材料

- 可复现演示脚本、简历事实表和失败复盘位于 `docs/portfolio/`。
- 开发说明、任务台账、项目规格、当前上下文与路线图均说明阶段状态、限制和人工验收门槛。
- 当前仓库中的 47 个 Markdown 文件重新完成本地相对链接存在性扫描：88 个目标，断链 0（行号后缀从路径中分离；外部 URL/纯锚点不计）。路线图 JSON 和 Cursor MCP 示例 JSON 均可解析。
- `TEST-*` synthetic 数据与真实论文索引隔离；AI 生成标签不作为人工金标。

## 限制与待验收

- 早期状态曾按用户要求暂缓提供真实许可 PDF；随后用户已提供并确认许可，完成的单篇版面抽样与全文导入见本节顶部及 R02 记录。
- R01/R03 现有单篇文献的 4 题用户证据支持标签见阶段记录；更大语料、系统生成回答盲评仍待补。R06 Skills 同题对照和 R07 多 Agent 收益评测等待用户明确许可语料、模型、题数、重复次数和费用上限。
- 用户本机 Docker Compose build/up 与服务 smoke 已通过；Codex 执行会话自身无法解析 `docker` 命令，因此未能通过此会话独立读取 `docker compose ps` 或执行清理。远程 GitHub Actions container job 仍未运行。R08 最终用户检查及真实论文质量闭环仍待完成。
- 用户本机最终检查已完成；这是本机交付验收，不是 GitHub 发布授权。所有改动仍仅在本地；不提交、不推送、不创建 PR。
