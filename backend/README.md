# 后端边界（待实现）

计划 FastAPI / Pydantic v2、SQLAlchemy 2 / Alembic、PostgreSQL、Redis；Python 3.12 基线。P1 核验并锁定版本，创建 pyproject.toml、uv.lock 和可运行入口。目前没有服务代码，不提供虚假启动命令。

预定模块：common（配置/数据库/认证/日志）、catalog/components/laptops（SKU 与规格）、pricing、compatibility、recommendation、comparison、agent（Harness/工具/回答契约）、knowledge、sources、admin、jobs。

兼容与评分为显式输入的纯函数。路由只负责认证、参数校验与服务调用。表单和 Agent 不各写一套推荐算法。worker 处理采集/索引/长任务，不阻塞 HTTP。

P1 配置 unit/integration/contracts 测试目录；集成使用真实 PostgreSQL。产品运行时流程在 app/agent/skills，开发工具技能另在根 .agents/skills，按需要再建立。
