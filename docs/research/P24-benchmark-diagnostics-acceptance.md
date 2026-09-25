# P24 验收：离线 benchmark 场景诊断

## 目标

让 P12 离线 benchmark 在总通过率之外，为每个场景明确展示实际状态与期望状态是否相符、越权执行是否为零、每条期望指标的实际值及失败原因，便于定位回归。

## 验收标准

- [x] 每个场景报告新增机器可读 `checks`，覆盖状态匹配、无越权执行，以及传入的每一项预期指标。
- [x] 报告新增稳定有序的 `failure_reasons`；成功用例为空列表，状态或指标故意不匹配时给出明确 reason code。
- [x] `passed` 由全部检查结果决定；摘要提供失败数和失败场景 ID，不只依赖通过布尔字段。
- [x] 升级 P12 报告 schema 版本并更新 README/开发说明/验收记录；不改 HTTP/OpenAPI 或数据库契约。
- [x] 自动测试覆盖所有场景通过，以及一个确定性失败场景的状态和指标不匹配诊断。
- [x] 全量后端测试、Ruff check/format、OpenAPI 导出、根 `git diff --check` 通过；未执行 Web/审计项记录原因。
- [x] 不访问外部 API/模型/真实数据库，不修改已有 ignored report 或用户本地状态。

## 当前状态

验收条件先于实现记录。本阶段已完成。

## 执行结果

- P12 报告 schema `papertrail-p12-offline-benchmark-v4`；9/9 场景通过，失败场景数为 0。
- 测试另构造一个预期状态与指标均错误的 synthetic case，确认报告精确包含 `status_mismatch` 和 `metric_mismatch:registered_tool_executions`，且显示两个断言的实际/期望值。
- 定向测试 4 passed；后端全量 pytest 110 passed（两条 Starlette/httpx 与 anyio 弃用 warning），Ruff check/format、OpenAPI 导出和根 `git diff --check` 通过。
- 未改 Web 代码，因此没有重跑 Web 格式/类型/构建/E2E；未修改依赖，因此没有执行 pip/pnpm audit。根 `scripts/check_foundation.py` 与 `scripts/check_source_review.py` 在当前 checkout 缺失，无法运行。
- 不涉及 OpenAPI 契约或数据库变更；未调用外部 API/模型/真实数据库，也未修改既有 ignored report。
