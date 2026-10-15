# 进度

## 2026-10-15 AI 标注真实语料评测（R01/R03）与简历材料刷新

用户要求尽快产出可写进简历的整块成果。本轮做 A1（真实语料评测）+ A3（简历材料刷新），A2（R04 账单硬上限/重启续跑）**因优先级调整暂缓**——它是开放式工程且简历价值低于评测结果。

### A1：9 篇真实语料上的 53 题 AI 标注评测

- 新增 `tools/export_labeling_candidates.py`（从活动库均匀抽 108 个候选 chunk）、三个独立 Agent 各读 3 篇产出标签、`tools/build_ai_labeled_dataset.py` **机械复核后**组装。
- **校验不是形式主义**：构建器丢弃了 1 条 `quote_not_verbatim` 不合格标签（该 Agent 自称已自检通过）。
- 新增评测模块 `app/evaluation/ai_labeled_tasks.py` + CLI `app/cli/evaluate_ai_labeled_tasks.py`：只读、0 次 provider 调用、强制校验活动库 lineage 与"是否扫描完整语料"，并**在代码层拒绝**任何声称人工复核/金标/质量声明的数据集。契约测试 `tests/test_ai_labeled_tasks.py`（8 项，`TEST-*`/`synthetic=true` 夹具）。
- **结果**（全库 3,294 chunks/查询）：证据命中 **@1 = 26/44 = 59.1%**、**@8 = 39/44 = 88.6%**；按题型 `figure_caption` 5/5、`single_fact` 22/24、`multi_hop` 11/12、**`table_lookup` 1/3（明确短板，与 R02 表格解析缺陷方向一致）**；BM25 top-1 分数上可答题均值 32.5 vs 不可答题 18.3（本样本中不可答题最高分低于可答题均值）。数据集 SHA `72e22a26…`。
- 详见 [AI 标注评测记录](research/R01-R03-ai-labeled-evaluation.md)；**标签为 AI 标注，非人工金标**，且题目写自被评测索引本身、分数偏乐观。

### A3：简历材料刷新到 v27 真实数字

- `docs/portfolio/resume-facts.md` 全面刷新：旧表写的是"四篇 / 1,369 chunks / 281 passed"，实际已是 **9 篇 / 3,294 chunks / 291 passed**——照旧表写简历会低估。新增本轮可写事实（索引升级 + 静默缺陷修复 + AI 复核闭环 + 53 题评测）与**中英文可直接粘贴的简历条目**。
- `docs/portfolio/demo-script.md` 更新为九篇/v27 与新增评测命令；`docs/portfolio/failure-postmortem.md` 新增 4 条本轮真实排障（首版丢词回挂造成重复、整表字符预算方案导致 `XAFPAY XAFPAY`、复核发现图形文字层假表、AI 标签被机械校验拦下 1 条）。

### 验收（本轮）

- 后端全量 **291 passed、0 failed**（336 项收集；45 个 error 为本执行环境无法使用 pytest 临时目录）；新增 8 项契约测试后 parser/表格定向 41 passed、AI 标注模块 8 passed；Ruff check 与 format 通过。
- 未调用付费模型/embedding（`provider_calls=0`）；未推送远端。

### 仍未做

- **依赖审计未重跑**：`pip-audit` 在本沙箱默认缓存目录被拒（`WinError 5`），改用可写 `--cache-dir` 后因无网络访问 advisory registry 而挂起（5 分钟超时）。**本轮没有拿到审计结果**，`pnpm audit` 未尝试。历史上该审计在获准本机网络的环境下通过，本条不覆盖该结论。
- **A2 暂缓**：provider 侧账单硬上限与重启续跑。现状边界是"不会发起超出剩余额度的调用"但仍非服务商账单硬上限；且运行账本按设计不保存问题正文，**重启后续跑只能由调用方重新提交问题**。
- 表头切词/错列、`section_path` 元数据、OCR/图像语义仍未解决。

## 2026-10-15 v27：修掉两个静默解析缺陷并建立可复现的复核包生成器

用户决定不再逐项人工打标签，改由 AI Agent 复核（记录为 **AI 复核**，不冒充人工金标）。据此把 v26 独立核验认定的两个**内容正确性**缺陷修掉，其余仅为表头碎片化的问题继续用 warning 披露。

### 修复内容（`backend/app/retrieval/pdf_parser.py`，parser → `pdfplumber-layout-v27`）

1. **网格丢词**：`Table.extract()` 在推断列边界落在表头末尾字形之外时会**静默丢弃**这些词（实测 `2609.39773` p39 表 8 丢掉表头词 `UMA`、表 10 丢掉 `max_k p_k`）。新增 `_reattach_grid_dropped_words`：以**整张表**的文本为参照集（不是单行——已在别的行出现的词只是错位，再复制一次就会重复表头，这个重复缺陷在做全语料版本对比时被抓到并修掉），只处理中心落在表格水平跨度（优先用比网格更宽的 ruled bbox）与纵向范围内的词，且仅当该词紧凑形式在全表缺失时，追加到中心所在行、最近的单元格——不重写既有文本，也不依赖任何论文专用词表。
2. **多视觉行错行**：`pdfplumber` 的行边界会落在同一单元格两行之间，使续行变成独立一行、原行该列为空（实测 `2610.12662` p14 表 1 的 Qwen "Level loop" 单元格）。新增 `_merge_continuation_rows` + `_is_continuation_neighbour`：单单元格行只能并入同列留空的相邻行，且**列宽必须保持**（拦截跨列合并行）、纵向间距必须在一行高以内。
3. 新增 `backend/tools/generate_parse_review.py`：此前复核包由一次性脚本生成、仓库里没有生成器，换 parser 版本就无法复现复核材料。现在草稿、复核包与 manifest 都可由该工具一条命令重建（只读，不碰 SQLite）。

### 修复后实测（对同一批源 PDF 重解析）

| 项 | v26 | v27 |
| --- | --- | --- |
| `2610.12662` p14 表 1 | `Level loop` 行的 Qwen 为空，多出一个只含 `jnp.arange` 的幻影行，7 行 | 5 行，Qwen = `jnp.arange .at[klevs].set` |
| `2610.12662` p14 表 2 | 表头首行 `Model` 落在单独一行 | `Model` 并入表头行 |
| `2609.39773` p39 表 8 | 表头 `D after`，`UMA` 丢失 | 表头 `D after UMA` |
| `2609.39773` p39 表 10 | 表头丢失 `max_k p_k` | 表头 `-mode fraction max k` |

**仍未修、只用 warning 披露的**：表头列线切穿单词造成的碎片化（如 `2610.12662` p17 表 4 的 `H2D Per` / `m. in Perm`）。这些元素文本无丢失、数据行正确，`row_semantics` 为 `grid_body_rows_header_uncertain`。

### 验收

- 新增 6 个合成用例（丢词回挂、**已在他行出现的词不得重复**、**单字符在他处出现也不得漏判**、续行合并、跨列行不被误并、**图形区域内假表拒绝**）；parser/table 定向 **41 passed / 0 failed / 22 errors**——22 个 error 全部来自本沙箱无法使用 pytest 临时目录，不是断言失败。Ruff check 通过、**87 files** format 通过。
- **全语料版本对比**（`tmp/v26-crops/compare_versions.py`）：9 篇共 26 张 v26 表；v27 保留 24 张合法表（另 2 张是图形文字层假表，已拒绝），**0 张表丢词**，回收 36 个此前被丢弃的词。实现中两次自纠：按"单行"判定会把已在相邻行的表头词复制进空行（`2607.24663` p10 行数 8→9），改为整表判定后修复。
- **独立 AI 复核（两轮）**：
  - 第一轮（`data/storage/reviewer-v27b/`）：10 supported / 6 unsupported，确认 `UMA`、幻影行、`↑`/`↓` 均已修好，7 条图注与全部表格正文正确、无重复；指出 3 处本机未发现的**单字符**丢失，并更正我 v26 对 `2610.09789` p10 的误判。
  - 第二轮（`data/storage/reviewer-v27c/`，复核实际发布构建）：**8 supported / 7 unsupported / 1 uncertain**；**字符丢失只剩 1 处**（下条）、**全样本 0 重复**、S6/S10 的丢字确认已修好；新发现 `2610.12662` p15 由 Figure 2 文字层冒充的假表。
- 据此追加两处修复：单字符改按**目标单元格字符预算**判定（同一字符几乎总在别处出现，会掩盖丢失）；无 `Table N:` 标题且 bbox 完全落在图形区域内的表格候选一律拒绝并记 `table_inside_figure_region_rejected`。两条被否决的路线（整表字符预算遍历导致正文标签重复 `XAFPAY XAFPAY`；多字符按单元格判定会重复表头文字）已记入 [升级记录](research/R02-v27-parse-upgrade.md)。
- **唯一残留字符丢失**：`2610.06874` p14 末尾单位被列线切掉的 1 个 `s`，已如实记录，未修。
- 全量后端回归 **291 passed、0 failed、45 errors**（同为环境 teardown 问题）。
- **活动 SQLite 已升级**：9 篇全部 `pdfplumber-layout-v27`、合计 **3,294 chunks**，lineage **9/9 verified**；活动库上六题只读检索诊断 **selected-reference top-8 5/6**、`provider_calls=0`、`quality_claim_allowed=false`。升级前备份 `data/storage/papertrail-pre-v27.sqlite3`。
- v27 草稿、复核包、manifest 已归档到 `backend/reports/live_eval/`；**最终构建**的复核报告归档在 `backend/reports/live_eval/v27-reviewer-reports/reviewer-report.md`。**中间构建**（v27b）的复核报告仍留在 Git 忽略的 `data/storage/reviewer-v27b/reviewer-report.md`——归档时两个文件同名导致后者覆盖前者，未为它再单独提权写入。
- 已知且**两版都有**的既有问题（非本次引入）：图形内数值曾被误判为表格（本轮已拒绝 p15/p18 两例）。表头切词/错列（S3/S5/S6/S7/S10）与 `section_path` 元数据问题仍未修，均为已披露的已知限制。
- 未调用模型/embedding；**AI 复核已取代人工打标签，但记录中一律标为"AI 复核"，不是人工金标**。

## 2026-10-15 DSH 接手：规范命令修复、v26 独立核验与解析版本循环冻结

接手时 AGENTS.md 的规范命令在本机**是坏的**，原因不是产品代码，而是历史临时目录与本执行沙箱的交互。

### 规范命令修复（只加配置，未删除任何既有文件）

- 症状：`backend/tests/tmp*`（57 个）、`backend/tmp/*`、`backend/.pytest-tmp/`、`backend/.pytest_cache/` 不可访问，导致
  `pytest -q` 在收集阶段报 57 个 `PermissionError` 直接中断（330 项根本跑不起来）；`ruff format --check .` 直接
  panic（`Expected a ruff source file`）；`backend/.ruff_cache` 不可写。
- 改动：`backend/pyproject.toml` 增加 `norecursedirs`、`extend-exclude`、`cache-dir = ".ruff-cache"`；根 `.gitignore`
  增加 `.ruff-cache/`。

| 检查 | 结果 |
| --- | --- |
| `pytest --collect-only` | **330 tests collected，0 error** |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 86 files already formatted |
| `git diff --check` | 退出 0（仅既有 CRLF 提示） |
| `python -m tools.export_openapi` | SHA `be007df662be75f9df7e1d480baee2c7284cd02714227d504d57d20324e0c258`，未变 |
| `pytest -q`（全量，10.25s） | **285 passed，0 failed，45 errors，3 warnings** |

**45 个 error 全部是测试 teardown 的环境错误，不是代码失败。** 最小复现：本沙箱下 `os.mkdir(p)` 正常，但
`os.mkdir(p, 0o700)` 之后该目录既不能列目录也不能删除（`WinError 5`）；`tempfile.mkdtemp` 固定使用 `0o700`，而仓库中约 30 处
测试都用 `tempfile.TemporaryDirectory(dir=Path(__file__).parent)`，因此每个用例结束时的 cleanup 必然失败。同一原因解释了
`backend/tests/` 下堆积的 **245 个 `tmp*` 残留目录**（全部已被 `.gitignore` 覆盖，目录本身在本环境下无法删除）。
**没有为了让沙箱通过而修改测试代码**；这些用例在历史记录的普通本机环境中为 330 passed。

### v26 独立核验（AI 辅助，非人工标签）

按 SHA-256 对齐 9 篇源 PDF 后从源文件重渲染 150 DPI 放大裁切，逐项对照 v26 复核包 16 项，并用 `pdfplumber` 词坐标探针
核实行归属。结论 **supported 11 / unsupported 4 / uncertain 1**；四个通用缺陷模式：多行表头被列线切穿并丢词
（`2609.39773` p39 表 8 丢 `UMA`、表 10 丢 `max_k p_k`）、两行式表头被输出成两行、双行单元格被拆到相邻行
（`2610.12662` p14 表 1 的 Qwen "Level loop" 单元格）、纯矢量图 caption 关联失败（`2610.10204` p3 为 `unmatched` 0.0）。
详见 [v26 独立核验](research/R02-v26-independent-review.md)，含供用户直接回复的最短勾选清单。**这是 AI 辅助对照，不是人工标签、不是金标。**

### 解析版本循环冻结

v20→v26 连续 7 个 parser 版本各自重出 16–17 项复核包，但 v25/v26 始终没有拿到人工标签。本轮**不再新增 parser 版本**，
待用户标签后再决定修哪几项。

### Web 检查

Prettier `format:check` 通过、`tsc --noEmit --incremental false` 通过、Next 生产构建通过（含集成 TypeScript 检查）。
构建产物把 `web/next-env.d.ts` 改为 `./.next/types/...`，已恢复为开始前的 staged 内容。
本沙箱下 `pnpm run *` 无法启动（不允许在只读的 `.pnpm-store` 下建临时目录），故改用仓库内锁定 CLI 直连；
Playwright 浏览器未安装（`%LOCALAPPDATA%\ms-playwright` 不存在），`test:e2e` **本轮未执行**，且 Web 源码本轮未改动。

**边界：** 未写活动 SQLite（仍为 v21）、未调用模型或 embedding、未暂存/提交/推送/上传；`v26` 人工验收仍未完成。

## 2026-10-14 v26 表头锚点列恢复与复核包（追加）

针对 v25 中 `2610.09789` 第 5 页 Table 1 因科学下标导致列恢复拒绝的问题，新增严格的表头锚点回退：要求表头出现可分隔列起点、每个起点在多数数据行中重复对齐，且任一原始词框不得跨过边界；不满足时仍降级为视觉行。现有列恢复不再只看表头不可靠，也检查正文网格是否切词。解析器版本升至 `pdfplumber-layout-v26`。原 PDF 视觉核对显示三列、9 条数据值/符号/含义与解析结果一致；行语义仍按视觉行，不推断额外逻辑关系。

基于同 9 篇许可 PDF、217 页生成 v26 离线草稿及 16 项本机复核包，manifest SHA-256 `f8bd20fac4b478ee6bc626d5dcaaf2a5a2c9739c4fdd3f5961be504dd59a98d5`；v25 包及草稿保留。3,254 元素机械审计：重复 ID 0、非法 bbox 0、复核元素映射错误 0、原页截图缺失 0；这些不代表语义全面正确。Parser/table 定向 **57 passed**；后端全量 **330 passed、1 条既有 Starlette/AnyIO 弃用警告**；目标文件 Ruff check/format 与 `git diff --check` 通过。全量测试通过给捆绑 Python 显式加入项目现有 pywin32 模块路径后完成；项目 `.venv` 未改。

**人工验收仍未完成：** 用户需检查 `backend/reports/live_eval/corpus-expansion-v26-human-review.md` 的 16 项。活动 SQLite 仍为 v21，未写数据库或调用模型/embedding。停止前最新 Codex 用量已用 85%（约余 15%）；本轮停在完整记录的人工门槛，不提交/上传。

**R01 当前状态核准：** 9 篇/217 页许可全文仍是活动语料；`2610.13595` 因 CC BY-NC-SA 4.0 排除。此前 10 个候选问题有单人 PDF 核验，另有六题 live 对照中五组所选回答经用户核对；这不是路线图目标的约 40 题、不可答集合、独立 held-out split 或双人金标。JSON 路线图、R01 验收页、TASKS 与 `current_contexts.md` 已同步纠正过期候选状态。R01 保持 in progress。

## 2026-10-14 v25 表格恢复边界复查与安全交接（追加）

对 `2610.09789` PDF 第 5 页 Table 1 做了只读几何诊断：原文字符仍在 v25 草稿，但解析结果明确降级为 10 条单列视觉行，不能可靠映射 Symbol/Value/Meaning 三列。现有 gutter 重建器对该样本返回 `None`。页面显示整理函数能输出 `K_{min}` 等完整符号；但 gutter 侦测按原始词坐标、3 pt 同行阈值分组，底标相对主体约偏移 4 pt，导致断行及不稳定候选列线。临时只读探针把底标强制对齐后仍未恢复出可靠列，说明只改同行阈值不足。拒绝构造列结构是当前保守行为；不能把文本存在等同于表格解析通过。该诊断不是用户标签，没有改解析器、SQLite、API 或评测数据；未运行测试。后续若改进，须用合成底标/变宽数字表格覆盖，并证明列边界既不切公式 token，也不混入 Meaning 文本，之后再重制 v25+ 人审包。

**安全交接点：** v25 人工复核包 v2 的 16 项仍是下一必要人工门槛；须由用户逐项给出 `supported` / `unsupported` / `uncertain`，特别检查该 Table 1 和其他复杂表头/图表关系。收到前不修索引、不把 v21 标签迁移到 v25。停止前最后一次额度查询为已用 74%（约 26% 可用）；按用户要求，本轮在已记录的检查点停止，之后恢复时先重新查询额度。未暂存、提交或上传。

## 2026-10-14 v25 BM25 R2 未映射项二次核查（追加）

只读检查 `2609.27579` 的 v25 页 2 草稿后确认：解析段落仍保留“系统是决策支持工具，不执行控制操作”的原文。诊断中的 R2 `no_exact_text_match` 表示 v21→v25 按完整文本、来源、页码和元素类型无法精确映射旧参考 chunk；它不能证明 v25 漏解析，也不能证明 BM25 未检出相关内容。当前不能给 R2 赋新版本排名或记 hit；应待 v25 人工确认段落边界后冻结新 locator。原报告保守地将未映射参考计为 miss，5/6 精确映射、全库 4/6 统计未更改。无模型调用、数据库写入或代码修改。详见 [诊断补充](research/R01-R03-v25-bm25-diagnostic-2026-10-14.md#follow-up-on-r2-mapping-2026-10-14)。

**下一人工门槛：** 审阅 `backend/reports/live_eval/corpus-expansion-v25-human-review.md` 中 16 项，并逐项给出 `supported` / `unsupported` / `uncertain`；特别核对 `2610.09789-S2` 的图表类型/输出，及被标为表格的复杂结构。此前 v21 标签不迁移。活动 SQLite 仍是 v21；收到结果前不升级索引。

## 2026-10-14 v21 用户人审结果复核（最新）

用户提供了 17 条 v21 review pack 人审标签；对应原包及逐项记录见 `docs/research/R02-v21-corpus-human-review.json`。只读对照 17 页 PDF 原页截图和原包输出后，绝大多数判定与观察一致：表格视觉行内容正确不代表列结构正确；2609.39773-S3 是审核包错配页面且没有解析元素，`uncertain` 合理，应从解析 pass/fail 分母排除；2610.06874-S3 caption 本文正确，但 Figure 5 关联为 unmatched，是关联覆盖缺口。需要更正的归因是 2610.10204-S2：原 PDF Figure 2 图注本身拼作 `iron-phytolankton`，v21 与 v25 均忠实保留，故不能作为解析器拼写错误；保留用户原始标签/评论，但单列为源文笔误，不计解析失败。该复核由 AI 辅助，不替代用户标签或独立金标。旧 v21 标签不迁移到 v25。

当前人工门槛切换为 v25 review pack 的 16 项（详见下方 v25 记录）；收齐前不升级活动 SQLite v21 索引。R04 共享预算修复见下一节。

用户要求后续运行注意 token 余量：在临近本轮额度且整体目标未完成时，先写明已完成工作、验收、限制与人工下一步，停在可恢复交接点；不得留下未记录的半成品。本次交接状态已写入根目录 `current_contexts.md`、本进度报告及任务台账。

## 2026-10-14 R04 模型输入预算预留（进行中；追加）

Harness 现于每次模型请求前按完整输入 UTF-8 字节上界（加 4,096 字节余量）预留共享额度，并据此限制输出；provider 报告模型输入高于上界则中止。dense/hybrid evidence 工具也在调用 embedding 前按 query UTF-8 字节 + 1,024 字节余量预检；额度不够时不发 embedding 请求，实际 usage 超估算则计入并停止后续步骤。R04/Harness 定向 **55 passed**、live-eval/P12 兼容回归 **14 passed**、全后端 **327 passed**，1 条既有 Starlette/AnyIO 弃用警告；Ruff check 与三个目标文件 format check 通过。测试用桌面捆绑 Python 加项目既有依赖目录，因旧 `.venv` 解释器路径失效、离线 uv 缓存缺少轮子，未完成标准 `uv run --locked` 环境重建；原 `.venv` 未更改。模型/embedding 预估均不是精确 tokenizer 或费用硬上限，provider 自报若超界只会在调用后被发现；R04 继续进行中。未调用真实模型/embedding、未更改 OpenAPI、未提交或上传。详见 [R04 验收](research/R04-agent-runs-acceptance.md)。

## 2026-10-14 v25 页外文字过滤、表格结构保留与复核包（进行中；最新）

v25 延续 v24 的保守表格策略：表头几何异常或解析 bbox 不完整时，仅当正文词语不被推断列线切开才保留列结构，并以 warning 表示不确定性。结构审计另发现 `2610.06874` PDF 36 页页脚词语被原 PDF 放在 MediaBox 页面范围外，解析器现剔除此类词并记录 `out_of_page_text_excluded`。Parser 版本为 `pdfplumber-layout-v25`，活动索引仍为 v21。

新增正文列线判定和页外词语过滤测试。定向 parser/table **54 passed**；显式收集 `test_*.py` 后完整后端 **322 passed，1 条既有 Starlette/AnyIO 弃用 warning**。改动目标 Ruff check/format 通过。首次全量 pytest 因扫描 `backend/tests` 下权限受限历史临时目录未能收集；改用显式测试文件清单后全量通过。

已生成 9 篇许可白名单论文、217 页 v25 离线草稿；16 项复核包 v2 manifest SHA-256 `1548235e8e173296c37d5dabb0050a2747c0d2d6bd77cb0c3ad39cf44fef0b78`。机械结构审计统计 3,254 个元素：重复 ID 0、越界/非法 bbox 0；36 页包含页外词语并显式告警；这不代表文本/表格语义正确。审查包 v1 把 2610.09789 第 9 页 Figure 3 错标为预期 `table`；v2 已更正为 `figure_caption`，展示完整图注及 matched vector-boundary 图像关联，v1 文件保留为审计记录。另做 v21→v25 只读 BM25 版本诊断：旧参考有 5/6 可按原文/来源/页码/类型精确映射，单篇 top‑8 为 5/6、九篇全库为 4/6；R2 未映射按 miss，报告明确非 gold recall，详见 [v25 BM25 诊断](research/R01-R03-v25-bm25-diagnostic-2026-10-14.md)。解析 JSON、页图和 SQLite 均留在本机；没有写活动数据库、调用付费 API、暂存、提交或上传。解析质量仍未通过。

**当前人工门槛：** 核验 `backend/reports/live_eval/corpus-expansion-v25-human-review.md` 的 16 项并回复 supported / unsupported / uncertain。旧版本标签不迁移。后续按新标签修复，再做 lineage/检索评估和索引升级。


## 2026-10-13 全库扫描修复与真实诊断（历史）

- 当前许可全文为 9 篇、217 页、4,871 chunks，parser v21；第十份 2610.13595 是 CC BY-NC-SA 4.0，未满足当前全文白名单，未导入全文。
- 修复 repository 的 SQL LIMIT 2000 静默截断：现对选定范围完整扫描，最多 50,000 chunks；超过返回 corpus_limit_exceeded 且不返回部分排名。索引枚举同样拒绝截断。50,000 是资源保护值，不是性能验收结论。
- 新全库评测清单冻结 9 篇 lineage，校验活动来源集合、每个结果来源/hash、完整扫描数量及 truncated 标志；源内与全库报告明确区分。公共 API 继续要求 source_type/source_id 成对提供。
- 全库六题全部 scanned_chunks=4871、truncated=false；参考 top-8 命中 4/6，R1/R2 未命中，R3–R6 排名 1/2/4/3。原单篇限定诊断为 6/6。两次全库重放报告 SHA 相同：eccc6fd5f8f5e4cf0ab552686d05577ff709ee51531c54bbd3a612ae386d95ff。非 gold、非独立 holdout，不宣称一般质量或扩库收益。
- 验收：项目 venv 全后端 304 passed、1 条既有 Starlette/AnyIO 弃用 warning；Ruff check 与 84 文件格式检查通过；OpenAPI 导出 SHA 未变。首次全回归暴露公共 API 部分过滤参数行为变化（303 passed/1 failed），已恢复契约后全量复验通过。新增 2,001 chunk 合成测试覆盖旧截断缺陷及超限拒绝。
- 未调用模型/embedding，未暂存、提交或上传。Web 未改，本轮未重复运行 Web 测试。仍待 v21 抽查包 17 项人审、Figure 5 叠框确认、第十篇兼容许可全文和独立评测集；R1/R2 全库漏命中仍待进一步泛化诊断。
- 详情见 `docs/research/R01-R03-current-v21-full-corpus-2026-10-13.md`；人工材料在 `backend/reports/live_eval/corpus-expansion-v21-human-review.md`。


## 2026-10-13：v21 表格降级解析、10 份 PDF 准入复核与重建索引

- 用户补充 6 份 PDF。按官方 arXiv `view license` 核对后，5 份为 CC BY 4.0，已获准全文处理；`2610.13595` 为 CC BY-NC-SA 4.0，不符合项目当前 CC0/CC BY 4.0 白名单，未处理全文。该论文的元数据 API 导入在受限与提升权限尝试中均超时，因此当前未确认数据库中已有它的元数据记录。没有擅自扩大许可白名单。
- 修复真实表格 bbox 不完整时“丢掉表格后又被双栏排序打乱”的数据丢失：parser v21 改为仅按视觉行输出单列文本，保留原页面 bbox，并附 `table_structure_unavailable_visual_lines_only` 警告，不伪造列结构。修复水平线区域比 caption 起始更宽时未覆盖完整规则区域的问题；2610.12662 PDF p14 Table 2 的 v21 bbox 收紧到 `[183.44,370.52,428.56,452.53]`，未再混入下方正文。合成覆盖测试通过。
- 9 篇获准全文已统一重解析为 v21。只读 lineage 审计 **9/9 verified**，五项来源/许可/SHA/数量/逐 chunk 哈希校验全部为 true；当前 **4,871 chunks、217 PDF pages**。这验证索引来源链路，不代表解析准确率。
- 后端 Ruff check/format 通过，完整 pytest **298 passed、1 条既有 Starlette/AnyIO 弃用 warning**；OpenAPI 导出成功（SHA `be007df662be75f9df7e1d480baee2c7284cd02714227d504d57d20324e0c258`）。
- v21 原 PDF 对照包 `backend/reports/live_eval/corpus-expansion-v21-human-review.md` 已生成，含 17 个审查项及对应的 17 张原页截图。抽样输出还显示双栏/旋转文字、图表网格、复杂多层表头等未解决边界；不能说新增论文解析验收通过。**当前需要用户逐项核对 17 项**。另一独立人工事项是对 Figure 5 v20 bbox 叠框图做视觉确认。
- 可自动推进的 R01/R03 版本回归已完成：旧六条选定参考按 retrieval/evidence text、来源、页码、元素类型在 v21 活动索引中唯一匹配后重放；BM25 top-8 为 6/6，rank `5/1/1/1/2/3`、locator 6/6、provider calls 0。该诊断只对原三个指定 arXiv ID 检索，不包含全库跨文献竞争；结果非 gold、未迁移用户语义标签。冻结文件与限制见 [v21 BM25 记录](research/R01-R03-current-v21-bm25-smoke-2026-10-13.md)。
- 手工补充前不扩大 allowlist、不做付费调用。无提交、推送或上传。若要达到 10 篇活动全文，需以 CC0/CC BY 4.0 PDF 替换 2610.13595，或由用户明确确认重新评估 NC-SA 条款及项目白名单。

## 2026-10-13：新增许可论文核验与导入（9 篇活动全文）

- 用户将 6 篇新 PDF 放入项目根目录并确认均有许可凭证。按论文标题逐一匹配官方 arXiv 版本页后，5 篇为 CC BY 4.0；`A data-driven heuristic.pdf` / arXiv:2610.13595 的具体许可是 CC BY-NC-SA 4.0，不在当前全文处理白名单（CC0/CC BY 4.0），因此只导入元数据，不导入 PDF。没有更改许可规则。
- 以 3 秒以上间隔从官方 arXiv API 导入另外 5 篇元数据，随后以已有本机 v20 parser 和逐篇 manifest 导入许可 PDF。新增 chunks 为 287/354/1,482/705/684。现有 9 篇活动许可全文合计 **4,881 chunks、217 PDF pages**。
- 只读 lineage 审计：9/9 verified；许可状态、源 PDF SHA-256、v20 parser、chunk 数和 chunk content SHA 一致。此项证明来源/索引可追溯，不证明解析准确率或检索质量。
- 新增本机人工抽查包 `backend/reports/live_eval/corpus-expansion-v20-human-review.md`，含 17 张所选原 PDF 页图和表格/图注解析结果，位于 Git 忽略目录。对 2610.09789 第 5 页 Table 1 的初检发现文本列/单词拆分问题，是明确 defect candidate；新增论文版面验收未通过，需继续修复和复核。五篇 parser warning 数 7/6/4/30/5，尤其 2610.06874 有多页双栏/旋转文字警告，均未被当作准确率。
- 后续需处理 `docs/research/R01-R03-corpus-expansion-2026-10-13.md` 中的两个人工事项：确认如何替换不符合白名单的第十篇；逐项复核 17 页抽查包。另有先前待确认的 v20 Figure 5 bbox 视觉包。无模型/embedding 调用、无新评测费用，未提交或上传。

## 2026-10-13：v20 修正 Figure 5 bbox，并统一当前许可索引

- 对应来源为 `A  Heterogeneous 200 mm Silicon.pdf`（arXiv:2608.02037），不是同目录医学物理 PDF。逐词坐标检查发现 v19 的 Figure 5 矢量框右边界切过 `(d)` 标题末尾 `nm` 约 1.27 pt。解析器 v20 给矢量组左右各增加 2 pt 边距并在页宽处截断；新 bbox `[70.31,298.97,521.68,655.65]`，边界不再穿过文字，caption 仍在框外。
- 按原 CC-BY-4.0 manifest 只重解析四篇已批准 PDF。Lineage 审计 4/4 verified；源 PDF SHA、许可复核时间与 chunk 数 `743/315/263/48` 不变，共 1,369 chunks。目录其余 PDF 未导入。v20 叠框图 `backend/reports/live_eval/figure5-v20-bbox-review.png` 等待用户视觉验收。
- 新增合成测试覆盖矢量图水平 padding 和页边界夹紧，Parser 定向 35 passed。全文检索诊断/lineage 定向 25 passed。Ruff check、84 文件 format check、OpenAPI 导出通过（SHA `be007df662be75f9df7e1d480baee2c7284cd02714227d504d57d20324e0c258`）。
- 新建 v20 非 gold 诊断 manifest，六个 v19 reference 逐字/页码/类型在 v20 中均唯一映射；两次只读 BM25 重放 6/6 top-8、locator 6/6、排名 `5/1/1/1/2/3`、0 provider calls，报告 SHA `4b55361e8ba4a940e5340f86ad55af1af9251a1a3280cce878437971e5c1ba0a`。该结果仅为小样本单人参考诊断，不是 gold recall。
- 全后端 suite 首次在受限执行环境输出 22 个进度点后停滞，手动中断；随后在可用本机 socket 环境以相同项目 `.venv` 完成完整回归：**297 passed、1 条既有 Starlette/AnyIO 弃用 warning**。另有一次 pytest 默认临时目录权限失败；定向 suite 使用工作区 `tmp` basetemp 成功。
- 用户暂缓扩充语料；未处理其他 PDF、调用模型、暂存、提交或上传。

## 2026-10-13：Figure 5 bbox 纳入图内标签，更新为 v19

- 渲染原 PDF 第 9 页后发现 v18 上沿切过面板上方的 `(a)/(d)` 和图内说明文字。v19 将联合矢量框上扩 12 pt；复渲染后六面板、标签均在框内，避开上方正文与下方 Figure 5 caption。新 bbox `[72.31,298.97,519.68,655.65]`，caption relation 保持 matched/confidence 0.965。
- 四篇既有许可全文统一至 v19，PDF SHA/审核时间/chunk 数保持；lineage 四篇 verified，共 1,369 chunks。A1 的 v18 逻辑行元数据修复也保留：Table II 8 行、3 个表头、原始 row_index 1–8。
- v19 六题 BM25 非 gold 重放 6/6 top-8，locator 6/6，排名 5/1/1/1/2/3，0 provider calls，两次报告字节一致；Parser 定向 **34 passed**，完整后端 **286 passed、1 条既有 Starlette/AnyIO 弃用 warning**，Ruff check、84 文件 format check、OpenAPI 导出通过。
- v19 阶段人工门槛的历史记录；当前 v20 需核对的叠框图与精确范围见本文件最上方的新记录。未扩大语料或调用模型；未暂存、提交或上传。

## 2026-10-13：R04 provider token 用量缺失时失败关闭

- Responses adapter 现在拒绝缺失、非整数、负数或 bool 类型的 input/output token usage；embedding adapter 同样拒绝缺失或无效 usage，防止静默记为 0 后低报共享预算。失败不会携带 provider 正文，并阻止继续执行。
- 测试：新增模型 usage 异常契约和 embedding usage 异常用例；完整后端 **294 passed、1 条既有 Starlette/AnyIO 弃用 warning**。Ruff check、84 文件格式检查、OpenAPI 导出通过（SHA 未变）。受限沙箱内 TestClient 本地 socket 测试曾挂起并已中断；完整套件随后在仓库本机环境通过。
- 仍不是账单硬上限：provider 自报、在途调用和输入/embedding 用量的事后可见性仍是边界。没有真实模型/embedding 调用；未暂存、提交或上传。

### 同轮 Web 回归

- Web 未改代码；使用项目依赖包的直接 CLI（Node 24）检查 Prettier，通过。Next 生产构建通过并完成其集成 TypeScript 检查；Playwright E2E **18/18 passed**。Next 构建把 `next-env.d.ts` 临时改为生产路由类型引用，已恢复到开始前已暂存版本。
- 独立 `tsc --noEmit` 未通过：本机 pnpm junction 解析下，TypeScript 找不到 `@playwright/test` 的传递模块 `playwright/test`；同一源码的 Next 构建集成 TypeScript 检查通过。标准 `pnpm run` 在沙箱下读取 `node_modules` 收到 EPERM，故用了本机 Node 24 直接调用已安装的锁定依赖 CLI。没有修改依赖锁文件；此次不据此声称 pnpm 独立 typecheck 脚本通过。

## 2026-10-13：Embedding 用量不明时终止 Agent 轮次

- 沿检索工具链复查发现，embedding provider 抛错会被证据工具转换为普通错误 observation，Harness 仍会向 LLM 请求下一步。现将该错误路径改为 `usage_unavailable`：记录脱敏 tool error、立即终止当前 run，不将 observation 交给模型；API 503、ledger failed、Web 显示对应错误。新增 TEST 合成回归确认只执行一个 LLM 轮次。
- 新增 Harness 停止和 API/ledger 集成回归：embedding usage 无效时只执行一个 LLM 轮次，API 返回 503，run 状态持久化为 failed。完整后端 **296 passed**、1 条既有 Starlette/AnyIO 弃用 warning；Ruff 与 84 文件格式检查通过。OpenAPI 已重新导出，SHA `be007df662be75f9df7e1d480baee2c7284cd02714227d504d57d20324e0c258`。Web Prettier、Next production build（集成 TS 检查）、E2E **18/18** 通过；未调用付费模型/embedding。
- 账单仍非 provider 侧硬上限，R04 保持 `in progress`；没有扩充语料或上传 GitHub。

### 用户复核补充

- 用户再次确认 v15 A1 表格内容 supported，并指出旧核验包的展示计数与 metadata 不一致；该逻辑空行计数已在 v18 修正，当前 v19 报告 8 行/3 个表头且保留物理 `row_index=1..8`。B2 三列结构及 IVIM 下标获用户确认 supported。人工标签仍绑定 v15 内容 SHA，不代表用户已审阅 v19 structured output。此回复不改变当前待人工确认的 v19 Figure 5 bbox 门槛。

## 2026-10-13：A1 逻辑表格行数收敛到 v18

- 用户对 v15 A1 确认表头内容支持，同时指出展示 8 行/3 个表头与元数据 9 行/4 个表头不一致。问题来自孤立 `V` 被归一化清空后，原始行仍被计入逻辑表行数。
- v18 在表头归一化后过滤空行，逻辑计数变为 8 行、3 个表头；保留 PDF 物理定位 `row_index=1..8`，不改 A1 表格文字、bbox、五条数据或原文支持性标签。增加 `TEST-synthetic` 回归。
- 四篇已许可 PDF 均统一重解析到 v18，保持 PDF SHA、审核时间及 chunks 数 48/315/743/263。lineage 四篇 verified，合计 1,369 chunks；本轮未增加语料。
- Parser 定向 **34 passed**；完整后端 **286 passed、1 条既有 Starlette/AnyIO 弃用 warning**。Ruff check、`app/tests/tools` 84 文件格式检查、OpenAPI 导出通过（SHA 不变）。
- v18 六题只读 BM25 诊断精确 remap 6/6，top-8 命中 6/6，locator 6/6，名次 5/1/1/1/2/3，0 provider calls；复跑报告字节一致，非 gold recall。见 [v18 报告](research/R01-R03-current-v18-bm25-smoke-2026-10-13.md)。
- 等待用户核验 Figure 5 bbox `[72.31,310.97,519.68,655.65]` 是否准确覆盖原 PDF 第 9 页六面板并排除图注和正文。OCR、图像像素语义和跨布局准确率未建立；语料扩充按用户要求暂缓。未暂存、提交或上传。

## 2026-10-13：PDF 复合图区域关联与 v17 活动索引

- 版面审计发现 `2608.02037` PDF 第 9 页 Figure 5 曾误连到约 69×3.39 pt 的内部细线。v17 排除过窄 image fragment，并把相邻矢量面板边框按二维接邻关系组成联合区域；实 PDF 联合 bbox `[72.31,310.97,519.68,655.65]` 覆盖六面板且止于图注上方，图注匹配置信度 0.965。新增四面板 synthetic 回归。
- 新增许可复核时间保留逻辑：同一来源、许可、证据 URL、署名和审核人下的解析器重建不刷新历史人工许可复核时间；本次四篇 v17 active rows 已恢复 v15 记录的原复核时间，`imported_at` 保留实际重建时间。新增回归覆盖解析版本变化时许可审核时间不漂移。
- 四篇已有 approved CC-BY-4.0 PDF 已重建活动索引至 `pdfplumber-layout-v17`，没有扩充语料。PDF SHA 与许可复核时间保持，chunk 数仍为 48/315/743/263；chunk/parent、caption 目标、bbox 与表格行列不变量通过，lineage CLI 四篇 `verified`，共 1,369 chunks。v13/v15/v16 检索报告与人审标签均保持各自版本，不迁移到 v17。
- Parser 定向 **33 passed**；完整后端 **285 passed、1 条既有 Starlette/AnyIO 弃用 warning**。Ruff check 及 `app/tests/tools` 84 个 Python 文件 format check 通过；OpenAPI SHA 未变：`3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`。BM25 smoke 中 Figure 5 完整 caption 排第 2，页 9；暂不把同页单项结果外推成普遍检索质量。
- 用原六题构建独立 v17 版本锁定诊断；六个参考均通过精确 chunk 文本+页码+元素类型唯一映射，重放 BM25 后均进入 top 8（名次 5/1/1/1/2/3），locator 6/6 一致，provider calls=0。仍为单人选定参考而非 gold recall；当前诊断与边界见 [v17 BM25 报告](research/R01-R03-current-v17-bm25-smoke-2026-10-13.md)。
- 仍未覆盖扫描 OCR、像素语义和跨版式准确率；语料扩充按用户要求暂缓。没有模型/外网调用、暂存、提交或上传。

## 2026-10-13：可复用的只读 PDF/索引 lineage 审计

- 新增 `backend/app/cli/audit_fulltext_lineage.py`，可按 `ARXIV_ID=PATH` 传入本机 PDF，流式计算文件 SHA-256，再只读核对活动版本的批准状态、允许许可、PDF 哈希、parser 版本、chunk 数及 chunk content SHA。输出不含论文摘录，不修改数据库；该命令证明版本/文件一致性，不证明解析准确率或许可法律范围。
- 本机四份已批准 CC BY-4.0 PDF 全部 `verified`：2609.27579=48、2608.02037=315、2607.24663=743、2608.20519=263 chunks，共 1,369；每篇文件 SHA 与当前索引相同。新增 13 项测试全通过。
- 后端完整回归 **281 passed、1 条既有 Starlette/AnyIO 弃用 warning**。在受限沙箱中现有 TestClient socket 测试会停滞；按项目授权测试流程使用可用本机 socket 后全量完成。Ruff check/format 均通过（84 个 Python 文件），OpenAPI SHA 未变：`3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`，根目录 `git diff --check` 通过。无 Web、数据库、PDF 内容、网络或模型调用；未暂存、提交或上传。
- CLI 用法及逐篇 SHA 见 [当前 corpus 版本审计](research/R01-R03-current-corpus-lineage-2026-10-13.md)。用户已暂缓新增语料；后续继续在现有许可数据上做离线质量工作。
- 顺带审阅现有合成评测集 split 防泄漏：12 个 synthetic documents 按 ID 分到 dev/test，40 题锚点跟随对应文档 split；split runner 仅检索本 split，现有自动化用例检查来源隔离、分母和错配拒绝。它不能代替真实论文的文档级 holdout，后者待用户未来选择许可语料并冻结任务。
- 刷新 `docs/portfolio/` 中过期的 PDF 人审、MCP Host、Skills/Multi-agent 结果和测试计数：现如实写明四篇/1,369 chunks、用户核验的指定解析样本、桌面 Host 单次 MCP smoke、Skills 2/6 vs 4/6 严格有效引用成功数及 Multi-agent 1/6 consensus/成本比约 2.20。限制项仍明确为小样本、无通用质量声明、远端 CI 未运行和发布未授权。
- 作品集三个 Markdown 文件的 17 个本地相对链接已核查，未发现断链；正文只记录已验收事实与对应限制。
- 按 `AGENTS.md` 重跑依赖审计：锁定后端环境 `pip-audit --progress-spinner off` 和 Web `pnpm audit --audit-level moderate` 均报告无已知漏洞。两项需访问 PyPI/npm advisory registry；默认沙箱先因网络/DNS 失败，随后在获准的本机网络检查环境完成。

## 2026-10-13：Harness 单次模型输出预算约束

- 发现每次 Responses 请求原先沿用固定 `LLM_MAX_OUTPUT_TOKENS`，即使本轮剩余 token 预算更小也会照常请求。现按“配置上限与剩余已观测总预算”动态设置 `max_output_tokens`；返回用量超过所请求输出额度后立即停止本轮，不再继续工具/模型步骤。live-eval 守卫会把该动态额度纳入本地费用预留。
- 定向 Harness/live-eval/multi-agent **62 passed**；完整后端 **256 passed、1 条既有 Starlette/AnyIO 弃用 warning**。Ruff check/format 通过；OpenAPI 导出 SHA 仍是 `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`。三项新旧 P12 mock contract 问题已修复后全套重跑通过。
- 当前限制：input token 与 embedding token 使用量在 provider/tool 返回后才可知，正在执行的一次调用仍可能超过剩余额度；系统之后停止。不能称 provider 账单硬上限，R04 不据此关闭。无真实模型调用。

- 用户暂缓扩充候选语料；接下来仅继续现有四篇活动索引可完成的离线工作，不下载或导入 PDF，也不发起付费模型调用。R01–R03 的大样本独立质量验收因此保持待办，不把该外部输入记为代码失败。

## 2026-10-13：当前许可全文检索诊断 CLI

- 新增版本锁定清单及只读 CLI：运行前核对活动许可、PDF SHA、parser v15 与索引 content SHA；逐题 exact-arXiv BM25 检索，并检查所选参考 chunk 页码和元素类型。输出不含原文摘录，`gold_standard=false`、`quality_claim_allowed=false`。
- 当前本机索引重放为 6/6 所选参考进 top 8，排名 **5/1/1/1/2/3**，locator 检查全通过，provider calls 为 0。忽略目录报告 `backend/reports/current-index-fulltext-v1.json`，清单 SHA `759d68c2c1078e8dc5b0b6155048b2686b470f98ddeabe5cbe14ea3a71e537f5`。该结果是小样本可复现诊断，不是 gold recall 或一般质量结论。
- 后端 API 的只读 lineage 查询及 CLI/评测守卫新增测试；评测函数强制只读 PaperStore。文档位置与解释见 [R01–R03 质量门槛](research/R01-R03-next-quality-gate.md)。
- 最终回归：全文检索评测定向 **13 passed**；完整后端 **268 passed、1 条既有 Starlette/AnyIO 弃用 warning**。Ruff check/format 82 个文件通过，OpenAPI 导出 SHA 未变。两次只读六题重放报告字节一致（SHA `360b0763d24477635375786d2766e328aaeb14d50ddb3d2b8d030bd9701c176e`）。第一次全量回归的 29 个 setup error 来自系统 pytest temp 权限；指定仓库内新 basetemp 后全量通过。未改 Web，不需 Web 回归；未调用模型、未改数据库/PDF。

## 2026-10-13：四篇活动全文只读 lineage 审计

- `PaperStore(readonly=True)` 核对四篇活动全文：均为 approved、CC-BY-4.0、parser v15；重新计算的四个本机 PDF SHA 均与活动版本 `source_document_sha256` 相同；metadata chunk count 与活动 chunk 查询相符，总计 1,369。详情见 [当前 corpus 版本审计](research/R01-R03-current-corpus-lineage-2026-10-13.md)。没有读取 excerpt、写数据库、重解析 PDF 或访问网络。
- 旧 R1–R6 候选清单绑定 parser v13 内容哈希；v15 人审/诊断不复用旧标签。现有 v15 六题 BM25 诊断独立绑定当前 SHA 且不能作为 gold recall。更大独立质量集仍需经用户许可确认的新语料；此步骤按用户要求暂缓。

## 2026-10-13：BM25 v3 保守复数例外修复

- 代码审查发现 v2 末尾 `-s` 规则会错误截短 `lens`、`gas`、`alias`、`canvas` 等常见单数，并遗漏部分对应复数。现增加单数保护及显式歧义复数映射；tokenizer、BM25、全文 BM25、Hybrid 与 synthetic scoring 均升版。中文 bigram 规则未变。
- 对同一组六题、同一 v15 活动全文只读重放，R1–R6 目标排名仍为 **5/1/1/1/2/3**，全部 top-8 chunk ID 列表与 v2 完全一致，源内容 SHA 未变。报告见 [说明](research/R01-R03-current-v15-bm25-v3-smoke-2026-10-13.md) 和 [JSON](research/R01-R03-current-v15-bm25-v3-smoke-2026-10-13.json)，SHA-256 `b02dbf7d0982d70e770c079e5c3081ac848fdc9f43793915333b650d8ee145ea`。仍是窄回归，不构成独立检索质量证明。
- 定向 BM25/metrics、全文 API 与 synthetic research-task 测试 **37 passed、1 条既有弃用 warning**；完整后端 **255 passed、1 条同 warning**。Ruff check 通过，`app/tests/tools` 79 文件格式检查通过；OpenAPI 导出通过且 SHA 未变。`uv` 默认用户缓存受限，验证使用已安装锁定环境；root `git diff --check` 通过。无网络/模型调用、无 DB/PDF 改写，未暂存/提交/推送。

## 2026-10-13：R1 词形漏检修复为 BM25 v2，六题目标回到 top 8

- 针对 v15 BM25 v1 中 R1 的“layers”/“Layer”词形不匹配，增加版本化英文复数归一及不规则词回归； tokenizer 标为 `unicode-latin-cjk-bigram-plural-v2`，BM25 / 全文 BM25 / Hybrid 分别升为 `okapi-bm25-v2`、`bm25_fulltext_v2`、`hybrid_rrf_v2`，保留 CJK bigram 规则。未改 parser 或活动 SQLite 内容。
- 相同六题、相同四篇 v15 内容只读重放：R1 由 v1 全库第 47/48 升至第 5；其余五题的目标排名保持 1/1/1/2/3；当前 6/6 参考定位进入 top 8。报告见 [说明](research/R01-R03-current-v15-bm25-v2-smoke-2026-10-13.md) 和 [JSON](research/R01-R03-current-v15-bm25-v2-smoke-2026-10-13.json)，SHA-256 `20260901215b9e1dceca22b39746719895d0dd230031258ad2eeecb9be1db1dd`。仅为六题窄回归，不是普遍召回或独立质量结论。
- 测试：`test_bm25_and_metrics.py` 7 passed，`test_research_tasks_evaluation.py` 15 passed，完整锁定后端/API 回归 **255 passed、1 条既有 Starlette/AnyIO 弃用 warning**。Ruff check 通过；format `app tests tools` 的 79 文件通过；`ruff format --check .` 发现 96 文件都已格式化，但因原有不可访问 `backend/.pytest-tmp` 无法枚举而退出非零。OpenAPI 导出通过，SHA `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb` 未变化。P05 准确冻结快照未在本机 DB，无法用于人审 qrels 的回归对照。语料扩充按用户意愿暂缓；无模型调用。GitHub 上传未授权。

## 2026-10-13：当前 v15 活动索引六题只读 BM25 复测

- 用户决定暂缓新增语料；本轮在现有四篇活动索引上重跑冻结六题 exact-source BM25 top-8，使用本机 `PaperStore(readonly=True)`，未写数据库/网络/模型调用。
- 当前人工核验来源定位排名：R1 在全库 48 个 chunk 中第 47（未命中 top 8）；R2 第 1/48，R3 第 1/315，R4 第 1/315，R5 第 2/743，R6 第 3/743。R1 虽取回“有四层”的前导段，但没有列出四层名称，按证据检索失败计。详细记录见 [Markdown](research/R01-R03-current-v15-bm25-smoke-2026-10-13.md) 与 [机器可读结果](research/R01-R03-current-v15-bm25-smoke-2026-10-13.json)，JSON SHA-256 `102fd55df4a5bdbe257d8c39222411c8512554567824eb52eaf73083214b55f3`。
- 结果为所选六题的 `5/6` 诊断值，不是一般 Recall@8、独立 holdout 或回答正确率；旧标签不迁移至 v15。R1 留作检索问题。未改产品代码，因此本轮未跑代码测试。GitHub 上传仍未授权。

## 2026-10-13：用户暂缓语料扩充，继续现有语料离线阶段

- 用户明确表示“等下再扩充语料，暂时先不管这部分”。6 篇候选 PDF 尚未获选择/许可确认，本阶段不下载、不导入，也不继续催要；当前工作转为现有四篇索引、实现与验收记录的离线审查。
- 用户最新对 v15 核验的补充结论与既有 [R02-v15 人审记录](research/R02-v15-human-review.json)一致：A1 表头内容 supported，结构计数差异是空解析行；B2 三列与 IVIM 下标 supported。当前文档已明确 raw 9 行/4 header slots = 1 空行 + 3 非空表头 + 5 数据行；不把空行描述成 PDF 可见行。A1/B2 是定向样本，不代表一般准确率。
- 用户此前已明确通过本机交付验收。R08 的“最终用户验收未完成”旧措辞已更新为“本机用户验收已通过”；R08 整体仍因 R01–R03 质量集未闭环保持 in progress。R06/R07 不宣称效果，Skills 与多 Agent 的生产开启门槛仍未达到。
- 本轮未改产品代码、未调用模型或导入语料，未重跑测试。针对当前 v15 parser/content SHA 的离线引用复测已执行，结果见上方最新小节；R1 未命中右栏细节，暂待后续检索诊断。GitHub 上传仍未授权。

## 2026-10-13：v15 表格修复通过定向复核；等待许可语料选择

- 用户最新核验确认 v15 A1 的 `∆V_strict vs. Naive` / `V_strict (%)` 表头正确、孤立 `V` 已消除；B2 三列、类别文本和 `f_p/D_t/D_p` 下标正确。A1 9 条结构行/4 表头与 8 条可见行/3 条非空表头的差异来自原始 structured data 的 `row_index=0` 全空行；已在 Git 忽略的 v15 review pack 中补充口径说明。标签、PDF SHA、v15 content SHA 见 [v15 人审记录](research/R02-v15-human-review.json)。A2/B1/B3/C 沿用之前结果。
- 已新增 [R01–R03 候选语料清单](research/R01-R03-corpus-candidates-2026-10.md)：通过 arXiv 页面许可入口初筛 6 篇 CC BY 4.0 候选，覆盖科学 Agent 过程评测、长篇知识图谱综述、CMS/ATLAS 实验论文、12 图用户交互系统及医学影像 3D 可视化。用户逐篇选择和确认具体 PDF 版本之前，不下载、不导入。
- 本轮仅更新项目文档/本机忽略的核验包；未修改产品代码、未调用模型或重跑测试。项目全文目标 10–12 篇，新增 6 篇候选若全部经用户确认可到下限 10 篇；约 40 题和隔离划分须在真实语料准备后冻结。此前 v15 后端测试记录仍为 253 passed；本轮未重跑代码测试。

## 2026-10-13：v14 人工核验发现两项表格解析缺陷，v15 已修复并重建索引

- 用户对 v14 抽样给出 A1/A2/B1/B2/B3/C：A2、B1、B3、C supported；A1、B2 unsupported。具体问题及 PDF SHA、旧内容 SHA 见 [人审记录](research/R02-v14-human-review.json)。
- A1：重建跨行表头，将孤立 V 与 delta 合并为 `∆V_strict vs. Naive`，并恢复 `V_strict (%)`。B2：把表头缺名的相邻物理分栏合并为三列，修正被切断的类别文本，恢复 `IVIM (f_p, D_t, D_p)` 下标。
- parser 升至 v15，四篇许可全文均用原 manifest 本机重建活动索引；旧版本保留。A2/B1/B3/C 的文本、结构、bbox、warnings 与 v14 对照完全相同；A1/B2 修复内容经用户复核通过。A1 raw row/header_count 的空行口径已在 Git 忽略核验包说明。
- 验证完成：parser 定向回归 30 passed；后端全量 `pytest` **253 passed、1 条既有 Starlette/AnyIO 弃用 warning**。后端 Ruff check 与 79 个 `app/tests/tools` 文件 format check 均通过。全套测试需要本地 socketpair，默认沙箱会停在第一条 TestClient 测试；经受控本地测试运行后通过。未改 OpenAPI 接口、未调用模型或网络。
- 当前索引 BM25 smoke：v15 Figure 5 图注仍第 1；IVIM Table 2 查询第 1 命中第 14 页表；Table II 数据行查询第 2 命中第 10 页表。语义和人工标签仍以 PDF 复核为准。

## 2026-10-13：四篇活动 PDF 统一 parser v14

- 用户验收后按“继续任务”执行本机解析器版本统一。只读 SQLite 核对四份 CC BY-4.0 PDF 的本地文件 SHA 与原活动索引一致；依照既有 manifest 将 parser v6/v13 的三篇 PDF 重解析到 v14。四篇当前版本均 v14，chunks 分别为 2607.24663=743、2608.02037=315、2608.20519=263、2609.27579=48；旧全文版本仍保留。没有模型/网络调用，不迁移旧 eval 标签。
- v14 结构盘点合计 67 页、1,349 elements、7 个 table elements、46 页级 warnings；warning 包含双栏/阅读顺序、旋转字排除及稀疏表格拒绝。该盘点不代表准确率。R4 同题 BM25 smoke 显示完整 Figure 5 `figure_caption` 仍排第 1。
- 新活动索引的表格/右栏样本已整理在 Git 忽略的 `backend/reports/live_eval/r02-v14-reindex-review.md`；待用户对照原 PDF 核验。此前本机应用验收仍有效，当前 parser 内容的抽样标签尚未确认。细节和下一步见 [R02](research/R02-pdf-structure-acceptance.md) 与 [真实质量门槛](research/R01-R03-next-quality-gate.md)。

## 2026-10-13：当前本机交付版获用户验收，继续质量阶段

- 用户明确回复“本机验收通过，请你继续任务”。已在 [R08 验收](research/R08-acceptance.md)、[最终清单](research/R08-final-user-acceptance.md)和路线图 JSON 分别登记；此人工结论只覆盖当前展示的本机版本和已披露的探索性结果，不授权 GitHub 上传。
- R01–R03 的独立真实 holdout、10–12 篇许可资料、约 40 题、不可答题与更大规模人工支持/召回尚未完成。R08 的本机用户接受子项已完成，但路线图整体 R08 仍因必选阶段质量证据不足保持 `in progress`。下一阶段条件与精确分母见 [真实质量门槛缺口](research/R01-R03-next-quality-gate.md)。
- 48 次真实模型调用授权已用尽；任何新增付费评估须另定模型、次数和费用上限。远端 CI 仍未运行，不提交/推送/创建 PR。

## 2026-10-13：首页截图外观检查

- 用户提供本机 PaperTrail 首屏截图；顶栏、搜索区、来源切换和研究助理面板正常显示，截图内未见明显错位。记录为首页外观 smoke，不替代已通过的 Web E2E 18/18，也不证明 OpenAlex 或 LLM 在当前 disabled 预览中可用。
- 用户询问是否还需验收。剩余人工判断仅为核对六题/工程记录的保守表述，以及是否接受当前界面外观；完整本机项目验收仍待用户明确回复。无新模型调用、无 GitHub 上传。

## 2026-10-13：本机验收材料与 UI 交接

- 用户确认修复后 Figure 5 第 9 页完整图注、`figure_caption` 类型、bbox、`[0,767)` 与 PDF SHA-256；但六题最终结果与工程记录先前未便于直接核对，界面当时未运行，所以完整本机验收**仍待确认**。
- 已补 [一页验收核对包](research/R08-local-acceptance-review-pack.md)，直接列出六题三臂原状态、人审 A–E、费用、工程测试、局限，并链接详细 [六题结果](research/R06-R07-live-postfix-result.md)与 [R08 工程记录](research/R08-acceptance.md)。没有将原始模型答案、PDF/全文或报告加入 Git。
- 在本机回环地址启动预览：`http://127.0.0.1:3000/` 首页与 `/api/status` 均 HTTP 200；后者 `status=ready`、SQLite available，LLM/embedding disabled。待用户实际浏览 UI 并阅读材料；远端 GitHub Actions 未运行，无新的模型调用或上传。

## 2026-10-13：A–E 人审登记、Figure 5 跨行图注修复与本机验收

- 用户对修复后六题三臂试验的 A–E 五组逐一核对原 PDF，**五组答案均为 `supported`**，对应 8 个机器选定答案；另 10 个 arm 未作答案语义评分。D 的旧 quote 缺 `(d) Transition` 且误标 `paragraph`，所以“回答获支持”不等于“旧引用完整有效”；E 的数值/最高判断获 Table III 全列支持，但视觉 PDF 空白/换行与解析器转录的严格同形未获核验。无模型正文的 [人审元数据](research/R06-R07-postfix-human-review-v1.json)绑定原报告/审阅包 SHA；原始报告及空白模板未改，已填写本机副本仍在 Git 忽略目录。
- 对 8 条旧引用作只读 SQLite 内部定位检查：chunk 均存在，元素半开字符范围等于存储摘录，quote 在摘录内，locator 与存储值一致。该检查不覆盖 PDF 像素排版或 D 的图注类型错误。按机器选定且答案得到 PDF 支持计：Skills 关闭 3/6、开启 4/6、多 Agent 1/6；要求旧图注引用完整时 Skills 关闭为 2/6。六题一次不支持一般化收益，多 Agent 费用比 2.20，生产保持默认关闭。
- parser 从 `pdfplumber-layout-v13` 升至 **v14**，修复 Figure 5 跨行图注在双栏歧义页被拆为 `paragraph` 的问题；新增 `TEST-*` 合成跨行/双栏回归。真实 2608.02037 PDF 第 9 页的新 `figure_caption` bbox `[72.0,666.27,523.26,759.92]`，同一元素同时包含 `(d)`/70 nm、`(e)`/220 nm。原许可 manifest 本机重导入后新版本 SHA `f6d9bcbf4bc7e88aba296103255c8f5463bbe3ad424ac77fdb0e887855f3f5a3`、315 chunks；同一 R4 问题当前 BM25 前 8 条中完整图注排名第 1。旧模型报告、冻结旧索引评价和旧 R4 漏命中不追写。
- 当前代码后端 `uv run --locked pytest` **250 passed、1 条既有 Starlette/AnyIO 弃用 warning**；Ruff check 通过，format 对 `app tests tools` 79 files 通过（根 `.` 命令因既有不可读 `.pytest-tmp` 目录返回访问错误）；OpenAPI 导出 SHA `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`。Web 格式、类型、生产构建与 Playwright **18/18** 通过；本机缺少 pnpm `.bin` 启动器，使用相同锁定包的 Node 入口运行。后端/Web 依赖审计均无已知漏洞，`git diff --check` 退出码 0。
- 48 次模型请求授权已用尽，不再发起付费调用。下一个人工步骤是最终项目验收和是否继续做更大样本/独立双审；GitHub 上传仍按用户要求暂缓。

## 2026-10-13：修复后六题三臂真实试运行完成，等待逐题人工审阅

- 用户明确新增最多 USD 2、`gpt-5.6-sol`、三篇已许可论文、六题各一次、Skills 关闭/开启/双 worker 三臂、最多 48 次请求。预检通过后只运行固定 `--post-fix-six-task` 一次：**18/18 arm、48/48 provider 请求、未触发停机**；本地保守费用估算 **USD 1.219042**（不是服务商账单）。独立原始报告仅在 Git 忽略目录，SHA-256 `3e60cdfdcda8068348f04eb2c4a95d53226a68818484fb23302fad822042d5f2`；旧报告未覆盖。48 次请求授权已用尽，即使费用估算低于 USD 2 也不再自动调用。
- 机器门禁：8 个 arm 的选定答案 `completed`，另有 1 个 `insufficient_evidence`、4 个单 Agent `unverified_evidence`；多 Agent 仅 R3 一题 `consensus`，R1/R2 为 `conflict`，R4/R5/R6 为 `insufficient_workers`。R1/R2 双 worker 主要因主张措辞不同而未满足**精确** consensus，不能把语义相近的 worker 答案改计为多 Agent 成功。R4 Skills-on 缺 `(d)` 的逐字 quote 绑定，R5/R6 的表格数据行 quote 缺表头列义，是本轮机械拒绝的可见原因之一；原运行状态保留，不做离线改写计分。由此尚不能证明 Skills 或多 Agent 收益。
- 离线 `prepare_live_review` 已生成**18 项、全空人工标签**的本机 JSON 审阅包，SHA-256 `c05ed5a3ea5b8301d0ec3f09a3db442f99a35458ddf6e6bb255a99e637f1f8b2`，其报告 SHA 绑定与 18 项完整性核对通过。8 个机器通过答案去重成 [本机 A–E 五组 PDF 人审清单](../backend/reports/live_eval/gpt-5.6-sol-r01-r03-postfix-human-check.md)，均保留原 run/arm 映射；等待用户核验原文支持和 locator。此前 R1 单题人工支持标签**不自动转移**给新运行。现有后端 248 passed、Web clean E2E 18/18 是代码未变前的最近回归；本次仅运行 CLI 和生成忽略报告，没有修改产品代码。没有暂存、提交、推送或创建 PR。

## 2026-10-13：六题生成答案的离线人工审阅交接

- 新增 `backend/app/cli/prepare_live_review.py`：只读取固定的修订后六题本机报告，生成同在 Git 忽略目录的 JSON 人审包。每个运行项保留 task/arm、机械状态、生成答案、claim/citation locator、多 Agent worker 状态与空白人工标签；绑定原报告 SHA-256，拒绝超出六题范围、重复项和已有审阅包覆盖。只有 18 项齐全且有完成标记才记 `completed`，否则标 `incomplete` 或 `stopped`。它不调用模型、不自动填人工标签、不把机器门禁等同语义正确。新报告尚不存在，因此没有真实审阅包；原诊断报告未改。
- 新增 5 项 `TEST-*`/`synthetic=true` 合成检查，覆盖定位保留、单/多 Agent 与中途停机、无原始模型输出外泄、非法/重复行、缺完成标记及一次性写入。追加后完整后端回归 **248 passed、1 条现有 Starlette/AnyIO 弃用 warning**；Ruff check/format 通过（79 files），`git diff --check` 退出码 0。Web 未改，最近 clean E2E 18/18。新的真实六题模型调用仍待最多 USD 2/48 次明确授权；所有文件留本机，未暂存、提交、推送或创建 PR。

## 2026-10-13：六题付费重跑前的完整后端复核

- 新六题三臂模式保持 dry-run，未发起付费调用。使用当前工作树显式枚举 `backend/tests/test_*.py`，以项目虚拟环境依赖及本机 bundled Python 完成完整回归：**243 passed、1 条现有 Starlette/AnyIO 弃用 warning**；Ruff check 与 format check 均通过（77 个 Python 文件格式合规）。这覆盖了追加 `--post-fix-six-task` 分支后的当前后端代码，但并非 `uv run --locked` 命令。Web 源码未变，本轮未重跑 Web；先前 clean E2E 18/18 为最近记录。
- 报告目标仍不存在且被 `.gitignore` 忽略；原始和诊断报告没有覆盖。费用上限只能由本机守卫估算，服务商账单可能不同。完整六题模型运行仍需新增明确授权；随后若产生答案，还需逐题人工语义核验。没有暂存、提交、推送或创建 PR。

## 2026-10-13：R1 新模型答案人工支持标签与下一轮六题预检

- 用户核对 arXiv:2609.27579 PDF 第 3 页后，确认修订版 R1 模型答案四层主张 `supported`。新 [机器可读审阅元数据](research/R06-R07-r1-generated-review-v1.json)只绑定原报告 SHA、task/source/chunk、人审标签与评估限制，不包含 OpenAI 生成答案或 PDF 原文；原运行 `invalid_model_output`、离线机械回放 `completed` 与用户语义 `supported` 三者分别保存。R1 既有冻结指定直接 chunk 漏命中记录仍保留；这一个新答案不能外推为六题表现。
- 为后续一次完整同题对照准备 `--post-fix-six-task` 独立模式：六题、Skills off/on/双 worker 三臂、每题一次、最多 48 次模型请求、本地保守费用守卫最多 USD 2；固定 `gpt-5.6-sol`、许可/冻结 SHA、只读同源 BM25 与旧报告不可覆盖。dry-run 通过，后端 CLI 定向 11 passed，Ruff check/format 通过。最新全后端 242 passed 是增加该模式前的回归；此次新增 CLI 分支由定向测试和预检覆盖。**新的六题付费调用尚未获授权，未发起。**
- 本轮同步项目台账与上下文，保留全部旧报告；不提交、推送或创建 PR。下一人工门槛为是否授权最多 USD 2 的六题三臂一次试验；若产生模型答案，还需按每题 PDF 人工核验。

## 2026-10-13：修订版 R1 验证、重复输出修复与人工审阅材料

- 用户在原 USD 0.50 总上限内额外批准最多两次 R1 请求。修订版单题验证正常完成两次调用，本地费用估算 `$0.047446`，连同第一次诊断 `$0.040386` 共 `$0.087832`；独立忽略报告 SHA-256 `209438d67d2957c232bde68846be67f65dc1ea2cfee87e0e0160200ddfe1cf4f`。原运行 `invalid_model_output`：模型这次用 `excerpt` 并保留换行，但最终文本是两份完全相同的完整 JSON 连在一起。服务商实际账单仍须以账单为准。
- 适配器仅折叠逐字相同且完整的 JSON 重复；保留普通分段合并，冲突对象仍交给原校验拒绝。对保存的原始模型输出和同轮工具观察离线回放，机械门禁为 `completed`（1 条 claim、1 条 citation）。**离线结果不是原真实运行状态，也不是人工语义正确标签。** 本机忽略的 [R1 人工审阅包](../backend/reports/live_eval/r1-verification-human-review.md)列出答案、逐字摘录、PDF 第 3 页及 chunk ID，待用户核验。
- 合成回归覆盖重复完整 JSON、单片重复、普通分段、冲突输出与跨行证据；后端完整 **242 passed、1 条既有 Starlette/AnyIO 弃用 warning**，Ruff check/format 通过。Web 本轮未改。已批准的额外两次请求均已用完；完整六题配对与最终用户验收尚待继续授权和人工核验。所有原报告保留本机，未暂存、提交、推送或创建 PR。

## 2026-10-13：R1 受控诊断定位精确引用拒绝原因

- 用户明确追加最多 USD 0.50、仅 R1 Skills-off 单 Agent、最多两次 `gpt-5.6-sol` 请求。运行正常完成两次请求，本地保守费用估算 `$0.040386`；原始结果 `unverified_evidence`。本地忽略报告 SHA-256 `b36420fed3eaf31b32513a8f543bf43503b4a9f33d608177dfc1f0699f05c0d4`。报告内模型原始结构化回答显示全文引用 `source_field=fulltext`（契约要求 `excerpt`），且把摘录原有换行折为空格。未把该模型回答计为通过。
- 只读本地反事实回放对同一输出分别修正字段、引用文本、两者一起：原始及两个单项修正版均 `unverified_evidence`，两项同时按工具原文修正才 `completed`。这是机械门禁定位实验，编辑后的结果不是模型真实回答，也不证明语义正确。修复为给 OpenAI 结构化输出 schema 限制 `source_field` 值并在 Harness 指令中明确全文 `excerpt`、原样保留换行和答案/claims 一致性；未放宽逐字引用校验。OpenAI 的 [结构化输出说明](https://developers.openai.com/api/docs/guides/structured-outputs)支持以 enum 和字段描述约束生成内容。
- 新增 4 个 `TEST-*` 合成跨行证据用例，正确字段与逐字换行通过，错误字段或压平换行被拒；定向 6 项通过。完整后端 **237 passed、1 条既有 Starlette/AnyIO 弃用 warning**，Ruff check/format 通过。测试最初因沙箱阻止 TestClient 本地 socketpair 而挂起；放开本机套接字后又遇默认系统 pytest 临时目录权限错误；使用工作区内全新临时目录完成完整回归。`git diff --check` 与 cached check 均无空白错误。Web 本轮未改。
- 这笔诊断授权中的**两次请求上限已用完**，即使本地费用估算低于 USD 0.50，也不自动扩大调用次数。下一步若要观察修订后的真实模型输出，须新的明确请求范围；完整六题三臂效果对照和生成答案人工验收尚未完成。未暂存、提交、推送或创建 PR。

## 2026-10-12：真实模型五次试运行、证据门禁与费用停机

- 用户本机配置 OpenAI Key 后，按已授权的 `gpt-5.6-sol`/六题/首次 USD 2 + 新增最多 USD 2 进行只读试运行；embedding 未启用。首次因本机网络阻断、后续依次因上下文上限、重复检索、工具 schema 不一致而中止或不可评分。修正后第 5 次完成 R1–R5 的 15 个 arm、39 次模型请求，15 次本地 BM25 工具观察为 `ok`；单 Agent 两臂全部 `unverified_evidence`，多 Agent 均 `insufficient_workers`，R6 未运行。没有模型答案通过 Harness 证据门禁，不能报告答案正确率或 Skills/多 Agent 收益。完整事件、各报告 SHA 与费用估算见 [中止记录](research/R06-R07-live-pilot-interruption.md)。
- 新增授权下，第 4/5 次本地估算分别 `$0.896874`/`$0.912712`，合计 `$1.809586`；剩余约 `$0.190414`，下一请求保守预检超限后自动停机。估算不是服务商账单。没有继续发起付费调用。原报告没有保存校验前结构化回答，无法定位每项 `unverified_evidence` 原因；已为后续本地忽略报告加入模型原始 final_text、工具调用与拒绝标志，并以合成 TEST 用例检查，未更改现有报告或放松证据门禁。
- 已准备独立 `--diagnostic-r1` 运行模式：仅 R1 Skills-off 单 Agent，最多一次 BM25 检索/两次模型请求、最多 USD 0.50 本地守卫、独立不可覆盖报告；dry-run 已通过，尚未付费执行。它用于确定具体证据拒绝原因，不是完整六题效果评估。下一人工门槛为新增诊断费用授权。
- 本轮后端 Ruff check/format 通过；用项目虚拟环境依赖与 bundled Python 显式枚举测试文件，**233 passed、1 条既有 Starlette/AnyIO 弃用 warning**。未使用 `uv run --locked`（本执行环境无可用 uv）；Web 本轮未改，沿用此前 clean E2E 18/18。未暂存、提交、推送或创建 PR。之后如有通过门禁的生成答案，还需逐题人工核验。最终项目验收与远端 Actions 均未完成。

## 2026-10-12：六题人审闭合与限额真实模型试运行准备

- 用户完成三篇许可 PDF 的六题单人审阅：R1/R3/R5 候选回答获 supported，R2/R4/R6 获 unsupported；这评的是助手预写候选，不是 Agent 模型输出。2609.27579 第 3 页收紧摘录 bbox `[304.72,176.61,540.32,496.92]` 和 2607.24663 第 10 页 Table III 裁剪输出均获人工通过。冻结的人审记录、任务清单及描述性结果见 [六题结果](research/R01-R03-real-evidence-pilot-result.md)。R1/R4 的指定直接证据 chunk 未进当次 BM25 前 8 条，不计检索成功。
- 用户授权把三篇 CC BY 4.0 论文的检索摘录发送至 OpenAI `gpt-5.6-sol`，六题各一轮，总费用上限 USD 2。官方当前标准短上下文价格为输入 $4/百万 tokens、输出 $20/百万 tokens；本机守卫保守按 $8/$30 估算，限制最多 72 次 provider 调用、单次输出 600 tokens、下一请求预估超额即停。协议与界限见 [R06/R07 live 预注册](research/R06-R07-live-eval-protocol.md)。本机守卫不是服务商账单硬上限。
- 新增默认 dry-run、显式 `--execute --confirm-licensed-excerpts` 的只读试运行器；固定六题/模型/上限、只允许逐题指定 arXiv 源的 BM25 工具、核对许可/index 和冻结文件 SHA，结果写入 Git 忽略的本机报告。5 项 TEST 合成门禁与 dry-run 通过；完整后端回归在本阶段复核。**本机 `D:\\papertrail-main\\.env`、`backend/.env` 与进程环境均未配置可供本运行器读取的 `LLM_API_KEY`，因此尚无任何新付费模型调用，也无 R06/R07 真实收益结论。**下一人工步骤是在本机配置凭据，勿在聊天发送密钥；之后继续同一固定试运行，不需要再次批准已授权的 6 题/$2 范围。未暂存、提交或推送。
- 后端完整回归改用现有本机 Python 与项目虚拟环境依赖，显式枚举 `tests/test_*.py` 以避开 `tests/tmp*` 旧锁定目录，并加入已安装的 pywin32 路径：**229 passed，1 条既有 Starlette/AnyIO 弃用 warning**。此前直接 `pytest -q` 因 pywin32 模块路径及旧临时目录权限在收集阶段失败，保留该失败记录，不把它说成通过。全后端 Ruff check/format 通过，OpenAPI 导出 SHA 仍为 `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`；Web 本阶段未改，先前 clean E2E 18/18 记录仍适用。显式 live 命令在无 Key 时拒绝、未生成报告、未产生付费请求。

## 2026-10-12：Web E2E 进程退出复核

- 此前 parser v13 阶段的 Playwright 18 个用例虽然输出通过，但进程未正常退出；本轮在本机忽略的 `web/node_modules` 内恢复缺失的 package junction，以 bundled Node 24.19.0 单独启动 Next 16.3.8 的 3001 开发服务，随后用同一 Node 调用 `node_modules/@playwright/test/cli.js test`。18 个用例全部通过，测试进程在 15.5 秒内以退出码 0 结束；开发服务随后停止，3001 端口未再监听。该结果补齐本机 E2E 的干净退出证据，没有修改 Web 源码或锁文件，也没有运行 GitHub Actions。
- R01/R03 六题仍待用户人工标注，Table III 裁剪结果仍待独立核对；不因自动 E2E 通过改变这些质量门槛。此次没有调用模型、暂存、提交或推送。

## 2026-10-12：第二轮 PDF 人工核验与 bbox 说明修正

- 用户确认 2609.27579 第 3 页右栏摘录内容、正文类型及独立性正确，指出原文档将含 `Query and Retrieval Pipeline` 的父 paragraph bbox 当成所列摘录 bbox；2608.02037 Figure 5 通过；2607.24663 Table II 五条数据、百分比单位与“解析器物理行 5–9”的含义通过。Table III 原表一表头加五数据行已由用户确认，但其裁剪输出尚未由用户独立核验。
- 只读复核 PDF 第 3 页逐行定位词坐标：所列 `Data Layer` 至 `similarity search and structured filtering.` 摘录 bbox 为 `[304.72,176.61,540.32,496.92]`，对应父元素字符 `[0,1375)`；父 paragraph bbox `[304.72,176.61,540.32,561.30]`，确实还包括 Query 标题、说明及 `Input: User query Q`。已在审阅包同时明确两种范围，没有修改解析器或数据库。
- 将 2607.24663 第 10 页 Table III 的实际结构化输出（bbox `[113.40,263.89,502.70,325.71]`、1 表头/5 数据）加入审阅包；其后独立正文元素最早从 y=`349.38` 开始。这个机器检查支持“当前解析未混入正文”，尚待独立人工核对该裁剪输出。
- 本项仅修订审阅材料和状态台账，不以既有自动测试结果冒充本轮重跑。R01/R03 真实许可语料的六题人工任务核验材料已在下节完成；R06/R07 真实模型收益仍待用户明确模型、题数、重复次数及费用上限。

## 2026-10-12：R01/R03 三篇真实语料六题候选与 BM25 排名冻结

- 基于 2609.27579、2608.02037、2607.24663 的已许可本机全文，准备 [六题人审包](research/R01-R03-real-evidence-pilot-review.md) 与 [机器可读候选/检索记录](research/R01-R03-real-evidence-pilot-v1.json)，JSON SHA-256 `9ceb30530faff7fae5a6ea085479b6755d6277077211c306e6758cd52e2ae0e3`。每题只读、固定源论文 BM25 前 8 项，记录源 PDF/index SHA、候选答案、助手指定来源及排名。没有调用模型或 embedding，没有改动索引。
- 六题中，助手指定的直接来源在前 8 项中的名次为 R1/R4 未进入、R2 第 1、R3/R5 第 2、R6 第 3；这只是来源候选的机械排名，不能当作真实 Hit@k 或质量分数。候选集中明确 `synthetic=false`、`review_status=pending_human`、`gold_standard=false`、`quality_claim_allowed=false`，所有 `human_review` 均为 null。JSON 已解析校验任务 ID 唯一及标签待审状态。
- 下一人工门槛：用户对六题给出 PDF 可答性、候选回答支持度，并核对 Table III 裁剪结果。此前单篇 4 题用户标签仍单独保存，不能与新候选合并成“十题已人审”。真实 Skills/多 Agent 对照还需用户指定 provider/模型、题数、重复次数和费用上限。
- 本阶段在人工门槛前复核：六题候选 JSON SHA-256 与审阅包一致；根目录 working/cached `git diff --check` 均退出码 0（working tree 只有既有 CRLF 提示）。此次只改文档及冻结候选数据，不重跑产品代码测试；此前 parser v13 的 `224 passed` 与 E2E runner 未正常退出状态保持原记录。未暂存、提交或推送。

## 2026-10-12：回应三篇许可论文人工核验并修订解析（parser v13）

- 用户人工复核结论：2609.27579 第 1 页摘要正确；第 3 页 `Textual sources...` 与 `Data Layer...` 都是右栏正文而非图中文字，之前抽样包分类有误且未展示完整段落。2608.02037 第 9 页 Figure 5 通过；2607.24663 第 10 页 Table II 列和值正确、四个指标单位为 `%`，原表为 5 条系统数据行，旧 locator“行 2–9”不够清晰。
- v13 将正文 positioned-word 的 `x_tolerance` 从 2 降为 1（表格单元格阈值仍为 2），重新解析后 2609.27579 第 3 页目标右栏保持单独 paragraph，bbox `[304.72,176.61,540.32,561.30]`，不包含左栏；`subsystem label`、`component identifier`、`time stamp (when available)`、`stored together with metadata` 的词间空格恢复。页面保留 `multi_column_reading_order_ambiguous` 警告，并在新审阅包展示右栏完整片段。PDF 原文里的跨行断词连字符和换行仍在。
- `2607.24663` Table II 结构有 9 行，其中前 4 行是分层表头、后 5 行为数据；chunk locator 明确为 `第 10 页 · table · 解析器物理行 5-9`，BM25 返回全部 5 个系统行。另核实 Table III 的结构化 bbox/内容只含表格的 1 行表头和 5 行数据，不包含下方正文。
- 三篇已按 v13 刷新本机全文：2609.27579 51 chunks，2608.02037 322，2607.24663 755；许可状态均保持 approved，源 PDF SHA 未变。2609 重复导入返回 `unchanged`。BM25 smoke 命中右栏、Figure 5 与 Table II。PDF 定向 `40 passed`；全后端 `224 passed, 1` 条既有 Starlette/AnyIO 弃用 warning；Ruff check/format 通过；OpenAPI 导出 SHA 保持 `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`；Web format/typecheck/build 通过。Playwright 18 个用例均输出 passed，但 runner 在用例结束后没有退出，等待后人工中断，退出码非 0，因此本轮 E2E 记录为“18/18 用例报告通过、进程退出未确认”，不作为干净通过。根目录及 cached `git diff --check` 通过，只有既有 CRLF 提示。未提交或推送。
- 新审阅包：[三篇论文 RAG 抽样审阅包](research/R02-three-paper-review-pack.md)。当前人工验收状态：2608.02037 已通过；另外两篇内容经代码修复后待用户确认新片段/定位。未提交或推送。

## 2026-10-12：三篇许可论文导入、双栏污染修复与 RAG 抽样（parser v11，历史）

- 用户在本机成功导入三条 arXiv 元数据：`2609.27579` snapshot `ffd3ddf1-1d6a-4b13-bd44-b72544202884`、`2608.02037` snapshot `b0b9a403-3cee-432f-8c4d-6818deafbe62`、`2607.24663` snapshot `fa04ccac-7251-46be-bf2e-e88ea1112c47`。来源元数据的 arXiv `CC0-1.0` 与各论文全文 `CC-BY-4.0` 是不同许可记录。
- 三篇逐篇许可 manifest 均通过检查，PDF 在本机导入默认 host SQLite，parser 为 `pdfplumber-layout-v11`：`2609.27579` 4 页/1 图像区域/1 图注/0 表格/111 chunks；`2608.02037` 16 页/27 图像区域/2 匹配图注/0 表格/318 chunks；`2607.24663` 38 页/13 图像区域/6 图注/4 表格/991 chunks。源文件 SHA-256 分别为 `f944b10d58484c1d57c5dba23a1e4c18fcc1a07a18606e0c2b728d9cb46ba20d`、`e3b9029a72c6466c837e8c1b320dbddca1800d353d0e667b383adfd552e04d51`、`eea9e7fa8917ca11c62802765865265aa4961c959579cd34633d8622f88ede5c`。三篇均保持 approved；重复导入 2609 返回 `unchanged`。
- 真实检索抽样：2608 查询命中第 9 页 Figure 5 的 488 nm 图注以及 940 nm 图注；2607 查询命中第 10 页 Table II 结构化表格，70.3、8.7、64.1、71.2 等列值保持列序。2609 查询检出双栏交错风险后，解析器按列边界拆分段落并从正文排除 upright=false 的旋转 arXiv 边栏文字；输出页级 `multi_column_reading_order_ambiguous` / `rotated_text_excluded` 警告。抽样是单次 BM25 smoke，不是准确率 benchmark。
- v11 回归：parser 定向 `24 passed`；全后端 `223 passed, 1` 个 Starlette/AnyIO 上游弃用 warning；Ruff check、format check、OpenAPI 导出均通过，OpenAPI SHA-256 仍为 `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`；`git diff --check` 与 cached diff check 通过，Git 仅报告既有 CRLF 转换提示。未调用 LLM/Embedding，未暂存/提交/推送。
- **下一步必须用户参与**：先核对 [三篇论文 RAG 抽样审阅包](research/R02-three-paper-review-pack.md) 的页码、表格值、图注及解析片段是否与原 PDF 相符，并回复每篇“通过/有误/需修改”。用户核验前不宣称 R02 新语料人工验收通过。Compose Web 使用独立命名卷，host CLI 导入不会自动显示在容器 Web。其后如运行 R06/R07 真实模型收益对照，仍需用户指定模型/provider、题数、重复次数与费用上限；未获 GitHub 上传授权前保持本地。

## 2026-10-12：新增三篇许可论文的 parser-only 检查与双栏表格修复

- 用户提供三篇论文及 arXiv 页面许可截图；项目方确认每篇为 arXiv 下载并显示 CC BY 4.0。官方条目/许可入口已核对，忽略目录中的三个 manifest 均通过许可预检。本机 SHA-256：`2608.02037` `e3b9029a72c6466c837e8c1b320dbddca1800d353d0e667b383adfd552e04d51`；`2607.24663` `eea9e7fa8917ca11c62802765865265aa4961c959579cd34633d8622f88ede5c`；`2609.27579` `f944b10d58484c1d57c5dba23a1e4c18fcc1a07a18606e0c2b728d9cb46ba20d`。
- parser-only 结果（未写入数据库）：`2608.02037` 16 页/330 元素/27 image regions/6 个 caption 元素/0 表格，6 页保留 sparse-table warning；`2607.24663` 38 页/476 元素/13 image regions/6 captions/4 表格，检测 Table I、II、III、IV，页 10 两张表与正文分离；`2609.27579` 4 页/66 元素/1 image region/1 caption/0 表格，无 warning。警告和指标不能等同于语义识别或质量准确率。
- 真实页对照发现旧 parser v6 漏掉 `2607.24663` 双栏 `TABLE I.`，且把 Table II 附近正文误纳入表格。parser v7 支持罗马数字/粘连 caption，通过表格局部横线约束 text-table crop，并在下一张表 caption 前停止。新增双 caption / 双栏回归；`test_pdf_parser.py` 当前 21 passed。真实 parser 抽样第 3、10、13 页可视结果：Table I（8 数据行）、Table II（5）、Table III（5）、Table IV（10）；页 10 两张表均不再混入正文。此修复不是一般 PDF 全面准确率证明。
- 本轮全后端回归 `220 passed, 1` 个 Starlette/AnyIO 上游弃用 warning；Ruff check、format check、OpenAPI 导出通过，OpenAPI SHA-256 仍为 `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`。使用 Codex bundled Python 加项目锁定 site-packages，配置 Win32 路径并用工作区 pytest basetemp；未声称 `uv run --locked`。
- 新论文的 arXiv 元数据尚未进入 host `data/papertrail.sqlite3`（三条精确 ID 读取均为空），全文自然也尚未导入/RAG 验收。先前本地 arXiv 请求遭上游限流；下一步需在用户 PowerShell 通过 CLI 精确导入三条元数据，然后主执行环境继续全文导入、表/图检索和验收。Docker Compose 用命名卷，与 host `data/` SQLite 不是同一份数据库；后续 Web 端数据演示要单独确认数据接入方式，不能把 host CLI 导入误报为 Compose 中可见。
- 本步仅改 parser 和合成回归，未写数据库、未调用 LLM/embedding，也未提交/推送。下文历史测试条目保持为当时快照。

## 2026-10-12：R03 单篇人工证据核验完成；R05 Host smoke 通过，下一步待容器运行时

- 用户完成 R03 核验包 E1–E4 标注：E1/E2/E3 `supported`；E4 `unsupported`，理由是 Table 3 列头下 Physician 均值 4.22 低于 Physicist 5.00，与候选回答相反。原始用户判断已登记在 [机器可读审阅记录](research/R03-human-evidence-review-arxiv-2608.20519-v1.json)。
- 该样本只是一位用户对一篇 CC BY 4.0 论文的 4 条候选答案做支持度判断；没有独立双标，也不是系统生成答案的盲评，不能据此报告总体 RAG 指标。真实文档仍与 `TEST-*` 合成集分离。
- 自动检查未因文档标签变化重跑；上一轮代码回归为 219 passed，Ruff check/format 通过。新增审阅 JSON 已解析校验通过，包含 4 条标签。
- 后续人工质量门槛：R05 MCP Host smoke 和 R08 本机 Compose build/up/readiness 已通过。尚需扩展真实许可论文的 R01/R03 评测，并由用户明确 R06/R07 live 对照的许可语料、模型、题数、重复次数与费用上限；最终用户验收及远程 GitHub Actions 尚未完成。

## 2026-10-12：外部 MCP Host 真实只读调用通过

- 用户桌面 Host 显示 `papertrail` 已连接并启用 5 个工具，随后用户实际调用 `retrieve_paper_evidence` 成功。响应状态 `ok`，`scanned_chunks=209`、`truncated=false`、`retrieval_method=bm25_fulltext_v1`。
- 前三条结果包含第 20 页 Table 3 说明段落、第 19 页结果段落和第 20 页结构化表格。来源为 arXiv `2608.20519`、许可 `CC-BY-4.0`，表格保留 Physicist/Physician/Pooled 列序与原值；Table 3 检索结果未带 element warning。人工用户调用，不由项目调用 Host 模型。
- R05 单 Host 只读 smoke 通过。只证明这一查询的协议、论文/许可来源与表格定位链路，不代表总体检索或答案质量。响应含第 18、19 页 `sparse_table_candidates_rejected` 警告，记为保留解析限制。完整证据和未覆盖范围见 [R05 验收](research/R05-mcp-acceptance.md)。
- 文档台账与当前上下文已同步；本步未改代码、未运行测试。机器可读 R03 标签仍为 E1–E3 supported、E4 unsupported。

## 2026-10-12：用户本机 Docker Compose build/up 验收通过

- 用户 Windows PowerShell 截图显示 `docker compose up --build -d` 成功：backend 和 web 镜像构建完成，Compose 6/6 资源就绪，backend `Healthy`、web 已启动；`docker compose ps` 中两容器均为 `Up` 且 `(healthy)`，Web 仅绑定 `127.0.0.1:3000`。
- 本执行会话访问 `http://127.0.0.1:3000/api/status` 得到 `status=ready`，application/database available、LLM/Embedding disabled；首页 HTTP 200 且包含 PaperTrail 标题。由于此会话 PowerShell 无法解析 `docker` 命令，容器清单依用户截图记录，无法由本会话单独检查生命周期或停止服务。
- R08 本机 Compose build/up/readiness smoke 通过；未配置或调用模型 API。GitHub Actions container job 仍未触发，R01/R03 扩展许可语料评测、R06/R07 live 收益对照和最终用户验收仍未完成。
- 本轮最终本机回归：后端 `219 passed, 1 warning`（Starlette/AnyIO 上游弃用）；Ruff check、Ruff format check、OpenAPI 导出通过，导出 SHA-256 `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`。Web format check、typecheck、production build 通过；Playwright E2E `18/18 passed`。E2E 在 Windows 下按开发手册先启动 3001 服务后执行。测试使用 Codex bundled Python 与项目锁定 site-packages，补入 pywin32 路径；本机 `uv` launcher 目标不可用，因此本轮未声称 `uv run --locked`。

## 2026-10-12：R02 PDF 表格续词、图注修正与全文 RAG 验收（本地复验）

- **后续复验更正前文状态**：用户运行 arXiv 精确 ID 导入成功；许可 manifest 预检后全文已导入本机索引。旧条目中“未导入/没有 SQLite/等待用户重试”为当时历史状态，现已被本条更新替代。
- parser v6 将定位文字与表格抽取统一使用 `x_tolerance=2`，修复 Figure 7/Table 3 caption 粘连。当前为 211 elements、3 tables、7 image regions（5 raster + 2 vector boundary）、7 captions、209 chunks；Figure 7 caption 如 `Independent expert ratings` 已恢复正确空格。保留 2 个 sparse-table candidate warnings。
- 用户运行 arXiv 导入成功，导入 1 条记录/1 个版本，snapshot `934cc269-9175-4cb7-abda-89713fa00864`。本机 PDF manifest 预检通过后写入默认数据库 `data/papertrail.sqlite3`；source document SHA-256 `7d664debd8dc5c83119c0b1b64a9d8ef2a277eca54cea402dd786fd9d311ce31`，source text SHA-256 `57a5b7dfa79828d1f2115e75d163f41901c1f6028ebda6245532128830aaa545`。同一输入重复导入返回 `status=unchanged`。
- BM25 smoke 命中 Table 1、Table 2/3 及 Figure 7 caption 的对应内容与页级定位。仅证明该单篇文献的导入/检索/定位链路，不证明语义问答质量或一般 PDF 准确率。Table 2 IVIM 下标错序、图表内部语义未解析仍为已知限制。
- 历史快照：当时为 R03 人工标注生成了 [逐题核验包](research/R03-user-evidence-review-pack.md)。用户后来已完成全部 4 题标注，见本文件顶部的后续记录；标签没有被当作通用 gold 或质量结论。
- v6 全后端 `219 passed, 1` 个 Starlette/AnyIO 弃用 warning；Ruff check 与 format check 通过。没有调用 LLM 或 Embedding API。

- 用户提供 arXiv:2608.20519v1 PDF，并确认来源为 arXiv、许可为 CC BY 4.0；核对官方 [arXiv 页面](https://arxiv.org/abs/2608.20519) 与 [CC BY 4.0 说明](https://creativecommons.org/licenses/by/4.0/)。源文件 SHA-256 `7d664debd8dc5c83119c0b1b64a9d8ef2a277eca54cea402dd786fd9d311ce31`，保留本机且未入索引、未提交。
- 在 `chunk_pdf_elements` 中仅合并明确的同列连字符续词；检索文本可恢复 `streaming` / `denoising`，citation evidence 保持原始抽取跨度，locator 保留全部物理表格行。普通换行和不明确的跨列延续保持原样。
- 为附近图注识别足够大的矢量矩形外框，生成 `region_source=vector_boundary` 的图像区域；真实论文 PDF 第 18/19 页 Figure 6/7 分别与 caption 关联。这里只建立可追溯的位置关系，不解析曲线、坐标或数值。随后将表格单元格抽取 `x_tolerance` 降至 2，修复 Table 1 单词粘连，解析输出版本升为 `pdfplumber-layout-v5`。
- 当前解析 29 页输出 211 elements、3 tables、7 image regions（5 raster + 2 vector boundary）、7 figure captions；保留 2 个页面级 warnings。真实表格和矢量图改进均有 `TEST-*` 回归，但单篇视觉抽样不等同于一般 PDF 准确率。
- 用户提供 PDF 第 6/14/18/20 页截图后，Table 2 的 3 列逻辑结构得到直接视觉证据。chunker 将 blank header 子列并入相邻可见标题，并把跨 cell 的 `h` + `ead` 合为 `head`，保留原始 4-cell evidence 字符串和原行 locator；`meta-analyses` 的词汇连字符也保留。真实 chunk 输出已确认 Table 2 为 `Attribute | Categories (examples) | Coverage`。
- 降低表格单元格抽取间距容差后，Table 1 的 `Web server and real-time progress streaming` 等文本恢复空格；parser/fulltext/store 组合 `50 passed`。全后端 `212 passed, 1` 个 Starlette/AnyIO 上游弃用 warning；全量 Ruff check/format 与 OpenAPI 导出通过。未导入 PDF 全文。
- 新增[原文与解析结果对照包](research/R02-user-review-pack.md)，给出表格检索 chunk、Figure 6/7 区域坐标和人工核验点。Table 2 的 IVIM 下标顺序仍有抽取缺陷，材料按真实输出展示；用户尚未确认 R02。
- 用户回复“看起来没什么问题，请你继续”，接受了本轮展示的表格 chunk 与 Figure 6/7 locator 抽样结果（保留 IVIM 下标等已披露限制）。R02 单篇样本人工核验通过，但不代表一般 PDF 准确率；图表内部内容读取仍不支持。Table 3 的 `±` 已确认解析为 U+00B1。详见 [R02 验收](research/R02-pdf-structure-acceptance.md) 与根目录 [`current_contexts.md`](../current_contexts.md)。
- 继续 R01/R03 真实全文 RAG 验收时，本机未发现 SQLite 目录，固定 arXiv 客户端针对 `2608.20519` 的请求被上游限流，尚未创建数据库或导入论文。已准备本地忽略的许可 manifest；待精确 ID 元数据导入成功后继续 PDF 全文导入、检索和证据回归。不调用 LLM/Embedding。
- 用户按步骤运行 CLI 后也收到 `ArxivRateLimitError`，确认问题来自上游限流而非命令。改进 CLI：安全读取 delta/date 两种 `Retry-After`，无有效提示时建议至少等待 5 分钟；错误文本不回显不可信响应头。新增限流头/非法值/CLI 可操作报错回归。后端全量 `218 passed, 1` 个 Starlette/AnyIO 弃用 warning；Ruff check/format 通过。待限流窗口过去后由用户再执行一次精确元数据导入。

## 2026-10-11：R02 PDF 引擎集成与 R04 Trace 脱敏补强

- R01/R07 当前工作树合成 CLI 复跑：R01 all/dev/test answerability accuracy 分别 40/40、21/21、19/19，Evidence Hit@1/3 分别 24/24、12/12、12/12；R07 冻结 manifest 校验与两题双臂配对 smoke 成功。所有 report 维持 `quality_claim_allowed=false`；R07 的 +0.75 任务差值来自手写 TEST observations，不是模型结果。忽略目录下的本地报告见 `backend/reports/audit-*.json`。
- 新增纯标准库合成的 `TEST-synthetic=true` 有效 PDF，实际交给 pdfplumber 打开，覆盖正文、带边框表格、单元格值和页面坐标；R02 parser/fulltext 定向测试由 24 项增加至 25 项。不引入生成器依赖，也不代表真实版面质量通过。
- 只读 R04 审查发现模型工具名未经白名单归一化就写入运行 trace。现在仅记录本轮注册工具的规范名称，未知名称记录为 `unknown_tool`；回归把 `TEST-SECRET` 置入问题和工具名，验证 API 返回对象与 SQLite 脱敏账本不泄漏明文。
- 运行生命周期 `completed/failed/cancelled` 与 `result_status` 分开；`insufficient_evidence` 等正常安全终态不再误记为执行失败。预算/超时/provider 不可用/无效输出仍标记失败。
- 新增 API 级 mock 取消回归，覆盖 ask 请求活动中收到 cancel、Harness 安全检查点返回及账本最终 `cancelled`；不调用真实模型。
- R03 claim 证据 gate 现在额外执行显式数量、单位、方向和实验组/数据集标签的一致性筛查，并绑定数量与同组标签，发现错配返回 `unverified_evidence`。7 个 TEST 合成端到端情形覆盖正例、数字/单位/组别错配和方向/否定矛盾；该规则不做语义蕴含判定。
- 全后端最新回归 `205 passed, 1` 个 Starlette/AnyIO 上游弃用 warning；全量 Ruff check 与 format 通过。R04 多实例活动任务协调及增量 trace/replay 仍未覆盖；许可 PDF 人工视觉验收继续按用户要求暂缓。
- R08 当前 Web 工作树复验：`pnpm run format:check`、`pnpm run typecheck`、`pnpm run build` 与 `pnpm run test:e2e` 均正常退出；E2E `18/18`，覆盖 375/768/1440 三种视口，未修改 Web 源码或依赖锁文件。

## 2026-10-11：R07 冻结任务集绑定与质量声明边界

- CLI 现在要求传入冻结 task manifest，校验 manifest 原始字节 SHA-256、schema、严格字段、唯一 task ID、synthetic 状态，以及 trial observations 与清单 task IDs 的精确一致；合成条目必须使用 `TEST-*` 和 `synthetic=true`。示例数据集哈希已绑定到真实文件字节。
- 评估报告改为 schema v2，明确记录 `label_source_declared` 和 `review_record_sha256_declared`。由于 CLI 无法认证许可或人审内容，`quality_claim_allowed` 对所有数据固定为 false，避免仅凭调用者声明打开质量结论。
- R07 配对评估定向测试：`8 passed`；加上协调器 `8` 项，共 `16` 项 synthetic R07 契约测试。R07 阶段全后端 `195 passed, 1` 个 Starlette/AnyIO 上游弃用 warning；Ruff check/format 通过；CLI 固定 TEST smoke 通过，报告摘要与 manifest SHA 一致，quality claim 关闭；OpenAPI SHA 维持 `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`。没有调用模型或使用真实论文。
- 随后 R02/R04 补强后，README、简历事实表、R08 验收文档与本路线图状态中的最新后端回归更新为 `197 passed`；R04/R05/R07 的阶段历史结果保留。
- R08 本轮再次执行依赖审计：后端 `pip-audit --progress-spinner off` 和 Web `pnpm audit --audit-level moderate` 均退出码 0、无已知漏洞；pnpm 为锁文件对应的 `11.25.0`。审计使用获准的本机网络；当前环境没有 `uv` 命令，后端使用项目 `.venv` 中的锁定 pip-audit，未声称执行 `uv run --locked`。
- R08 本轮扫描当前 47 个 Markdown 文件的 88 个本地相对链接目标，断链 0；扫描排除依赖/构建缓存，忽略 `:line` 行号后缀，外部 URL 和纯锚点不计。
- Git 可见文件盘点发现历史 pytest 临时目录仍含合成 PDF fixture。为保护现有本机状态未删除文件；新增 `.gitignore` 规则 `backend/.pytest-tmp-*/` 和 `backend/tests/.pytest-tmp-*/`，将这类生成目录排除在 Git 可见路径外，已复核忽略规则生效。
- R08 Web clean install 复核：从 `web/package.json` 和 `pnpm-lock.yaml` 在隔离临时目录运行 `pnpm install --offline --frozen-lockfile --ignore-scripts` 成功，31 个锁定包从本地 store 安装；Prettier `3.9.8`、TypeScript `5.9.3`、Next `16.3.8`、Playwright `1.63.0` 均能解析。临时目录已清理，锁文件未改动。
- R08 容器复现：新增后端/Next.js Dockerfile、根 `compose.yaml`、两个 build-context `.dockerignore`；Web 启用 standalone 输出。Next standalone 构建、本机 `node server.js` + 临时 SQLite 后端的 Web→API readiness smoke (`HTTP 200`, `ready`)、Web format/typecheck/build/E2E `18/18` 均通过；Compose/CI YAML Prettier 解析格式通过。GitHub Actions 新增依赖后端和 Web jobs 的 container job，配置校验后 build/up 并烟测首页与 readiness，最后删除临时 DB volume。当前主机没有 Docker/Podman且未推送变更，因此镜像 build/up 和该 CI job 均未执行，仍是 R08 验收缺口。单独跨沙箱 loopback 探测失败，已在同一受控测试进程中成功验证并记录限制。

## 2026-10-11：R04 有界多轮约束修正

- Agent 请求增加 `history`：最多 4 组完整 user/assistant 对，最多 8 条、累计 8,000 字符，每条 ≤4,000 字符，并验证角色严格交替。Web 工作区按最近 8 条/8,000 字符保留内存对话，支持追问和清空；不使用 localStorage，刷新后历史清空。
- 历史以显式标记的 JSON 上下文放入当前模型输入并声明为 untrusted context only。Harness 的 citation/quote ledger 每轮重新创建，因此历史回答不能代替本轮检索证据；token/context/deadline/tool budgets 仍逐运行执行。
- Migration 0010 为 `agent_runs` 增加 `history_sha256`，只保留摘要；旧数据库既有行用空历史 digest 默认值升级。question/history 明文都不持久化。
- API/OpenAPI 与 Next 代理增加有界 history 合约，含 HTTP schema 验证、角色序列和字节体积限制。验收：后端全量 `187 passed, 1` 个 Starlette/AnyIO 弃用 warning；Ruff check/format 通过；Web format/typecheck/build 通过，E2E `18/18`；OpenAPI SHA-256 `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`。历史明文不落盘，migration 0010 兼容旧 run 行。真实论文质量验收仍待用户提供许可 PDF。

## 2026-10-11：R05 MCP SQLite 引擎只读加固

- 发现原 MCP 注册表虽只公开读工具，底层普通 `PaperStore` 读路径会执行 schema 检查并自动应用缺失迁移；这与“外部工具只读”的安全表述不完全一致。
- 新增 `PaperStore(readonly=True)`：SQLite URI 使用 `mode=ro`，不创建缺失文件/目录，不自动迁移旧数据库；打开前核验数据库 schema 当前且 migration checksum 一致。MCP 默认路径不再实例化完整 Settings，仅读 `DATA_STORAGE_PATH`，避免为了只读查询加载不相关的 provider 配置。
- 新增缺失/旧 schema 不写入、引擎拒绝 DDL、MCP 实际只读打开的回归；另补 Cursor Windows stdio 配置和人工 smoke 步骤。外部 Cursor Host 尚未连接。
- 验收：全后端 `192 passed, 1` 个 Starlette/AnyIO 弃用 warning；Ruff check/format 通过。OpenAPI 未变化。同步审阅报告中的源码链接为仓库相对路径，并扫描 43 个 Markdown 文件的本地链接，未发现断链。

## 2026-10-11：R07 配对对照评估与协调器加固（后续已由上方验收补强）

- 增加禁用于生产路径的单 Agent/多 Agent 配对评估模块与 CLI：按 `task_id` 聚合同题重复 trial，要求两组题目和 trial 完全匹配；输出逐题成功率、task-level paired delta/bootstrap 区间、成本比、token、延迟、证据有效率与安全违规数，并绑定输入/任务数据 SHA。
- 原始版本仅检查调用者声明；后续已由上方 R07 补强改为验证冻结任务清单 SHA 与 task ID，并对所有结果关闭 quality claim。没有调用模型或加载真实论文。
- Coordinator 捕获单 worker 异常并只记录异常类型，不把原始异常内容带入结果；用模型分项和工具 trace 分项的最大值核算 token，防止聚合字段低报。失败 worker 后可以继续其他 worker。
- 阶段初验收时新增 R07 定向用例 `13 passed`、后端全量 `183 passed`；最新验收数字见本文件顶部。真实收益仍待许可语料/用户预算和人工评审。
- 同步当前上下文、R07 验收、作品集 README 测试数和链接；本地未提交、未上传。

## 2026-10-11：R03 arXiv inline 引用与 R06 对照开关

- Harness 现在检查正文中可识别的 OpenAlex `W…` 和新式/旧式 arXiv ID（包括版本后缀）是否列入对应 citation IDs；ID 仍须出现在本轮工具观察中。arXiv 端到端回归涵盖已列引用通过、漏列引用拒绝。
- Harness 新增 `skills_enabled` 内部对照开关，默认值保持 `true`；关闭 Skills 时仍使用固定 system policy 与完整只读 tool registry。相同问题、固定 mock 输出的 on/off 测试对比终答、证据、引用、工具调用和 skill metadata；此测试不证明真实模型效果，开关不暴露生产 API。
- R03/R06 已同步 roadmap、TASKS 与阶段验收文档。代码改动后需重跑全量回归并更新最终计数。

## 2026-10-11：Agent Harness、结构 PDF 与评测闭环改进（本地实施中）

- 用户已授权完整本地改进、测试和用户验收前暂不上传；Git 的起始 staged additions 已保留。本轮不 commit、不 push。
- R02 已完成高风险解析修复并通过目标 synthetic 测试：双栏顺序、章节跨页、表格原始行/bbox/cell 对应与 chunk locator、图注歧义标记、缺坐标时的表格重复规避、同一份 PDF bytes 哈希与解析、重复元素 ID，以及 legacy offset 和删除级联。真实版面质量仍待许可样本人审。
- R01 synthetic 任务集升级为 v2：12 篇 `TEST-*` 文档按文档分组切为 6/6 dev/test，40 题按其证据文档归属拆分为 21/19，runner 支持 `--split` 并只检索同 split 文档；全量/dev/test CLI 均已运行。结果仍只是 synthetic contract，不是独立质量结论；详见 [R01 验收](research/R01-acceptance.md)。
- R03 增加书目元数据字段与许可全文 excerpt 的证据类型区分；claim 只能引用本轮观察到的准确 field/quote/chunk，答案文本必须精确等于 claims 的服务端规范拼接，拒绝未声明句子。UI 标示书目字段/全文位置，并继续说明语义蕴含未经验证。chunk 按 1,800 UTF-8 bytes 上界切分（非 provider 精确 tokenizer）；migration 0009 将 retrieval/evidence 分离，PDF child chunk 关联到原解析元素，命中时最多扩展同 parent 或同 section path 的相邻 child，并逐项验证 quote/citation。表格检索 context 可含重复表头，引用 excerpt 只包含原始数据行；整节全量扩展和语义质量评估仍未实现。
- R04 增加模型与 embedding 共用的累计观测 token 预算；迁移 0008 保存 run ID、问题 SHA-256、状态、计数和脱敏 trace，不保存问题正文、回答或证据摘录。重复 run ID 返回冲突，提供状态查询/主动取消，查询到无活动实例的 running run 时标为 interrupted。预算按 provider 返回 usage 结算，单次在途调用仍可能越过上限；字符上下文上限不是 tokenizer 精确 token 限额；进程重启仅识别中断，不自动重放调用，也不保存多轮正文。
- R05 MCP 固定只读 tools、stdio/SDK 客户端协议测试通过；Server 只暴露当前可用 BM25 evidence 方法，embedding 错误在 MCP 结果中标为协议错误。
- R06 三个 registry/hash pin Skills 的选择、正文漂移和执行白名单契约通过；尚无真实模型同题收益结论。
- R07 用户选择“先搭框架、待提供许可语料和批准预算后验收收益”。新增默认不接入生产 `/agent/ask` 的 sequential worker/supervisor 实验协调器，限制最多 3 workers，共享 token/tool/deadline/cancel 预算，只在 claims 与 citation IDs 完全一致时报告 consensus，冲突不合成答案。合成契约不构成效果证明。
- R00 锁定 clean install、后端/Web 全量检查、OpenAPI 导出及依赖审计已完成；细项见根目录 [`current_contexts.md`](../current_contexts.md)。用户本轮暂缓提供真实许可 PDF，故版面验收记为待补材料；真实模型效果和多 Agent 收益亦不作质量声明。
- R08 本地交付材料已同步：运行说明、任务/项目规格、进度台账、路线图事实状态和 R04—R07 验收记录已更新。用户最终检查仍未完成，因此本轮目标未标记整体完成。
- R08 验收记录：[工程交付与作品集](research/R08-acceptance.md)。容器配置已补齐；本机 Next standalone 入口 smoke 通过，但 Docker/Compose build/up 需在安装容器运行时后验收。
- R03 发现并修正字符数 chunk cap 对 CJK 高估 context 的缺口；新增长篇 CJK 正文和表格切块测试，真实 PDF/语义验收仍待许可材料。

## 2026-10-11：启动完整改进（R00/R01）

- 用户已恢复本地改进工作，要求实现计划中的 Skills/MCP/上下文与 multi-agent 项，并持续到完整验收；不推送 GitHub。
- Git 仓库已存在但 `master` 无任何 commit，起始工程 126 个文件均为用户此前暂存的新增。将这个 index 保持原样，不提交/重置；本轮产品代码将在工作区修改。详细上下文见根目录 [current_contexts.md](../current_contexts.md)。
- R00 基线结果：Ruff check/format 通过；后端 pytest `103 passed, 2 warnings`（指定 backend/.pytest-tmp 并 elevated 以处理 Windows pytest temp 权限）；OpenAPI 导出后无差异；Web format/typecheck/build 通过；E2E `15 passed` 且退出码 0。
- Web `node_modules` 起始缺少 pnpm 根链接/命令 shims，pnpm 锁包位于 `.pnpm`；从其已解包锁定依赖恢复忽略目录链接后完成基线。运行版本为 pnpm 11.25.0（package 声明 11.19.0），clean install/version复核仍待完成。
- 子 Agent 只读审查了 PDF/许可/数据库及 Harness/Skills/MCP/Multi-agent；没有改文件或跑真实论文。细节见 `current_contexts.md`。R01 使用 TEST-* synthetic 工程夹具，不会冒称论文质量/金标。
- 依赖审计未运行；历史 Next.js 安全公告需联网重新核验。P17 初版代码存在，用户真实 PDF 质量验收待完成；TASKS 中合并重复 P17 行并标记 in progress。未提交或推送。

## P17 初版实现：许可准入 PDF 结构解析（质量与用户验收待完成）

- 新增本地 PDF 导入解析器（pdfplumber），提取版面文本、表格和作者图注；为检索片段保存页码、元素类型、章节标签、bbox、解析器版本及 PDF 源哈希。支持现有许可人工确认门禁，文本导入不变。
- 本轮图表支持限于原文图注和图像区域定位；尚未实现扫描件 OCR、视觉内容理解或图像原件持久化，解析质量需用用户许可样本验证。
- `pdfplumber>=0.11.7,<1.0` 已锁定；后端 103 项 pytest、Ruff check/format 和 OpenAPI 导出通过；Web 格式、类型、构建通过。Playwright 的 15 个浏览器用例逐项显示通过，但进程在输出测试通过后未正常退出，完整 E2E 命令状态不能确认。根 `git diff --check` 不能运行，因为当前工作副本没有 `.git` 元数据。项目审核服务报告 1 项 Next.js critical advisory（当前锁定 16.3.5，修复版本 >=16.3.6）；后端锁定环境依赖审计无已知漏洞。没有推送或访问 GitHub 写接口。

更新日期：2026-09-24。PaperTrail 已迁移为仓库根目录项目，并发布至 [GitHub](https://github.com/ZXN1225/papertrail)；默认分支 `main` 是唯一远程分支，旧项目开放 PR 已清理。旧电脑推荐项目源码从当前 Git 工作树移除并保存在本机忽略目录 `.local/legacy-computer-project/`。P11 用户本机验收修复并验证 arXiv 检索；P12 离线评测与展示资料完成；P05 80 条人工复核 qrels 已导入；P13/P14 结果仅为 AI 标签探索性诊断。后端 99 项自动测试、Web 15 项 E2E 及静态检查通过；GitHub Actions 最终运行通过。

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
