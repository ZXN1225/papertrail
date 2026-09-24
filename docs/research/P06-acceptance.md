# P06 验收记录：受限 Agent Harness 与引用契约

日期：2026-09-23。分支：`codex/paper-research-agent`。

## 验收标准

- 固定只读工具白名单，参数由严格 JSON Schema/Pydantic 校验；不得提供任意 URL、文件、SQL、shell、写操作或来源抓取工具。
- Harness 限制模型轮数、工具调用次数、观察大小和总运行时间；未知工具、畸形 JSON 与超预算行为安全失败。
- OpenAI 适配器使用官方 Responses API function calling；模型 Key 仅在服务端；structured final answer 匹配 schema。
- 所有引用只能来自本轮成功执行工具输出中的 OpenAlex ID/source URL；未知引用不能透传为已核验事实。
- 文档元数据/摘要明确作为不可信文本提供给模型，提示注入文本不改变工具权限。
- 未配置模型、上游失败、全文检索未实现、搜索无结果和无证据问题返回可辨认状态，不伪造回答或论文证据。
- 自动化测试全部通过假模型与 HTTP mock，不触发真实 OpenAI 费用；真实 API 烟测只在后续明确运行验证阶段执行。
- P05 qrels 保持 `assistant_seed_pending_human_review`，P06 只依赖已实现的 BM25 baseline，不会借由 Agent 测试把其提升为人工金标。
- 完成本阶段后更新任务、进度与演示说明，精确暂存文件；不提交/推送，也不删除旧电脑代码/分支。

## 验收结果

- [x] 5 个固定只读工具，严格 schema + Pydantic 参数校验；工具不提供 URL/shell/SQL/文件访问。
- [x] Harness 默认 4 轮、8 次 tool call、45 秒总时限；有界 observation 和安全预算错误状态。
- [x] 固定官方 Responses API + `store=false`、单次顺序工具调用、严格函数 schema、结构化最终输出；API Key 仅置于 server Authorization header。
- [x] citation allow-list 根据已成功工具观察生成；未检索 ID 与答案文本内未经列表确认的 Work ID 被拒绝；无引用时不展示 unsupported model text。
- [x] system instructions 将论文 title/abstract 标记为不可信数据；工具结果不具备权限提升路径。
- [x] mock 测试覆盖 allowlist/参数错误、搜索、详情、compare 参数、全文 unavailable、工具 budget、max steps、deadline、模型错误/拒答、损坏答案、重复 call ID、引用验证、Responses payload/HTTP 错误和 API disabled。
- [x] 后端 47 passed；ruff check/format check 通过。只出现 2 条 Starlette/httpx 上游弃用提示。
- [x] OpenAI Key 未调用；LLM 默认保持 disabled。P05 qrels 仍是待人工复核，不包装成 gold。
