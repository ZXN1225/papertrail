# T12 验收（实施前固定）

步骤 13 实现单 Agent 的受限工具协议、Harness 和默认禁用的模型适配边界；不实现知识库、SSE、取消或自然语言回答契约。

- 模型只能选择白名单中的 `search_catalog`、`get_product_facts`、`get_offers`、`rank_laptops`、`solve_pc_builds` 与 `check_compatibility`。没有 SQL、shell、任意 URL、导入发布或快照写入工具。
- 每个工具先由 Pydantic 校验，调用现有目录、推荐或兼容性领域服务。笔记本和 PC 求解从已保存画像读取预算、地区、品牌限制和 Wi-Fi 要求，模型参数不能覆盖这些硬约束。
- Harness 只接受服务端所有者可读的精确画像 revision。默认最多 4 个决策回合、8 次工具调用、45 秒总时限；读取按规范化工具名和参数在一次运行内去重。所有 Provider 观察均转换为有界 JSON。
- 截至 T12 验收时，默认 `llm_provider=disabled` 返回 `provider_disabled/MODEL_DISABLED`，不执行工具、不伪造回答。脚本化 Provider 仅用于测试；OpenAI HTTP 配置由后续 T21 单独验收。
- `POST /api/v1/agent/preview` 复用现有会话、CSRF、Origin、体积限制和限流。它只返回结构化运行/观察结果，不保存会话运行或输出最终自然语言答案。
- 测试覆盖禁用降级、工具读取去重、工具预算、JSON 观察规范化；真实 PG 环境覆盖会话所有权和 HTTP 契约。
