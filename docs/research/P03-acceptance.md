# P03 验收记录：OpenAlex 元数据客户端

日期：2026-09-23。分支：`codex/paper-research-agent`。

## 验收结果

- [x] 生产客户端固定访问 `https://api.openalex.org/works`；可选 Key 仅放 `Authorization: Bearer` 请求头。
- [x] 查询文本、页大小、翻页深度有界；固定 `select` 字段集只请求论文元数据，不下载全文。
- [x] 响应验证 OpenAlex Work ID 和分页 envelope，忽略未申请字段。
- [x] 429 与暂时性 5xx/传输超时只做有限重试；`Retry-After` 有 5 秒上限；认证、限流、超时、协议失败有独立安全错误。
- [x] 搜索接口 `GET /api/v1/papers/search` 返回来源元数据、检索时间及可用的额度观测字段，不返回 Key。
- [x] Mock 测试覆盖固定 host、Bearer 认证/keyless、字段投影、限流退避、认证失败、服务故障、超时、坏响应和参数边界。
- [x] 文档说明 `.env` 放置方法与 OpenAI Key 保管位置；当前没有读取本机 `.env`、打印或使用用户密钥。
- [x] 用户在本机 `.env` 配置 OpenAlex Key 后完成一次真实小查询。

## 自动验证

- `uv sync --locked --all-groups`：通过，锁定依赖 31 个。
- `uv run --locked pytest`：20 passed。
- `uv run --locked ruff check .`：通过。
- `uv run --locked ruff format --check .`：通过。
- 一次真实 `/works` 搜索（`retrieval augmented generation`，每页 3 条）：返回 3 条、meta.count=191142；额度头显示 limit=10000、remaining=9981、credits_used=10。只打印了记录 ID 和标题存在性，没有输出标题或密钥。
- 未调用 OpenAI、未下载论文全文。

首次真实测试暴露 `.env` 模板中的空 `EMBEDDING_DIMENSIONS` 会使配置解析失败；已设置 `env_ignore_empty` 并添加回归测试，修复后真实搜索通过。

## 当前 API 使用依据

- [OpenAlex 认证与限流](https://help.openalex.org/api/authentication/)说明 Key 既可放 `api_key` 参数，也可用 Bearer Header；本实现选 Header 以避免密钥出现在 URL，并限制请求频率。
- [OpenAlex Search](https://help.openalex.org/api/searching/)说明 `/works` 的 `search` 覆盖标题、摘要和全文索引；本项目只接收返回的 Works 元数据，不请求全文内容。
- [OpenAlex Select Fields](https://help.openalex.org/api/selecting-fields/)说明 `select` 只支持根字段，因此本客户端固定选择所需根字段。
- OpenAlex Works 当前支持 `per_page` 1—100；本项目 Works 搜索/导入与 SQLite 快照现采用每页最多 100 条，受限至单页导入，不执行无界同步。作者搜索仍限制每页 25 条。
