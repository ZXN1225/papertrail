# I01：可运行工程基础与三入口首页

此前仓库只有计划、数据研究记录和目录说明，无法运行。本轮增加 FastAPI、Next.js 中文首页、固定依赖、真实 PostgreSQL 基线迁移、PG/Redis 就绪检查及 CI。首页可编辑台式机、笔记本和单零件需求草稿；数据未准备好时明确提示，依赖故障可重试，不生成商品和报价。

## 范围

- 固定 Python/Node/uv/pnpm 版本、uv.lock/pnpm-lock.yaml；开发 Compose 镜像固定摘要。
- live/ready/platform status 三个 GET API；OpenAPI 导出与前端类型生成；生产缺关键配置拒绝启动。
- 迁移只建立 Alembic 基线；真实业务表留给 T02，页面草稿仅在当前页面内存中。
- 真实 PostgreSQL 迁移、依赖失败测试，三个宽度的浏览器流程与依赖审计，启动说明见 docs/development.md。

## 验证与限制

本机：13 项后端测试通过（真实 PostgreSQL 17.11）；9 项 E2E 通过（375/768/1440）；ruff、前端格式/类型、Next 构建、契约生成、基础记录检查与依赖审计通过。Redis 在本机显式关闭。

[GitHub CI 完整运行](https://github.com/ZXN1225/Agent_Computer_Recommanding_Platform/actions/runs/35506174415) 全部通过，包括真实 PostgreSQL/Redis 联测、锁定安装、OpenAPI 重生成无差异、前端构建、依赖审计和浏览器测试。该链接记录实现提交 ed5b6ff 的验证；最终文档同步提交的状态见 PR 当前检查。没有运行本机 Compose；同一固定镜像在 CI 服务环境验证，不把两者混为一谈。

没有真实目录/报价、会话保存、管理员写入、模型调用或正式推荐。V01 的 D01—D03 数据发布阻塞保留。尚未生产部署，不合并 PR，不提前进入 I02。

## 叠加审阅关系

起点为 01d2966，base 为 codex/v01-source-feasibility（PR #2），只审查 I01 增量。#1/#2 尚未合并；未来按顺序处理并核对 diff，必要时调整 base 或重放增量，避免 squash 后重复提交。用户本轮确认成果不自动构成合并授权。

## 手动验收

打开本机 3000 首页，切换三入口，输入预算并预览需求；刷新确认草稿清空。界面应始终说明数据准备中，不出现商品与购买清单。关闭后端再重试会显示连接失败，恢复后端可恢复空数据状态。完成后等待用户确认步骤 04。
