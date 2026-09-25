# P23 验收：离线引用图工作流基准

## 目标

把用户已在本机验收的 OpenAlex 种子检索与一跳引用拓展纳入可复现的 P12 离线 Agent benchmark，确认生产 `AgentHarness` 能保留种子/候选引用、年份及双向关系来源，并拒绝把引用元数据夸大成论文结论。

## 验收标准

- [x] 新增一个 P12 Agent 场景，使用真实 Harness 与受控模型/工具 mock，按“OpenAlex 主题发现 → `both` 方向引用拓展 → 有界元数据回答”执行。
- [x] 夹具仅含 `TEST-*` 标题/夹具键并标记 `synthetic=true`；由于生产 Citation schema 要求合法 OpenAlex ID，使用 `W900`/`W901` 形状标识，明确声明不是实际作品且不读取真实索引。
- [x] 断言 Agent 仅引用本轮工具观察过的作品；年份和 `references`/`cited_by` 关系及种子 ID 被保留；候选仅出现一次；答案将关系限定为发现元数据，不声称论文相互支持/反驳。
- [x] P12 报告含该场景可审阅的确定性摘要；无真实网络/数据库/模型，`synthetic=true`、`quality_claim_allowed=false` 和费用未测量保持不变。
- [x] 重复运行时该场景结果字段稳定；仅运行耗时等运行观察字段允许变化。CLI 退出码要求所有场景通过。
- [x] 更新 P12/P23 验收记录、README、TASKS、PROGRESS；不修改用户数据库或既有报告，不调用外部 API/模型，不提交全文、密钥或本机缓存。
- [x] 后端 Ruff check/format、全量 pytest、OpenAPI 导出、根 `git diff --check` 通过；当时未运行的项目检查已注明。

## 当前状态

验收条件先于实现记录。本阶段已完成（2026-09-25）。详见 P23 与 P24 执行记录。
