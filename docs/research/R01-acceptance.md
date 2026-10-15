# R01：研究任务与隔离评测集

更新：2026-10-12。状态：synthetic 评测闭环通过；四篇许可论文合计 10 题已分别获得单人证据支持度核验，其中新增三篇六题同时标注了 PDF 可答性和指定来源。系统输出盲评、不可答题与独立 holdout 仍待补。

## 当前真实语料与任务集状态（2026-10-14）

- 当前活动全文为 9 篇许可白名单 PDF、217 页。用户提供的第十篇 arXiv:2610.13595 是 CC BY-NC-SA 4.0，按现行 CC0/CC BY 白名单未导入全文；没有扩大许可政策。
- 旧单篇 4 题与新增三篇 6 题合计 10 个候选问题有单人 PDF 证据支持审核；六题系统对照的五组所选回答获用户核对。它们是小样本，不是独立真实 holdout 或双人金标。
- 路线图 10–12 篇/约 40 题、不可答任务和按文档/主题隔离的真实 held-out split 尚未实现。v26 的 16 个 PDF 结构标签另待用户逐项提交，不计为 R01 任务答案金标。

## Synthetic regression fixture

- 数据集：`TEST-research-task-lexical-v2`，版本 2，SHA-256 `ace44db91c3fd45948a5113a785ea22141d3931d7faf74b44f71e157d8c01ebd`。
- 12 个 `TEST-*` synthetic 文档按文档 ID 分为互斥 dev/test，各 6 篇；每项任务的证据/关联文档必须与任务 split 一致，防止同一文档跨 split 泄漏。
- 全量 40 题（24 可答/16 不可答）；dev 21 题（12/9），test 19 题（12/7）。CLI 支持 `--split all|dev|test`，分别过滤任务和候选文档，并报告分母。
- 锁定词面 runner 的 all/dev/test 三次实际运行均完成；各自命中率和可答性准确率为 100%。这是人工设计、同分布的 synthetic fixture，不能证明现实论文检索质量或模型表现，也不是独立人审 holdout 或金标准。
- 2026-10-11 在当前工作树重跑 `all/dev/test` 三种 split：all 为 40/40、dev 为 21/21、test 为 19/19 answerability accuracy；证据 Hit@1 与 Hit@3 分别为 24/24、12/12、12/12。三份本机报告写入 Git 忽略目录 `backend/reports/audit-research-{all,dev,test}.json`。数据哈希仍为上述固定值，三份报告均标记 `quality_claim_allowed=false`；这些值只证明合成 runner 可重现。
- 保留 v1 unsplit fixture 的 `--split all` 兼容；旧格式不能请求 dev/test，以免误把全语料报告标成留出集。
- split/leakage/legacy 兼容测试 15 passed；R01/R03 验收当时全后端为 176 passed；本轮新增评估/Harness 回归后全量为 184 passed，1 个上游弃用 warning。

重跑示例（在 `backend/` 目录）：

```powershell
uv run --locked python -m app.cli.evaluate_research_tasks --split all --output reports/TEST-all.json
uv run --locked python -m app.cli.evaluate_research_tasks --split dev --output reports/TEST-dev.json
uv run --locked python -m app.cli.evaluate_research_tasks --split test --output reports/TEST-test.json
```

## 待补工作

- 已新增三篇逐篇许可的 arXiv PDF；旧单篇 4 题用户标签见 [R03 人工核验包](R03-user-evidence-review-pack.md) 与 [机器可读审阅记录](R03-human-evidence-review-arxiv-2608.20519-v1.json)。新的 [六题候选记录](R01-R03-real-evidence-pilot-v1.json) 在人审前已冻结，用户后续标签见 [审阅记录](R01-R03-real-evidence-pilot-human-review-v1.json) 与 [描述性结果](R01-R03-real-evidence-pilot-result.md)。六题均可答，候选支持/不支持各 3；助手预先指定证据的 BM25 前 8 条命中 4/6，R1/R4 未命中。候选不是系统生成答案，检索结果也不是全部相关性金标。四篇十题均为单人小样本，不足以声称总体 RAG 性能；后续需增加不可答题、独立编题与复核任务集。
- 真实文档与 synthetic corpus 的索引、向量和评测结果需继续隔离；对后续论文仍须逐篇核对许可并经 manifest 预检后才可导入。
