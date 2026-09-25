# P25 验收：跨来源补充检索与 DOI 去重

## 目标

让 Agent 在用户需要较全面的论文发现时，能把 OpenAlex 与 arXiv 作为互补元数据来源，应用各来源实际支持的年份筛选，依据双方可见的 DOI 合并重复作品，并保留 OpenAlex 与 arXiv 的来源链接。引用图拓展仍限定在 OpenAlex 一跳。

## 验收标准

- [x] Agent 在需要广覆盖时可按关键词分别补充 OpenAlex 与 arXiv 检索；来源工具由实际启用的客户端决定。
- [x] arXiv Agent 搜索支持可选年份范围，按官方 `submittedDate` 查询；OpenAlex 年份/OA 条件仍由 OpenAlex 结构化字段处理。arXiv 来源不被描述为满足 OpenAlex OA 筛选或全文许可条件。
- [x] OpenAlex/arXiv observations 与 citation 暴露 DOI；仅规范化 DOI 完全相同时才合并展示，并保留备用来源 ID/链接。单元测试确认 DOI 不同或缺失时不合并。
- [x] Agent 指令说明跨源 DOI 去重策略及年份/OA 限制；来源仍是非可信数据，论文结论仍须受许可全文证据支持。
- [x] Harness 与离线 benchmark 验证双源搜索、同 DOI 归并、备用链接、不同/缺失 DOI 不合并及年份范围参数。上游为空或只有一个来源时由可用工具实际观察决定；未构造独立空来源 UI 用例。
- [x] 离线 benchmark 加入跨源发现用例，无真实网络、数据库或模型；保持质量声明禁用。
- [x] 同步 OpenAPI、前端类型/UI、README、开发说明、PROJECT_SPEC、P23 验收状态、TASKS 和 PROGRESS。
- [x] 后端 Ruff check/format、pytest 与 OpenAPI 导出通过；Web format/typecheck 和 E2E 通过；根 `git diff --check` 通过。
- [ ] Web 生产构建待用户运行的 localhost:3000 服务停止后再执行，避免覆写共享 `.next`。依赖审计受环境限制：Python 环境未安装 `pip-audit`；`pnpm audit` 连接 npm registry 时返回 EACCES/fetch failed。
- [x] 不读取或更改用户数据库/真实报告，不调用外部来源、LLM 或 embedding API，不提交全文/密钥/本机缓存。

## 当前状态

验收条件先于实现记录。本阶段验证中。

## 执行记录

- 将严格 OpenAlex/arXiv 搜索 schema 暴露给模型；arXiv 年份选项通过官方 Atom API 的 `submittedDate` 日期范围过滤（arXiv 官方 [API 手册](https://info.arxiv.org/help/api/user-manual.html)）。此字段表示提交日期范围，与 OpenAlex 出版年语义不同。
- 扩充 citation DOI 与 `alternate_sources` 契约；只按规范化精确 DOI 归并，优先 OpenAlex 主卡片并保留 arXiv 链接。直接 Harness 测试覆盖相同、不同与缺 DOI；UI 来源卡片显示备用来源链接。
- P12 离线报告升至 v5，增加 OpenAlex/arXiv 同 DOI 合成场景，最终必须为 10/10 通过且保持无网络、无真实模型/数据库与 `quality_claim_allowed=false`。
- 自动化验收中可安全执行的项目均已完成；生产构建因共享 `.next` 上有用户开发服务而暂缓，依赖审计未成功。功能阶段完成，以上两项环境检查明确保留待办。
