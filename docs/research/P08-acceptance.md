# P08 验收：arXiv 元数据源与跨源标识

## 验收条件

- arXiv 固定走官方 Atom API；解析仅接受预期 Atom feed/entry，响应大小有界，拒绝 DTD/ENTITY；请求顺序串行、默认间隔至少 3 秒。
- 搜索与 ID 查询、页大小、offset 和 arXiv ID 均受界限约束；区分限流/上游错误/超时/无结果，不向客户端透出 XML 错误正文。
- 只接收并持久化 arXiv 元数据，不下载 PDF/源文件；记录来源查询、时间、许可口径、版本哈希和快照 lineage，重复导入幂等、变化追加版本。
- OpenAlex 与 arXiv 记录保存在隔离源表，不以标题相似度合并。自动交叉映射只允许标准化 DOI 完全相等；记录匹配方法和 DOI 证据，冲突或缺 DOI 不链接。
- API 和 Agent 通过固定只读入口调用；工具 schema 严格、引用只使用本轮工具观察中的 arXiv/OpenAlex IDs。
- mock 测试覆盖 Atom 正常/异常、实体拒绝、大小/字段限制、ID 版本归一化、3 秒限速、分页、快照/版本、exact DOI 映射反例和 Agent 工具 schema。

## 计划实施

- `app/sources/arxiv.py`：固定 API host、序列化限速客户端、有限 Atom 解析与 arXiv ID 归一化。
- schema migration 0002 增加 arXiv snapshots/works/versions/items 和 DOI-only crosswalk。
- 导入 CLI、只读搜索/详情路由和受限 Agent 工具；保留 OpenAlex 为独立主数据源。
- 每个请求只取一页、最多 25 项；本轮 mock 验证，不主动发起外网 arXiv 请求。

## 外部依据

- [arXiv API 用户手册](https://info.arxiv.org/help/api/user-manual.html)：Atom 响应、`search_query`/`id_list` 和分页。
- [arXiv API 使用条款](https://info.arxiv.org/help/api/tou.html)：metadata CC0、论文文件版权分离、legacy API 每 3 秒最多一次且单连接。
- [arXiv API Access](https://info.arxiv.org/help/api/index.html)：独立非商业研究项目需致谢，避免造成 arXiv 背书印象。

## 验证结果与边界

- `uv run --frozen ruff check .`：通过。
- `uv run --frozen ruff format --check .`：通过。
- `uv run --frozen pytest -q`：59 passed；有 2 条来自 FastAPI/Starlette 测试依赖栈的弃用警告。
- 根目录 `python scripts/check_foundation.py` 与 `python scripts/check_source_review.py`：通过；`git diff --check`：通过。
- 所有新来源和 Agent 测试使用 HTTP/model mock；未做线上 arXiv 请求、未调用 OpenAI、未验证真实 API 可用性或检索质量。
- 当前限流器是进程内共享；多进程/多副本必须换成共享协调器。仅拉取 Atom 元数据，PDF/全文仍由 P09 许可登记阶段处理。
