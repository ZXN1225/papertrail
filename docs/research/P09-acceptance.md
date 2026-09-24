# P09 验收：全文许可登记与受许可 RAG

## 验收条件

- 仅本地导入 UTF-8 纯文本；没有任意 URL 抓取、PDF 下载或模型代替人判断许可的路径。
- 仅人工核对并明确确认的 `CC0-1.0` 与 `CC-BY-4.0` 可以发布到全文检索；未知、缺失、`CC-BY-NC-*`、`CC-BY-ND-*`、`CC-BY-SA-*` 及其它许可一律拒绝。许可证名称来自源方许可页面，不以 OpenAlex `is_oa` / OA 分类作为授权依据。
- 入库保留论文来源 ID/URL、文本来源 URL、许可名称/URL、核对时间、操作者标识、源文本 SHA-256、解析/分块版本和导入时间；保留逐段字符位置与可重建文档哈希。
- 文本长度、文件大小、分块大小、分块数有硬上限；拒绝无效 UTF-8、空文本、超限内容和未知论文 ID。相同内容幂等，变化内容新建版本，不静默覆盖历史。
- RAG 只检索当前已批准且未删除的 chunk；返回论文来源、许可归属、片段 ID、字符定位、相关度和原始文本。许可未批准或删除的内容不得通过 API、Agent 或缓存返回。
- Agent 的 `retrieve_paper_evidence` 改为接收 OpenAlex/arXiv 来源 ID，只输出已批准的有界证据；最终 Citation 带 attribution 与 evidence locator。元数据引用仍允许引用本轮观察到的来源记录。
- 删除全文会立即从活动检索中移除内容和 chunk，保留不含正文的删除审计（来源 ID、原内容哈希、理由、时间）；同一来源可在后续重新导入已审核内容。
- 测试覆盖 license allow/deny、未确认/unknown、路径和 URL 不可变、哈希/幂等/更新、字符位置、分块边界、超限、撤销删除、跨 OpenAlex/arXiv 和 Agent 引用反例。

## 明确不在本阶段

- 不自动查询或下载出版商、arXiv、OpenAlex 或仓储的全文；不读取 PDF/DOCX，不验证签名或自动识别许可证。
- 不宣称已检查版权、获得律师意见或证明任何具体论文许可。本地操作者必须逐篇查看原始许可页面并确认在其具体用途下允许处理。
- 不启用 embeddings/vector search、reranker、UI 和质量 benchmark；分别在 P10、P11、P12 处理。新建 RAG 夹具必须使用 `TEST-*` 与 `synthetic=true`，不可混入真实索引。

## 设计依据

- OpenAlex 对 OA 的判断是“免费可读”的宽口径；每个 location 有独立 license，license 可能为空；其 OA 分类包括较受限的 NC-ND。因此本项目自行执行更严格的许可白名单。
- [OpenAlex Locations 与 license 字段](https://help.openalex.org/data/locations/)
- [OpenAlex Works 的 OA 与 license 说明](https://help.openalex.org/data/works/open-access/)
- [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/legalcode.en)
- [Creative Commons CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/legalcode)
- [arXiv API 条款](https://info.arxiv.org/help/api/tou.html)：元数据 CC0 不意味着论文文件也属于 CC0；逐篇查看 arXiv 记录所示论文许可证。

## 实施结果

- 新增 SQLite migration 0003、人工确认的本地 `.txt` 导入 CLI、删除 CLI、当前批准全文 BM25 检索 API 和 Agent 工具。OpenAlex/arXiv 必须先在目录中有元数据记录。
- 准入只允许规范 URL 对应的 CC0-1.0/CC-BY-4.0；所有其它许可、未显式确认、非 HTTPS 来源都拒绝。代码不会对 text/许可 URL 发起请求。
- source/license/provenance/reviewer/attribution/check time/hash/chunker version 持久化。仅当前内容版本建立活动 chunks；内容变化保留历史版本；删除级联清除全文和 chunks，仅留哈希审计。
- Agent 最多接收 8 个片段，最终论文 citation 经本轮工具结果 allow-list 校验，并提供署名与 evidence chunk/字符范围。
- `uv run --frozen ruff check .`、`uv run --frozen ruff format --check .`：通过；`uv run --frozen pytest -q`：66 passed，2 条 Starlette/httpx 依赖弃用警告。
- `uv run --frozen python -m tools.export_openapi`：通过并生成仓库 OpenAPI 契约；基础检查、来源记录一致性检查、`git diff --check` 通过。
- 所有论文全文为测试函数内的临时虚构文本，使用隔离临时 SQLite；没有真实全文下载/提交，没有真实 LLM 或外部源请求。没有许可证法律判定或真实 RAG 质量报告。

## 本机验收补充（2026-09-23）

- 用户提供的 `arXiv:2609.25991` 文本经用户核对后导入本机数据库，许可为 CC BY 4.0，18 个 chunks。相同输入重复导入返回 `unchanged`，SHA-256 保持 `07ba6f68dc9ad4c1330ff9441f50360685591f27abfa3d461304bffb635af29e`。
- 用户运行 Agent 的负例对随机控制标识返回 `insufficient_evidence` 且无 citation；运行 trace 显示一次成功的 `retrieve_paper_evidence` 调用。正向问题可从该篇全文检索并生成带证据引用的回答；具体学术质量仍需 P12 数据集评估。
- 在 SQLite 备份保护下运行删除 CLI。删除后 API 与 Agent 工具均返回 `no_results`，0 chunks 被扫描；正文版本/chunks 清空，删除审计保留 1 条，元数据仍存在。随后用原 manifest 与 UTF-8 文本恢复，状态为 `approved`，原 SHA-256 和 18 chunks 均恢复；删除审计仍保留。
- 本轮后端全测 67 passed；Ruff check/format、OpenAPI schema 一致性、基础/来源登记检查与 diff check 通过。BM25 数据集重跑 8 个 query、10 篇文档，报告仍为 exploratory；候选 qrels 未人工复核。
- 此处证明的是本机功能链路和撤回/恢复行为，不构成对论文许可的独立法律判断，也不代表论文 QA 的普遍质量。
