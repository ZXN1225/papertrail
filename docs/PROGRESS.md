# 项目进度

更新日期：2026-09-20。当前交付：步骤 03 / I01。分支：codex/i01-engineering-foundation；起点：01d2966。最终提交以 git log -1 为准。

## 本轮成果与边界

- 用户已确认 V01 并授权继续一步；本轮仅工程基础，不进入 I02/T02。
- FastAPI 三个 GET 接口、严格生产配置、依赖状态/请求 ID；Next 中文三入口、页面草稿、空数据与故障重试。
- Python/Node/uv/pnpm 及完整依赖锁定；OpenAPI 导出、前端类型生成、固定镜像与 Actions SHA 的 CI。
- Alembic 0001_baseline 只建立版本记录，不创建商品/画像业务表。真实发布 SKU=0、报价=0、data_version=null，LLM disabled。
- 本机便携 PostgreSQL 17.11 可运行，未注册 Windows 服务；本机无可用 Docker/WSL 发行版，Redis 显式关闭。Compose 提供完整开发环境，CI 验证真实 PG/Redis。
- 开发说明见 development.md，验收见 research/I01-acceptance.md；PROJECT_SPEC 原文未修改。

## 验证

- 本机后端 13 项测试通过，包含真实 PG 空库、迁移/重复升级/回滚/重升、PG/Redis 故障、生产配置拒绝、CORS；未把 Redis 成功连接算作本机实测。
- Playwright 9 项通过：375/768/1440 三种宽度，真实 API 三入口与草稿/刷新清空、网络错误/重试、键盘与无效预算。桌面和手机截图已目视检查。
- ruff 检查/格式、前端格式/类型/生产构建、OpenAPI 导出/生成、基础文件/来源记录检查、git diff --check 均通过。pip-audit 和 pnpm audit 未检出已知漏洞。
- 本地配置值与跟踪文件比对通过；随机开发凭据、.env、数据库与下载二进制均未入库。
- 第三方 Starlette 测试客户端有 httpx 与 AnyIO 弃用警告，未掩盖；不影响当前测试。
- [GitHub CI 首次完整验证](https://github.com/ZXN1225/Agent_Computer_Recommanding_Platform/actions/runs/35506174415) 全部通过：锁定安装、真实 PG/Redis 后端集成、迁移、OpenAPI 无差异、前端构建、审计和浏览器 E2E。该运行对应实现提交 ed5b6ff；文档更新后仍以 PR 当前提交检查为准。

## Git 与审阅

本轮开始时 #1/#2 均 OPEN，工作区干净；未合并。[I01 PR #3](https://github.com/ZXN1225/Agent_Computer_Recommanding_Platform/pull/3) 以 codex/v01-source-feasibility 为 base，只审查本轮增量。实现提交 ed5b6ff，后续文档同步提交以 git log 为准。未来按 #1→#2→#3 顺序核对，调整 base 或在 squash 后重放增量。

本机预览已启动于 http://127.0.0.1:3000，API 为 8000，便携 PG 为 55432。进程 PID 保存在忽略入库的 .local/preview-pids.json；电脑重启后按 development.md 重新启动。该预览仅监听本机，不是正式部署。

## 下一轮（必须等待确认）

步骤 04 / I02 + T11：匿名会话身份、HttpOnly/SameSite/生产 Secure、CSRF/Origin、画像保存/revision、跨会话资源隔离、并发冲突、新对话隔离；不接模型。现在首页草稿不保存，不是已经完成该步骤。

D01 来源使用权限、D02 精确身份/BIOS、D03 真实人工报价仍阻塞后续数据发布；I01 不解除这些条件。没有生产部署或真实推荐验收。
