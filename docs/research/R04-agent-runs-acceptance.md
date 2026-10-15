# R04：运行状态与 Harness 验收

日期：2026-10-11。此记录只覆盖本轮本机代码与自动化测试，不代表生产负载或真实模型质量验收。

## 已实现

- `agent_runs` 迁移保存 UUID、问题 SHA-256、状态、创建/结束时间、模型/embedding/总 token、工具调用/步骤/耗时和脱敏 trace。
- 不保存原始问题、回答正文、工具参数或论文摘录。重复 UUID 返回冲突；状态查询能识别并标记没有活跃内存任务的遗留 `running` 记录；Web/API 提供协作取消入口。
- 模型与 embedding 共用观测 token 预算。对外部 provider 的用量在调用结束后才可知，因此正在执行的单次调用可能导致一次超额；context 长度上限是字符近似，不是精确 tokenizer 额度。
- 进程重启后不自动重放模型调用，也不保存多轮对话正文。取消只能在当前 provider/tool 调用边界生效。
- 提供 request-scoped 多轮约束修正：单次请求最多携带 4 轮完整 user/assistant 对（8 条、合计 8,000 字符），只保存在请求/当前浏览器内存，不写入 SQLite 或 localStorage。新增 migration 0010 只记录 `history_sha256`；原始历史正文不持久化。
- 历史在模型输入中显式标为不可信上下文，不算证据；每条事实仍需当前 run 工具观察、准确 quote 与 citation ID。Harness 不会继承上一轮 `citations_seen`/quote ledger。Web 支持追问和清空；刷新页面后上下文消失。

## 自动验收

- 后端完整测试：本轮全量回归 187 passed，1 个 Starlette/AnyIO 上游弃用警告；R04 阶段的 locked clean-env 176 项记录为更早的历史验收。
- 后端 `ruff check`、`ruff format --check`、OpenAPI 导出均通过。当前契约 SHA-256：`3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`。
- 测试覆盖账本隐私字段、重复 ID、任务状态、孤立任务中断和取消信号；测试使用本地 mock，不调用付费模型。
- R04 request-history API/Harness/migration contract 与 Web follow-up/reset E2E 通过；数据库只返回单独的问题/历史摘要哈希，测试确认未存入历史明文。migration 0010 兼容已有 run 记录。
- Web format、typecheck、production build 通过；Playwright E2E 18/18 通过，含三种视口下的追问和清空。

## 验收边界

自动测试证明代码契约，不证明数据库备份/恢复策略或多实例并发部署能力。账本没有租期清理策略、通用任务队列或重启续跑。任何需要保存用户问题/回答的能力都需单独设计授权、保留和删除规则。

## 后续审查补强（2026-10-11）

- 只读 R04 审查发现模型可返回任意工具名称，旧 Trace 将该名称直接保存。现在只有精确命中本轮注册工具集合的名称才会进入 Trace；其余统一记为 `unknown_tool`。回归用例把 `TEST-SECRET` 同时放入问题和未知工具名，确认 API 响应与持久化运行记录均不包含该文本。
- 任务生命周期状态与 Agent 结果状态分离：正常完成的 `insufficient_evidence` 等安全结果记为 run `completed`，并把具体状态保留在 `result_status`；运行中断、预算/超时、provider 不可用和无效模型输出记为 `failed`，用户取消单独记为 `cancelled`。
- 新增 API 级取消链路测试：请求进入活动状态后，取消端点发出信号，mock 服务在安全检查点返回，ask 响应与持久化状态最终均为 `cancelled`。该用例不触发真实模型或外部服务。
- 补入无外部 PDF 生成依赖的标准库合成 PDF 集成测试，使用真实 pdfplumber 打开文件并提取正文、表格单元格及坐标。真实许可论文视觉核验仍待用户提供材料。
- 后续全后端回归为 `198 passed, 1` 个 Starlette/AnyIO 上游弃用 warning；全量 Ruff check/format 通过。多实例活动运行协调与运行中增量 trace/重放仍未实现，不宣称生产级分布式任务执行。

## 2026-10-13：每次模型调用的输出预算封顶

- Harness 现在将每次请求的 `max_output_tokens` 限制为配置上限与本轮剩余已观测 token 预算的较小值，并在 provider 返回超出该上限的用量时立即失败、不再调用后续模型步骤。live-eval 费用守卫将该动态上限带入调用预检和费用估算；OpenAI adapter 只接受不超过服务配置上限的覆盖值。
- 新增回归覆盖动态输出额度、provider 输出超限和输入用量事后超额后停止；Harness、P12 mock 与 live-eval mock 均适配同一接口。定向 Harness/live-eval/multi-agent 回归 62 passed；完整后端 256 passed、1 条既有 Starlette/AnyIO 弃用 warning；Ruff check/format 与 OpenAPI 导出通过，契约 SHA 未变。
- 预算仍不是 provider 账单硬上限：模型输入 token 与 embedding 用量只在调用结束后可知，单个正在执行的 provider/tool 调用仍可能造成预算超额；系统发现后不再继续。没有精确 provider tokenizer 时，不能声称总账单绝对封顶，因此 R04 仍保持 `in_progress`。

## 2026-10-13：provider 用量缺失时失败关闭

- 审计发现 Responses adapter 会把缺失、负数、布尔值或非整数 token usage 静默折成 0；若部分字段仍有效，Harness 可能低报已观测用量。现在模型响应必须同时提供非负整数 `input_tokens` 和 `output_tokens`，否则返回不含响应正文的 `ModelUnavailable`，停止本轮后续工具/模型步骤。Embedding adapter 也要求显式有效的非负整数用量；缺失或 malformed usage 按 `invalid_provider_response` 拒绝，避免向共享预算记 0。
- 新增合成契约覆盖模型 usage 缺失/字段不全/字符串/负数/bool，以及 embedding usage 缺失/bool。后端全量 **294 passed**，1 条既有 Starlette/AnyIO 弃用 warning；Ruff check 与 84 文件格式检查通过；OpenAPI SHA 保持 `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb`。
- 此修复防止未知用量被记为零，但不能约束 provider 自报错误、在途请求花费或保证账单硬上限；R04 仍保持 `in_progress`。未发起真实模型/embedding 调用。

## 2026-10-13：Embedding 用量不明时终止 Agent 轮次

- 进一步沿工具错误路径审查发现：Embedding adapter 虽会拒绝缺失/无效 usage，但证据工具将异常转成普通 observation，Agent 仍可能继续发起 LLM 请求。现在 Harness 识别 `embedding_error` 后记脱敏 tool error trace，并返回 `usage_unavailable`，不把错误 observation 再交给模型；API 返回 503，运行 ledger 将状态记为 failed，Web 显示明确的用量核验失败提示。
- 新增 TEST 合成用例证明 dense 检索 embedding 返回无效 usage 时只发起一个 LLM 轮次，随后停止；API/ledger 集成用例确认返回 503 并将 run 记为 failed。完整后端 **296 passed**、1 条既有 Starlette/AnyIO 弃用 warning；Ruff check/84 文件格式检查通过。OpenAPI 因新增响应状态更新，SHA `be007df662be75f9df7e1d480baee2c7284cd02714227d504d57d20324e0c258`。
- Web Prettier、Next 生产构建（集成 TypeScript 检查）、Playwright E2E **18/18 passed**。无真实模型/embedding 调用。预算仍不能保证 provider 账单绝对封顶；R04 保持 `in_progress`。

## 2026-10-14：模型输入预留加入 Harness 共享 token 守卫

- 每次模型请求前，Harness 使用 `estimate_input_tokens_upper_bound` 对指令、完整输入、工具 schema 和响应格式计算 UTF-8 字节保守上界，并从剩余共享 token 额度中先行预留；请求输出额度限制为 `min(configured_output_cap, remaining - input_upper_bound)`。若保留输入后没有输出空间，则在调用 provider 前以 `token_budget_exceeded` 结束。
- Evidence `dense`/`hybrid` 工具调用也在执行前按查询 UTF-8 bytes + 1,024 bytes provider-envelope reserve 预留共享 token；余额不足时不执行 embedding，provider 实际 usage 超过该上界时，计入已观察值并停止后续模型调用。无 embedding provider 的 BM25 路径不预留。自定义 ToolRegistry 若没有此估算方法仍依赖 Harness 对 returned usage 的事后计入。
- provider 返回后，除累计实际 usage 及输出上限检查外，若报告的模型输入 token 数超过请求前上界，也会立即停止本轮；embedding 在同一 run 内亦检查实际用量不超过其 query 上界。模型与 embedding 上界均不是服务 tokenizer 的精确值。
- 新增合成回归覆盖预算不足时零 embedding 请求、按模型输入预留收紧输出上限、模型/embedding usage 超过估算上界时失败关闭。R04/Harness 定向 **55 passed**；live-eval/P12 兼容回归 **14 passed**；全后端 **327 passed**、1 条既有 Starlette/AnyIO 弃用 warning。Ruff check 与 3 个目标文件 format check 通过。
- 测试环境说明：项目 `.venv` 的 Python 解释器路径已失效，`uv` 默认缓存不可访问；锁定离线重建因本机缓存缺少 `ruff`/`pillow` 轮子而未完成。全套测试使用桌面捆绑 Python 加项目既有 `.venv/Lib/site-packages`，并向 MCP 子进程传入现有依赖路径，最终全部通过。没有覆盖或修复原 `.venv`。
- 该上界依赖 UTF-8 字节数及 4,096（model）/1,024（embedding）字节的包络余量，不是精确 tokenizer 结果或账单硬上限；usage 仍在调用完成后核验，provider 自报也无法由本地证明准确。单个在途调用仍可能超过预算（例如 tokenization/usage 超出本地上界）；项目无法提供 provider-side monetary hard cap。R04 继续 `in_progress`；本轮未调用模型/embedding API，未更改 OpenAPI。
