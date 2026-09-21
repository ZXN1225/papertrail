# 评测计划（待建立数据集）

初始目标至少 120 独立场景：PC 20、笔记本 20、兼容 25、规格/比较 15、多轮 15、缺失/过期/无解 15、注入/权限 10；另建不参与调参的保留集。当前人工审核金标场景数仍为 0。

`datasets/synthetic-safety-v1.json` 的 10 条 `TEST-GOLD-*` 项仅用于验证失败语义与发布阻塞，不能计入 120 条人工金标。运行 `python evals/validate_dataset.py evals/datasets/synthetic-safety-v1.json` 校验夹具元数据；运行 `python scripts/release_preflight.py` 查看当前发布阻塞。后者预期以退出码 2 结束，直到所有生产前置条件真实满足。

每条保存 case_id、profile/messages、snapshot_id、expected_constraints、valid_candidate_predicate、required_evidence、forbidden_claims、expected_route/status。允许多种正确推荐，不以唯一 SKU 为答案。金标由证据独立标注，不由被测业务代码生成。

关键反例：预算超 1 分；漏运费；BIOS 未知；GPU 尺寸超限；PSU 连接器不足；同系列屏幕混用；套装条数；过期报价；跨会话访问；旧 revision 晚到；坏批导入；LLM 超时；提示注入。

报告记录提交、数据/规则/评分/模型/提示词版本、时钟、种子、成本、样本数、分母与限制。付费模型评测单独触发；未来向量/重排/多 Agent 与相同预算基线比较。验收阈值见执行计划和原规格 §16。
