# P05 验收记录：BM25 基线与人工检索金标

日期：2026-09-23；人审复评更新：2026-09-24。分支：`codex/paper-research-agent`。

## 验收标准

- 对冻结 OpenAlex 本地快照实现确定性、只读 BM25 排序；默认 Okapi 参数、分词规则与语料范围有版本记录。
- 查询与 qrels 使用稳定 ID；相关性等级由人工标注，数据集明确记录人工判定范围、数据快照 ID、内容哈希和 corpus size。
- 金标只引用已导入、可追溯的真实 OpenAlex work ID；不可把 `TEST-*` 或 `synthetic=true` 数据混入本轮质量报告。
- 实现 Hit@k、MRR@k、NDCG@k、分桶宏平均、查询均值/P95 延迟、空结果率；明确无相关判断查询的计分约定。
- CLI 可从固定 manifest 重复生成 JSON 报告；报告写出评测集哈希、语料版本、模型/分词器参数、运行时间和配置，不提交动态运行报告。
- 测试覆盖分词（中英文）、得分与 tie-break 稳定性、指标边界、未知文献 ID、无检索结果和重复运行确定性。
- 不调用 OpenAI、不运行 embeddings、不下载全文；禁止将 10 条小语料或当前少量人工标注包装成检索质量结论。
- 完成本轮后更新进度与台账，精确暂存 P05 代码/文档；旧电脑项目文件及分支仍保留，直到通用 Agent/Harness 迁移经验证。

## 评测范围声明

P05 最初建立 benchmark 草案和可复现 BM25 baseline，使用 8 个 query / 10 篇文献。候选 qrels 后续由用户逐项复核，形成 `p05_human_reviewed_v2.json`，因此本项目有一份小规模 human-reviewed 评测集。由于规模仍只有 8 queries / 10 papers，报告保持 `exploratory_only=true`，不支持统计泛化或对外检索质量承诺。P13/P14 的 3,000 对则仍是助手候选分数，未人工核验，与 P05 v2 明确分开。

## 当前实现验收结果

- [x] 确定性 Okapi BM25 和版本化英语/CJK tokenizer 已实现，无新增运行时依赖。
- [x] 报告绑定完整 OpenAlex work ID、冻结快照与每篇 metadata hash；数据变化或缺快照时拒绝评测。
- [x] Hit@k、MRR@10、NDCG@k、分桶宏平均、平均/P95 延迟与空结果率均已实现。
- [x] 本机 CLI 已运行：10 篇、8 个查询；每项实验 `exploratory_only=true`，qrels 待人工复核。
- [x] 测试覆盖分词、并列排序、分级指标、空排名、语料哈希漂移；后端 `36 passed`，ruff 通过。
- [x] 用户导入 80 项人审 qrels，生成 v2 数据集；复核清单见 [P05 qrels 复核](P05-qrels-review.md)。
- [x] OpenAI、embedding 与全文下载均未调用；报告保存在本地忽略目录。

## 人审复评结果（2026-09-24）

- 使用 `backend/data/evaluation/p05_human_reviewed_v2.json` 重跑 BM25，并以原始候选数据集重跑对照；两份报告绑定同一个冻结语料快照、同一 10 篇文献和相同检索器配置。
- 两种标签的排名完全相同。Hit@1=0.75、MRR@10=0.875；人审标签下 NDCG@3=0.800794、NDCG@5=0.794560、NDCG@10=0.884906。相对候选标签 NDCG@10 增加 0.009012；这是标签变化造成的指标差，不代表排名器变好。
- 人审报告与候选对照报告分别位于被 Git 忽略的 `backend/reports/p05-human-reviewed-bm25-report.json` 和 `backend/reports/p05-candidate-bm25-report.json`。人审数据集哈希为 `9f15ae00e7f7bc4479b9cff79e06741b0801431e4e58c25565970096f66c5f2f`。
- `exploratory_only=true` 仍成立，因为 benchmark 只有 8 个 query 和 10 篇论文；这只是流程验收与小语料探索结果，不可泛化为检索质量声明。
