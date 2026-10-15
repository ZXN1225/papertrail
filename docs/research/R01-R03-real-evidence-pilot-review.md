# R01/R03：真实论文证据核验小样本（待人工标注）

日期：2026-10-12。此包使用三篇已逐篇确认 CC BY 4.0 的本机 PDF，冻结的检索记录见 [机器可读候选集](R01-R03-real-evidence-pilot-v1.json)，文件 SHA-256 为 `9ceb30530faff7fae5a6ea085479b6755d6277077211c306e6758cd52e2ae0e3`。候选问题、回答和参考位置由助手准备，**尚不是人工金标，也不是模型生成答案**。检索只调用本机只读 BM25，没有调用付费模型或 embedding。每题只在指定 arXiv 论文内检索，最多记录前 8 项。

**后续状态（2026-10-12）**：用户已完成六题原文可答性与候选支持度标注，另通过 Table III 裁剪输出与 2609 摘录 bbox。原核验题目保留不改；标签和描述性统计见 [人工审阅记录](R01-R03-real-evidence-pilot-human-review-v1.json) 与 [结果说明](R01-R03-real-evidence-pilot-result.md)。下文“待人工标注”是发给用户时的历史说明。

## 标注方法

请先看对应 PDF 原文，再给每题两项标签：

1. `answerable` / `unanswerable` / `uncertain`：原 PDF 能否回答问题。
2. `supported` / `partially_supported` / `unsupported` / `insufficient_evidence`：下面的**候选回答**能否由所列原文位置支持。若数值、方向或对象错位，请标 `unsupported` 并写一句原因。

所列“参考位置”仅是助手选出的核验候选，不能自动算作真实相关性金标。括号中的 BM25 排名表示这一候选 chunk 在本次前 8 条中的位置；“未进前 8”只描述检索结果，不直接判定回答质量。

## arXiv:2609.27579 — ELBE 系统

来源：[arXiv 页面](https://arxiv.org/abs/2609.27579)，CC BY 4.0，索引内容 SHA-256 `8806728fcc1d5c30ef0a74eef04ac1a42922b5e0978aa0191bc04ce1a2d2966b`。

### R1：架构层级

- 问题：Which four layers make up the proposed ELBE RAG framework?
- 候选回答：The four layers are Data, Indexing, Retrieval, and Generation.
- 参考位置：PDF 第 3 页右栏，从 `Data Layer` 到 `Generation Layer`；对应 chunk 在本次 BM25 前 8 条之外。第 1 条检索结果为同页左栏的架构概述，列出 data ingestion、semantic indexing、retrieval 和 response generation。

### R2：系统权限

- 问题：Does the proposed ELBE assistant directly perform accelerator control actions?
- 候选回答：Yes. It directly performs accelerator control actions.
- 参考位置：PDF 第 2 页，关于 decision-support tool 的正文；BM25 第 1 条，原文含 `does not perform control actions`。

## arXiv:2608.02037 — SiN 光子平台

来源：[arXiv 页面](https://arxiv.org/abs/2608.02037)，CC BY 4.0，索引内容 SHA-256 `f7e369019af0246a8ac5a2b2513f2d711a43f6493b996d085118d5c7f43e78fe`。

### R3：Figure 5(a)

- 问题：In Figure 5(a), what wavelength and SiN thickness were measured?
- 候选回答：Figure 5(a) uses a wavelength of 488 nm and 150 nm thick SiN.
- 参考位置：PDF 第 9 页 Figure 5(a) 图注；BM25 第 2 条，图注直接给出厚度和波长。

### R4：Figure 5(d)/(e)

- 问题：Which a-Si:H thickness belongs to panels d and e of Figure 5?
- 候选回答：Panel (d) uses 220 nm a-Si:H, while panel (e) uses 70 nm a-Si:H.
- 参考位置：PDF 第 9 页 Figure 5(d)/(e) 图注；对应图注 chunk 未进入本次 BM25 前 8 条。这也保留了一个真实检索失败候选，不能靠候选回答反推检索成功。

## arXiv:2607.24663 — APS-RAG

来源：[arXiv 页面](https://arxiv.org/abs/2607.24663)，CC BY 4.0，索引内容 SHA-256 `24d68b981e8d126093e77c0b064d46b1395b780adc3ff8998d6d6a3ab27f63b4`。

### R5：Table II 两项指标

- 问题：What were the strict vital recall and hallucination rate for Agentic GraphRAG in Table II?
- 候选回答：Agentic GraphRAG (ours) achieved 70.3% strict vital recall and 8.7% hallucination rate.
- 参考位置：PDF 第 10 页 Table II，`Agentic GraphRAG (ours)` 行；BM25 第 2 条，locator `解析器物理行 5-9`。BM25 第 1 条是同页不完整的正文片段，不能只凭它核对表格数值。

### R6：Table III 列比较

- 问题：Which system has the highest NDCG at 10 in Table III?
- 候选回答：GraphRAG had the highest NDCG@10 in Table III, at 73.3%.
- 参考位置：PDF 第 10 页 Table III 的 NDCG@10 列；BM25 第 3 条，结构化结果给出 `Hybrid RAG 73.6` 和 `GraphRAG 73.3`。用户已确认原表为一行表头、五行数据；完整裁剪结果见 [R02 三篇论文审阅包](R02-three-paper-review-pack.md)，仍需独立核对其是否混入正文。

## 回复格式

```text
R1 answerable / unanswerable / uncertain；supported / partially_supported / unsupported / insufficient_evidence；原因（可选）
R2 ...
R3 ...
R4 ...
R5 ...
R6 ...
Table III 裁剪输出：通过 / 有误（指出多余或缺失的行）
```

这六题和先前单篇四题合计仍只是小样本；标注前不计算真实语料质量指标。即使标注完成，也只能报告这组题的描述性结果，不能据此声称一般论文 RAG 准确率。
