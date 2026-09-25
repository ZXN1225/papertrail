# P22 Agent 结构化终答恢复验收

## 问题

本机实际调用偶发返回 `invalid_model_output`，通常表示模型的终答未通过 `FinalAnswer` JSON 契约，整轮结果因此被安全拒绝。自动重试必须受严格预算约束，且不能绕过原有来源引用核验。

## 验收条件

- 若终答 JSON/schema 无效且仍有 `AGENT_MAX_STEPS` 预算，只允许增加一次格式修复模型轮次。
- 修复请求不得调用工具、不得引入新事实；仅使用本轮已收集的 observations，无法回答时按契约返回证据不足。
- 修复答案仍通过原 `FinalAnswer` schema 和引用 allow-list 校验；无效/伪造引用继续拒绝。
- 没有剩余步数时不超预算；一次修复仍失败时返回 `invalid_model_output`，trace/warnings 仅显示安全状态，不泄露模型原文或异常。
- 合成测试覆盖修复成功、修复失败和预算耗尽；无真实模型/来源 API 调用。

## 实施与验证

- Harness 只在终答 JSON/schema 校验失败且剩余模型步数大于零时追加一次格式修复轮次；不把失败的模型正文回灌给模型，只追加固定修复指令和既有工具 observations。
- 修复轮次不提供工具定义；若模型仍返回工具调用，服务端拒绝且不执行。修复终答再次使用原 `FinalAnswer` 和引用账本校验；修复失败不会放宽验证。
- warning 区分修复已尝试、修复失败、剩余预算不足和修复轮次要求工具；不返回模型原始内容。
- 合成回归覆盖修复后成功、第二次格式错误仍拒绝、轮数耗尽不重试、修复轮试图调用工具时不执行。
- `uv run --locked ruff check .` 与 `uv run --locked ruff format --check .`：通过。
- `uv run --locked python -m pytest -q`：109 passed；仅有 Starlette/httpx 上游弃用提示。
- 无真实模型、OpenAlex 或 embedding API 调用；无需 OpenAPI 或数据库迁移。
