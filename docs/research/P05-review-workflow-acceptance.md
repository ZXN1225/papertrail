# P05 人工 qrels 复核工作流验收

## 目的

为尚未复核的真实 OpenAlex 候选标签提供可离线导出/导入的人工审阅包。系统负责呈现固定查询、冻结语料标题/摘要、助手建议分级与可编辑人工分级；最终相关性判断由用户作出。工具不得自行把 assistant 候选改标为人工金标。

## 验收标准

1. 从本地 SQLite 中找到与 P05 数据集 work IDs、内容哈希精确匹配的不可变快照；找不到、重复或内容变更时拒绝导出。
2. 导出 UTF-8 JSON 复核包，包含数据集/语料哈希、全部 query-doc pair（当前 8×10）、查询文字/意图桶、标题/年份/摘要、原建议分级、空人工分级、人工审核勾选和备注栏；不写入数据库或原始 dataset。
3. 导入必须以未修改的原 dataset 为基准，校验 source dataset SHA、query/doc 覆盖、唯一 pair、文档哈希、所有人工分级 0—3、每项 reviewed=true 和显式 reviewer；不完整或 stale 包拒绝。
4. 成功导入只写用户指定的新文件，记录 `judgment_status=human_reviewed`、审核者、审核时间与输入复核包哈希；原始候选集保持不变。显式 `--confirm-human-review` 是导入者对已人工审阅的确认。
5. CLI 的默认操作仅为 export；不得联网、调用模型、访问任意路径或打印摘要之外的敏感本机配置；输出不含 API keys。导出的 OpenAlex 元数据副本按 CC0 来源标记。
6. 测试覆盖完整往返、缺失 pair、重复 pair、越界等级、未勾选 reviewed、基准 hash 过期和 output 不覆盖 source。
7. 文档给出 Windows PowerShell 操作步骤和等级含义；完成工具本身不改变 qrels 状态，等待用户实际逐项审核后才能导入。

## 边界

仅解决人审准备与校验，不把小规模 8-query/10-paper 评测宣传为通用质量结论。P05 完整验收还需用户实际审阅并在新的数据集上运行 BM25 报告。

## 当前实现结果（2026-09-24）

- 已新增 `app.cli.review_qrels export|import` 与 `app.evaluation.review`。
- 11 项定向测试通过，覆盖人审副本生成、80-pair 完整性规则的代表性边界、stale hash/snapshot/metadata/query、重复或缺失 pair、等级范围、reviewed 标志与禁止覆盖输入；Ruff 检查与格式检查通过。
- 尚未由 Codex 读取本机数据库或导出用户文献摘要，也未生成 `human_reviewed` 数据集。该状态只有用户逐项审阅并显式运行带 `--confirm-human-review` 的导入命令后才会改变。

## 用户本机完成记录（2026-09-24）

- 用户已导入 `reports/p05-review-suggestions.json`，命令输出 `status=imported_human_review`、`judgment_status=human_reviewed`、`reviewed_pair_count=80`、reviewer=`me`；输出文件为 `data/evaluation/p05_human_reviewed_v2.json`。原候选集与复核包未被覆盖。
- 随后使用 v2 与原候选集分别运行 BM25，报告均完成；详见 [P05 验收记录](P05-acceptance.md)。
