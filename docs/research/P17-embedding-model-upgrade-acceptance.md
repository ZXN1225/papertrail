# P17 验收：升级论文检索 Embedding 模型

## 目标

将可选 Dense/Hybrid 检索的 OpenAI Embedding 从 `text-embedding-3-small` 升级到 `text-embedding-3-large`，并保留 BM25 默认路径。模型能力提升是官方基准而非 PaperTrail 自身质量结论；本阶段必须用相同冻结评测集重跑，且继续标明 P14 qrels 未经人工核验。

## 验收标准

- [x] 示例/本机配置、开发说明、README 与测试使用 `text-embedding-3-large`、3072 维和估价 `$0.13 / 1M input tokens`；Embedding provider 仍默认关闭，BM25 仍为默认。
- [x] OpenAI Embeddings 请求将模型和维数固定为配置值；新增自动测试验证 Large/3072 路径以及异常响应仍安全失败，不访问外网。
- [x] 文档说明升级后必须为当前批准的全文重新建立 Large 向量索引；旧 Small 索引保留为历史向量但不会被 Large 查询误用。全文仅在显式启用并执行索引命令后发送给 provider。
- [x] README/P14 历史报告仍准确记录原先 Small 模型及其当次指标/费用，不覆盖历史结果或把新模型结果与旧运行混为一谈。
- [x] 使用相同冻结数据和查询，重跑 P14 Large 对 BM25、Dense、Hybrid 的对照；报告记录新模型、维数、token、估算费用与哈希，并继续设置 `exploratory_only=true`、`quality_claim_allowed=false`。输出到独立 `reports/p17-large-retrieval-comparison.json`，避免覆盖 Small 历史报告。
- [x] Ruff、后端测试（100 passed）、OpenAPI 契约、Web Prettier/typecheck 与 `git diff --check` 通过。

## 本机复评核对

- 报告：`backend/reports/p17-large-retrieval-comparison.json`；Large、3072 维、130 inputs、23,960 tokens、3 API calls，估算费用 `$0.0031148`。费用与 token 数及 `$0.13/1M` 单价相符。
- 与 P14 Small 基线使用相同 P13 数据 SHA-256、snapshot、100 篇文献及 30 个查询；runner 哈希也与当前 P14 评测实现一致。
- 指标（Hit@1 / MRR@10 / NDCG@10）：BM25 `0.533333 / 0.644444 / 0.522229`；Large Dense `0.800000 / 0.849339 / 0.695197`；Large Hybrid `0.766667 / 0.847778 / 0.646557`。对照 Small，Dense 的 NDCG 提升而 Hit@1、MRR 略降；Hybrid 的 MRR/NDCG 提升。标签未经人工核验，不能据此下质量结论。
- 报告的 `reproducibility.command` 没有包含用户实际指定的 `--output reports/p17-large-retrieval-comparison.json`。这不改变已记录指标、数据哈希或费用，但复跑会默认写入 P14 报告路径。后续 P18 修复 CLI 的实际参数/输出路径记录；不为修复此元数据而重跑收费 API。
- `AGENTS.md` 列出的根 `scripts/check_foundation.py` 和 `scripts/check_source_review.py` 当前检出中不存在，因此未运行；本次实际可用的后端与 Web 检查均通过。此工作约定/仓库状态不一致已记下。

## 已知权衡

官方 OpenAI 文档将 `text-embedding-3-large` 标为其当前最强 Embedding 模型，面向英文和非英文任务；指南列出的 MTEB 为 64.6%，`text-embedding-3-small` 为 62.3%。Large 默认 3072 维，Small 默认 1536 维。官方模型页面列出的标准输入价格分别为 `$0.13` 和 `$0.02` 每百万 tokens。以上是通用模型信息；不能代替 PaperTrail 本身检索评测。来源：[模型页](https://developers.openai.com/api/docs/models/text-embedding-3-large)、[Embeddings 指南](https://developers.openai.com/api/docs/guides/embeddings)。

## 当前状态

P17 已完成验收。Large 是当前可选 Dense/Hybrid 模型；BM25 仍为默认。此次实测仅作为 AI qrels 探索性诊断，不能宣称 Large 普遍优于 Small 或代表检索质量。
