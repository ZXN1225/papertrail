# 任务台账

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
| R04 | 任务运行状态与共享预算 Harness                      | R01、R03                | in progress（有界 request-scoped 多轮约束、历史 hash/当前轮证据隔离、无效用量失败关闭及 embedding usage 不明时中止已实现；账单硬上限与重启续跑未实现）                                                                               |
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
