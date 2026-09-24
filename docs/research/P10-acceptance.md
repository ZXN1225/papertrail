# P10 验收：Embedding、Hybrid 与排序消融

## 目标

在 P09 BM25 全文检索上增加可替换的向量召回与混合排序，使用固定语料和查询对 BM25、Dense、Hybrid 做可重复对照。该阶段验证的是本项目实现与小型评测集表现，不把有限样本结果包装成通用论文检索质量结论。

## 验收条件

- 首选验证模型为 `text-embedding-3-small`，默认 1536 维；OpenAI 官方文档列出 8192 token 单输入上限，并支持指定缩短维度。官方页面当前列价为每百万输入 token $0.02。采用小型版是因为成本低且官方说明具备更高多语言表现；本项目仍需以自己的评测集决定是否足够，不能把模型卡基准当成本项目结果。[OpenAI Embeddings 指南](https://developers.openai.com/api/docs/guides/embeddings)
- 在实施前核对并记录所选 embedding 服务的当前官方模型、维度、请求限制、价格与数据处理设置；Provider 默认关闭。单元测试使用 fake provider，不隐式发起付费 API 请求。Live embedding smoke 仅在本机显式配置且用户要求测试时运行，并记录模型、维度、实际 token/调用数与费用口径。
- 定义稳定的 embedding Provider 契约：批量输入有界、输出数量/维度/有限数值校验、超时与错误分类明确；模型名、维度、原始未归一化存储方式、cosine 检索和内容哈希纳入索引 lineage。配置或模型不匹配时拒绝混用旧向量。
- 向量存储只服务本地已批准的全文片段；沿用 P09 的许可门禁、当前版本语义和撤回行为。删除/换版后旧向量不可检索，重复索引幂等；Embedding 不更改原文、许可记录或 citation lineage。
- 同一冻结语料、查询和 qrels 分别运行 BM25、Dense cosine 与 Hybrid（固定并记录 RRF 参数）；不得为某个方法单独过滤文档或调整 qrels。确定性 tie-break、top-k、空结果处理和数据/模型/配置哈希写入 JSON 报告。
- 评测集与真实索引隔离：新增的演示语料和 qrels 均用 `TEST-*` ID、`synthetic=true` 标记，不导入真实 namespace，也不纳入真实论文引用。当前单篇 18 chunks 的 CC-BY 论文只可做人工许可的功能 smoke，不足以支持质量比较。
- 报告 Hit@1/3/5/10、MRR@10、NDCG@10、空结果率，以及索引耗时、单查询均值/P50/P95 延迟、embedding 调用数/token 和可核算成本。synthetic 结果显式标 `exploratory_only=true`；P05 OpenAlex qrels 经人工复核前也不得称作 gold 或质量结论。
- 测试覆盖 embedding 成功/异常/超时/错误维度、空输入、重复索引、索引版本失效、撤回后向量不可见、BM25/Dense/Hybrid 报告可复现、TEST/真实数据隔离及证据 citation 不变。

## 本阶段不做

- 不启动付费 embedding 请求作为 CI 的一部分，不将密钥写入命令行、报告或 Git。
- 不引入 reranker、多 Agent、在线自动更新索引或大规模向量数据库；先根据本地小语料实测确认是否需要更复杂的存储后端。
- 不用合成集指标声称现实学术检索质量提升；真实质量评估留给经人工复核的固定文献 qrels 与 P12。

## 实施顺序

1. 核验可用 embedding Provider 和模型的当前官方能力/成本，冻结候选模型及配置。
2. 冻结隔离的 `TEST-*` 小语料、查询、qrels 与哈希；保留现有 BM25 作为基线。
3. 实现 provider 契约、向量索引 lineage、Dense 与固定参数 Hybrid 检索。
4. 执行 mock 回归和离线同题评测，检查撤回/版本更新与隔离反例。
5. 交付模型决策、可复现报告、限制和实际验证结果；如需 live API smoke，另行显式运行。


## 实施结果（2026-09-23）

- 已实现 `text-embedding-3-small` 兼容的 OpenAI Embeddings HTTP Provider、bounded batching、结果维数/有限值校验、错误分类与可选费用估算。Provider 默认关闭；自动化测试使用 fake provider，不发起网络调用。
- Migration 0004 增加全文片段向量表。索引仅接受当前批准全文版本，模型/维度必须匹配；索引 CLI 可按来源过滤、最多处理 2000 个 chunks、批次最多 64 项，不打印正文或密钥。Dense 使用 cosine；Hybrid 使用固定 RRF k=60。API 和 Agent 默认 BM25，需显式选择 dense/hybrid。
- `TEST-P10-*` 合成评测仅测试融合与指标执行路径。当前 6 个文档、4 个 query 的小夹具中 Hit@1 均为 1.0；BM25 NDCG@10=0.936413，Dense/Hybrid NDCG@10=1.0。此结果由固定合成向量构造，必须按 `quality_claim_allowed=false` 解读，不是模型质量比较。
- 自动回归：79 passed，2 条第三方弃用提示。用户随后完成本机 live smoke：health readiness 为 ready/database sqlite_available/embedding configured；真实索引 18 chunks、1536 维、5782 input tokens，CLI 估算费用 USD 0.00011564。BM25、Dense、Hybrid API 均返回对应 retrieval_method，Dense/Hybrid 单次 query 各报告 12 input tokens、估算 USD 0.00000024。Agent 端到端请求 status=completed，调用 `retrieve_paper_evidence` 并返回论文引用。
- API 响应乱码检查：PowerShell `Invoke-RestMethod` 输出曾显示乱码；用 `Invoke-WebRequest -OutFile` 保存原始 JSON，再按 UTF-8 解析后，数据库片段与本地 `.txt` 对应范围比较为 `True`。原文和数据库均未损坏，无需重新导入或重建向量。
- 边界：真实检索 smoke 只覆盖 1 篇论文、18 chunks、1 条问题，验证功能/引用链路，不足以支持语义检索质量结论。合成结果仍标记 `quality_claim_allowed=false`；P05 qrels 人工复核仍是有质量结论的前置条件。实际账单以 OpenAI 用量记录为准。推荐模型依据及当时官方价格见 [OpenAI Embeddings 指南](https://developers.openai.com/api/docs/guides/embeddings)。
