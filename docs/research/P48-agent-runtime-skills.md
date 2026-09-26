# P48：受控运行时 Agent Skills

状态：第一版实现、离线安全回归与三项真实模型样例验收已完成；发现并修复文献发现重复检索导致步数耗尽的问题。

## 目标与边界

Agent 可以按任务选择一个版本控制的研究工作流，让复杂任务具有可审计步骤和更窄的工具范围。Skill 只提供任务说明与固定工具名，不是可执行插件，也不能扩大 Agent 的权限。

运行时目录是 `backend/app/agent/skills.json`。供开发者和 Codex 使用的流程文档放在根目录 `skills/`；运行时不会扫描该目录、用户目录或任意文件。

## 内置 Skill

| Skill | 用途 | 工具范围 |
| ----- | ---- | -------- |
| `literature_discovery` | 发现和筛选论文元数据 | 本地、OpenAlex、arXiv 的已启用书目工具 |
| `evidence_synthesis` | 总结和比较论文方法/发现 | 获准全文检索与已启用的精确元数据读取 |
| `citation_analysis` | 追溯 OpenAlex 引用脉络 | Works 搜索/读取与有界一跳引用工具 |

Harness 在创建时验证 Skill JSON 的结构、名称唯一性、字段长度、工具名白名单和每个 Skill 的调用预算。模型调用 `activate_skill` 后，Harness 将模型工具列表缩到该 Skill 所声明且当前实际启用的工具交集；一次运行只激活一个 Skill，并强制该 Skill 的数据工具调用上限。达到上限后隐藏全部工具，提示模型用已收集观察作答；若仍请求工具，则不执行并返回预算错误。全局步骤、总调用次数、deadline 和 observation 限制仍生效。用户内容和论文内容不能增添 Skill 或工具。

Skill 仍为可选的工作流选择机制：模型可以在简单问题上直接使用固定工具。显式 arXiv 内容请求继续隐藏 arXiv 元数据工具。激活记录进入现有脱敏 trace；不记录 Skill 以外的个人/文献正文。

## 验证

- `test_runtime_skill_activation_limits_available_tools` 检查模型可见目录、Skill 激活后缩减的工具集、注入的 Skill 指引与 trace 事件。
- `test_runtime_skill_blocks_tool_outside_its_allowlist` 检查模型调用未列出的工具会得到 `tool_not_allowed`。
- `test_runtime_skill_catalog_rejects_unregistered_tools` 检查恶意/未知工具名使目录验证失败。
- `test_runtime_skill_tool_budget_stops_repeated_searches` 检查文献发现 Skill 的三次数据工具调用预算及耗尽后的无工具终答。
- 后端全量自动测试：145 passed，2 条依赖弃用警告。
- Ruff check 与 format check：通过。

真实模型样例验收覆盖三个 Skill。`evidence_synthesis` 比较 arXiv:2609.25991 与 arXiv:2604.14572：trace 中 `activate_skill` 成功，两次 `retrieve_paper_evidence` 均为 `ok`，回答有 Markdown 表格、范围说明及对应全文证据卡片。`citation_analysis` 以 W7118085507 为种子：trace 为 `activate_skill`、`get_openalex_work`、`expand_openalex_citations`，全部 `ok`，共 3 次工具调用、4 个模型轮次、11,445 tokens；回答返回 3 篇参考文献并正确说明引用边不表示结论相互支持。

`literature_discovery` 主题发现样例没有通过：运行在 8 次工具调用/模型轮次上限处结束，135,992 tokens，trace 显示模型反复发起宽泛搜索，并出现一次 `search_papers` 参数错误。没有将其记作 Skill 验收通过。为避免再现长循环，运行时现为三个 Skill 分别设置最多 3/4/3 次数据工具调用；耗尽后隐藏工具要求基于已有观察作答，并由 Harness 强制拦截后续工具请求。新增离线回归覆盖该硬限制。真实模型只做一次失败探索，不再重复以免产生额外费用；自动回归确认其预算处理路径。
