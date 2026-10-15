# R02：三篇新许可论文的 RAG 人工抽样包

原抽样更新时间：2026-10-12，解析器 `pdfplumber-layout-v13`。本页展示系统从本机原 PDF 解析并检索的内容，供逐项与原 PDF 对照；不是对原始 PDF 做视觉修改。**2026-10-13 后续修正：**用户在真实模型人审发现 Figure 5 的 `(d)` 图注续行被旧版拆成 `paragraph`。解析器 v14 已修复并重新导入 2608.02037；下文 v13 抽样结果保留为历史快照，修复后验收见 [六题人审结果](R06-R07-live-postfix-result.md)。

## 论文 1：arXiv:2609.27579

文件：`integration of RAG.pdf`；4 页；CC BY 4.0；全文只保存在本机 host SQLite。

用户已确认第 1 页 Abstract 检索片段与 PDF 原文一致，第 3 页所列文字是右栏正文且没有跨栏拼接。**下方所列摘录的 bbox 为 `[304.72, 176.61, 540.32, 496.92]`**：起点是 `Data Layer` 行，终点是 `similarity search and structured filtering.` 行，按两行及其中各行的定位词坐标取外接框。数据库中的父 paragraph 元素 `pdfel_d4b7cf941edd4d7c1dcf6535` 的 bbox 则是 `[304.72, 176.61, 540.32, 561.30]`；它还包括下方 `Query and Retrieval Pipeline` 标题、开头说明和 `Input: User query Q`。所列摘录是该父元素的字符范围 `[0, 1375)`，没有把父元素 bbox 冒充摘录 bbox。页面保留 `multi_column_reading_order_ambiguous`，PDF 的跨行断词也按原文保留。

以下是 BM25 查询 `ELBE accelerator control system logbooks` 对应的右栏摘录（保留 PDF 行末断词）：

```text
Data Layer: Electronic logbooks, interlock and machine
protection records, archived process variables, and subsys-
tem documentation.
Indexing Layer: Text chunking, metadata enrichment,
embedding generation, and storage in a vector database.
Retrieval Layer: Hybrid semantic search combining sim-
ilarity retrieval with metadata filtering and time constraints.
Generation Layer: Context-conditioned response gen-
eration using a large language model with enforced source
traceability.
Data Processing and Indexing
Textual sources (logbooks, manuals, technical reports)
are expected to be segmented into semantically coherent
chunks and enriched with metadata fields including subsys-
tem label, component identifier, time stamp (when available),
and source type. Event-based records such as interlock trig-
gers would be stored as structured entries containing event
time, subsystem, and affected components. Archived time-
series process variables are planned to be accessed through
a dedicated interface. For semantic integration, selected
time windows would be summarized into compact statistical
descriptors before being included in the language model
context when required. All textual and event records would
be embedded using a domain-adapted embedding model and
stored together with metadata in a vector database supporting
similarity search and structured filtering.
```

## 论文 2：arXiv:2608.02037

文件：`A  Heterogeneous 200 mm Silicon.pdf`；16 页；CC BY 4.0；全文只保存在本机 host SQLite。

用户已确认 PDF 第 9 页 Figure 5 通过： (a) 488 nm、150 nm SiN；(b) 940 nm、300 nm SiN；(c) 940 nm、220 nm a-Si:H；(d)/(e) 940 nm、300 nm SiN 分别耦合至 70/220 nm a-Si:H。箱线图统计描述也与原文一致。v14 本机当前版本仍解析出 27 个图像区域和 2 个图注关联；第 9 页完整图注现为单个 `figure_caption`，包含 `(d)` 与 70 nm 的衔接。没有从图像像素读取曲线数据。

## 论文 3：arXiv:2607.24663

文件：`A corrective agentic hybrid RAG.pdf`；38 页；CC BY 4.0；全文只保存在本机 host SQLite。

用户已确认 PDF 第 10 页 Table II 的列顺序、数值和百分比单位正确；原表有 5 条系统数据行。修订后 locator 使用 **`第 10 页 · table · 解析器物理行 5-9`**：这里的 5–9 是解析器记录的 1-based 物理行号；前 4 行为多层表头，并没有计作数据行。BM25 结果包含全部 5 条数据行，`Agentic GraphRAG (ours)` 行是 strict vital recall 70.3、hallucination rate 8.7、accuracy 64.1、F1 71.2。所有四项的单位均为百分比，PDF 第 10 页的多栏警告不会改变这张位于页面顶部的通栏表格单元格定位。

同页 Table III 的解析 bbox 为 `[113.40, 263.89, 502.70, 325.71]`，结构化结果如下；其后的独立正文元素最早从页面 y=`349.38` 开始。2026-10-12 用户已独立核对该解析裁剪输出：表头、五条数据及各列数值与原 PDF 一致，没有多余/缺失行，也没有混入下方正文。

```text
System | MRR@10 (%) | NDCG@10 (%) | Recall@5 (%) | Recall@10 (%) | Recall@20 (%)
Naive RAG | 80.7 | 69.6 | 63.5 | 67.3 | 71.2
Hybrid RAG | 89.0 | 73.6 | 62.6 | 70.4 | 76.3
Agentic RAG | 83.8 | 71.0 | 67.8 | 76.5 | 74.0
GraphRAG | 87.0 | 73.3 | 61.9 | 69.1 | 76.7
Agentic GraphRAG (ours) | 85.6 | 72.2 | 62.1 | 69.1 | 75.1
```

## 当前人工验收状态

- 2609.27579：第 1 页摘要、第 3 页右栏文本/独立性及收紧后的摘录 bbox 均已由用户确认；父元素 bbox 另列。
- 2608.02037：通过。
- 2607.24663：Table II 原文内容和物理行 locator、Table III 六行裁剪结果及正文排除均已由用户确认。

这些人工抽样不构成通用 PDF 准确率、OCR 或图像语义理解能力的证明。三篇全文仍只在本机；尚未上传或提交。
