# R05：只读 MCP Server 验收

日期：2026-10-11。此记录覆盖 MCP SDK 协议和工具边界，不代表已连接所有桌面 Host。

## 实现与边界

- 使用锁定的 MCP Python SDK，通过 stdio 提供固定注册的只读 PaperTrail 工具；不开放任意 URL、shell、SQL、文件读取或写库工具。
- MCP 进程通过 SQLite URI `mode=ro` 打开目录库。目录库必须已存在且处于当前 migration 版本；MCP 不创建目录/数据库，也不自动运行迁移。更新数据库请先用 PaperTrail 后端正常执行迁移，再启动 Host。
- MCP 进程只读取 `DATA_STORAGE_PATH` 环境变量来定位数据库，不加载 Agent/Embedding provider 配置，也不需要把 API key 传给 MCP Host。应用默认数据库为仓库根目录 `data/papertrail.sqlite3`；MCP 未设置变量时按 backend 相对路径解析，因此 Cursor 配置必须显式传入本机数据库的绝对路径。
- 全文检索 schema 限为当前真实可用的 BM25 能力，不把未配置 embedding 的 Dense/Hybrid 伪装为可用工具。
- 工具错误、embedding 不可用/错误和索引缺失均映射为 MCP error 结果，防止客户端把失败当作成功答案。

## 自动验收

- 使用官方 SDK Client 连接 server 对象验证协议。
- 启动真实 stdio 子进程执行客户端交互。
- 注入检索错误状态并断言协议结果为 `isError`。
- MCP 定向协议、错误映射与 stdio 子进程测试通过。新增只读存储用例验证缺失数据库不会被创建、旧版 schema 不会被迁移、SQLite 引擎拒绝写操作；覆盖绝对与相对 `DATA_STORAGE_PATH`；只读存储 + MCP 定向组 `29 passed`；本轮后端全量回归 `192 passed`，1 个 Starlette/AnyIO 上游弃用 warning。

## Cursor 本地 Host 手工 smoke 指引

Cursor 支持在全局 `~/.cursor/mcp.json` 或项目 `.cursor/mcp.json` 配置 stdio MCP server。建议放在用户全局配置，避免把机器路径或本机数据目录写进项目仓库。参见 [Cursor MCP 官方文档](https://docs.cursor.com/context/model-context-protocol)。

Windows 配置示例；将 `<REPO_ROOT>` 替换为 PaperTrail 本机绝对路径，将数据库路径替换为已由 PaperTrail 初始化并迁移过的 SQLite 文件：

```json
{
  "mcpServers": {
    "papertrail": {
    "command": "uv",
    "args": ["run", "--offline", "--locked", "--project", "<REPO_ROOT>\\backend", "python", "-m", "app.mcp_server"],
      "env": {
        "PYTHONPATH": "<REPO_ROOT>\\backend",
        "DATA_STORAGE_PATH": "<REPO_ROOT>\\data\\papertrail.sqlite3"
      }
    }
  }
}
```

配置后重启 Cursor，在 MCP 工具列表中确认出现 5 个 PaperTrail 工具；调用 `search_papers`，空库返回 `no_results` 也代表协议链路已通。需要验证全文工具时，使用已有获准数据调用 `retrieve_paper_evidence` 并核对返回的论文 ID、许可字段、chunk ID 与 locator。MCP Host 的 AI 对话调用可能使用 Host 自己的模型/额度，不属于 PaperTrail MCP server 的测试成本。

2026-10-12：用户提供桌面 Host 截图，`papertrail` 显示绿色连接状态并列出 5 个 enabled tools，注册/工具发现通过。随后用户通过该 Host 实际调用 `retrieve_paper_evidence`，状态 `ok`，返回 arXiv `2608.20519`，许可 `CC-BY-4.0`，`scanned_chunks=209`、`truncated=false`、检索方法 `bm25_fulltext_v1`。前三条结果定位到第 20 页 Table 3 段落、第 19 页结果段落和第 20 页 Table 3 表格；表格结构化数据保留 `Dimension | Physicist | Physician | Pooled` 列序及对应值（临床推理 5.00、4.22、4.61；总体 4.78、4.52、4.65），与用户先前对 E4 的人工判断一致。首条 paragraph 的 `expanded_evidence` 同时携带关联表格 chunk；来源、CC BY 4.0 许可与页/节/表格定位均完整。此次实际调用由用户发起，项目未承担 Host 模型额度。

质量边界：该结果验证了一个 Host、一个许可论文、一次 BM25 查询的协议接入、来源溯源及结构化表格检索链路，不构成通用检索准确率或 LLM 回答质量证明。返回仍带有 `sparse_table_candidates_rejected`（第 18、19 页）解析告警；命中 Table 3 本身未带 element warning。保留该限制供 R02/R08 质量总结使用。

## 未覆盖

- 未确认截图所示 Host 的产品名称/版本；本记录只称“用户桌面 Host”。
- 未在其他 Host 上重复验证，也未验证重启后的持久连接行为。
- 未将一次查询结果用作总体 retrieval benchmark；BM25 排名和其他查询仍需独立评估。
- 解析告警、复杂表格语义与 OCR 能力仍按 R02/R08 的限制记录。
