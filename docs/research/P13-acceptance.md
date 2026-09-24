# P13 验收：扩展论文检索评测集与 AI 标注诊断

## 目标

将 P05 从 8 个查询 / 10 篇论文扩展到 30 个研究查询 / 100 篇 OpenAlex Works 元数据。用户选择不逐项人工审核，因此交付为 AI 候选分数填充副本和探索性 BM25 诊断；不构造人工金标。OpenAlex 元数据按 CC0 记录；本阶段不下载或索引全文，不调用 OpenAI。

## 验收标准

- [x] OpenAlex Works 单页导入安全上限调整至官方当前支持的 100；SQLite 对既有数据库通过新迁移扩展约束，历史迁移文件不修改。
- [x] 新冻结语料包含 100 个唯一 Work ID，全部来自同一完整导入快照；记录查询、抓取时间、许可标识和逐条内容哈希。
- [x] 新版数据集包含 30 个查询、14 个研究意图桶，ID 唯一，均为自然语言问题而非论文标题复写。
- [x] 与 P05 v2 分离保存；3,000 个 query-paper pair 完整覆盖。原候选集状态为 `assistant_seed_pending_human_review`。
- [x] 原复核包仍完整保留且 3,000 项均为 `reviewed=false`。另生成 AI 填分副本 `backend/reports/p13-ai-labeled-pack.json`；3000 个 `reviewed_grade` 已复制候选 `suggested_grade`，但 `reviewed` 仍为 false，并注明未人工核验。
- [x] 新评测数据 `backend/data/evaluation/p13_ai_labeled_v1.json` 将状态标为 `assistant_labeled`，来源哈希绑定原候选集；报告措辞明确 qrels 为助手生成且未人工核验。
- [x] AI 标注副本 BM25 报告 `backend/reports/p13-ai-labeled-bm25-report.json` 绑定数据集哈希、语料快照和 BM25 配置，`exploratory_only=true`。指标只描述该候选标签下的离线诊断，不表示标签正确性或检索质量。
- [x] 后端 96 项测试、Ruff、OpenAPI 生成通过。基础/来源登记/diff 检查在阶段结束前复核。

## 当前数据快照

- 查询：`retrieval augmented generation`；单页 100 条，OpenAlex API 记录为 CC0-1.0。
- snapshot ID：`f7f7267d-78fa-4364-b5ca-0305986f1e89`；快照 SHA-256：`5fc1638778f37a26c9d0f9f6de2e66b576a3746576b948000744da975eefdf22`。
- 数据集：`backend/data/evaluation/p13_rag_retrieval_v1.json`；SHA-256：`c84a60720a43001717141dd5b139857e09a2cc8d634d24eef1621c662a335b3a`。
- 共 3,000 条候选判断，其中 127 条为非零候选。原始人审包 `reviewed=true` 数为 0；用户已决定放弃人工全审，后续仅使用明确标记的 AI 诊断副本。
- 候选报告位于 `backend/reports/p13-candidate-bm25-report.json`。它只用于检查数据/评测管线，不应作为检索器质量声明。

## 标注分布与边界

- 批量填分完全复制候选建议，不额外声称逐条进行了新的语义判定。分布：0 分 2,873，1 分 31，2 分 47，3 分 49。
- 原候选数据集与原人工复核包未改写。AI 副本的 `human_reviewed=false`，无项目被记为人工审核。
- AI 标注数据用于复现管线和探索错误/排名模式；不得命名或宣传为 gold、人工标注或质量改进证据。若要可信质量结论，仍需独立人工标注或其他外部评估。
- 本轮使用现存 SQLite 快照重跑本地 BM25，不下载全文、不调用 OpenAI。
