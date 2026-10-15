# R03 人工证据支持度核验包

状态：用户已完成 4 题人工标注（2026-10-12）。此材料从本机已许可导入的 arXiv:2608.20519v1 全文索引生成，用于检查检索证据能否支持候选回答，不评价论文结论正确性，也不代表通用 RAG 质量。没有调用模型。

## 文献来源与本轮索引

- Yunxiang Li et al., *An integrated diffusion-weighted imaging processing and interpretation platform for MR-guided radiotherapy*, arXiv:2608.20519v1。
- 来源：[arXiv 条目](https://arxiv.org/abs/2608.20519)；许可：CC BY 4.0（[许可文本](https://creativecommons.org/licenses/by/4.0/)）。
- 本机 parser：`pdfplumber-layout-v6`；全文索引版本 SHA-256：`7b0d97da02fdc2e3d419f29a184257fc3a81aeab207368d8ab78546594f75c63`。
- 许可归属：Yunxiang Li, Yan Dai, Yen-Peng Liao, Jie Deng, Jill B De Vis, You Zhang, arXiv:2608.20519v1, CC BY 4.0。

## 请如何标注

对每题只看“候选回答”和列出的检索证据，判断证据对候选回答的支持程度：

- `supported`：所列证据直接、完整地支持回答。
- `partially_supported`：大意有依据，但关键限定、比较对象、数值或上下文缺失。
- `unsupported`：证据不支持回答，或与证据矛盾。
- `unanswerable`：这份证据不足以判断；不要用论文常识或外部知识补全。

请回复每题 ID 和标签；若选 `partially_supported` 或 `unsupported`，请用一句话说明缺失/矛盾点。可以指出 locator 或抽取文本的问题。这里不需要你重新导入文件或运行命令。

## 逐题核验

### E1：组件与功能

- 问题：论文中的哪一项 Web 组件负责双向实时通信/进度更新？
- 候选回答：Flask 与 Flask-SocketIO 组合承担 Web 服务和实时进度通信。
- 检索位置：PDF 第 6 页，`2 Methods / 2.1 System overview and architecture`，Table 1，行 3–4；BM25 首位为 `table` chunk。
- 检索证据（excerpt）：`Flask / Flask-SocketIO | 2.3 / 5.5 | Web server and real-time progress stream-`；续行 `| | ing`。正文第 5 页另描述 Flask-SocketIO 用于双向实时通信，并让长任务把进度报告给浏览器。
- 用户人工标签：`supported`。

### E2：Table 2 参数覆盖数量

- 问题：Table 2 分别报告多少篇论文涉及 ADC 与 IVIM 参数？
- 候选回答：ADC 为 28 篇，IVIM 为 13 篇。
- 检索位置：PDF 第 14 页，`2 Methods / 2.5 Retrieval-augmented clinical-interpretation agent`，Table 2，参数行；BM25 首位为 `table` chunk。
- 检索证据（excerpt）：`Parameters | ADC | 28 papers`；`IVIM (…) | 13 papers`。
- 用户人工标签：`supported`。

### E3：汇总临床效用评分

- 问题：Table 3 中 pooled overall clinical utility 的均值和标准差是多少？
- 候选回答：`4.83 ± 0.38`。
- 检索位置：PDF 第 20 页，`3 Results / 3.2 Expert evaluation results`，Table 3，`Overall clinical utility` 行；BM25 top-3 命中表格 chunk。
- 检索证据（excerpt）：`Overall clinical utility | 4.78 ± 0.44 | 4.89 ± 0.33 | 4.83 ± 0.38`；列头区分 Physicist、Physician、Pooled。
- 用户人工标签：`supported`。

### E4：跨列比较与否定判断

- 问题：根据 Table 3，physician 对 clinical reasoning soundness 的评分均值是否高于 physicist？
- 候选回答：是；physician 的均值更高。
- 检索位置：PDF 第 20 页，同一 Table 3，`Clinical-reasoning soundness` 行。
- 检索证据（excerpt）：`Clinical-reasoning soundness | 5.00 ± 0.00 | 4.22 ± 1.20 | 4.61 ± 0.92`；列头顺序为 Physicist、Physician、Pooled。
- 用户人工标签：`unsupported`。理由：列头顺序表明 physician 均值为 4.22，低于 physicist 的 5.00，与候选回答相反。

## 标注回传格式

```text
E1 supported — …
E2 supported — …
E3 partially_supported — …
E4 unsupported — …
```

以上是一个用户对单篇论文、四条候选回答的人工支持度判断；不是独立双人标注或通用质量评测，不足以计算可泛化的 RAG 指标。机器可读记录见 [R03 人工复核 JSON](R03-human-evidence-review-arxiv-2608.20519-v1.json)。
