# P07 验收：OpenAlex 研究 API 与 Agent Harness 可观测性

## 验收范围

- 研究用 OpenAlex 能力仅暴露官方固定 host 的只读 Works/Authors 操作：Works 搜索与精确详情、作者搜索与详情、作者作品分页；作品保留引用数和有界参考作品 ID。
- 请求有查询长度、分页深度和页大小限制；ID 经过实体类型校验；只请求显式字段；Key 只经 Authorization Bearer 发送；上游错误不透传响应体。
- API 能由后端路由直接调用，也能由 Agent 的严格函数工具调用。Agent 工具注册为本地 5 项 + OpenAlex 5 项；未提供 API client 时不会向模型暴露不可执行工具。
- Agent 响应附 run ID、总耗时和顺序化脱敏 trace；trace 只含 model/tool 名称、状态、耗时与 token 数，禁止 prompt、arguments、论文文本、Key 和 raw exception。
- 原有回合、工具调用、观察大小、超时、严格 schema、引用 allow-list 和拒答边界继续生效。

## 实现

- 新增 OpenAlex 单篇作品、作者搜索/详情、作者作品列表方法与 `/api/v1/openalex/...` 路由。
- 新增 5 个有界 OpenAlex Agent 工具，并与本地 BM25/详情/比较/全文 unavailable 工具合并；线上 API 客户端每次 Agent 请求总超时 4 秒、不做内部重试，使 Harness deadline 可控。
- 加入 OpenAlex Work 参考作品 ID 字段；摘要与引用关系仍是元数据，不能据此声称读取了论文全文或验证研究结论。
- Agent 返回可供 UI 和后续离线评测使用的脱敏运行 trace；当前 trace 只在响应中返回，尚未持久化、导出 OpenTelemetry 或提供管理仪表盘。

## 验证结果

- OpenAlex mock 覆盖固定域名、Bearer 头、Works 搜索/详情、Authors 搜索/详情、作者作品过滤、ID path traversal 反例。
- Agent mock 覆盖 OpenAlex 工具注册、调用、论文引用采集和运行 trace 字段边界。
- `uv run --frozen ruff check .`：通过。
- `uv run --frozen ruff format --check .`：29 个文件格式通过。
- `uv run --frozen pytest -q`：51 passed；Starlette/httpx 与 anyio 上游 deprecation warning 2 条。
- 根 `python scripts/check_foundation.py`：通过；`git diff --check`：通过。
- 本轮未调用真实 OpenAlex API 或 OpenAI；无真实模型质量、实时额度或成本声明。

## 边界与后续

- 这覆盖论文检索工作流核心实体，不是 OpenAlex 全部实体/参数 API 的镜像。Search endpoint 支持当前简单 query；复杂 filter/facet/group-by/export 和 cursor 遍历不开放。
- OpenAlex API key 已由用户配置，但本轮只做 mock 验证。用户可在确认后单独安排一次小额 live smoke test。
- P05 qrels 仍是待人工复核的候选数据；Hit/MRR/NDCG 不能作为人工金标质量结论。
- 后续依次推进：P08 arXiv 与跨源去重；P09 授权全文 RAG；P10 embedding/hybrid 对照；P11 UI/E2E；P12 完整检索/RAG/Agent/工程指标评测。完整测试计划覆盖 Hit@k、MRR、NDCG、引用 precision/recall、证据支持/拒答、工具选择与参数、token/cost、p50/p95、超时/限流和红队反例。
