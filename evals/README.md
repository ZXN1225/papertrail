# 评测计划

初始目标至少 120 独立场景：PC 20、笔记本 20、兼容 25、规格/比较 15、多轮 15、缺失/过期/无解 15、注入/权限 10；另建不参与调参的保留集。当前人工审核金标场景数仍为 0。

`datasets/synthetic-safety-v1.json` 的 10 条 `TEST-GOLD-*` 项仅用于验证失败语义与发布阻塞，不能计入 120 条人工金标。运行 `python evals/validate_dataset.py evals/datasets/synthetic-safety-v1.json` 校验夹具元数据；运行 `python scripts/release_preflight.py` 查看当前发布阻塞。后者预期以退出码 2 结束，直到所有生产前置条件真实满足。

每条保存 case_id、profile/messages、snapshot_id、expected_constraints、valid_candidate_predicate、required_evidence、forbidden_claims、expected_route/status。允许多种正确推荐，不以唯一 SKU 为答案。金标由证据独立标注，不由被测业务代码生成。

## T19 可复现检索基线

`datasets/synthetic-retrieval-v1.json` 是隔离的 TEST-only 小型检索金标，用于验证指标实现、排序对照和报告格式，不代表真实市场、生产知识库或 Agent 质量。运行：

```powershell
python evals/run_retrieval_eval.py evals/datasets/synthetic-retrieval-v1.json --method overlap --k 3
python evals/run_retrieval_eval.py evals/datasets/synthetic-retrieval-v1.json --method bm25 --k 3
python -m unittest evals/test_retrieval_metrics.py
```

报告包含 Hit@k、MRR@k、NDCG@k、查询均值/P95 延迟、数据集 SHA-256、方法和限制。只有在独立人工金标、保留集、固定环境和足够样本完成后，才能把这些指标用于项目质量结论。

## T20 多桶对照与 Agent 工具策略

运行 24 条多桶检索集的词面 overlap、BM25 和 RRF(overlap+BM25) 对照，并可写出 JSON 报告：

```powershell
uv run --directory backend --frozen python ../evals/run_retrieval_eval.py ../evals/datasets/synthetic-retrieval-v2.json --k 5 --output ../evals/reports/synthetic-retrieval-v2.json
uv run --directory backend --frozen python ../evals/run_agent_policy_eval.py ../evals/datasets/synthetic-agent-policy-v1.json --output ../evals/reports/synthetic-agent-policy-v1.json
uv run --directory backend --frozen python -m unittest discover -s ../evals -p "test_*.py"
```

Agent 策略结果仅表示固定工具名和参数 Schema 的接受/拒绝情况，不调用 LLM，也不执行工具。Provider 仍 disabled，禁止把策略准确率表述为 Agent 任务成功率。

本轮 24 条 synthetic 查询在 k=5 下三种方法 Hit@5 均为 1.0、MRR@5 均为 0.951389；NDCG@5 为 overlap 0.949384、BM25 0.938008、RRF 0.950099。RRF 相比 overlap 的差异很小，而且两个通道都是词面检索，不构成独立检索证据；当前保留 BM25/overlap 作为简单基线，不据此宣称 RRF 有质量收益。12 条工具契约场景全部符合预期（3 条接受、9 条拒绝）。样本规模与人工合成标签不足以支持质量外推，延迟只作本机微基准记录。

关键反例：预算超 1 分；漏运费；BIOS 未知；GPU 尺寸超限；PSU 连接器不足；同系列屏幕混用；套装条数；过期报价；跨会话访问；旧 revision 晚到；坏批导入；LLM 超时；提示注入。

报告记录提交、数据/规则/评分/模型/提示词版本、时钟、种子、成本、样本数、分母与限制。付费模型评测单独触发；未来向量/重排/多 Agent 与相同预算基线比较。验收阈值见执行计划和原规格 §16。
