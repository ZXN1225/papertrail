# Agent 电脑推荐平台

面向中国大陆市场，以预算、用途和偏好为输入，提供可追溯的笔记本精确 SKU 或经过规则校验的 PC 装机清单。默认人民币、中文、全新零售商品；市场和币种最终可配置。

**当前进度：第二步 V01 来源可行性核验已完成（含明确失败证据），第一步 T01 已完成。平台尚不能运行；真实目录、报价和模型接入仍为空。下一步为 I01 工程搭建，等待用户确认。**

## 从这里开始

- [完整执行计划](docs/EXECUTION_PLAN.md)：分步交付、验收、确认节点。
- [任务台账](docs/TASKS.md)：T01—T16、前置关系与状态。
- [进度与接续说明](docs/PROGRESS.md)：实际检查、环境缺口和下一步。
- [第二步核验报告](docs/research/V01-source-feasibility.md)：5 个 CPU 规格样本、主板/笔记本/报价通道限制与后续条件。
- [技术版本矩阵](docs/runtime-matrix.md)、[人工报价维护路径](docs/manual-offer-workflow.md)。
- [原始项目规格](docs/PROJECT_SPEC.md)：用户附件原文，保留研究结论的原始表述；不代表本仓库已复核参考项目。
- [架构决策](docs/adr/README.md)、[数据字典](docs/data-dictionary.md)、[来源登记](docs/data-sources.md)、[API 计划](docs/api-contract.md)。

## 核心原则

Agent 负责理解需求、调用受控工具和解释证据；预算、价格、兼容性、筛选与排序由共享领域服务负责。关闭 LLM 后，未来的表单推荐仍需可用。金额用整数分，未知价格为 null，必要兼容信息未知不能判通过。测试数据必须隔离并标记 `synthetic=true`、`TEST-*`。

## 当前可执行的检查

在仓库根目录使用 Python 3.11 或更新版本执行（仅标准库，不需安装依赖）：

```powershell
python scripts/check_foundation.py
python scripts/check_source_review.py
git diff --check
```

这些检查只验证基础文件和研究记录一致性；不代表业务测试或来源授权通过。后端保留 Python 3.12 基线，V01 已核验支持范围；P1 实际安装、锁定依赖并构建验证。

## 目录职责

| 目录 | 职责与状态 |
|---|---|
| backend/ | API、领域服务、Agent、worker；当前只有边界说明 |
| web/ | Next.js 中文问卷、结果和对比；当前只有边界说明 |
| data/ | 空模板与禁止发布的研究元数据；没有可导入的真实商品/报价 |
| evals/ | 正确性、Agent 和故障评测计划 |
| deploy/ | 后续 Compose、Nginx、迁移和恢复说明 |
| scripts/ | 当前可运行的骨架检查 |
| docs/ | 项目规格、计划、台账、决策和验收记录 |

## 本地启动与配置

本轮没有服务器启动命令。不要把 `.env.example` 当作可运行生产配置；其中数据库、认证和模型凭据均留空。P1 将提供锁定安装、PostgreSQL 迁移、健康检查和无模型空数据页面的启动步骤。

项目采用阶段确认：每次完成可审查步骤后暂停，用户确认后再继续。当前代码不复制参考仓库；本仓库代码许可尚待选择，不能把参考仓库的 Apache-2.0 自动套用于本项目。

GitHub 审阅见 [第二步 PR 说明](docs/reviews/V01-PR.md)；第一步记录保留在 [T01 PR 说明](docs/reviews/T01-PR.md)。
