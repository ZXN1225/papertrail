# 当前本机许可全文版本审计

日期：2026-10-13。活动索引先用既有审核元数据将四篇已批准 PDF 重解析至 v19，再通过 `PaperStore(readonly=True)` 只读核验 lineage；lineage 命令本身不读取 PDF 正文、不写数据库、不调用模型或外部服务。

| arXiv ID | 本机 PDF | 状态 | 许可 | Parser | 活动 chunks | PDF SHA-256 | 活动 content SHA-256 |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| 2609.27579 | `integration of RAG.pdf` | approved | CC-BY-4.0 | pdfplumber-layout-v19 | 48 | `f944b10d58484c1d57c5dba23a1e4c18fcc1a07a18606e0c2b728d9cb46ba20d` | `75e0a5d3fcade025ed2b5a6cf3ab8f33ac08961a9ca4f8e58b9030bd37a24ca9` |
| 2608.02037 | `A  Heterogeneous 200 mm Silicon.pdf` | approved | CC-BY-4.0 | pdfplumber-layout-v19 | 315 | `e3b9029a72c6466c837e8c1b320dbddca1800d353d0e667b383adfd552e04d51` | `5bd3a8ff88b511766b70a184bb9aff90997eb9e983258bb2342d8238891e3888` |
| 2607.24663 | `A corrective agentic hybrid RAG.pdf` | approved | CC-BY-4.0 | pdfplumber-layout-v19 | 743 | `eea9e7fa8917ca11c62802765865265aa4961c959579cd34633d8622f88ede5c` | `2abfc608ecff5294873678b96b6a2b8538d6bd5e1111e2d6a3f5d226ccd55b58` |
| 2608.20519 | `An integrated diffusion-weighted.pdf` | approved | CC-BY-4.0 | pdfplumber-layout-v19 | 263 | `7d664debd8dc5c83119c0b1b64a9d8ef2a277eca54cea402dd786fd9d311ce31` | `3d42eeb534db0043900ceb9ab63860e883ca89637b37b6152fb3e3d30b7de8d1` |

对每篇论文，使用表中本机 PDF 重新计算的 SHA-256 均与活动版本中的 `source_document_sha256` 完全一致；版本元数据的 chunk 数也与只读查询到的活动 chunk 数相同，活动 chunks 全部使用该行所列 content SHA。共 1,369 chunks。该核对证明本机 PDF 字节、数据库版本 lineage 和许可记录一致，不证明 PDF 的通用解析准确率，也不重新裁定许可授予的法律范围。

以上结果现可用只读命令复现（从 `backend/` 目录运行；命令只对 PDF 字节计算 SHA，不抽取或输出 PDF 文本）：

```powershell
.venv\Scripts\python.exe -m app.cli.audit_fulltext_lineage `
  --pdf "2609.27579=..\integration of RAG.pdf" `
  --pdf "2608.02037=..\A  Heterogeneous 200 mm Silicon.pdf" `
  --pdf "2607.24663=..\A corrective agentic hybrid RAG.pdf" `
  --pdf "2608.20519=..\An integrated diffusion-weighted.pdf"
```

机器可读输出不含 excerpt，显式标注 `read_only=true` 与 `quality_claim_allowed=false`。`verified` 仅表示许可/版本元数据和当前本机 PDF 字节及活动 chunks 对齐；不能据此推断解析正确率。

## 与历史评测版本的隔离

早期 `R01-R03-real-evidence-pilot-v1.json` 冻结在 `pdfplumber-layout-v13`，其来源哈希与上表 v19 内容哈希不同；v15/v17/v18 六题诊断也绑定旧 content SHA。原冻结任务、旧检索排名和旧人审标签继续绑定各自版本；不迁移或回填为 v19 金标。`backend/data/evaluation/arxiv-r01-r03-current-v15-v1.json` 的 SHA-256 为 `759d68c2c1078e8dc5b0b6155048b2686b470f98ddeabe5cbe14ea3a71e537f5`。v19 有单独六题版本诊断，精确映射旧参考后 6/6 进入 top 8、locator 6/6 一致；这仍是单人选定参考而非 gold recall，详见 [v19 BM25 诊断](R01-R03-current-v19-bm25-smoke-2026-10-13.md)。

## 验收范围

- 四篇活动全文：approved、CC-BY-4.0、parser v19；metadata chunk count 与只读活动记录一致。
- 旧三篇 R1–R6 人审标签绑定 v15 清单；v19 新诊断是逐段精确重映射，不是新的人工支持性标注。
- 未执行：新增语料导入、独立 holdout、跨布局准确率统计、v19 新内容的人审支持性抽样、LLM/Skills/Multi-agent 新调用。
- 外部条件：更大独立评测仍需用户选择并确认候选许可 PDF；用户已暂缓此步骤。Skills/Multi-agent 质量比较仍需新的模型调用授权和预算。
