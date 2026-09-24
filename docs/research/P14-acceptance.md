# P14 验收：检索方法对照与失败查询诊断

## 目标

在 P13 固定的 100 篇 OpenAlex 元数据、30 个研究问题上比较 BM25、OpenAI Dense 与 RRF Hybrid，输出总体和 14 个意图桶指标，并列出方法分歧最大的查询供后续改进。该数据集的标签来自助手建议，所有结论都仅用于探索诊断。

## 验收标准

- [x] 命令只接受 `assistant_labeled` 数据集，校验固定 100 个 Work ID、逐篇内容哈希和 snapshot ID。
- [x] 仅在显式传入 `--allow-provider-call` 且 embedding provider 已配置时访问固定 OpenAI Embeddings endpoint；130 个输入分 3 批（最多 64 条），输入为 OpenAlex 标题/摘要与 30 个查询。报告记录模型、维数、token、估算成本，不保存 API Key 或向量。
- [x] BM25、Dense、RRF@60 使用相同 query、语料、0—3 标签；输出 Hit@1/3/5/10、MRR@10、NDCG@1/3/5/10、14 桶指标、每查询 top-10 和方法差异排序。
- [x] 报告明确 `exploratory_only=true`、`quality_claim_allowed=false` 和 AI 标签未人工验证；保存数据集哈希、runner 哈希、模型及运行环境。
- [x] 3 个新增测试覆盖成功对照、批大小、未标注数据和快照不匹配拒绝；测试通过。
- [x] 本轮仅使用 100 篇 CC0 元数据，不读取许可全文，不调用聊天 LLM。

## 结果

## 实际结果（2026-09-24）

- 数据：30 queries / 100 Works；P13 snapshot `f7f7267d-78fa-4364-b5ca-0305986f1e89`，AI 数据 SHA-256 `1892413b3a4acc9006390db287e64b5ba065f0584f37ddc1131d81a3681d5495`。
- 使用 `text-embedding-3-small`，130 输入、23,960 tokens、3 次 API 请求；估算单次运行成本约 USD 0.0004792（按本机配置的单价估算，实际账单以账户为准）。为修正 MRR@10 只计前十名后重跑过一次；总估算约 USD 0.0009584。向量没有持久化。
- Hit@1 / MRR@10 / NDCG@10：BM25 `0.533333 / 0.644444 / 0.522229`；Dense `0.833333 / 0.856151 / 0.646412`；Hybrid `0.700000 / 0.820833 / 0.632071`。在这份 AI 标签下，Dense 的 MRR 和 NDCG 较高；Hybrid 的 Hit@3/5/10 较高。不可据此作质量声明。
- BM25 的最低 NDCG 查询包括 graph RAG 分类架构（P13-Q07）、检索质量控制（P13-Q12）、RAG 隐私风险（P13-Q23）；方法差异最大的有 P13-Q07、P13-Q17、P13-Q05、P13-Q02、P13-Q12。详细 top-10 和全部分桶结果写入本机忽略报告 `backend/reports/p14-retrieval-comparison.json`。
- 限制：qrels 只是从标题/摘要候选建议复制，未人工核验；语料本身来自 `retrieval augmented generation` 检索结果，主题选择偏差明显；embedding 基准只包含这 100 篇/30 个查询。这是故障定位线索，不是泛化的模型对比结论。
