# T21 OpenAI Provider 接入与本机联调验收

更新：2026-09-22。目标是在保持模型默认关闭的前提下，支持用户自备 OpenAI API Key，在本机通过现有 Harness 调用 GPT 并执行受限工具。

## 验收条件

1. `LLM_PROVIDER` 只允许 `disabled` 或 `openai`；默认 `disabled`。启用时必须校验 API Key 与模型名，Key 使用 SecretStr 且错误/日志不得泄露密钥或完整模型上下文。
2. OpenAI Responses API 仅接收本轮用户需求、服务端保存画像、先前结构化工具观察和服务端生成的工具 Schema；响应经服务端解析为既有 AgentDecision。
3. 仅暴露 ToolRegistry 中白名单工具；模型不得指定额外工具、SQL、shell、URL、预算或发布操作。每次模型响应最多执行一个工具调用，保持 Harness 回合、调用、时间与观察截断上限。
4. 请求设输出 Token 上限、超时和 `store=false`；Provider 故障须清理成稳定错误状态，不把供应商错误正文传给用户。
5. 增加无网络的 Provider 映射、Schema/禁用状态与故障处理测试；CI 和默认本地配置不要求 API Key。
6. 更新本机配置和手工联调指南；真实 GPT 请求仅在用户自行保存 Key 并启动时发生。本轮没有 Key 时不伪称真实 API 已验证。

## 本轮不包括

- 生产 Key、真实电脑资料或用户个人数据；测试仅使用 synthetic/TEST 资料。
- 付费模型批量质量评估、自动评分、生产发布和部署。
- 依赖 ChatGPT 订阅提供 API 额度；API 平台计费独立。

## 用户可手动联调的完成定义

用户在本机 `.env` 配置 `LLM_PROVIDER=openai`、`LLM_API_KEY` 与可用 `LLM_MODEL`，本机完成项目启动和测试数据库迁移后，从现有 Agent 页面发起请求；至少观察到一次 GPT 工具决策、服务端执行 TEST 工具并返回结构化结果。测试报告需保留数据集哈希、模型 ID、日期、延迟/调用量、预期与实际结果；不含 API Key。
