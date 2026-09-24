# P11 验收：论文研究工作区

## 目标

提供可本机运行的中文研究工作区，使用户能搜索 OpenAlex/arXiv 元数据、浏览本地库、查看论文详情、比较已选论文，并向受限 PaperTrail Agent 提问和检查证据引用。

## 验收条件

- 实施时前端曾位于独立 `web/` 子目录，现已随用户确认迁至仓库根目录的 `web/`。
- 页面提供 OpenAlex、arXiv 和本地库搜索入口；表单有输入校验、提交/加载、空结果、上游失败/重试状态；真实记录来源和链接可见，不伪造数据。
- 结果支持详情展开和选择 2–3 篇进行字段对比；引用原始后端返回，不由前端推导或生成事实。
- Agent 面板调用既有只读 `/api/v1/agent/ask`，展示状态、回答、运行 ID、token/耗时、trace 与 citations；每条引用展示来源、许可/署名、证据片段和原论文链接。Agent disabled / insufficient-evidence 需清楚显示。
- 所有前端请求经同源 Next Route Handler 代理到固定服务端 `API_BASE_URL`，无任意 URL 转发、不把 OpenAlex/LLM/Embedding Key 暴露到浏览器；代理仅允许固定路径和 HTTP 方法。
- Agent 代理拒绝额外字段与超出 16 KiB 的请求体，避免借 UI 代理透传任意目标或无界输入。
- 对话/查询等状态可键盘操作，正确 label/ARIA、焦点样式；375、768、1440 宽度可用。
- Playwright E2E 通过浏览器 API mock 覆盖搜索、详情、比较、Agent 引用、空结果、服务失败/重试、键盘可达性和三种视口；另直接测试 Agent 代理输入校验。mock fixture 标记 synthetic，不接触用户数据库或真实 OpenAI。
- 格式、类型、生产构建和 E2E 通过；启动说明、阶段任务和进度同步。
- 前后端锁定依赖漏洞审计均完成，没有已知漏洞。
- 本机真实 arXiv 查询完成 200 正向验收：短语查询 `retrieval augmented generation` 返回 5,985 条匹配、10 条记录，并经过后端 Atom 解析与 Web 同源代理。使用与运行时一致的 `Python/3.12` User-Agent；`python-httpx/0.28.1` 会被网关以 406 拒绝。查询空格采用 `%20` 编码；仍保持每进程最少 3 秒请求间隔。

## 本阶段边界

- 不变更后端检索/Agent 策略，不请求或保存新论文全文；不在测试中触发收费模型/Embedding 调用。
- 本阶段 mock E2E 只验证浏览器和代理契约，不是 OpenAlex 可用率、Agent 质量或数据质量证明。
- 比较能力仅并列展示来源已有元数据；不产生模型排名或新的学术结论。
