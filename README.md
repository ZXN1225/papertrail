# Agent 电脑推荐平台 · 选机有据

面向中国大陆市场，以预算、用途和偏好为输入，逐步构建可追溯的笔记本精确 SKU 推荐与经过规则校验的 PC 装机清单。

**当前步骤 06 / T03：人工导入、预览、审核、原子发布与通知重试的功能已实现。真实样本仍待授权资料验收；公开目录、报价选择和推荐尚未开放。本轮结束后等待确认。**

## 本地运行

完整的环境准备、安装、迁移、启动、停止和测试命令见 [开发指南](docs/development.md)。固定 Python 3.12.14、Node 24.19.0、uv 0.12.10、pnpm 11.19.0，依赖由 uv.lock/pnpm-lock.yaml 锁定。

准备 PostgreSQL 和 `.env` 后，从根目录运行：

```powershell
uv sync --directory backend --frozen
pnpm --dir web install --frozen-lockfile
uv run --directory backend --frozen alembic upgrade head
uv run --directory backend --frozen uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

另开终端执行 `pnpm --dir web dev`，访问 <http://127.0.0.1:3000>。本机已初始化便携 PG 和 `.env`，无需重新生成配置；新机器按开发指南选择 Compose 或便携 PG。

页面读取真实 API，正常时显示“数据准备中”，异常时提供重试。已保存需求在同一浏览器会话中可恢复，固定 24 小时有效；未保存编辑仍会在刷新时丢失。无需模型密钥；ready=200 只表示基础依赖正常，不代表可推荐。[会话与版本设计](docs/sessions.md) 说明隔离、删除、限流和过期清理。

## 文档与验证

- [完整执行计划](docs/EXECUTION_PLAN.md)、[任务台账](docs/TASKS.md)、[进度与验证记录](docs/PROGRESS.md)。
- [人工导入操作与边界](docs/manual-imports.md)、[流程演示结果](docs/reviews/T03-demo.md)、[T03 验收](docs/research/T03-acceptance.md)、[本轮 PR 说明](docs/reviews/T03-PR.md)。
- [商品模型](docs/catalog-model.md)、[版本矩阵](docs/runtime-matrix.md)；前轮记录保留于历史文档。
- [来源可行性核验](docs/research/V01-source-feasibility.md)、[人工报价路径](docs/manual-offer-workflow.md)。D01—D03 仍阻塞真实数据发布。
- [原始规格](docs/PROJECT_SPEC.md)、[架构决策](docs/adr/README.md)、[数据字典](docs/data-dictionary.md)、[来源登记](docs/data-sources.md)、[API 边界](docs/api-contract.md)、[生成的 OpenAPI](docs/openapi.json)。

根目录可执行 `python scripts/check_foundation.py`、`python scripts/check_source_review.py`、`git diff --check`。后端 ruff/pytest、前端类型/构建/Playwright、契约生成与审计见开发指南和 AGENTS.md。CI 使用锁定安装、真实 PG/Redis；不把未执行的测试记为通过。

## 代码边界

Agent 后续负责理解需求、调用受控工具和解释证据；价格、预算、兼容性与排序由共享领域服务决定。金额为整数分，未知价格为 null，必要信息未知不能判通过。测试商品必须 synthetic=true、TEST-* 且隔离。本轮未导入商品或报价。

| 目录 | 当前职责 |
|---|---|
| backend/ | FastAPI、会话与导入领域服务、PG 迁移、管理员 CLI 和测试 |
| web/ | 中文首页、草稿、生成的 API 类型、浏览器测试 |
| deploy/ | 开发 PG/Redis Compose；生产部署留待 P7 |
| scripts/ | 记录检查、开发配置生成、便携 PG 启动 |
| data/ | 空模板与禁止发布的研究记录 |
| docs/、evals/ | 规格、计划、阶段记录、未来评估设计 |

每轮完成后暂停。PR 不等于合并或生产发布。本仓库代码许可仍待选择，不沿用参考项目许可。
