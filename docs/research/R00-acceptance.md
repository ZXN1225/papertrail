# R00：可复现基线与工程验收

日期：2026-10-11。所有命令在本机执行。CI workflow 的本地等价命令通过，但本轮没有提交变更，不能触发或声称 GitHub Actions 通过。

## 环境与结果

| 验收项 | 环境/命令 | 结果 |
|---|---|---|
| 后端全新安装 | Python 3.12.4；隔离目录 `.uv-clean-check`；`uv sync --locked`；无需开发机既有虚拟环境 | uv.lock 解析 78 packages；运行/开发/审计依赖安装成功 |
| 后端测试 | uv.lock 全新隔离环境 `.uv-final-check` 执行 `python -m pytest tests -q --basetemp=.pytest-goal-final-176` | 176 passed；1 个 Starlette/AnyIO 上游弃用 warning |
| 后端静态检查 | 隔离环境 `python -m ruff check backend`、`python -m ruff format --check backend` | 通过；72 files already formatted |
| OpenAPI | 隔离环境 `python -m tools.export_openapi` | 成功；SHA-256 `7209e09b73230c9728fdba5dfec412a9c55ac156757158fffd4152476afbcef3` |
| 服务启动 | 隔离环境运行 Uvicorn；`APP_ENV=test`、模型/embedding disabled、临时 SQLite | `/api/health/live` 返回 `alive`，`/api/health/ready` 返回 `ready`；结束后删除临时数据库和日志 |
| 后端依赖审计 | 隔离环境 `pip-audit --progress-spinner off` | 退出码 0；No known vulnerabilities found |
| Web clean install | Node 24.19.0 / pnpm 11.25.0；全新临时目录 frozen offline install | 成功 |
| Web 检查 | format:check、typecheck、build、test:e2e | 全部通过；E2E 15/15 |
| Web 依赖审计 | `pnpm audit --audit-level moderate` | 退出码 0；无已知漏洞 |
| 根目录差异检查 | `git diff --check` | 退出码 0；输出仅含 Windows LF→CRLF 工作副本提示，没有 whitespace error |

后端干净环境首次离线同步因缓存缺少 `pywin32` 和 `ruff` wheel 未完成；经授权连接锁定包源后安装成功，再在该环境完整测试。沙箱网络权限下 TestClient 本机回环会挂起；完整 pytest 在本机隔离执行环境正常结束。没有访问真实模型或导入论文全文。

## CI 对齐变更

- Web workflow 的全局 pnpm 版本调整为项目声明的 11.25.0。
- CI 加入锁定开发环境中的 `pip-audit` 与 Web `pnpm audit`，使依赖审计由本机约定进入自动检查。
- `pip-audit==2.10.1` 仅为后端开发工具，加入 `uv.lock`；不进入服务运行依赖。

本次修改未提交，远端 Actions 结果仍待用户验收与后续授权发布。
