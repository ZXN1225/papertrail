# R02 v26 独立核验记录（AI 辅助，非人工金标）

被核验对象：`backend/reports/live_eval/corpus-expansion-v26-human-review.md`（v1，包 SHA-256
`f8bd20fac4b478ee6bc626d5dcaaf2a5a2c9739c4fdd3f5961be504dd59a98d5`）、parser `pdfplumber-layout-v26`
草稿、9 篇 CC BY 4.0 许可全文。

核验日期：2026-10-15。核验人：AI 助手（视觉/坐标只读对照）。**这不是用户人工标签，也不是独立金标。**

## 方法与边界

- 只读操作。按 SHA-256 把 9 个本机 PDF 与复核包声明的 PDF SHA 逐一对齐后，用
  `tmp/v26-crops/make_crops.py` 从**源 PDF**重新渲染 150 DPI 放大裁切（输出在
  `data/storage/v26-crops/`，Git 忽略），覆盖 17 个待核验表格/图注区域。
- 对两处可疑行归属另用 `tmp/v26-crops/probe_rows.py` 直接读取 `pdfplumber` 词坐标（y/`top`、x0）核对。
- 未写数据库、未调用模型或 embedding、未改动解析器或复核包；活动 SQLite 仍为 v21。
- 未做 OCR 或图像像素语义判断；本记录只覆盖这 16 项，不能外推为 217 页整体解析质量。

## 逐项结论

| # | 项 | 页 | 期望类型 | 结论 | 依据 |
| - | -- | -- | -------- | ---- | ---- |
| 1 | `2610.09789-S1` | 5 | table | **supported** | Table 1 恢复为 3 列（Symbol/Value/Meaning）、9 条数据行；`K_{min}`、`K_{0}`、`δ_{K}`、`∆K`、`θ`、`r_{B}`、`r_{A}`、`A_{0}`、`B_{0}` 的符号、数值与含义逐条与原页一致。 |
| 2 | `2610.09789-S2` | 9 | figure_caption | **supported** | Figure 3 图注全文逐字一致（含 `Eqs. (1)–(3)`、1.42/1.29）；图注紧接双面板图下方，`matched` 合理。 |
| 3 | `2610.09789-S3` | 10 | table | **supported** | Table 2 三列 9 行内容一致，跨行连字符（`tran-sient`、`enforce-ment`）保留。 |
| 4 | `2610.09789-S4` | 6 | figure_caption | **supported** | Figure 1 图注全文一致（含断词 `iden-tical`）；四面板图在其上方。 |
| 5 | `2610.12662-S1` | 14 | table | **unsupported** | Table 1 全部字符串都在，但 Qwen 列 "Level loop" 单元格的两行（`jnp.arange` / `.at[klevs].set`）被拆到相邻行：词坐标显示 `jnp.arange` 在 `top=240`，而 `Level loop` 与其它列在 `top=246–248`、`.at[klevs].set` 在 `top=254`。结果 `Level loop` 行的 Qwen 单元格为空，多出一行只含 `jnp.arange`。同项 Table 2 的 4 条数据行与表头行内容完整（表头分两个视觉行）。 |
| 6 | `2610.12662-S2` | 16 | table | **supported** | Table 3 六条数据行 × 3 个数值全部与原页一致；表头 `ε_v` / `E_v/ε_v` 被拆成两个视觉行，语义可复原。 |
| 7 | `2610.12662-S3` | 17 | table | **unsupported** | Table 4 的 11 条数据行 × 8 个数值全部正确；但表头列线切穿词：`H2D Per`+`(ms) (`、`m. in Perm`+`ms) (m`、`. out`+`s)`、`Total`+`(ms) t`、`F-order`+`otal (ms)`，列标签需跨视觉行重新拼合。 |
| 8 | `2610.12662-S4` | 15 | figure_caption | **supported** | Figure 2 图注逐字一致。 |
| 9 | `2609.39773-S1` | 35 | table | **supported** | Table 6 的 18 条数据行 × 5 个指标、分组结构（Target/Method、MCF 无误差棒）全部一致；Table 7 三条数据行一致。**附轻微缺陷**：表头的 `↑`/`↓` 方向标记与括号内空格被丢弃（`Solved(collisionsallowed)`）。 |
| 10 | `2609.39773-S2` | 39 | table | **unsupported** | Table 9 完全正确。但 Table 8 表头被切穿且**丢词**：原页表头词为 `CSD ID / Rotatable bonds / Energy rank / RMSD after MMFF94s / RMSD after UMA`，解析输出为 `CSD ID Rotatab | le bonds | Energy rank RMSD | after MMFF94s RMS | D after`，`UMA` 在整个 S2 段落中出现 0 次。Table 10 表头同样错列并丢失 `max_k p_k`：输出 `Effective components eff Dominant | -mode fraction`。两张表的数据行本身正确。 |
| 11 | `2610.06874-S1` | 14 | table | **unsupported** | Table 1 五条数据行数值正确；表头下标/单位被重排为 `dev. [%] σ | / σ [m/ u w`，原表头应为 `dev. [%]` 与 `σ_u / σ_w [m/s]`。 |
| 12 | `2610.06874-S2` | 21 | table | **supported** | Table 2 的 7 行 × 5 个 test 列全部一致（含 PID/Geometric SE(3) 基线行）。 |
| 13 | `2610.06874-S3` | 13 | figure_caption | **supported** | Figure 5 图注逐字一致；双面板图在其上方，`matched` 合理。 |
| 14 | `2610.10204-S1` | 3 | figure_caption | **uncertain** | Figure 1 图注文本逐字一致（含原页拼写/语法）；但 caption↔figure 关联为 `unmatched`（confidence 0.0），而图就在图注正上方。属关联能力缺口，非文本缺陷。 |
| 15 | `2610.10204-S2` | 4 | figure_caption | **supported** | Figure 2 图注逐字一致；原页图注本身即拼作 `iron-phytolankton`（源文笔误），解析忠实保留、未引入新错误；关联 `matched` 0.967。 |
| 16 | `2610.10204-S3` | 5 | figure_caption | **supported** | Figure 3 图注一致（含原页 `models variables`、`cloud represent`）；关联 `matched` 0.967。 |

小计：**supported 11、unsupported 4、uncertain 1**（AI 辅助结论，待用户确认）。
判为 `unsupported` 的是第 5、7、10、11 项，判为 `uncertain` 的是第 14 项。

## 归纳出的通用缺陷模式

1. **多行表头被列线切穿（最高频）** — `2610.12662-S3`、`2609.39773-S2`（表 8、表 10）、`2610.06874-S1`。
   由粗体表头行推断的列边界穿过多行表头单元格，产生词中截断、错列，甚至**整词丢失**（`UMA`、`max_k p_k`）。
   这些元素仍带 `table_header_geometry_unreliable` 警告，但输出仍以结构化表格形式呈现，容易被下游当作可信表头。
2. **两行式表头被输出成两行表格行** — `2610.12662-S1`(表 2)、`2610.12662-S2`(表 3)。
   内容无损、语义可复原，但首个表头行首列为空，`header_row_count` 语义变模糊。
3. **双行单元格按视觉行拆开** — `2610.12662-S1`(表 1)。
   单元格内第二个视觉行被当成新的一行，导致数据落到错误的行。
4. **纯矢量图无法建立 caption↔figure 关联** — `2610.10204-S1` 为 `unmatched` 0.0，
   而同论文其它页同类图注为 0.95+。图注文本本身没有缺陷。

模式 1 与 3 是**内容正确性**问题（丢词、错行），模式 2 与 4 是**结构/关联**问题。

## 供用户勾选的最短清单

请对照原页逐项回复 `supported` / `unsupported` / `uncertain`（AI 建议仅供参考，请按你自己的判断填写）：

```
1.  2610.09789-S1  p5  Table 1            [ AI: supported   ] 你：
2.  2610.09789-S2  p9  Figure 3 caption   [ AI: supported   ] 你：
3.  2610.09789-S3  p10 Table 2            [ AI: supported   ] 你：
4.  2610.09789-S4  p6  Figure 1 caption   [ AI: supported   ] 你：
5.  2610.12662-S1  p14 Table 1 + 2        [ AI: unsupported ] 你：
6.  2610.12662-S2  p16 Table 3            [ AI: supported   ] 你：
7.  2610.12662-S3  p17 Table 4            [ AI: unsupported ] 你：
8.  2610.12662-S4  p15 Figure 2 caption   [ AI: supported   ] 你：
9.  2609.39773-S1  p35 Table 6 + 7        [ AI: supported   ] 你：
10. 2609.39773-S2  p39 Table 8 + 9 + 10   [ AI: unsupported ] 你：
11. 2610.06874-S1  p14 Table 1            [ AI: unsupported ] 你：
12. 2610.06874-S2  p21 Table 2            [ AI: supported   ] 你：
13. 2610.06874-S3  p13 Figure 5 caption   [ AI: supported   ] 你：
14. 2610.10204-S1  p3  Figure 1 caption   [ AI: uncertain   ] 你：
15. 2610.10204-S2  p4  Figure 2 caption   [ AI: supported   ] 你：
16. 2610.10204-S3  p5  Figure 3 caption   [ AI: supported   ] 你：
```

若只回答第 5、7、10、11 项（AI 判为 unsupported 的四项）与第 14 项，也足以驱动下一轮修复。

## 如何自行核验这 5 项（操作说明）

### 先说清楚 "supported / unsupported" 在这里指什么

这一项审的是**解析器输出的表格/图注元素是否忠实代表原页**。请按三条轴分别看，任何一条不通过就可以判 `unsupported`：

1. **类型**：原页这里是不是该类型（`table` / `figure_caption`）？
2. **内容完整性**：原页上的每个词/数字/符号，解析输出里是否都还在（没有静默丢词）？
3. **结构或归属**：表格单元格是否落在正确的行/列；图注是否关联到正确的图？

判断时不要把"解析器已经给了 `table_header_geometry_unreliable` 这类 warning"当作通过理由——warning 只披露不确定性，输出仍以结构化表格呈现，下游会当可信表头用。另外，"把两个视觉行拼起来能读通"算**可复原**（可判 supported 但需注明）；**拼起来仍缺词**算不可复原（判 unsupported）。

### 怎么打开材料

**先看解析结果本身。** 本轮提供了一个只读查看器 `tmp/v26-crops/inspect_v26.py`（不写数据库、不写 `reports/`），在 `backend/` 目录下运行：

```powershell
cd backend
$env:PYTHONIOENCODING='utf-8'          # 否则中文/数学符号在控制台会乱码

# 1) 列出复核包的 16 项
..\.venv\Scripts\python.exe ..\tmp\v26-crops\inspect_v26.py list

# 2) 看某一项的解析结构（第 5 项；第二个参数是该项里的第几个元素）
..\.venv\Scripts\python.exe ..\tmp\v26-crops\inspect_v26.py sample 5
..\.venv\Scripts\python.exe ..\tmp\v26-crops\inspect_v26.py sample 5 2

# 3) 直接看逐篇 v26 草稿里的任意元素（全 217 页都在）
..\.venv\Scripts\python.exe ..\tmp\v26-crops\inspect_v26.py draft 2610.12662 --page 14 --type table
..\.venv\Scripts\python.exe ..\tmp\v26-crops\inspect_v26.py draft 2610.10204 --id pdfel_222a0a4d92cbc3baadc7adb9
```

输出里会直接给出 `row_semantics` / `structure_status` / `row_count`、表头单元格、以及每行的 `row_index` 与四个单元格文本——上面第 5 项的"幻影行 + Qwen 空单元格"就是这么看到的。图注元素会额外打印 `image_relation`。

**再看原页图片对照。** 复核包在 `backend/reports/live_eval/corpus-expansion-v26-human-review.md`，每项都有 `Original page` 链接指向 `v23-review-pages/*.png`；更清楚的是本轮从源 PDF 重渲染的 150 DPI 放大裁切，在 `data/storage/v26-crops/`：

```powershell
explorer data\storage\v26-crops
start "" "evaluating llms for translating.pdf"   # 或直接开原 PDF
```

**数据文件位置**（都可直接打开）：
- 逐篇完整解析草稿：`backend/reports/live_eval/<arxiv>-v26-draft.json`（含 `elements` / `table_regions` / `image_regions` / `figure_captions` / `warnings`）
- 复核包的机器可读清单：`backend/reports/live_eval/R02-v26-human-review-manifest.json`
- 渲染裁切的生成脚本：`tmp/v26-crops/make_crops.py`（`probe_rows.py` 是词坐标探针）

### 逐项核对卡

**第 5 项 · `2610.12662-S1` · p14 · 图 `12662-p14-t1t2.png`**

- 原页应看到：Table 1 的 **Qwen 列在 "Level loop" 行是一个两行单元格**，内容是 `jnp.arange` / `.at[klevs].set`，两行合起来才是该单元格的值。
- 解析输出（复核包 621–636 行）：
  ```
  Column loop | vmap | vmap | fori_loop
   |  |  | jnp.arange          ← 多出来的第 2 行
  Level loop | jnp.arange | jnp.arange(nz) + clip |     ← Qwen 单元格为空
   |  |  | .at[klevs].set
  ```
- 要判断的：`jnp.arange` 是否被挂到了 "Level loop" **上一行**、使 "Level loop" 行的 Qwen 单元格变空。词坐标已确认 `jnp.arange` 在 `top=240`，而该行其它列在 `top=246–248`。
- **决定性结构证据**（2026-10-15 补充）：该元素的 JSON 声明 `row_semantics = "pdfplumber_grid"`、`structure_status = "pdfplumber_grid"`，即解析器**主张这 7 行是真实表格行、不是视觉行**；但 `row_count = 7` 而原表只有 4 条数据行（含表头应为 5 行）。逐行单元格如下：
  ```
  row_index=0 : ['Design aspect','Claude/GPT','Gemini','Qwen']
  row_index=2 : ['Column loop','vmap','vmap','fori_loop']
  row_index=4 : ['','','','jnp.arange']              ← 幻影行
  row_index=5 : ['Level loop','jnp.arange','jnp.arange(nz) + clip','']   ← Qwen 为空
  row_index=6 : ['','','','.at[klevs].set']
  row_index=8 : ['Top boundary','scalar index','jnp.clip + jnp.where','.at[].set()']
  row_index=10: ['Subcycle loop','while_loop','while_loop','while_loop']
  ```
  因此本项**没有丢字符**（文本块按阅读顺序仍可读懂），但**按行查单元格会错**：查 "Level loop" 行的 Qwen 得到空值，且多出一个无名行。若验收口径只看文本保真，可判 `supported`；本文按复核包自己写明的 "table row/column mapping" 口径判 `unsupported`。同一缺陷模式会影响语料中其它多行单元格表格，所以这里的标签不只决定这一张表。
- 同项的 Table 2（983–989 行）表头分成两行但 4 条数据行完全正确，其 `row_semantics` 为 `grid_body_rows_header_uncertain`（表头不确定、正文行声明为网格），可单独认定。

**第 7 项 · `2610.12662-S3` · p17 · 图 `12662-p17-t4.png`**

- 原页应看到表头：`Columns`、`Input (MB)`、`Output (MB)`、`H2D (ms)`、`Perm. in (ms)`、`Perm. out (ms)`、`D2H (ms)`、`Total (ms)`、`F-order total (ms)`。
- 解析输出（1739–1743 行）表头三行：
  ```
   | Input | Output | H2D Per | m. in Perm | . out | D2H | Total | F-order
  Columns |  |  |  |  |  |  |  |
   | (MB) | (MB) | (ms) ( | ms) (m | s) | (ms) | (ms) t | otal (ms)
  ```
- 要判断的：列线是否**切穿了表头单词**（`Per`+`m.`、`Perm`+`ms)`、`F-order`+`otal`）。11 条数据行 × 8 个数值我已逐条对过全部正确，本项问题只在表头标签。

**第 10 项 · `2609.39773-S2` · p39 · 图 `39773-p39-t8t9.png`、`39773-p39-t10.png`**

- 原页应看到：Table 8 表头最后一列是 **`RMSD after UMA`**；Table 10 表头最后一列是 **`Dominant-mode fraction max_k p_k`**。
- 解析输出：
  - 4733 行 Table 8 表头 = `CSD ID Rotatab | le bonds | Energy rank RMSD | after MMFF94s RMS | D after` → 拼起来是 "…RMSD after"，**`UMA` 不见了**（整段检索出现 0 次）。
  - 5576 行 Table 10 表头 = `… | Effective components eff Dominant | -mode fraction` → **`max_k p_k` 不见了**。
- 要判断的：这是**丢词**（不可复原）还是可接受。Table 9（5004 行起）完全正确，可单独认定。

**第 11 项 · `2610.06874-S1` · p14 · 图 `06874-p14-t1.png`**

- 原页应看到表头：`z [m]`、`⟨u⟩ [m/s]`、`log law [m/s]`、`dev. [%]`、`σ_u / σ_w [m/s]`。
- 解析输出（6006 行）：`… | dev. [%] σ | / σ [m/ u w` → 最后一列的下标 `u`、`w` 与单位 `s]` 被拆散重排。
- 要判断的：五条数据行数值我已逐条对过全部正确，问题只在表头符号。

**第 14 项 · `2610.10204-S1` · p3 · 图 `10204-p3-fig1.png`**

- 原页应看到：Figure 1 的图就在图注正上方，图注文本本身完整。
- 解析输出：文本逐字一致，但元素记录的 `image relation` 是 `"status": "unmatched", "confidence": 0.0`——解析器**没能把这条图注关联到那张图**；同论文 p4/p5 的同类图注都是 `matched` 0.967。
- 要判断的：文本没问题，缺的是"图注↔图"关联。若你认为关联能力属于该项验收范围 → `unsupported`；若只验收文本 → `supported` 并注明关联缺口。我给 `uncertain` 正是因为这条取决于你的口径。

### 快捷路径

不想逐条读上面的话：打开 `data\storage\v26-crops\`，依次看这 5 张图，每张只问一句"解析输出里那一段是不是原页那一段"，然后回复 5 个词即可。若认可我的读法，直接回：

```
5 unsupported  7 unsupported  10 unsupported  11 unsupported  14 uncertain
```

## 建议的后续动作

1. 修模式 1：当表头列线会切穿任何原始词框时，不应输出带列结构的表格表头，而应降级为视觉行
   或明确标记表头不完整；缺失词（`UMA`、`max_k p_k`）尤其不能静默丢弃。
2. 修模式 3：同一单元格的多视觉行必须合并到同一行，不能按 y 阈值另起一行。
3. 为每个缺陷补 `TEST-*` 合成覆盖（多行表头、双行单元格、矢量图无边界）。
4. 修复后重建 v26+ 草稿与人审包；本记录中的 v26 标签不迁移到新版本。
