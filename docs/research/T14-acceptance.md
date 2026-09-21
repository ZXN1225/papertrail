# T14 验收：结构化 Agent 运行、SSE 与取消

## 验收目标

- Agent 对话、运行和事件均以当前匿名会话为所有者；跨会话读取统一不可见。
- 创建运行要求画像与对话 revision，并以 `client_request_id` 和规范化请求体哈希实现幂等；旧 revision 或不同内容复用请求标识返回 409。
- 回答只含工具观察导出的候选、引用、缺失字段和数据版本；模型未配置时没有虚构候选或购买结论。
- SSE 每个事件有递增 `event_id`、`run_id` 与 revision，支持 `Last-Event-ID` 回放，仅含可公开的友好摘要。
- 取消在服务端持久化，并在结果提交前复查取消状态，避免晚到结果覆盖取消状态。

## 实现证据

- `0007_agent_runs` 迁移创建 `agent_sessions`、`agent_runs`、`agent_events`，事件随对话删除级联清理。
- `/api/v1/agent/sessions`、运行创建/读取、SSE、取消和会话删除接口由 `AgentRunService` 共用同一会话所有权检查。
- `AgentRunService._answer` 只解析 `rank_laptops`、`solve_pc_builds` 和 `retrieve_knowledge` 的结构化数据；`ToolObservation` 不把供应商文本直接作为商品事实展示。
- 当前执行器为同步受控 Harness，默认 Provider 仍为 disabled；持久化 queued 状态为后续 worker 接管预留，不把它描述为异步模型服务。

## 本轮验证

- 后端 Ruff 检查、格式检查通过。
- `pytest -q`：82 passed、75 skipped；跳过项仍需要独立 `test_*` PostgreSQL/Redis 集成环境，不能视为完整集成验证。
- OpenAPI 导出、前端 API 类型生成、格式、类型检查和 production build 通过。
- 根目录基础检查、来源研究记录一致性检查和 `git diff --check` 通过；来源检查不证明来源授权。
