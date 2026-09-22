# 本地运行与检查（T04/T05）

本阶段提供三入口首页、状态 API、匿名会话、画像保存/版本历史、已发布目录和确定性报价计算。没有推荐或模型调用。已保存需求固定 24 小时有效，未保存编辑刷新即丢失。`ready=200` 只表示基础依赖可用，不表示数据已可推荐。身份保护、删除与过期清理见 [会话设计](sessions.md)。

## 固定工具

Python 3.12.14、Node 24.19.0、uv 0.12.10、pnpm 11.19.0。版本文件位于根目录，完整依赖见 backend/uv.lock 与 web/pnpm-lock.yaml。uv 可用 `uv python install 3.12.14` 准备 Python。不要用系统 Python 3.11 直接运行后端。

以下命令除特别标记外均从仓库根目录执行。先确保对应版本工具可用，再选一种数据库运行方式；不要同时启动两个占用 55432 的 PostgreSQL。

## 方式 A：Docker Compose（推荐的完整环境）

需要可运行 Linux 容器的 Docker 和 Compose v2。

```powershell
python scripts/init_env.py
docker compose --env-file .env -f deploy/compose.yml up -d --wait
docker compose --env-file .env -f deploy/compose.yml exec postgres createdb -U computer test_computer
```

最后一条只在首次创建测试库时执行。脚本生成忽略入库的 `.env`，凭据随机且不打印；已有文件时拒绝覆盖，后续重启只执行 Compose 命令。PG 映射本机 55432、Redis 56379，仅绑定 127.0.0.1。镜像按版本和摘要固定。Redis 开发实例无密码，因此只能保留本机绑定，不可将此配置直接部署公网。

## 方式 B：当前 Windows 的便携 PostgreSQL

本机没有可用 Docker/WSL 发行版，本轮已用 EDB PostgreSQL 17.11 二进制包完成真实数据库验证，不注册 Windows 服务。

新机器可从 [PostgreSQL 官方 Windows 下载页](https://www.postgresql.org/download/windows/) 指向的 [EDB 二进制下载页](https://www.enterprisedb.com/download-postgresql-binaries) 获取 17.11。此次包为 `postgresql-17.11-3-windows-x64-binaries.zip`；解压其中 `pgsql/bin`、`pgsql/lib`、`pgsql/share` 到仓库 `.local/pgsql/`，不提交二进制文件。缺少运行库时按 EDB 的系统要求安装。

```powershell
python scripts/init_env.py --without-redis
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local-postgres.ps1
```

本机已有 `.env` 和已初始化的集群，**不用重复生成配置**，重启只运行第二条。脚本读取 `.env`，初始化 `.local/pgdata`，创建 computer/test_computer 两个数据库。本机 Redis 明确关闭；此路径不能算作 Redis 成功连接验证，完整组合由 CI 实测。生产配置禁止关闭 Redis。

## 安装、迁移和启动

```powershell
uv sync --directory backend --frozen
pnpm --dir web install --frozen-lockfile
uv run --directory backend --frozen alembic upgrade head
uv run --directory backend --frozen uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

另开终端，从仓库根目录运行：

```powershell
pnpm --dir web dev
```

- 首页：<http://127.0.0.1:3000>。
- 后端接口文档：<http://127.0.0.1:8000/docs>。
- 存活：<http://127.0.0.1:8000/api/v1/health/live>。
- 就绪：<http://127.0.0.1:8000/api/v1/health/ready>。

## 可选：启用 GPT Provider 做本机 Agent 联调

OpenAI API 与 ChatGPT 订阅分开计费。先确认你所在的欧洲国家/地区出现在[官方 API 支持列表](https://help.openai.com/en/articles/5347006-openai-api-supported-countries-and-territories)，然后在 [OpenAI API Platform](https://platform.openai.com/) 设置 API 账单并创建项目 API Key。API Key 由后端使用；不要放入前端环境、截图、聊天或 Git。官方密钥创建和调用步骤见[开发者快速入门](https://developers.openai.com/api/docs/quickstart)。

只修改仓库根目录本机 `.env` 中的模型配置，保留其数据库、会话和其他已有字段：

```dotenv
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=你的项目API密钥
LLM_MODEL=gpt-6-astra
LLM_TIMEOUT_SECONDS=15
LLM_MAX_OUTPUT_TOKENS=512
```

模型名必须是当前项目可调用的模型；若默认模型没有权限，在 API Platform 的项目模型页选择已启用模型并替换 `LLM_MODEL`。保存后重启后端。默认 `LLM_PROVIDER=disabled`，缺 Key 时 OpenAI 模式会拒绝启动配置。代码只允许 OpenAI 官方 HTTPS API 地址；常规联调请保留默认地址。人在欧洲不代表请求自动在欧盟区域处理；EU endpoint 只适用于项目已获相应数据驻留/处理资格的情况，详情看[官方数据控制文档](https://developers.openai.com/api/docs/guides/your-data)。

确认 API `/api/v1/health/ready` 返回 200，再打开 <http://127.0.0.1:3000>：

1. 进入笔记本或 PC 推荐表单，填写少量需求并保存画像。
2. 点击“开始核对”。该请求会把当前用户文本、保存画像和本轮结构化工具观察发送到 GPT。初次学习测试不要写入真实个人资料。
3. 在 Agent 页面观察状态、工具调用摘要和最终回答。空目录时仍可能发生 GPT 调用和工具循环，但商品结果应为空；不要把此结果当作真实推荐。
4. 运行离线保护测试（无需 API Key）：`uv run --directory backend --frozen pytest -q tests/test_openai_provider.py tests/test_agent_harness.py`。

每轮 Agent 受 4 个决策回合、8 次工具调用、45 秒 Harness 总时限约束；单次模型响应默认最多 512 个输出 Token、15 秒 HTTP 超时、逐轮发送且 `store=false`。多轮调用仍会按输入/输出 Token 计费，先只试 1—3 个请求并在 API Platform 查看 usage/billing。此阶段没有服务端美元硬预算器，也不纳入 ChatGPT Plus/API 共享额度。Key 和提示内容不会放进模型评测文件，但供应商会收到实现一次 Agent 决策所需的请求上下文。

手工联调是唯一会产生真实 API 调用的步骤；mock 测试不会连接 OpenAI。真实目录仍为空时只能验证模型选工具、服务端执行和回答循环，不能验证推荐准确性；真实商品/价格仍受 D01—D03 数据授权与样本阻塞。

Alembic `0001_baseline` 创建版本记录，`0002_sessions` 新增会话表，`0003_catalog` 新增 13 张空商品/来源/证据领域表。预览应用不会自动迁移；未迁移、版本不匹配、PG 失联或已配置 Redis 失联均返回 ready=503。升级后先运行 upgrade head，再重启 API/web。隔离 E2E 入口会自行迁移 test_* 数据库。T02 表关系与迁移边界见 [数据模型](catalog-model.md)，记录契约可在 API `/docs` 的 Schemas 查看，无目录写入接口。

当前 head 为 `0004_imports`，新增 6 张导入/版本/通知表，并为规范事实投影建立数据库引用约束。管理 API/CLI 入口与认证配置见 [人工导入指南](manual-imports.md)。管理员配置默认空值；未配置返回 ADMIN_DISABLED，不为了预览而设置通用密码。无真实资料时不向开发库导入 TEST 商品；合成验证须 APP_ENV=test 且 test_* 数据库。

前端将固定状态 GET、公开目录/报价和白名单会话/画像 API 转发到本机 8000；若改端口，在启动 Next 的进程环境中设置服务端 `API_BASE_URL`。公开目录只读取当前发布版本，空目录不会填充样例；报价计算不访问第三方 URL。没有浏览器可控 URL 代理，也不向浏览器传数据库或模型凭据。`.env` 由后端加载，Next 不读取根目录密钥。写请求需要允许的精确 Origin/JSON；会话密钥不足 32 字符时会话服务返回 503。

`APP_ENV=production` 必须提供 PG、Redis、至少 32 字符会话密钥、HTTPS 的 PUBLIC_BASE_URL/CORS_ALLOWED_ORIGINS。CORS 只允许配置来源、GET/POST/PATCH/DELETE 和明确头，带身份写入须匹配 CSRF。管理员写入和生产部署仍在后续阶段实现。开发 Redis 关闭时仍使用 PG 共享限流；默认 SESSION_WRITE_LIMIT=60 次/分钟/会话，可配置 1—600。

## 验证

根目录的记录检查：

```powershell
python scripts/check_foundation.py
python scripts/check_source_review.py
git diff --check
```

后端（工作目录 `backend`）：

```powershell
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen python -m tools.test_local
uv run --frozen python -m tools.export_openapi
uv run --frozen pip-audit --progress-spinner off
```

`tools.test_local` 仅接受 development + 本机地址，从 `.env` 派生 test_computer 连接，避免复制密码。该数据库用户需要创建数据库权限。集成测试仅连接名称以 test_ 开头的测试入口，创建独立 `test_i01_<随机ID>` 空库并只清理自己创建的库，覆盖空库/升级/重复升级/回滚/重新升级与依赖故障；不接触 computer 库。外部测试环境可显式设置 TEST_DATABASE_URL 和 TEST_REDIS_URL 后运行 `uv run --frozen pytest -q`。未提供 TEST_DATABASE_URL 的普通 pytest 会跳过集成测试，不可声称完整通过。

前端（工作目录 `web`）：

```powershell
pnpm run api:generate
pnpm run format:check
pnpm run typecheck
pnpm run build
pnpm audit --audit-level moderate
pnpm exec playwright install chromium
pnpm test:e2e
```

E2E 通过 tools.serve_e2e 启动独立 8001 后端与 3001 Next 生产构建，拒绝非 test_* 数据库且不复用预览服务。要求已有 test_computer 数据库和本地 `.env`（或 CI 的 TEST_DATABASE_URL/SESSION_SIGNING_SECRET），自动迁移该测试库。三个宽度共 15 项：三入口保存/恢复、跨标签冲突、新需求/删除/隔离、保存失败、网络重试/键盘。报告位于 web/playwright-report，截图位于 web/test-results（均不入库）。

API 变化后依次导出 OpenAPI、生成 TypeScript 并一同提交。CI 重新生成后检查无差异，使用真正 PostgreSQL/Redis 服务、锁定安装和上述检查，浏览器报告保留 7 天。漏洞审计只反映当时已知数据库结果，不是全面安全认证。

## 停止服务

前后台终端按 Ctrl+C 停止；本轮后台预览的 PID 记录在 `.local/preview-pids.json`（存在时先核对 PID 对应命令，再停止）。便携 PG 可保留数据停止：

```powershell
& ./.local/pgsql/bin/pg_ctl.exe -D ./.local/pgdata -m fast -w stop
```

Compose 运行方式用 `docker compose --env-file .env -f deploy/compose.yml down` 停止；不要添加 `-v`，以保留数据库。更改 `.env` 密码不会自动修改已初始化集群账户，需通过数据库管理操作协调更新，不能删除集群重建来覆盖用户数据。
