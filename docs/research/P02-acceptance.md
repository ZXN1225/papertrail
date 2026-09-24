# P02 验收记录：新项目骨架

日期：2026-09-23。分支：`codex/paper-research-agent`。

## 验收结果

- [x] Python 3.12.14、uv 锁定安装可用；`uv sync --locked --all-groups` 成功。
- [x] FastAPI 单一入口 `app.main:app`，通过 `create_app` 工厂构造。
- [x] 存活与就绪接口可测试；就绪响应明确显示数据库未配置、OpenAlex 未连接。
- [x] 默认关闭 LLM/embedding；没有密钥时服务仍可启动，健康响应不包含密钥或模型名。
- [x] 开启 OpenAI Provider 时缺 Key/模型配置会被拒绝。
- [x] GitHub Actions 包含锁定安装、ruff lint/格式与 pytest。
- [x] PowerShell 与 Unix 的本地启动说明已提供。
- [x] 不创建数据库、不访问 OpenAlex/LLM/embedding、不迁移或删除旧项目代码、不推送 GitHub。

## 实际执行检查

- `uv sync --locked --all-groups`：通过，Python 3.12.14，31 个锁定依赖。
- Uvicorn 本机启动烟测：`GET /api/health/ready` 返回 HTTP 200，响应如实显示 database `not_configured`、OpenAlex `not_connected`、LLM/embedding `disabled`。
- `uv run --locked pytest`：3 passed。
- `uv run --locked ruff check .`：通过。
- `uv run --locked ruff format --check .`：通过。
- 根目录 `python scripts/check_foundation.py`：通过。
- 根目录 `python scripts/check_source_review.py`：通过；此项只检查记录一致性，不代表来源获授权。
- 根目录 `git diff --check`：通过。

pytest 输出含当前 Starlette/httpx 组合的弃用提示；没有测试失败。后续依赖升级时应复查兼容性。

## 运行方式

详见 [`development.md`](../development.md)。服务默认监听 `127.0.0.1:8001`，不需要 API Key 或数据库。
