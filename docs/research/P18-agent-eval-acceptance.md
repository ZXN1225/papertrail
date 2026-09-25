# P18 验收：Agent 离线失败场景矩阵与复现信息

## 目标

扩展现有 P12 离线 benchmark，使它从三个安全/错误场景扩展为覆盖 Agent 常见失败模式的可复现矩阵；不调用网络、真实数据库、OpenAI 模型或 Embedding API。修正 benchmark 报告未记录实际 CLI 输出路径的问题。

## 验收标准

- [x] 使用生产 `AgentHarness`、受控 mock 模型和 `TEST-*` 工具数据，覆盖无证据保守拒答、论文文本提示注入与越权工具拒绝、错误工具参数、检索工具错误、伪造引用拒绝、格式错误终答、模型不可用、工具预算耗尽。
- [x] 报告每个场景的期望/实际状态、通过结果、工具尝试、已登记工具执行、越权尝试/执行、参数错误、模型/工具错误和 mock token；所有场景符合 harness 契约，未登记工具执行数为 0。
- [x] 将“工具副作用执行”更名为 `registered_tool_executions`；只读 synthetic 检索调用不会混称副作用。
- [x] 报告 schema/version、输入数据哈希、评测 runner 哈希、真实 argv/`--output` 路径；CLI 定向测试覆盖自定义输出路径和命令参数记录，不覆盖历史报告。
- [x] 报告明确 `synthetic=true`、无网络/真实 DB/真实模型、费用 `null/not_measured_mock_mode`、`quality_claim_allowed=false`；本机耗时不冒充线上延迟。
- [x] 更新 P12/P18 验收记录、开发说明与 README 展示的场景数量/运行命令。
- [x] 后端 pytest、Ruff、OpenAPI 导出、Web format/typecheck、`git diff --check` 通过。Web 构建/E2E 未重跑，因为本轮没有修改 Web 运行时代码。

## 当前状态

验收标准先于实现记录。本阶段已完成，下一阶段另行确认后开始。

## 执行结果

- 本机离线报告：`backend/reports/p18-agent-eval-report.json`（Git 忽略）；8/8 场景通过、拦截越权尝试 1 次、越权执行 0 次、费用 `null`、`quality_claim_allowed=false`。
- P12/P14 报告分别保存 `command_args` 和 `output_path`。新增 P12/P14 CLI 定向测试检查自定义输出位置与 argv。
- 后端全测 101 passed；Ruff check/format、OpenAPI export、Web Prettier/typecheck、`git diff --check` 通过。未改 Web 运行代码，因此没有重跑 build/E2E；根目录两项约定脚本不存在，记录在 P17 验收说明。
- 本阶段不调用任何付费 API。P12 数据和耗时都是 synthetic/mock，仅用于 Harness 逻辑和错误边界检查。
