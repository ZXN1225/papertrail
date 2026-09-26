# P48：受控运行时 Agent Skills

状态：第一版实现、离线安全回归和一项真实模型现场验收已完成。

## 目标与边界

Agent 可以按任务选择一个版本控制的研究工作流，让复杂任务具有可审计步骤和更窄的工具范围。Skill 只提供任务说明与固定工具名，不是可执行插件，也不能扩大 Agent 的权限。

运行时目录是 `backend/app/agent/skills.json`。供开发者和 Codex 使用的流程文档放在根目录 `skills/`；运行时不会扫描该目录、用户目录或任意文件。

## 内置 Skill

| Skill | 用途 | 工具范围 |
| ----- | ---- | -------- |
| `literature_discovery` | 发现和筛选论文元数据 | 本地、OpenAlex、arXiv 的已启用书目工具 |
| `evidence_synthesis` | 总结和比较论文方法/发现 | 获准全文检索与已启用的精确元数据读取 |
| `citation_analysis` | 追溯 OpenAlex 引用脉络 | Works 搜索/读取与有界一跳引用工具 |

Harness 在创建时验证 Skill JSON 的结构、名称唯一性、字段长度和工具名白名单。模型调用 `activate_skill` 后，Harness 将模型工具列表缩到该 Skill 所声明且当前实际启用的工具交集；一次运行只激活一个 Skill，沿用既有全局步骤、调用次数、deadline 和 observation 限制。用户内容和论文内容不能增添 Skill 或工具。

Skill 仍为可选的工作流选择机制：模型可以在简单问题上直接使用固定工具。显式 arXiv 内容请求继续隐藏 arXiv 元数据工具。激活记录进入现有脱敏 trace；不记录 Skill 以外的个人/文献正文。

## 验证

- `test_runtime_skill_activation_limits_available_tools` 检查模型可见目录、Skill 激活后缩减的工具集、注入的 Skill 指引与 trace 事件。
- `test_runtime_skill_blocks_tool_outside_its_allowlist` 检查模型调用未列出的工具会得到 `tool_not_allowed`。
- `test_runtime_skill_catalog_rejects_unregistered_tools` 检查恶意/未知工具名使目录验证失败。
- 后端全量自动测试：144 passed，2 条依赖弃用警告。
- Ruff check 与 format check：通过。

用户完成了 `evidence_synthesis` 的现场验收：比较 arXiv:2609.25991 与 arXiv:2604.14572 的知识库组织和 Agent 导航方式。trace 显示 `activate_skill` 成功、两次 `retrieve_paper_evidence` 均为 `ok`；回答包含 Markdown 比较表、比较范围说明和分别对应两篇论文的授权全文来源卡片。截图没有显示模型激活后的工具清单细节，因此本次只确认该样例可运行及证据回链正确；离线 Harness 测试负责验证工具子集约束。一次验收不代表模型普遍会正确选择 Skill，也没有覆盖其他两个 Skill。

后续若扩展验收，可用主题发现（`literature_discovery`）和给定 OpenAlex ID 的引用脉络（`citation_analysis`）各补一个现场样例；这不阻塞当前 MVP 交付。
