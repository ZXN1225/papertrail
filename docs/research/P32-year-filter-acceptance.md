# P32 远程来源年份检索过滤

日期：2026-09-25。状态：实现与自动验收完成。

## 问题

P31 的年份筛选只对浏览器已载入的结果生效。对于关键词命中量很大的来源，第一页可能恰好都在年份范围之外，于是 UI 显示 0 条，且匹配总数仍是未按年份过滤的数量。此结果不能说明指定年份内没有论文。

## 修复

- OpenAlex 的 `from_year/to_year` 通过既有白名单日期过滤器作为 `from_publication_date/to_publication_date` 传入来源 API。匹配总数现在对应年份筛选后的集合。
- arXiv 的 `from_year/to_year` 通过既有 `submittedDate` 范围传入；其语义为提交年份，不等同于 OpenAlex 的出版年份。
- 页面初始检索和“加载更多”请求携带相同年份条件。UI 明确说明远程来源在检索时按年份过滤，修改范围后需要重新检索。我的文献库是本地已导入数据，年份筛选仍只覆盖已载入数据。
- API 对年份做整数、范围和起止顺序校验。OpenAlex 当前允许 1400–2100；arXiv 为 1991–2100。

## 验证

- `backend/.venv/Scripts/python.exe -m pytest -q --basetemp .local/pytest-p32`：116 passed。
- 后端 Ruff check 与 format check 通过；`tools.export_openapi` 成功并同步 `docs/openapi.json`。
- Web Prettier 与 TypeScript 检查通过。
- Playwright 复用用户已运行的 `127.0.0.1:3000` 服务；18 项、375/768/1440 三视口全部通过。E2E 检查年份范围同时出现在第一页和下一页请求中。
- `git diff --check` 通过。

本轮没有调用真实 OpenAlex/arXiv 服务，因此自动测试证明参数被正确传入，不是对实时来源可用性或具体关键词召回数量的保证。
