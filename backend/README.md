# 后端 · I02

Python/FastAPI/PG 版本与锁文件沿用 I01。启动与验证见 [开发指南](../docs/development.md)，本轮设计见 [会话与画像](../docs/sessions.md)。

除健康/平台状态外，现已提供匿名会话、画像创建/读取/PATCH、历史快照、重置和删除 API。app/profiles/service.py 是共享领域服务，HTTP 仅处理输入和身份边界；未来 Agent 必须复用。预算严格整数分，事务内锁定会话并校验 expected_revision，追加不可覆盖的快照；用户不可指定 owner。

0002_sessions 从基线新增会话/画像/限流表，尚无商品/证据表。ready 要求当前 revision。cookie/CSRF/Origin/请求体限制、PG 多实例写限流与 Redis 故障拒绝见会话设计；LLM disabled，管理员写路由未开放。

本目录 `uv run --frozen python -m tools.test_local` 使用本机 development 配置和独立测试库；CI 设置 TEST_DATABASE_URL/TEST_REDIS_URL 后运行 pytest。没有 TEST_DATABASE_URL 则跳过集成，不能报完整通过。tools.export_openapi 导出后须同步前端类型；tools.cleanup_sessions 删除已过期会话并级联历史。tools.serve_e2e 只接受 test_* 数据库并绑定 8001，不用于生产。
