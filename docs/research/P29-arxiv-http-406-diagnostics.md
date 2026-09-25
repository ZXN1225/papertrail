# P29 arXiv HTTPX 406 诊断与验收

日期：2026-09-25。状态：用户已在本机确认 arXiv 搜索成功。

## 观测

- 用户本机 HTTPX 0.28.1 的调试日志显示请求已到 `export.arxiv.org`，上游明确返回 `HTTP/1.1 406 Not Acceptable`；PaperTrail 原先将该响应映射为 `arxiv_unavailable`，本地 API 返回 502。
- 对同一搜索 URL、相同 `Accept: application/atom+xml` 与 `User-Agent: Python/<runtime version>`，PowerShell `Invoke-WebRequest` 和 Python `urllib` 均返回 HTTP 200。
- `urllib` 默认的 `Accept-Encoding` 为 `identity`；HTTPX 默认广告其支持的压缩编码。由此推测 HTTPX 的压缩协商与网关 406 有关，但尚未通过真实 HTTPX identity 请求验证。

## 实施

- `ArxivClient` 显式设置 `Accept-Encoding: identity`，其余查询、User-Agent、节流与响应解析保持原有行为。
- 新增客户端 mock 测试，确保 HTTPX 发出的请求保留该 header。

## 当前验证

- `tests/test_arxiv_client.py`：8 passed。
- 两个修改文件的 Ruff check 与 format check 通过。
- 未在此环境访问 arXiv 网络；mock 测试不能证明上游接受该请求。

## 用户本机验收

1. 停止旧后端并启动当前工作树版本。
2. 等待至少 3 秒后，在 PaperTrail 发起一次 arXiv 搜索。
3. 成功标准：页面返回 arXiv 结果，后端日志中请求为 200；若仍失败，请运行项目 Python 客户端一次并提供 HTTPX `INFO:httpx` 状态行。

arXiv 的 legacy API 要求所有受控机器合计每三秒最多一次请求、同时仅一个连接。测试失败后不要连续点击重试。

用户随后确认 arXiv 搜索成功，P29 live 验收通过。
