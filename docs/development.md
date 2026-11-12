# 本地开发

## R06/R07 六题真实模型小样本：本机密钥步骤

用户已批准三篇 CC BY 4.0 论文检索摘录发送 OpenAI `gpt-5.6-sol`，六题各一次、总费用上限 USD 2。模型实验仍需人工审阅生成答案，价格守卫是本机估算而非服务商账单硬限制。当前项目根 `.env` 尚不存在或没有 `LLM_API_KEY`，因此还没有发起本轮模型请求。

1. 在 `D:\papertrail-main` 下，若 `.env` 不存在，就把 `.env.example` 复制成 `.env`；如已存在，保留原文件并直接编辑。
2. 用文本编辑器打开根目录 `.env`，仅在 `LLM_API_KEY=` 后填入自己的 OpenAI API Key 并保存。不要把 Key 放在聊天、终端命令、Web `.env.local` 或 Git。此独立运行器会固定模型为 `gpt-5.6-sol`，无需改动生产环境的 `LLM_PROVIDER`/`LLM_MODEL`。`backend/.env` 不是项目 `Settings` 的读取位置。
3. 在 `D:\papertrail-main\backend` 运行 `uv run --locked python -m app.cli.run_live_eval`，只会核对冻结 SHA、许可和本机索引，看到 `dry_run_passed` 与 `credential_configured: true` 即可；此步不会调用模型或收费。不要自己运行带 `--execute` 的命令，避免与本任务重复计费；回复“已配置”，本任务再按获准的 6 题/$2 运行。

若本机尚无可用 OpenAI API Key，先保留当前文件与本地进度，待凭据可用后继续；无需重新导入 PDF 或重做六题人工标签。完整协议见 [R06/R07 live 预注册](research/R06-R07-live-eval-protocol.md)。

## Docker Compose 本地部署

仓库根目录提供 `compose.yaml`、后端/前端多阶段 Dockerfile。Compose 只把 Web 端口绑定到本机回环地址，后端 API 只在内部网络暴露；SQLite 使用名为 `papertrail-data` 的持久卷。容器启动前会检查 `/api/health/ready`，后端就绪检查会初始化/校验数据库 schema。未配置模型时，LLM 与 Embedding 保持关闭。

需要 Docker Engine 和 Compose 插件。首次启动会下载固定版本基础镜像及锁定依赖，必须能访问配置的镜像/包源：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build -d
docker compose ps
```

打开 <http://127.0.0.1:3000>。可通过根目录 `.env` 设置 `OPENALEX_API_KEY`；只有明确决定调用可能收费的服务后，再配置 `LLM_PROVIDER`/`LLM_API_KEY`/`LLM_MODEL` 或 `EMBEDDING_PROVIDER` 对应变量。密钥只传给后端容器，不提交 `.env`。

默认只发布 Web 的 `127.0.0.1:3000`。如确需局域网访问，可设置 `PAPERTRAIL_WEB_BIND=0.0.0.0` 并自行限制网络访问。后端不映射到宿主机端口。SQLite 数据保存在 named volume；普通 `docker compose down` 保留数据，删除 volume 会永久清除容器数据库。

`backend/.dockerignore` 排除 `.env`、SQLite、PDF、评测报告和本机缓存；Dockerfile 使用非 root 用户。Windows PowerShell 的 Docker Compose build/up、容器健康与首页/readiness smoke 已由用户本机完成；详细记录见 [R08 验收](research/R08-acceptance.md)。新增 CI 容器 job 使用 `ubuntu-24.04`，其官方软件清单列有 Docker Compose；job 仍需未来在 GitHub 上运行验证。[GitHub Ubuntu 24.04 runner inventory](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md)

## P11 Web 研究工作区

前置需要 Node.js 24.x 和 pnpm 11.x。先按上文启动后端，再开第二个 PowerShell 窗口：

```powershell
Set-Location .\web
pnpm install --frozen-lockfile
pnpm dev
```

浏览 `http://127.0.0.1:3000`。若使用默认地址，可不创建 `.env.local`；代理默认将请求转发到 `http://127.0.0.1:8001`。需要改地址时，只能在服务端 `.env.local` 配置 `PAPERTRAIL_API_BASE_URL`，不能将 OpenAlex、OpenAI 或 Embedding 密钥写入 Web 环境变量。页面状态栏读取后端 readiness；OpenAlex/arXiv 搜索需要后端可联网，本地文献库只查询本地 SQLite。Agent 会使用已配置的模型并可能产生 API 费用；LLM 未启用时会显示服务错误，不会伪造回答。

在 `web` 目录运行 `pnpm run format:check`、`pnpm run typecheck`、`pnpm run build` 和 `pnpm run test:e2e`。Playwright 以浏览器路由 mock 后端响应；`TEST-*` fixture 全部是合成数据，测试不连接 SQLite、OpenAlex 或 OpenAI。首次运行前若 Chromium 尚未安装，可执行 `pnpm exec playwright install chromium`。

Windows 本机运行 E2E 时，可先在一个终端启动开发服务器，让 Playwright 复用该服务；当前套件有 18 项用例：

```powershell
node ./node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3001
```

再开另一个终端运行 `pnpm run test:e2e`；完成后回到服务器终端按 `Ctrl+C`。GitHub Actions 在 Linux CI 中会自行启动与清理独立 E2E 服务。

## 前置环境

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

SQLite 目录会在首次就绪检查/导入时自动建立，无需单独安装数据库服务。OpenAlex 搜索支持无 Key 的小规模试用；配置免费 Key 可提升日请求额度。LLM 与 embedding 仍默认关闭。

## Windows PowerShell

```powershell
Set-Location .\backend
uv sync --locked --all-groups
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

浏览 `http://127.0.0.1:8001/docs` 查看 API，或访问：

- `http://127.0.0.1:8001/api/health/live`
- `http://127.0.0.1:8001/api/health/ready`

## macOS / Linux

```bash
cd backend
uv sync --locked --all-groups
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

## 配置

在仓库根目录执行 `Copy-Item .env.example .env`（如果 `.env` 已存在就不要覆盖），再用编辑器打开 `.env`。将 OpenAlex Key 填入 `OPENALEX_API_KEY=` 后面。无需引号，例如：

```dotenv
OPENALEX_API_KEY=你的OpenAlexKey
LLM_PROVIDER=disabled
LLM_API_KEY=
```

OpenAlex Key 可从 [OpenAlex API 设置](https://openalex.org/settings/api) 获取；免费 Key 用于提高日请求额度和查看用量。没有 Key 时 OpenAlex 也允许基础查询。不要把 Key 粘贴到命令行、URL、浏览器前端、聊天或 Git。`.env` 已被忽略；如果曾误提交或泄露，应在 OpenAlex 设置页轮换 Key。

你已有的 OpenAI Key 暂时不要启用：之后配置时放在同一个服务端 `.env` 的 `LLM_API_KEY=`，并按对应阶段设置 `LLM_PROVIDER` 和模型名。本阶段只调用 OpenAlex，不会调用 OpenAI，也不会消耗 OpenAI 额度。写入/修改 `.env` 后需重启后端进程。

客户端只访问固定的 `https://api.openalex.org` 官方域名；认证使用服务端 `Authorization: Bearer` 请求头。受控的直连接口包括 `GET /api/v1/papers/search`（Works 搜索）、`GET /api/v1/openalex/works/{WID}`（Work 详情）、`GET /api/v1/openalex/authors/search`、`GET /api/v1/openalex/authors/{AID}` 和 `GET /api/v1/openalex/authors/{AID}/works`。所有列表最多每页 25 条、限制在前 10,000 条；不下载论文全文。完整 schema 可在 `/docs` 查看。

Key 写入并保存后，在运行后端的终端按 `Ctrl+C` 停止旧进程，再重新运行上面的 Uvicorn 命令。访问 `http://127.0.0.1:8001/api/v1/papers/search?q=agent%20research&per_page=5` 进行一次小规模真实搜索。返回 JSON 中应有 `meta.count`、`results`、`fetched_at` 和可用的额度信息；不需要也不要把 Key 放入 URL。浏览器地址栏只包含公开查询词，不包含 Key。不要连续刷新；OpenAlex 会在响应中提供额度信息并对超额/过快请求返回 429。

## 导入本地论文元数据

从仓库根目录在已配置 `.env` 后执行一次有界导入。每次只请求一个 OpenAlex Works 搜索页，默认 10 条、最多 25 条；相同数据重复导入幂等，变化内容会建立新版本。命令只输出计数、快照 ID、哈希与本地数据库路径，不打印论文标题或摘要。

```powershell
Set-Location .\backend
uv run --locked python -m app.cli.import_openalex --query "retrieval augmented generation" --per-page 10
```

OpenAlex Works 单页最多可导入 100 条元数据；一次运行仍只处理指定的一页。较大的本地评测集可用 `--per-page 100` 创建一个内容哈希锁定的完整快照，不会下载论文全文。

数据库默认路径是 `data/papertrail.sqlite3`，可通过 `.env` 中的 `DATA_STORAGE_PATH` 改为绝对路径或相对项目根目录的路径；SQLite 文件被 Git 忽略。就绪检查 `/api/health/ready` 会创建/校验 schema 并在 SQLite 不可用时返回 HTTP 503。

只读本地接口：`GET /api/v1/catalog/papers?limit=20&offset=0` 列出本地结果；`GET /api/v1/catalog/papers/W...` 读当前版本，或加 `?snapshot_id=<快照ID>` 读取该快照中的历史版本；`GET /api/v1/catalog/snapshots` 列出导入批次；`GET /api/v1/catalog/snapshots/<快照ID>` 读取批次 lineage。空目录返回空列表，不生成示例论文。当前不下载或保存论文全文。

## P05 BM25 离线评测

确认 P04 的十条 OpenAlex 导入仍在本地 SQLite 后，在 `backend` 目录运行：

```powershell
uv run --locked python -m app.cli.evaluate_bm25
```

评测仅使用 `backend/data/evaluation/p05_gold_v1.json` 声明的固定 OpenAlex ID 与逐篇内容哈希；找不到完全匹配的快照或文档内容发生变化时会停止并报错。报告默认写到 `backend/reports/p05-bm25-report.json`，该目录已忽略，不会提交。报告包含 Hit@k、MRR@10、NDCG@k、分桶平均、空结果率、单查询均值/P95 延迟、数据集与语料哈希、BM25 和 tokenizer 版本。

默认数据 `p05_gold_v1.json` 是候选标签；用户已逐项复核的副本为 `p05_human_reviewed_v2.json`。两者都只有 8 个 query / 10 篇论文，结果均标为 exploratory。若要使用人审版本，显式传入 `--dataset data/evaluation/p05_human_reviewed_v2.json`；不能把小样本探索结果包装为大规模质量证明。该命令不访问 OpenAlex，不调用 OpenAI/embedding，也不下载全文。

### P05 人工复核候选标签

P05 的候选相关性分级需要你逐条审阅。先确认本机已导入与固定 P05 ID/内容哈希完全匹配的 10 篇快照，然后在 `backend` 运行：

```powershell
uv run --frozen python -m app.cli.review_qrels export
notepad .\reports\p05-review-pack.json
```

复核包列出 8 个查询与 10 篇论文的全部 80 个组合，包括题目、摘要、助手建议分级、`reviewed_grade`、`reviewed` 和备注。对每行填写 `reviewed_grade` 为 0—3，确认该行后把 `reviewed` 改为 `true`；备注可解释不确定判断。没有摘要时不要假装核验了全文，相关性按可用的标题/摘要信息判断。分级含义：0 不相关，1 背景相关，2 直接相关，3 高度相关。

逐项检查完后，用你认可的审核者标识导入为独立的新数据集：

```powershell
uv run --frozen python -m app.cli.review_qrels import `
  --pack .\reports\p05-review-pack.json `
  --reviewer "local-project-owner" `
  --confirm-human-review
```

这会新建 `backend/data/evaluation/p05_human_reviewed_v2.json`，不会覆盖候选文件或复核包。若你没有完成全部 80 行、标签越界、论文快照/hash 已变化或复核包基于另一版数据，导入会失败。该 CLI 不联网、不调用模型，也不修改 SQLite。导入动作中的 `--confirm-human-review` 表示你确认每一行都已由人检查；在你执行前，原始候选仍不是 gold。之后运行 BM25 时需显式指定 `--dataset data/evaluation/p05_human_reviewed_v2.json`；由于样本仍很小，报告仍会标记 exploratory。

## P06 Agent 本地运行

Agent 默认关闭 LLM。若要做后续真实模型烟测，可在服务端 `.env` 配置 `LLM_PROVIDER=openai`、`LLM_API_KEY` 和账户可用且支持 function calling/structured outputs 的 `LLM_MODEL`，并按需调整 `AGENT_MAX_STEPS`、`AGENT_MAX_TOOL_CALLS`、`AGENT_DEADLINE_SECONDS`；默认限制分别为 4 轮、8 次工具调用和 120 秒。`AGENT_DAILY_USER_TOKEN_BUDGET` 可设为不小于 `AGENT_MAX_TOTAL_TOKENS` 的正整数，以限制每个账号按 UTC 创建日统计的 token 预算；默认 `0` 表示不启用日额度。活跃 run 预留各自完整的单次上限，完成后按实际已报告 token 结算，并发创建通过 SQLite 写锁串行检查。该额度按 token 计，不是美元上限，也不能约束单次 provider 调用或供应商账单。保存 `.env` 后重启后端。

`AGENT_MAX_TOTAL_TOKENS` 是每轮 Agent 的累计上限，包含模型输入/输出和可计量的 embedding 输入，默认 300,000。`LLM_MAX_OUTPUT_TOKENS` 限制单次模型输出，默认 8,192；对推理模型也包含推理 tokens。预算守卫按 UTF-8 字节数预留输入，因此可能在实际用量低于上限时阻止下一次调用。可通过 `LLM_REASONING_EFFORT` 为支持该参数的模型设置推理强度；不设置时使用提供商默认值。当前本机 `gpt-5.6-luna` 设为 `low`，速度和成本可能降低，也可能影响复杂问题的回答质量。设置新的模型前请核对其支持的参数。修改后重启后端。

请求 `POST http://127.0.0.1:8001/api/v1/agent/ask`，JSON 格式例如：

```json
{"question":"请找出 RAG 检索质量评测的代表论文，并说明本地元数据能支持什么结论。"}
```

当前 Agent API 需要登录，可读固定只读工具可访问的 OpenAlex/arXiv 元数据、获准共享全文以及当前账号的私有 PDF。每个账号有独立会话历史；网页可列出并切换最近 100 个会话、新建会话或清空当前会话。消息读取最多 500 条，Agent 每轮最多取最近 8 条历史。个人论文库保存搜索结果的来源 ID 和带哈希的元数据快照，可按标题/ID 检索、打开来源页或移除。Agent 收到该用户最多 50 个已保存来源 ID 作为检索线索，必须重新调用只读工具取证；快照不能作为事实证据。用户可将 PDF 关联至本人文库条目，也可在“我的稿件”只填标题上传未发表论文；两种情况均需逐篇声明拥有版权或已获授权。文件、MinerU chunks 与检索结果仅供该账号私有处理，支持状态查看、失败重试和删除；个人稿件引用无公开来源链接，只显示私有定位。登录态 Agent 证据检索使用本地 BM25，不向 embedding provider 发送查询；若启用云端 LLM，问答命中的私有摘录仍会发送给所配置的模型服务。该声明不授予共享全文导入权限。若没有设置 LLM，接口返回 503 `model_disabled`。自动测试使用假模型/HTTP mock，不消耗 API 额度。

请求可附带客户端生成的 UUID `run_id`（Web 工作区会自动生成）：

```json
{"question":"请找出 RAG 检索质量评测的代表论文。","run_id":"8bf11a32-52a0-4f8e-a3f1-d7f5521748d1"}
```

同一 `run_id` 重复提交返回 HTTP 409，避免重复触发调用。响应包含 run ID、总耗时、token 用量和脱敏模型/工具 trace；状态可通过 `GET /api/v1/agent/runs/{run_id}` 查询，取消可通过 `POST /api/v1/agent/runs/{run_id}/cancel` 请求。取消是协作式的，在当前模型/工具调用返回后生效，不能强制中断 provider 网络请求。运行账本不保存原始问题、回答、工具参数或论文摘录；如请求带有用户 `conversation_id`，对话正文会单独保存到该用户会话表中，用户可清空或删除会话。遗留 `running` 状态在查询时标记为 `interrupted`，不会自动重放。模型与 embedding 使用同一累计观测 token 预算；provider 用量在调用完成后才可结算，因此单次在途调用可能使预算超出一次。上下文长度按字符近似，不等于 tokenizer token 额度。当前不估算货币费用。

本地 MCP stdio Server 可用 `uv run --locked python -m app.mcp_server` 启动。MCP 进程仅以 SQLite 引擎只读模式打开**已存在且已迁移**的数据库；首次初始化和 schema 升级需由 PaperTrail 后端完成。Host 配置应显式设置 `DATA_STORAGE_PATH`，不需要向 Host 传入 Agent/Embedding API key。Cursor Windows 配置范例及手工 smoke 步骤见 [R05 验收记录](research/R05-mcp-acceptance.md)。五个内置 Product Skills（问答、比较、综述、文稿修订、引用核验）由 Harness 确定性选择，并受固定工具白名单约束。文稿 Skills 只给修改建议，不会写回或保存用户文件。多 Agent 协调器仅用于受控实验，默认不接入生产 ask 路径；其当前框架范围和未完成的真实收益对照见 [R07 验收记录](research/R07-multi-agent-experiment.md)。

### 网页中的真实 Agent 烟测

自动化测试使用假模型，不会验证真实模型回答。要从网页发起一次真实调用：

1. 编辑仓库根目录 `.env`（保留已有设置），配置 `LLM_PROVIDER=openai`、自己的 `LLM_API_KEY`，以及账户当前可用且支持 Responses API 工具调用和结构化输出的 `LLM_MODEL`。密钥只放在服务端环境，不要发到聊天或填写在网页里。
2. 按 [Docker Compose 本地部署](#docker-compose-本地部署) 重启服务；若手动启动后端，停止旧进程后再从 `backend/` 启动，并确保该进程读取到模型配置。Web 代理也必须指向这个后端。
3. 登录持久化数据库中的账号。在“发现论文”里保存一篇论文的元数据；要验证全文证据，上传你有权处理的 PDF 并等待解析完成。“加入个人库”只保存元数据，不会自动下载 PDF。
4. 打开“科研助手”，先问一个可由该论文明确回答的问题，再追问一次以检查会话上下文。检查答案、右侧证据片段、论文来源和页码；再问一个资料无法回答的细节，确认助手说明证据不足。
5. 展开“运行记录与工程指标”，检查模型、工具调用和 token 用量。`AGENT_DAILY_USER_TOKEN_BUDGET` 是 token 限额，不是金额上限；费用上限需在模型提供方账户中设置。

启用云端模型后，问题及检索到的论文摘录会发送给所配置的模型服务。只使用你有权分享给该服务的数据。当前禁用 LLM、点选示例问题或运行 E2E 测试都不会产生真实 Agent 回答；验收模型行为必须从启用模型的网页发起请求。

## arXiv 元数据（P08）

arXiv API 无需 API Key。服务端接口为 `GET /api/v1/arxiv/search?q=...`、`GET /api/v1/arxiv/works/{arxiv_id}`；已导入的元数据可通过 `/api/v1/catalog/arxiv` 查询。Agent 使用固定工具 `search_arxiv_metadata` 和 `get_arxiv_metadata`。手动导入单页：

```powershell
uv run --directory backend --frozen python -m app.cli.import_arxiv --query 'all:"retrieval augmented generation"' --max-results 10
```

客户端限制每个进程至多每 3 秒发起一次请求；分布式多实例部署前须改用共享限流器。导入仅保存元数据，不下载 PDF/全文。元数据依 arXiv 条款为 CC0；论文文件许可另行判断。使用该 API 的项目应展示 arXiv 要求的致谢：`Thank you to arXiv for use of its open access interoperability.`

## 许可全文导入与检索（P09 / P17）

系统不会从网页下载论文。先在论文原始来源页面逐篇确认使用许可确实允许你的用途，再准备本地 UTF-8 `.txt` 或 PDF 文件和 JSON manifest。当前准入白名单仅为 `CC0-1.0` 与 `CC-BY-4.0`；`is_oa=true`、可免费阅读、仅有 DOI 或 arXiv 元数据 CC0 都不够。未知、NC、ND、SA 等许可不会进入共享全文索引。命令行确认不构成法律意见，也不代替你核对原始许可。

Manifest 示例（请用实际论文和许可证据替换示例值；不要将全文或真实个人信息提交到 Git）：

```json
{
  "source_type": "arxiv",
  "source_id": "2401.12345",
  "text_source_url": "https://arxiv.org/pdf/2401.12345",
  "license_id": "CC-BY-4.0",
  "license_url": "https://creativecommons.org/licenses/by/4.0/",
  "license_evidence_url": "https://arxiv.org/abs/2401.12345",
  "reviewer": "local-project-owner",
  "attribution": "作者、论文标题、arXiv:2401.12345, CC BY 4.0"
}
```

只有当你已从允许的来源合法取得文件并核对许可后才执行。文本输入必须是 `.txt` 且不超过 8 MB；PDF 输入上限 40 MB / 500 页。PDF 默认由本机 MinerU 解析版面、表格、公式和图表，并保留页码/元素区域；图表不生成推测性视觉描述。首次使用前需安装并校验本地 MinerU 模型（见下节）。旧 pdfplumber 解析器可通过 `PAPERTRAIL_PDF_PARSER=pdfplumber` 显式选择。论文 ID 需要先导入本地元数据目录：

```powershell
uv run --directory backend --frozen python -m app.cli.import_licensed_fulltext --manifest path/to/manifest.json --text path/to/paper.txt --confirm-license-reviewed
# 或导入经许可审核的本地 PDF
uv run --directory backend --frozen python -m app.cli.import_licensed_fulltext --manifest path/to/manifest.json --pdf path/to/paper.pdf --confirm-license-reviewed
```

### MinerU 本机模型准备

在 `backend/` 安装锁定的可选解析依赖；标准档使用本地 ONNX + llama.cpp 模型。模型目录在 `.gitignore` 中排除，不应提交模型或全文：

```powershell
uv sync --locked --extra pdf-mineru
New-Item -ItemType Directory -Force .\data\mineru-models | Out-Null
$env:MINERU_HOME = (Resolve-Path .\data\mineru-models).Path
$env:MINERU_MODEL_SOURCE = "local"
$env:MINERU_TELEMETRY_DISABLED = "1"
uv run --locked mineru-kit models download --tier standard --small-backend onnx --vlm-engine llama-cpp --source huggingface
uv run --locked mineru-kit models verify --tier standard --small-backend onnx --vlm-engine llama-cpp
```

首次模型下载需要网络并占用数 GB 磁盘；解析本身在本机执行。Docker 使用持久化 `papertrail-models` 卷，需在首次解析前将对应 tier 所需模型下载到该卷；服务不会在请求时自动联网下载模型。`PAPERTRAIL_MINERU_TIER` 支持 `basic`、`standard`、`advanced`，仓库默认 standard；只有 advanced 开启 image/chart analysis，解析器返回中的生成描述带未核验标记且不作为 Agent 的逐字引用证据。私有 PDF 索引当前不保存/检索这些结构化视觉描述。私有 PDF 解析在本机子进程执行，30 分钟超时，远程 VLM 配置会被拒绝；该子进程尚无操作系统级网络/内存隔离。MinerU 输出经过页数、字符数、bbox 与结构转换边界校验；跨布局人工盲审尚未完成，因此这次接入不代表解析质量已经全面证明。

本机检查单篇 PDF 可运行 `uv run --locked python -m tools.evaluate_mineru_sample ../paper_test/<文件名>.pdf --tier standard`；命令只打印结构与耗时指标。加 `--save-review` 会将原文解析元素写入已忽略的 `backend/reports/live_eval/mineru/`，仅用于本机复核。五篇样本的探索性记录见 [MinerU 试验](research/mineru-five-paper-pilot-2026-11-06.md)。若 Hugging Face 大模型下载停滞，可用同一 `MINERU_HOME` 运行 `uv run --locked mineru-kit models download MinerU2.5-Pro-2605-1.2B-GGUF --source modelscope` 后重新执行 `models verify`。

目前真实样本抽查发现 MinerU 的表格单元格有错列，图注有错配和 OCR 错字。私有 PDF 的图表片段会保留供本机复核，但 Agent 检索暂不将它们作为可引用证据；依赖图表细节的问题可能因此明确返回证据不足。旧适配器版本的私有文档会显示 `reindex_required`，用户可重试解析。请勿将解析片段数量理解为可引用图表数量。

重复导入相同版本幂等；新内容产生新版本，只检索当前版本。查询许可证据：

```powershell
Invoke-RestMethod 'http://127.0.0.1:8001/api/v1/evidence/search?q=your%20research%20question&limit=5'
```

### P10 Dense / Hybrid 检索

BM25 仍是默认且不产生 embedding API 调用。OpenAI 官方 Embeddings 指南当前推荐候选 `text-embedding-3-small`（1536 维，单输入最多 8192 token；当前标价每百万输入 token $0.02），项目首次实验固定用 1536 维，不裁剪。开始前需自行确认账户可用性与当前数据处理设置；启用后，获准全文片段和检索问题会发送到 OpenAI Embeddings API。来源：[OpenAI Embeddings 指南](https://developers.openai.com/api/docs/guides/embeddings)。

启用前将服务端 `.env` 配置如下。Embedding API Key 单独放 `EMBEDDING_API_KEY`；默认保持 disabled。

```dotenv
EMBEDDING_PROVIDER=openai
EMBEDDING_API_KEY=你的OpenAI_API_Key
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EMBEDDING_PRICE_PER_MILLION_USD=0.02
```

`EMBEDDING_PRICE_PER_MILLION_USD` 用于本机估算报告，需按当前账户/模型价格手动维护；留空则费用估算为 null。该字段不决定实际账单。

重启后端后，先用 `--dry-run` 核对缺失 chunk 数、UTF-8 字节费用上限和配置模型；不调用 provider、不写数据库。全库缺失量和单篇都必须显式给出 chunk/费用上限：

```powershell
uv run --directory backend --frozen python -m app.cli.index_fulltext_embeddings --source-type arxiv --source-id 2609.25991 --dry-run --max-chunks 2000 --max-cost-usd 0.05
```

真实索引还必须同时提供 `--confirm-data-transfer`；这会将缺失 chunk 的全文发给 embedding provider。费用是 UTF-8 字节上限估算而非服务商账单硬限额。

然后 API 可按 `retrieval_method=bm25|dense|hybrid` 检索。Dense/Hybrid 的每个搜索问题也会发一次 embedding 请求；Hybrid 使用 BM25 与 Dense 的 RRF（k=60）。若某模型/维度索引不完整，接口返回 `embeddings_missing`，不会悄悄退回 BM25 冒充混合结果。没有启用 Provider 时 Dense/Hybrid 返回 503。Agent 全文工具包含相同检索方法参数；默认仍选 BM25，模型可明确请求 Dense/Hybrid。

独立 synthetic pipeline 不请求外部 provider，也不读写真实论文库：

```powershell
uv run --directory backend --frozen python -m app.cli.evaluate_hybrid
```

这项报告中的向量是固定 `TEST-*` 夹具，仅验证排名融合、指标和报告管线；`quality_claim_allowed=false`，不能当作 OpenAI embedding 的质量分数。真实向量 A/B 需要在固定授权语料和人工审核 qrels 上另行执行。

### P12 离线端到端 benchmark

执行单一命令，将 P10 的确定性检索评测与真实 AgentHarness 的离线 mock 安全场景合并为本机 JSON 报告：

```powershell
uv run --frozen python -m app.cli.evaluate_p12
```

默认输出为 Git 忽略的 `backend/reports/p12-offline-report.json`。报告包含夹具与 runner SHA-256、BM25/Dense/RRF Hit/MRR/NDCG、TEST 证据 span 的精确位置/支持断言、工具错误恢复、拒答与注入用例、mock token、Agent 调用数和本机 mock pipeline p50/p95。运行不需要 `.env`、SQLite、OpenAlex 或 OpenAI，不会联网。所有 mock 论文均为 TEST 数据；`quality_claim_allowed=false`、费用为 `null/not_measured_mock_mode`。mock 延迟不是 API/服务端延迟，mock token 不产生账单。

运行完整自动测试仍用 `uv run --locked pytest -q`。其中现有全文集成测试另覆盖许可门禁、真实存储 span locator、引用 lineage 与伪造引用拒绝；P12 报告里的固定 span 检查不替代这些测试。P05 的人工复核数据已存在，但只有 8 个 query / 10 篇论文，仍是探索性小样本；真实 PDF 结构质量、逐主张语义支持和用户单独批准的小批量 live Agent 评测尚未完成，不能对外宣称真实检索/Agent 质量提升或真实模型成本。

撤销某篇论文的全文并清除其所有版本和切片：

```powershell
uv run --directory backend --frozen python -m app.cli.delete_fulltext --source-type arxiv --source-id 2401.12345 --reason 'license verification failed'
```

删除审计只保留来源 ID、原内容哈希、理由与时间，不保留正文。没有获准片段时 API 和 Agent 返回 `no_results`，不会退回到摘要冒充全文证据。

## 验证

在 `backend` 执行：

```powershell
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv run --locked python -m tools.export_openapi
```

OpenAPI 契约输出到 `docs/openapi.json`；CI 会重新生成并检查提交版本没有差异。
# 私有向量索引更新

用户同意将正文发送至配置的 embedding 服务后，在 backend 目录运行：

```powershell
uv run --locked python -m tools.index_private_embeddings --user-id <账号UUID>
```

命令编码该账号缺失或文本已变化的可检索正文块，会产生 embedding 用量；不包含待验证图表。
新上传或重新解析后需再次运行。已索引块在 Agent 请求 hybrid 时使用 BM25 与向量召回的 RRF 融合；无可用向量时退回 BM25，返回的 retrieval_method 表明实际方法。
向量按账号、模型、维度和块文本哈希过滤；删除文档会级联删除向量。
