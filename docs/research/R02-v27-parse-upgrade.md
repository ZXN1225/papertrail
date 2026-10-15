# R02 v27 解析升级证据记录

适用范围：parser `pdfplumber-layout-v21` → `pdfplumber-layout-v27`，9 篇 CC BY 4.0 白名单全文。
本轮把活动索引从 v21 升级到 v27 前的全部验证证据集中在此，便于复核与追溯。

**这不是质量声明**：所有指标都是小样本、单人选定参考或机械一致性检查；`quality_claim_allowed` 全程保持 `false`。
人工验收门槛已由用户改为 **AI 复核门槛**（见 `current_contexts.md`），本记录不冒充人工金标。

## 1. 代码变更

parser 版本 `pdfplumber-layout-v27`，改动集中在 `backend/app/retrieval/pdf_parser.py` 的表结构路径：

| 缺陷 | 现象 | 修复 |
| --- | --- | --- |
| 网格静默丢词 | `Table.extract()` 的推断列边界落在表头末尾字形之外时，这些词被**静默丢弃**（`2609.39773` p39 表 8 丢 `UMA`、表 10 丢 `max_k p_k`） | `_reattach_grid_dropped_words`：以**整张表**文本为参照集，只把全表都缺失、且中心落在表格水平跨度与纵向范围内的词追加到所在行最近单元格 |
| 多视觉行错行 | pdfplumber 行边界落在单元格两行之间，续行变成独立行、原行该列为空（`2610.12662` p14 表 1 Qwen "Level loop"） | `_merge_continuation_rows` / `_is_continuation_neighbour`：单单元格行只并入同列留空的相邻行，并强制列宽与行距约束 |

新增 4 个 `TEST-*` 合成用例（丢词回挂、已在他行出现的词不得重复、续行合并、跨列行不被误并）。
**表头碎片化**（列线切穿单词，如 `2610.12662` p17 表 4）未修，继续由 `table_header_geometry_unreliable` +
`row_semantics=grid_body_rows_header_uncertain` 披露；这些元素无丢词、数据行正确。

## 2. 全语料 v26 ↔ v27 差异（`tmp/v26-crops/compare_versions.py`）

按页码 + 元素类型 + 四舍五入 bbox 对齐两版草稿，逐表比较词的多重集：

```
9 篇共 26 张表，两版都是 26 张，26/26 全部匹配
v27 仅 7 张表内容变化，回收 33 个此前被丢弃的词
0 张表丢词、0 处重复
```

回收内容既含表头标签（`UMA`、`max_k p_k`、`Parameter`、`GRPO`、`Symmetric` …），也含被丢的实测数值
（`2610.12662` p15/p18 的 `1163.16`、`632.06`、`751.16` …）。

**实现过程中的自纠**：首版按"单行"判断缺失，会把已在相邻行的表头词复制进空行——`2607.24663` p10 因此从 8 行变成 9 行且表头词重复。
全语料版本对比抓到后改为整表判定，该表恢复为 0 变化。

### 2.1 行数变化逐表核对（合并只在应当发生处触发）

26 张表中 8 张行数变化（词多重集不变 = 纯合并，未丢词）。逐张核对结果：

| 表 | v26 → v27 | 结论 |
| --- | --- | --- |
| `2607.24663` p3 | 11 → 10 行 | 表头左侧标签 `Collection` 从单独一行并回表头行 ✓ |
| `2607.24663` p13 | 13 → 12 行，表头 3 → 2 | `Configuration` 并回表头行 ✓ |
| `2610.12662` p14 表1 | 7 → 5 行 | Qwen "Level loop" 单元格复原（见 §1）✓ |
| `2610.12662` p14 表2 | 7 → 6 行 | `Model` 并回表头行 ✓ |
| `2610.12662` p16 | 8 → 7 行，表头 2 → 1 | `Variable` 并回表头行 ✓ |
| `2610.12662` p17 | 13 → 12 行，表头 3 → 2 | `Columns` 并回表头行 ✓ |
| `2610.12662` p15 / p18 | 行数不变，表头行数各降 1 | 图内数值误判表（见 §6），仅表头行合并 |

没有任何一张表的合并破坏原有数据行；`2610.12662` p17 的表头**词中截断**（`H2D Per`、`m. in Perm`）属未修的表头碎片化，合并未使其变差。

## 3. 重新索引（先在数据库副本上演练）

`data/storage/v27-reindex.sqlite3` = 活动库副本 + 9 篇按 v27 重新导入（演练；活动库当时未改动）。

- 导入：9/9 成功，`failures=0`，全部 `status=approved`，`parser_version=pdfplumber-layout-v27`。
- 语料规模：**217 页 / 3,254 元素 / 3,296 chunks**（v21 为 4,871 chunks）。

### 文本体量对比（`tmp/v26-crops/compare_index_volume.py`，只比较各来源的活动版本）

| | v21 | v27 | 比值 |
| --- | --- | --- | --- |
| 文档正文字符 | 712,009 | 715,744 | **1.005** |
| chunk 正文字符 | 701,984 | 709,056 | 1.010 |
| chunk 数 | 4,871 | 3,296 | 0.677 |
| 平均 chunk 字符 | 144 | 215 | 1.49 |

**结论：chunk 数下降来自分块变粗，不是文本丢失**——正文体量反而多了 0.5%。逐篇比值 1.000–1.029，
唯一低于 1 的是 `2610.06874`（0.982），与该篇 v25 引入的 `out_of_page_text_excluded`（页外文字过滤）一致。

## 4. Lineage 审计（`app.cli.audit_fulltext_lineage`，只读）

```
status=verified  verified=9/9  quality_claim_allowed=False
每篇 parser=pdfplumber-layout-v27，checks 全部为 true（approved / license_allowed /
pdf_sha_matches / chunk_count_matches / chunk_content_hashes_match）
```

lineage 只证明来源与索引可追溯，**不证明内容正确**。

## 5. 六题只读检索诊断

v21 版数据集按 parser 版本钉死，升级后无法直接复用，因此新增
`backend/tools/reversion_retrieval_dataset.py`（此前该数据集同样靠一次性脚本重制）生成
`backend/data/evaluation/arxiv-r01-r03-current-v27-v1.json`：

- 参考块映射规则与历史记录一致：来源 + 页码 + 元素类型 + `retrieval_text` + `evidence_text` **唯一精确匹配**；
  无唯一匹配时保留旧 id 并按 miss 计，不静默算命中。
- 映射结果 **5/6**（`R2` 无精确匹配，与 v25 记录的 `no_exact_text_match` 同一现象）。
- 诊断结果：**selected-reference top-8 命中 5/6**（v25 记录同为 5/6），`provider_calls=0`，
  `quality_claim_allowed=false`，dataset SHA `5cf05970e0ec391faa482f654008e15adee2b99c194429ebb891ad22962b5c1d`。

该诊断是单人选定参考的小样本回归，**不是 gold recall**，也不能外推为扩库收益。

## 6. 已知限制（两版都有，本轮未处理）

- `2610.12662` p15/p18 的图内数值被 `page.find_tables()` 误判为表格，单元格结构本就错乱；
  本轮只是把 `extract()` 丢掉的数值补回，结构错误未变。
- 表头碎片化未修（见 §1）。
- Page 级 warning 会把某张表的 `table_header_geometry_unreliable` 泄漏到该页所有元素上（warning 归因问题，未修）。
- OCR / 图像像素语义、跨布局通用准确率仍未建立。

## 7. 独立 AI 复核（第一轮）与随后的修复

用户把人工验收门槛改为 **AI 复核门槛**，因此由独立 reviewer Agent（不告知其本机结论）对 v27 逐项核验。
第一轮结论：**10 supported / 6 unsupported**（复核记录：`data/storage/reviewer-v27b/reviewer-report.md`）。

复核确认本轮修复**有效**：

- v26 报告丢失的表头词 `UMA` 已恢复（`'D after UMA'`）；
- v26 的"幻影行 + Qwen 空单元格"已消失（`Level loop | jnp.arange | jnp.arange(nz) + clip | jnp.arange .at[klevs].set`）；
- v26 被丢弃的 `↑`/`↓` 方向标记已在 v27 出现；
- 7 条图注逐字符一致；**所有表格正文单元格**逐值核对无误；**全样本无重复**。

复核同时指出 3 处**本机复核未发现的单字符丢失**，以及对我 v26 结论的一处更正：

| 项 | 复核发现 | 处理 |
| --- | --- | --- |
| `2610.12662` p16 | 表头 4 个 `v` 下标只剩 3 个（丢 1 个 `v`） | **已修**：改为按"目标单元格字符预算"判定单字符 |
| `2609.39773` p39 表 10 | `max_k p_k` 尾部丢 `p` 与 1 个 `k` | **已修**：同上 |
| `2610.06874` p14 | 末尾 `[m/s]` 的 `s` 被列线切掉 | **未修**，见下 |
| `2610.09789` p10 | 我 v26 报告称"三列一致"**是错的**——该表其实被压成 `column_count: 1` 的视觉行 | 更正确认：属表头无法锚定时的保守降级，已如实记为 unsupported |

**修复方式**：单字符不能再用"整表是否出现过"判断——同一个字符几乎总在别处出现（下标 `v`、`max_k p_k` 的 `p`），会掩盖丢失。改为单字符按**目标单元格的字符预算**判定，多字符仍用整表判定以避免重复。

**试过并否决的两条路线**（都因为引入新缺陷而回退，记录以免重复踩坑）：
1. 整表字符预算的贪心遍历：解析文本中同名长词会吃掉预算，导致正文单元格出现重复标签（`XAFPAY XAFPAY`、`CG-OMatG-IRL CG-OMatG-IRL`）。回退。
2. 多字符词改为"按目标单元格是否已出现"判定：当表头行带落在字形下方时，词的最近单元格恰是它不属于的空单元格，会把表头文字再写一遍。该场景由既有合成用例 `test_word_present_in_another_row_is_never_duplicated_into_an_empty_row` 直接抓到。回退。

**当前 v27 构建的机械核验**（`tmp/v26-crops/deficit_check.py`，对比"元素 bbox 内 PDF 词"与"解析单元格文本"的字符多重集）：

```
2609.39773 p39 idx2 : DEFICIT={}            (max p k k 全部回收)
2610.12662 p16 idx0 : DEFICIT={}            (/ε v v — 第 4 个 v 回收)
2610.06874 p14 idx0 : DEFICIT={'s': 1}      ← 唯一残留
其余抽查表          : DEFICIT={}
```

**已知残留（如实记录）**：`2610.06874` p14 末尾单位 `[m/s]` 中被列线切掉的 1 个 `s` 仍会丢失。原因是该片段既是多字符词、又恰好作为 `log law [m/s]` 的子串在整表出现，两条判定都不会把它当成缺失；而按单元格判定会在表头行带错位时造成表头重复。该表仍带 `table_header_geometry_unreliable` + `row_semantics=grid_body_rows_header_uncertain` 披露，正文 5 行全部正确。

**复核第二轮**：构建变更后（复核包 SHA-256 `530671e1a7b86605b7f57712bd6dea848ccfecb7bfa46ad761a303bd9183d80a`，9 份 v27 草稿）重新交给一个独立 reviewer Agent 核验，因为必须复核**实际要发布的产物**，而不是它之前的版本。

### 第二轮复核结论（8 supported / 7 unsupported / 1 uncertain）

复核记录：`data/storage/reviewer-v27c/reviewer-report.md`（已归档到 `backend/reports/live_eval/v27-reviewer-reports/`）。要点：

- **字符丢失只剩 1 处**：`2610.06874` p14 第 5 个表头单元格右边界 `x=407.92` 切掉了 `[m/s]` 的 `s`（`x 407.05–410.54`）与 `]`（`410.54–413.53`）。即 §7 已记录的残留，与本机独立复核一致。
- **全样本 0 重复**（去除解析器自加的 `Table N (page M)` 前缀与 `_ { } ^ |` 记法字符后，21 个抽样元素的 `EXTRA` 全为空）。
- **S6 与 S10 的字符丢失已确认修好**：S6 的 4 个 `v` 下标齐全、S10 表 10 的 `max p k k` 在表内；两者仍判 unsupported 是**表头归属错误**（`E_v/ε_v` 被拆到两个单元格、`Dominant` 落到第 3 列、元素右边界裁掉列标签），不是丢字。
- **新发现（前两轮都没报）**：`2610.12662` p15 有一个**由 Figure 2 图形文字层冒充的 `table` 元素**，带伪造的 `Table 1 (page 15)` 标题，把坐标轴标签与刻度数字当成 9 列表格，还把 `6316.30` 切成 `63`/`16`。复核认为这是整包里最误导人的产物。

### 据此追加的最后一个修复

**规则**：没有 `Table N:` 显式标题的表格候选，若其 bbox **完全落在**某个图像/矢量图形区域内（且该区域小于整页 80%），则拒绝输出，并记 `table_inside_figure_region_rejected`。
新增 `_fully_inside` 与 1 个合成用例（完全包含才拒绝、仅相交不拒绝、考虑亚点舍入）；parser/table 定向 **41 passed**。

效果（全语料）：`2610.12662` 的表格数 6 → 4，被移除的正是 p15、p18 两个图形文字层假表；其余 24 张合法表全部保留，全语料对比仍为 **0 张表丢词**。
复核包仅新增了该披露告警（复核包 SHA-256 `5d315dae0e02cc69d56a8f765c2adbec6270d236914e5e104a2fb10e258031ac`），16 个抽样元素的内容与图注关联未变——即本轮改动**只删掉了复核指出的假表并为其加了披露**，没有引入未经复核的新行为。

## 8. 活动索引升级（已完成）

用户把人工验收门槛交给 AI 复核后，按"复核通过即升级"执行：

- 全量后端回归：**291 passed、0 failed、45 errors**（45 个 error 全部是本沙箱临时目录环境问题，非断言失败）。
- v27 草稿、复核包、manifest 与提示报告已归档到 `backend/reports/live_eval/`（**最终构建**的复核报告在 `v27-reviewer-reports/reviewer-report.md`）；**中间构建（v27b）**的复核报告仍在 Git 忽略的 `data/storage/reviewer-v27b/reviewer-report.md`——两者归档时同名，后者覆盖了前者，未再为它单独提权写入。
- **活动 SQLite 已切换**：9 篇全部 `pdfplumber-layout-v27`，合计 **3,294 chunks**；lineage 审计 **9/9 verified**。
- 六题只读检索诊断（在活动库上执行）：**selected-reference top-8 5/6**，`provider_calls=0`，`quality_claim_allowed=false`，dataset SHA `87db19bece61ca54190b5b634ee0a0f731e3c5c0972acd9fdedf4b3f23e461a5`。
- 升级前备份保留在 `data/storage/papertrail-pre-v27.sqlite3`。

### 尚未闭环（如实记录，供后续判断）

1. `2610.06874` p14 表头仍有 1 个 `s` 丢失（§7）。
2. 表头切词/错列（S3、S5、S6、S7、S10）：正文与字符均完整，但列标签不可复原；已由 `table_header_geometry_unreliable` + `row_semantics=grid_body_rows_header_uncertain` 披露。
3. `2610.09789` p10 整表被压缩成 `column_count: 1` 的视觉行。
4. 每个 table 元素的 `text` 带解析器自加的 `Table N (page M)` 行；`section_path` 在抽查页面上不正确（复核 §4.6）。
5. 图注元素 `section_path` 亦有个别不正确（如 `2610.09789` p6/p9 记为 `Introduction`）。

以上 2–5 属**已知、已披露**的结构/元数据问题，本轮未修，也未据此宣称解析质量达标。

