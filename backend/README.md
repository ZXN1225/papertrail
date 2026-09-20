# 后端 · I01

Python 3.12.14 / FastAPI / Pydantic v2 / SQLAlchemy 2 / Alembic，精确依赖见 pyproject.toml 与 uv.lock。启动、迁移和测试见 [开发指南](../docs/development.md)。

三个只读接口：/api/v1/health/live、/api/v1/health/ready、/api/v1/platform/status。ready 校验真实 PG 和迁移版本；Redis 配置后成为必要依赖。生产缺关键配置拒绝启动。迁移只建立版本基线，业务表在后续步骤实施。

app/common 放配置、依赖和响应契约，app/main.py 组装应用。LLM 当前必须 disabled，管理员写路由未开放。预算/兼容/评分未来进入共享领域服务，路由和 Agent 不各写一套算法。

本目录运行 `uv run --frozen python -m tools.test_local`，需本机 development 配置、test_computer 库和创建测试数据库权限。外部测试环境显式设置 TEST_DATABASE_URL/TEST_REDIS_URL 后运行 pytest；未提供测试库时会跳过集成。tools.export_openapi 导出契约，前端须同步生成类型。

未来模块包括 catalog/components/laptops、pricing、compatibility、recommendation、comparison、agent、knowledge、sources、admin、jobs。采集/索引/长运行在 worker；本轮没有开放这些能力。
