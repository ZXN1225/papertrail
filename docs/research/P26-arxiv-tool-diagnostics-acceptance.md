# P26 arXiv 工具失败诊断与重复请求保护

日期：2026-09-25。状态：实现、自动化验收和用户本机 arXiv live smoke 均通过。

## 验收条件

- 工具错误 trace 只包含白名单格式的错误码，不输出异常正文、请求参数或敏感数据。
- 同一 Agent run 中，某来源工具失败后，该来源后续工具调用会被本地短路，不会再次访问来源 API。
- Agent 规则明确要求来源失败时停止重复请求，并说明回答来源不完整；前端 trace 显示可读错误码。
- 自动化测试验证 arXiv 连接失败、重复请求短路、异常脱敏和错误码 UI。

## 实施与结果

- 后端 `AgentTraceEvent` 增加可空 `error_code`；Harness 使用安全错误码并在 warnings 中提供诊断。原始异常消息仍不进入响应。
- Harness 按来源记录失败状态；该来源后续工具调用返回 `source_unavailable_after_failure`，不再外呼。
- Agent 指令要求每个请求来源至多调用一次，来源报错后标注不可用，并将其他来源的结果标为部分结果。
- Web 运行记录将错误码与 `error` 状态一起显示。
- 后端全量测试 114 passed；故障注入验证 arXiv 同一轮中不同参数的后续请求也不会再外呼，trace 分别显示 `arxiv_unavailable` 和 `source_unavailable_after_failure`，异常正文不泄漏。

## Live 网络诊断

故障定位时，`http://127.0.0.1:8001/api/v1/arxiv/search` 对 arXiv 返回 `arxiv_unavailable`。同一项目 `ArxivClient` 使用 `submittedDate` 年份查询，在允许出站网络的测试进程中成功获得结果。因此查询构造与客户端路径可用；当时运行的本机后端进程遇到出站网络访问失败。本阶段代码改善错误可见性与避免重试，不能为受限进程授予网络权限。

用户按下方说明从本机 PowerShell 重启后端后，确认 arXiv 检索成功；截图显示 OpenAlex 与 arXiv 的结果均列出，状态为已完成。本机 live smoke 通过。

本机复验时，在后端运行终端按 Ctrl+C 停止后端，再从正常 Windows PowerShell（可访问 arXiv 的网络环境）启动：

```powershell
cd D:\Coding\Computer_Recommand\backend
uv run --locked python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

在 PaperTrail 搜索页用 arXiv 来源执行一次查询。成功时运行记录应出现 `search_arxiv_metadata ok`；失败时应出现 `error · arxiv_unavailable` 或其他安全原因码。同一 Agent run 内 arXiv 首次失败后，后续 arXiv 工具调用应显示 `source_unavailable_after_failure`，且不会再次访问 arXiv。

## 限制

- 本阶段没有改动 API 查询语义、节流策略或 arXiv 服务端；不会绕过本机网络策略。
- 后端全量测试 114 passed（2 条上游弃用 warning）；Ruff check/format、OpenAPI 导出通过。Web Prettier、TypeScript 通过，E2E 15/15 通过三种视口运行。根 git diff --check 通过。未运行生产构建，以免与用户现有 Next dev 服务共享 .next 目录。
- 未调用真实 LLM、未导入全文、未读取/修改本机数据库或报告。
