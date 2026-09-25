# P27 Agent 回答安全 Markdown 渲染

日期：2026-09-25。状态：实现与自动化验收完成。

## 验收条件

- Agent 结构化文本中常用标题、列表、加粗、斜体、行内代码和换行可读呈现。
- Markdown 链接只有指向 OpenAlex、arXiv 或 DOI 官方域名的 HTTPS 地址才转成可点击链接。
- 不使用 `dangerouslySetInnerHTML` 或将模型输出作为 HTML 执行；不安全链接保持为普通文本。
- 浏览器 E2E 覆盖有效链接和 `javascript:` URL 拒绝。

## 实施与结果

- 前端新增轻量 Markdown 子集渲染器，使用 React 节点输出段落、标题、列表、强调、代码和安全链接；不引入新依赖。
- 链接协议必须是 HTTPS，host 精确允许 `openalex.org`、`arxiv.org`、`www.arxiv.org`、`doi.org`、`www.doi.org`；锚点使用新标签页并设置 `rel="noreferrer"`。未知主机或危险协议不会生成链接。
- E2E 加入合成 Agent 回答，验证加粗显示、OpenAlex 链接 href 和 `javascript:` URL 不可点击。
- Web Prettier、TypeScript 检查通过；E2E 15/15 通过，覆盖 375/768/1440 三种视口。隔离目录 Webpack 生产构建通过，见 [P28 验收](P28-isolated-production-build-acceptance.md)。
- Turbopack 在临时副本使用外部依赖 junction 时拒绝构建；Webpack 编译成功，未影响用户正在运行的 `.next`。没有增加依赖或调用外部 API。

## 边界

这是有限 Markdown 子集，不承诺支持表格、嵌套列表或任意 Markdown 扩展。论文引用仍由独立来源卡片和后端校验的引用契约呈现。
