# R02：PDF 结构解析与 chunk 定位验收

## 2026-10-14：parser v26 表头锚点回退（等待用户复核）

- 在 v25 视觉行降级的基础上增加表头锚点回退。只有表头列起点在多数正文视觉行中重复对齐、所有原始词框均不跨越推断边界时才恢复列；captioned table 正文网格切词也会触发保守恢复/降级判定。不满足时保留视觉行无结构，且不推断逻辑行语义。parser 版本升至 `pdfplumber-layout-v26`。
- 在原 PDF 视觉页与 parser v26 对照后，`2610.09789` 第 5 页 Table 1 输出 3 列（Symbol/Value/Meaning）、9 条数据行；下标、单位/数值和含义均对应原表。此为单样本 spot check，非用户标签或总体准确率证明。
- 9 篇许可 PDF、217 页 v26 离线草稿和 16 项本机复核包已生成，manifest SHA `f8bd20fac4b478ee6bc626d5dcaaf2a5a2c9739c4fdd3f5961be504dd59a98d5`。机械审计 3,254 个元素：重复 ID/非法 bbox/样本映射错误/缺页图均为 0。v25 与 v21 标签不迁移；活动 SQLite 仍 v21。用户需要逐项核对 `backend/reports/live_eval/corpus-expansion-v26-human-review.md`。
- parser/table 57 passed；完整后端 330 passed、1 条既有弃用 warning；Ruff check/format 与 diff check 通过。未写 SQLite、未调用模型/embedding、未提交或上传。一般跨版式准确率、OCR、图片像素语义和检索泛化仍未测量。

## 2026-10-14：parser v25 页外文字过滤、表格结构保留与等待复核

- 当 captioned table 的表头几何异常或解析 bbox 未覆盖预计表框时，v25 检查正文词语是否被推断列线切开。正文词语未被切开则保留现有列结构、扩大元素 bbox 到完整预计区域，并用 `grid_body_columns_preserved_header_unreliable` / `grid_columns_preserved_bbox_incomplete` 与 warning 表明范围；正文有文字被列线切开则保持视觉行无结构回退。它不推断不可靠表头的含义。另过滤 PDF 页面范围之外的定位词并加显式 warning。
- 合成回归覆盖列线穿词降级、完整正文网格保留和页外词过滤。parser/table 定向 54 passed；全后端 322 passed、1 条既有 Starlette/AnyIO 弃用 warning；改动文件 Ruff check/format 与 diff check 通过。
- 9 篇准入论文 217 页离线输出已重算为 `pdfplumber-layout-v25`；活动数据库仍为 v21。16 项人工复核包 v2 在 Git 忽略路径 `backend/reports/live_eval/corpus-expansion-v25-human-review.md`，manifest SHA-256 `1548235e8e173296c37d5dabb0050a2747c0d2d6bd77cb0c3ad39cf44fef0b78`。机械检查 3,254 元素中重复 ID 0、无效/页外 bbox 0；36 页存在页外文字并有 warning。v1 的 2610.09789-S2 把原 PDF Figure 3 错列为 table；v2 已改为完整 `figure_caption`，且原页 v25 草稿确有 matched image relation。用户需核对 caption 与图像关系；旧 v1 保留。
- 当前不作 R02 解析准确率通过声明。v25 16 项核验包待用户检查，之后再决定进一步修复及是否重建活动全文索引；没有触发付费模型、更新 SQLite、提交或上传。

## 2026-10-14：用户 v21 复核标签与归因核对

- 用户已对 v21 包的 17 项提交标签；标签按原样保存在 `R02-v21-corpus-human-review.json`。AI 辅助只读对照确认：2609.39773-S3 是无解析元素的错配样本，排除 parser pass/fail 分母；2610.06874-S3 的 caption 转录吻合，但图片关系 `unmatched`，属于关联覆盖缺口。
- 2610.10204-S2 用户指出的 `iron-phytolankton` 在原 PDF Figure 2 caption 中已如此拼写，解析器忠实保留。保留用户原始 `unsupported` 标签但不得计为 parser 拼写缺陷。视觉行值吻合不等于表格列结构通过。
- 这组标签冻结于 `pdfplumber-layout-v21`，不能证明 v25，也不能自动迁移。v25 仍需用户复核其 16 个新选取样本；活动索引保持 v21。

## 2026-10-13：parser v21 与扩展语料本机验收状态

- 修复 captioned table 的 ruled bbox 被截断时，丢弃候选后表格词落回全页双栏排序而产生的文字错序：v21 现在在结构不可信时保留 bbox 内的视觉行，使用单列结构并显式标记 `table_structure_unavailable_visual_lines_only`。没有推断或伪造列关系。另修复横线区域超出居中标题横向范围的问题，减少 2610.12662 p14 Table 2 与后续正文粘连。
- 当前 9 篇 CC0/CC BY 4.0 活动全文均为 `pdfplumber-layout-v21`；只读来源 lineage audit 9/9 verified。语料扩充 review pack `backend/reports/live_eval/corpus-expansion-v21-human-review.md` 有 17 项及原 PDF 页面截图，等用户逐项核验。复杂表头、多栏、旋转文字、图表线网格仍有抽查风险；不宣称一般解析准确率。
- parser 单测与完整后端 suite 已过（36 parser tests；298 backend tests，1 条既有 Starlette/AnyIO deprecation warning），Ruff 和 OpenAPI 通过。代码/自动测试通过不代表 17 项人工核验通过。

## 2026-10-13：v20 修正 Figure 5 右侧图内标签裁切

- 使用对应光子学论文 PDF（arXiv:2608.02037）第 9 页逐词 bbox 检查，发现 v19 矢量框右边界 x=519.68pt 穿过 `(d)` 面板标题末尾 `nm`（文字范围到 x=520.95pt）。因此 v19 叠框图的右缘不完整。
- v20 在矢量图联合框左右各加 2 pt 水平 padding 并限制在页面宽度内；当前 bbox `[70.31,298.97,521.68,655.65]`，右侧标题文字完整落入框内，caption 从 y=666.27pt 开始，框底 y=655.65pt；上方正文与框有间距。四篇许可 PDF 的所有矢量边界逐词检查均无跨边界文字。
- 新叠框图：`backend/reports/live_eval/figure5-v20-bbox-review.png`。仍待用户视觉核验六面板/图内标签均被包含、正文和 caption 均排除；程序坐标检查不作为人工验收。
- 四篇已批准 CC-BY-4.0 PDF 均按原 manifest 重解析为 v20，仅更新本机索引；PDF SHA、license_reviewed_at 与 chunk 数 743/315/263/48 不变，lineage 4/4 verified。未处理其他 PDF，也未扩充语料。
- Parser 定向测试 35 passed；全文检索诊断与 lineage 测试 25 passed；全后端 **297 passed、1 条既有 Starlette/AnyIO 弃用 warning**。Ruff check/84 文件格式检查、OpenAPI 导出通过。受限环境首轮停滞后，在可用本机 socket 环境重跑并通过完整套件。BM25 v20 只读诊断 6/6 top-8、locator 6/6、rank 5/1/1/1/2/3，provider calls 0；两次报告字节一致，明确不是 gold recall。

## 2026-10-13：v19 图内标注纳入 Figure 5 联合框

- PDF 渲染检查发现 v18 的面板边界上沿切过 Figure 5 内部的子图说明文字。v19 将矢量面板联合框上扩 12 pt；在原 PDF 第 9 页生成叠框图后，红框完整包含六个面板及其图内标签，避开上方正文与下方 Figure 5 caption。
- 当前 bbox 为 `[72.31,298.97,519.68,655.65]`，caption 仍为 `matched`、confidence `0.965`、region source `vector_boundary`。叠框图位于 Git 忽略的本机 review 材料，供用户直接验收。
- 四篇许可 PDF 已统一到 `pdfplumber-layout-v19`。Parser 定向 **34 passed**；完整后端 **286 passed、1 条既有 Starlette/AnyIO 弃用 warning**，Ruff check/84 文件格式与 OpenAPI 导出通过。v19 BM25 六题 exact remap 与排名结果见 [v19 报告](R01-R03-current-v19-bm25-smoke-2026-10-13.md)。
- **等待用户核验**红框范围；OCR、像素语义和跨布局准确率仍未建立。没有扩充语料、模型调用、暂存、提交或上传。

## 2026-10-13：v18 表格逻辑行计数修正

- 用户确认 A1 表头内容正确，并指出 v15 核验包展示 3 条表头 + 5 条数据（8 行），却报告 9 行、4 个表头，元数据说明不足。复查发现孤立 `V` 被表头归一化删除后，空行仍留在结构行列表中。
- v18 在表头修复后移除逻辑内容全空的行，同时保留后续行的原始物理 `row_index`。真实 2607.24663 PDF 第 10 页 Table II 现报告 `row_count=8`、`header_row_count=3`、`column_count=8`，物理行索引为 1–8；bbox 与表格渲染文本哈希不变。该字段现在代表非空逻辑行，物理定位仍通过行索引。
- 新增合成回归覆盖“修复后空表头行被排除、物理行索引保留”。Parser 定向 **34 passed**；完整后端 **286 passed、1 条既有 Starlette/AnyIO 弃用 warning**。Ruff check、`app/tests/tools` 84 文件格式检查与 OpenAPI 导出通过，OpenAPI SHA 未变。
- 为保持活动 corpus 解析器版本一致，四篇既有许可 PDF 均重建到 v18。Lineage 审计四篇 verified，共 1,369 chunks；PDF SHA 与许可审核时间保持。新 v18 六题 BM25 诊断 exact remap 6/6，top-8 6/6、locator 6/6、排名 5/1/1/1/2/3、0 provider calls；报告仍非 gold recall。v15/v17 旧报告和历史审阅标签继续冻结。
- v18 bbox `[72.31,310.97,519.68,655.65]` 已被 v19 上沿扩展版取代；当前人工验收只针对本文件顶部记录的 v19 bbox。没有语料扩充或模型调用。

## 2026-10-13：v17 复合图 bbox 与图注关联（历史快照）

- v15 Figure 5 caption relation 曾指向 bbox `[205.87,640.28,275.2,643.67]`（约 69.33×3.39 pt），是内部细线，不代表六面板图。v16 先将窄片段排除后标成 `unmatched`；v17 使用相邻矢量面板聚类恢复完整图区域。
- `2608.02037` PDF 第 9 页 Figure 5 的 v17 目标 bbox 为 `[72.31,310.97,519.68,655.65]`，与渲染页面中六面板图范围吻合，底边在图注起始 y≈666 pt 之上；caption relation `matched`、confidence `0.965`、region source `vector_boundary`。图注文本、原文 bbox 和 767 字符范围沿用用户已核验版本。该工作只定位矢量边框，不解释像素/曲线语义。
- `_vector_figure_boxes` 仅选择满足尺寸/面积阈值的显式矩形，移除嵌套矩形，再将横向或纵向接邻且显著重叠的 panel 聚成联合 bbox。低尺寸 image fragment 保留但不可作为 caption target。合成覆盖包括单个边界、四面板拼接、分离图组不误合并和细线不误配。
- 重解析时发现许可元数据 `license_reviewed_at` 被 parser rebuild 时间覆盖。repository 现仅在来源 URL、license ID/URL/evidence URL、署名与审核人都一致时沿用已有人审时间；解析重建时间保存在 `imported_at`。新增回归通过；四篇 v17 活动记录的复核时间恢复到 v15 原人工审核记录。
- 四篇活动索引统一为 `pdfplumber-layout-v17`，PDF SHA、许可审核时间、table 文本/bbox/structured rows、caption 文本/bbox 均与 v15 不变；chunks 保持 48/315/743/263。lineage CLI 全部 verified，1,369 chunks；bbox、表格行列、chunk/parent 和 matched relation 目标引用检查均无错误。Figure 5 BM25 smoke 仍在页 9返回完整 caption，排名第 2。
- Parser 定向 **33 passed**；完整后端 **285 passed、1 条既有 Starlette/AnyIO 弃用 warning**。Ruff check 与 `app/tests/tools` 84 文件 format check 通过；OpenAPI SHA 未变。v15 六题报告及所有旧人审结果保持冻结，不迁移到 v17。新增许可语料与新付费模型调用仍未执行。

## 2026-10-13：v14 人工核验与 v15 修复

- 用户核验六项 v14 样本：A1/B2 unsupported；A2/B1/B3/C supported。理由、页面、bbox、PDF SHA 和 v14 内容 SHA 见[人审记录](R02-v14-human-review.json)。
- A1 的五条数据、数值和 bbox 正确，但 V 与 strict 子项错位。v15 现将表头规范为 `∆V_strict vs. Naive` 与 `V_strict (%)`，孤立 V 不再单独进入表格文本。
- B2 bbox 正确但旧解析拆成四列。v15 从首个明确表头识别空的续栏，把 Categories 合并为逻辑列，并用合并后的单元格 bbox 重新提取整词；IVIM 参数规范为 `f_p、D_t、D_p`。
- 四篇活动全文均已按原许可 manifest 本机重解析为 `pdfplumber-layout-v15`；旧版本留存。A2/B1/B3/C 的文本、structured 数据、bbox 和 warnings 与 v14 完全相同；它们的标签可按逐元素比较沿用。A1/B2 新输出已由用户对照原 PDF 复核；包在 Git 忽略的[本机修复核验包](../../backend/reports/live_eval/r02-v15-correction-review.md)。
- parser 定向测试 30 passed；全后端 `pytest` 253 passed、1 条既有 Starlette/AnyIO warning；Ruff check 与 79 个 `app/tests/tools` 文件 format check 通过。默认沙箱因 TestClient 的本地 socketpair 测试停住，受控本地运行全套后通过。BM25 smoke：Figure 5 图注第 1、IVIM 表格第 1。尚未测一般正确率或 OCR/图像语义能力。

### v15 修复样本人工复核（2026-10-13）

- 用户对 v15 A1/B2 样本确认内容均支持：A1 strict 表头次序与 `V_strict (%)` 正确、孤立 `V` 消失；B2 已为三列，类别文本与 IVIM 下标正确。人工标签绑定活动 PDF SHA 和 v15 content SHA，记录在 [v15 人审 JSON](R02-v15-human-review.json)。这只是两项定向复核，不是通用准确率。
- A1 展示为 3 条非空表头行 + 5 条数据行（共 8 行），结构元数据为 9 行、`header_row_count=4`。只读活动 v15 element 检查确认 `row_index=0` 是全空的原始解析行；结构计数保留它，而渲染文本省略全空行。因此 9=1 个空解析行+3 条非空表头+5 条数据，4=空解析行+3 条表头。已在本机忽略的 v15 核验包中说明，不改解析器行索引或把空行说成 PDF 可见内容。
- 本轮无产品代码变化，未重跑测试；此前 v15 后端回归 253 passed、1 条既有 warning 仍是最近代码测试结果。尚未测一般解析准确率、OCR 或图像像素语义。

### 用户补充说明（2026-10-13）

用户再次提交的 A1/B2 失败描述与 v14 原人审记录相符。随后用户对 v15 修复包确认 A1 strict 表头、B2 三列和 IVIM 下标均正确；A1 的 raw 9 rows 与渲染 8 visible rows 差异由一条全空解析行造成，已在本机 review pack 中解释。v15 人审见 [R02-v15-human-review.json](R02-v15-human-review.json)。其余 A2/B1/B3/C 沿用核验结论。

## 2026-10-13 本机统一重解析补充

- （历史快照）当时活动索引统一为 v14。随后用户按本节下方最新记录核验，并由 v15 替代。
- 最新 chunk 数：2607.24663=743、2608.02037=315、2608.20519=263、2609.27579=48。四份解析总计 67 页、1,349 元素、7 个结构化表格元素、46 页级 warnings。警告会说明两栏/阅读顺序、旋转文本排除或稀疏表候选拒绝；这不是解析准确率指标。
- R4 同题 BM25 复核后 Figure 5 完整 `figure_caption` 仍排第 1。已为更换版本的三篇建立本机 [v14 对照包](../../backend/reports/live_eval/r02-v14-reindex-review.md)，列出 2607.24663 第 10 页两表、2608.20519 第 6/14/20 页结构表与 2609.27579 第 3 页右栏父元素。其内容含原论文摘录，只在 Git 忽略目录；旧 run/qrels 不迁移。上述新版抽样待后续人审，不能把用户旧版标签自动继承为 v14 标签。

状态：v14 指定样本发现的两项缺陷已在 v15 修复并由用户定向复核；A1 空解析行的元数据/渲染计数口径已解释。既有许可范围及单篇用户验收仍有效。parser 整体正确率仍未建立，不能据少量样本宣称一般 PDF 解析通过。

## 最新人工核验闭环（2026-10-12）

用户确认 2609.27579 第 3 页右栏摘录 bbox `[304.72,176.61,540.32,496.92]` 恰好覆盖所列文本，不纳入下方标题/正文；2607.24663 第 10 页 Table III 的解析裁剪输出恰有一表头、五数据行，各列数值与原 PDF 一致，没有正文污染。此前 2608.02037 Figure 5、2607.24663 Table II 与物理行 locator、2609 右栏内容和独立性均已核验。详见 [三篇审阅包](R02-three-paper-review-pack.md) 与 [六题/版面审阅记录](R01-R03-real-evidence-pilot-human-review-v1.json)。这完成列出项目的人工抽样，不覆盖所有页、OCR、图像像素语义或一般解析准确率。下方的“待用户核对”段落是先前阶段快照。

## 新增许可论文 parser-only 复核（2026-10-12）

用户确认新增的三份本机 PDF 来自 arXiv，arXiv 条目均标示 CC BY 4.0；逐篇核对官方 [2609.27579](https://arxiv.org/abs/2609.27579)、[2608.02037](https://arxiv.org/abs/2608.02037)、[2607.24663](https://arxiv.org/abs/2607.24663) 的 license 入口和 [CC BY 4.0 条款](https://creativecommons.org/licenses/by/4.0/)。三个本地忽略的许可 manifest 预检通过。文件 SHA-256 及未提交/未入库边界见 [PROGRESS](../PROGRESS.md)。

- `2608.02037`：16 页、330 个解析元素、27 个图像区域、6 个图注元素、0 个表格区域；6 页有 `sparse_table_candidates_rejected`，说明其中候选更像稀疏图表而非结构化表格。PDF 有 6 幅图，但本轮仅证明图注文字提取和图像区域检测，不证明图像与图注语义配对准确。
- `2607.24663`：38 页、476 个元素、13 个图像区域、6 个图注元素、4 个表格区域。视觉抽样对照第 3、10、13 页确认 Table I–IV 的主要行列可恢复；Table II/III 同页，表格区没有纳入后续正文。仍存在 Table I/II/IV 的分层表头拆行/空单元格问题，未经 chunk 检索人工签核。
- `2609.27579`：4 页、66 个元素、1 个图像区域、1 个图注元素、0 个表格区域，无 parser warning。此统计不证明其图表结构可读。
- 发现 `2607.24663` 的真实 `TABLE I.` 在旧版 v6 下因罗马数字编号和双栏 ruled layout 漏检；旧通用 text crop 还可能把 Table II 附近正文混进表格。v7 限定在明确表格 caption 和相邻横线的列区域内抽取，并在后一张表 caption 前截止。增加了 synthetic 双 caption/双栏回归；parser 定向测试 `21 passed`。这项局部修复不代表通用 PDF 解析准确率。
- 本步为 parser-only，不写入全文数据库；host SQLite 中三条 arXiv 元数据目前不存在，因此全文导入、chunk 检索、citation locator 和用户对照验收仍待继续。Docker Compose 使用独立命名卷，host SQLite 导入不会自动出现在 Compose Web 中。

## 自动覆盖的解析契约

- 阅读顺序和章节路径跨栏/跨页；元素 ID、页码、bbox 与解析器 warning。
- 表格 structured rows/cells、来源 row index、表格/正文去重、长表格行拆分与 locator。
- 图注候选歧义不得被静默强制配图；同一 PDF 字节数据用于 hash 与 parse。
- migration 0007 为历史 offset 标记 unknown，并覆盖结构元素删除级联。
- 导入许可证预检先于读取 PDF，测试证明无效 manifest 不调用解析器。
- 定向 parser 与全文集成测试结果及后端全量结果见 [R08](R08-acceptance.md)。所有 `TEST-*` 样本均为合成夹具，不作为真实论文质量标签或版面准确率证明。

## 真实许可 PDF 抽样核验（2026-10-12）

- 论文：arXiv:2608.20519v1，29 页。用户确认下载自 arXiv 且标示 CC BY 4.0；核对了 [arXiv 条目与许可入口](https://arxiv.org/abs/2608.20519) 和 [CC BY 4.0 许可说明](https://creativecommons.org/licenses/by/4.0/)。
- 本机源文件 SHA-256：`7d664debd8dc5c83119c0b1b64a9d8ef2a277eca54cea402dd786fd9d311ce31`。PDF 原件保持本机；经用户确认许可并通过 manifest 预检后，全文导入被 Git 忽略的本机 SQLite，未提交或上传。
- 初次抽样用 `pdfplumber-layout-v3` 得到 209 个元素；针对发现的问题已升级到 `pdfplumber-layout-v6`。`x_tolerance=2` 修复 Table 1 单词粘连，并用于定位文字抽取，修复 Figure 7/Table 3 caption 粘连。当前解析得到 211 个元素、3 个表格 region、7 个 image region（5 个 raster、2 个 vector boundary）、7 个 figure caption；抽查 PDF 第 2、6、7、14、18、19、20 页。最终输出见[原文与解析结果对照包](R02-user-review-pack.md)。
- 修复并回归验证两类通用误判：任意 Title Case 文本（如表头、数值或公式片段）不再自动成为 heading；稀疏图表网格不再作为 table element 输出。现在页面 18、19 的候选图表网格被显式告警拒绝，而不是包装成错误表格。
- 新增以明确 `Table N` caption 为锚点的 text-aligned table fallback，三张表分别在 PDF 第 6、14、20 页恢复为 3、4、4 列结构，表格标题编号保留；synthetic fake-page 回归覆盖有 caption 的无边框表格。PDF 第 18、19 页的稀疏绘图网格仍被拒绝。
- chunker 现在只在同列、前一物理行单元格以连字符结尾、续行唯一内容为小写词尾时合并检索文本（本论文 Table 1 的 `streaming`、`denoising`）；`evidence_text` 仍是原始抽取跨度，locator 覆盖对应物理行。Table 2 根据其 blank header 子列，将物理 extraction 的 4 列映射为 3 个可见逻辑列；合并 `h` + `ead and neck` 为 `head and neck`，`meta-analyses` 保留词汇连字符。raw evidence 仍保留原始 4-cell 行；表头和检索文本改为 3 列。其他换行不猜测性合并。
- Table 2 的 IVIM 参数下标仍被抽取为错序字符；对照包按当前真实输出展示，没有用猜测文本替换解析结果。
- 第 18/19 页 Figure 6/7 现在可根据与 caption 邻近、重叠的大型矢量矩形边界建立 `image_region`，关系中标为 `region_source=vector_boundary`。该机制仅提供几何 locator，不提取曲线、轴、图例或数据，也不能当作 OCR/图像理解。5 个 raster region 与 2 个 vector boundary 均可定位，不代表其他 PDF 的通用图表召回率。
- 用户之后运行 arXiv 精确元数据导入成功：本地 snapshot `934cc269-9175-4cb7-abda-89713fa00864`；许可全文导入 `pdfplumber-layout-v6`，209 chunks、source text SHA-256 `57a5b7dfa79828d1f2115e75d163f41901c1f6028ebda6245532128830aaa545`。重复导入返回 `unchanged`，未重复创建全文版本。
- 本地 BM25 smoke 能检索 Table 1、Table 2/3 与 Figure 7 caption 并返回对应页/元素 locator；这验证单文档检索链路，不是问答正确率评测。
- 仍未通过的点：Table 2 有跨列换行被拆分到相邻单元格，IVIM 下标错序；扫描页 OCR、矢量图语义/数值读取不支持。许可 PDF 的 RAG 证据支持质量仍需人工标注和评估。
- 对 PDF 第 20 页 Table 3 的特殊字符另外做了 Unicode 码点检查：解析结果为 U+00B1（`±`），终端显示为乱码样式是字体/输出呈现问题，不是替换字符缺陷。
- 表格续词与矢量 locator 增补后，仍没有把全文导入活动 RAG 索引：Table 2 跨列单元格边界和最终引用 excerpt 需要用户对照视觉原文核对。
- 定向 `test_pdf_parser.py` 为 17 项通过；parser/fulltext/store 合并定向为 48 项通过，1 个 Starlette/AnyIO 上游弃用 warning。Ruff check/format 通过。该次补强后的全后端测试与最终 Git diff 检查另见 `docs/PROGRESS.md`。
- 以上是单篇、本机、抽样视觉核验，不是独立标注的 benchmark，也不能外推为一般 PDF 准确率。

## 解析器限制

## 三篇新增论文：v11 导入快照（历史记录，已由 v13 更新）

前文“parser-only / 元数据不存在 / 未入库”是 2026-10-12 实施中的历史快照，已被本节更新。用户在 PowerShell 成功导入三条 arXiv metadata 后，本机用逐篇 CC BY 4.0 manifest 和 `--confirm-license-reviewed` 完成全文导入。数据库不纳入 Git；重复导入 2609.27579 返回 `unchanged`。

| arXiv | 页数 | image regions | captions | structured tables | chunks | parser warnings 摘要 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2609.27579 | 4 | 1 | 1 | 0 | 111 | 第 1 页旋转水印排除；第 1/2 页双栏；第 3 页阅读顺序不确定 |
| 2608.02037 | 16 | 27 | 2 | 0 | 318 | 稀疏表格候选拒绝；第 9 页双栏顺序不确定；若干旋转文字排除 |
| 2607.24663 | 38 | 13 | 6 | 4 | 991 | Table I–IV 可结构化检索；第 10 页含双栏顺序不确定警告；多页旋转文字排除 |

最终代码改进：

- parser `pdfplumber-layout-v11` 支持罗马数字表号和贴合 caption 的 table crop；跨栏正文段落按列边界分开。
- 如果跨栏阅读次序被宽幅内容打断，会按 x 坐标标注左右列并保留 `multi_column_reading_order_ambiguous`，避免将左右栏静默拼为同一段。
- 过滤 `upright=false` 的旋转页边文字并标记 `rotated_text_excluded`；不把 arXiv 页边水印混入摘要。
- 另加横向起点大幅跳变时拆分段落，减少未被双栏启发式捕捉时的跨栏串接。这个规则可能产生短段；本次抽样显示 2607.24663 chunk 数增到 991，需继续看人工抽样是否可用，不能把更高 chunk 数称为质量提升。

BM25 smoke：2608.02037 的查询 `propagation loss 488 nm 940 nm` 命中 PDF 第 9 页 Figure 5 的 488 nm 图注和 940 nm 描述；2607.24663 的查询 `Agentic GraphRAG strict vital recall Table II` 命中 PDF 第 10 页结构化 Table II，`Agentic GraphRAG (ours)` 行的 70.3 / 8.7 / 64.1 / 71.2 保持列序。2609.27579 的检索命中 Abstract 与第 3 页图内/正文文本；首页抽取中已剔除旋转 arXiv 边栏。检索样例及逐篇人工检查点见[三篇论文 RAG 抽样审阅包](R02-three-paper-review-pack.md)。

验收结果：parser 24 tests；全后端 223 passed，1 个 Starlette/AnyIO 上游弃用 warning；Ruff check/format 与 OpenAPI 导出通过，OpenAPI SHA-256 `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`。用户尚未确认本节的三篇新论文抽样。因此 R02 新语料人工验收仍未完成。`2608.02037` 的图表仅有区域与图注，无像素级曲线理解；`2607.24663` 部分复杂表头仍需核对；阅读顺序警告仍应在答案中暴露。Compose 使用独立命名卷，不会自动看到 host SQLite 的全文。

## 用户首轮核验后的修订：parser v13

- 用户确认：2609.27579 第 1 页摘要与原文一致；其第 3 页 `Textual sources...` 与 `Data Layer...` 是右栏正文而非图中标注，且旧审阅包没有足够上下文判断跨栏；2608.02037 Figure 5 的对应关系、波长、厚度与箱线说明通过；2607.24663 Table II 列序、数值、百分比单位正确，但只有 5 个数据行，旧“行 2–9” locator 有歧义。
- 将 `PARSER_VERSION` 升到 `pdfplumber-layout-v13`，正文定位词抽取用 `x_tolerance=1`，结构化表格单元格仍使用 `x_tolerance=2`。重新解析后，2609.27579 第 3 页右栏父 paragraph 元素独立在 bbox `[304.72,176.61,540.32,561.30]`，正确恢复 `subsystem label` 等空格；保留其版面歧义 warning 和 PDF 原有行末断词。父元素包含 Query 标题和开头说明；所列摘录的较小 bbox 见下节及[新版三篇审阅包](R02-three-paper-review-pack.md)。
- 2607.24663 Table II 为 9 个解析物理行，其中前 4 行是堆叠表头，后 5 行是系统数据；BM25 locator 现为 `第 10 页 · table · 解析器物理行 5-9`，返回 5 条数据，四个目标指标单位为 `%`。同页 Table III 结构结果为 1 表头 + 5 数据，无正文混入。
- 三篇按 v13 刷新本机索引：页数/image regions/captions/tables/chunks 分别为 2609.27579 `4/1/1/0/51`、2608.02037 `16/27/2/0/322`、2607.24663 `38/13/6/4/755`。2609.27579 重复导入返回 `unchanged`；三篇许可维持 approved，PDF SHA 不变；BM25 smoke 分别命中右栏、Figure 5、Table II。定向后端测试 `40 passed`，随后完整后端回归 `224 passed, 1` 条既有上游弃用 warning。人工核验进一步结果见下节。

## 第二轮人工核验：内容通过与摘录坐标修正

- 用户确认 2609.27579 第 3 页右栏文本、正文类型、词间空格和无跨栏拼接；指出此前文档给出的父元素 bbox 覆盖了未列出的 Query 标题、说明和 `Input: User query Q`。逐行 PDF 坐标只读复核后，所列 `Data Layer` 至 `similarity search and structured filtering.` 摘录 bbox 修正为 `[304.72,176.61,540.32,496.92]`、父元素字符 `[0,1375)`；父 paragraph bbox `[304.72,176.61,540.32,561.30]` 仍正确描述其完整存储范围。两者已在审阅包明确区分，解析器、索引与数据库无需重写。
- 2608.02037 Figure 5 再次通过；2607.24663 Table II 五行、列序、百分比值和“解析器物理行 5–9”定位说明通过。Table III 的原表行数当时通过；机器裁剪输出 bbox `[113.40,263.89,502.70,325.71]`，一表头/五数据，下方正文元素从 y=`349.38` 起。其后用户已独立核验裁剪内容与边界，见本文件顶部最新闭环。
- 本轮只更新核验材料；不把页面内容确认推断为通用 PDF 解析准确率，也不把未核对的 Table III 裁剪结果记成人工通过。

## 已完成的单篇人工验收

请在本机打开原 PDF `An integrated diffusion-weighted.pdf`，依次核对：

用户提供 PDF 第 6、14、18、20 页的原文截图，确认了 `stream-` / `ing` 断行、Table 2 三列布局、Figure 6 复合图内容和 Table 3 的 ± 符号。代码已按 Table 2 视觉证据完成修正；当前请对照最终 chunk 再验一次，并看 Figure 7 locator：

1. PDF 第 6 页 Table 1：检索文本应显示 `streaming`、`denoising`，引用 evidence 保留原始断行和对应物理行 locator。
2. PDF 第 14 页 Table 2：最终表头为 `Attribute | Categories (examples) | Coverage`；`head and neck` 合并在 Categories 中，`prostate`、`secondary` 仍对应正确行。
3. PDF 第 18、19 页：确认 Figure 6/7 的 `vector_boundary` 区域覆盖目标整张复合图，不误包正文/其他图。
4. PDF 第 20 页 Table 3：`±` 的码点是 U+00B1，抽取的均值/标准差与原文一致。

用户在 2026-10-12 回复“看起来没什么问题，请你继续”，据此记录当前单篇抽样输出可继续使用。已披露的限制仍包括 Table 2 IVIM 下标错序、无 OCR、无图表语义读取；该确认不等同于一般 PDF 质量证明，也不代表 IVIM 缺陷已修复。

- 没有 OCR，不解析扫描页中的文本；没有图像理解，不根据图片像素生成研究结论。图表内容目前来自可提取文本、结构化表格单元格和原文图注。
- 不接受仅凭元素数量或没有 warning 推断解析质量；人工 visual QA 需要记录顺序、bbox、表格行列/单位、图注关系和最终证据 locator。
