# P21 引用关系与年份展示验收

## 问题

Agent 的 OpenAlex 引用扩展已返回出版年份和引用边方向，但 Harness 的引用账本只保留标题、来源 URL 等通用字段，研究工作区来源卡片因此不显示候选论文年份及其与种子论文的关系。读者需要从回答正文推断关系，结果也不便于快速检查范围。

## 验收条件

- OpenAlex `Citation` 结构保留工具观察到的 `publication_year` 与 `citation_relationships`；关系仅允许 `references` / `cited_by`，缺失年份保持 null。
- 同一论文经多次工具观察时，引用方向去重合并；不得由模型正文填充这些字段。
- Web 来源卡片展示可用年份与中文关系标签；一般搜索结果等没有引用方向时不展示虚构关系。
- OpenAPI 与类型同步；合成测试覆盖参考/被引标签、年份缺失和关系合并。
- 不发起真实 OpenAlex 或模型 API 请求，不读取/修改本机论文数据库。

## 实施与验证

- 后端 `Citation` 增加可空 `publication_year` 与有类型的 `citation_relationships`；Harness 只合并实际工具 observations 中的关系，对非法关系忽略，未观测到年份时为 null。
- Web `Citation` 类型与来源卡片同步展示出版年份、种子论文 ID 和关系中文标签。无引用边的普通条目不显示关系标签。
- OpenAPI 已重新导出。
- 后端 `ruff check`、`ruff format --check` 通过；`python -m pytest -q` 为 107 passed。仅有 Starlette/httpx 上游弃用提示。
- Web Prettier、TypeScript、production build 通过。15 项 E2E 在运行中的本机 Next 开发服务上通过，覆盖 375/768/1440 三种视口；临时 Playwright 配置已删除。
- `git diff --check` 通过；没有调用真实 OpenAlex、OpenAI 或 embedding API，没有访问/修改论文 SQLite。
