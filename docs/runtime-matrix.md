# 运行时与依赖矩阵

## I01 实装（2026-09-20）

| 层 | 锁定版本 / 验证 |
|---|---|
| 工具 | Python 3.12.14（uv 管理）、Node 24.19.0、uv 0.12.10、pnpm 11.19.0 |
| API | FastAPI 0.141.1、Pydantic 2.13.5、pydantic-settings 2.15.0、Uvicorn 0.53.0 |
| 数据访问 | SQLAlchemy 2.0.54、Alembic 1.20.0、psycopg 3.3.6、redis Python 8.1.0 |
| 前端 | Next 16.3.5、React/React DOM 19.3.0、TS 5.9.3、Tailwind 4.3.3、PostCSS 8.5.28 |
| 验证 | pytest 9.1.1、ruff 0.16.8、pip-audit 2.10.1、Playwright 1.63.0、openapi-typescript 7.13.0、Prettier 3.9.8 |
| PG | 17.11；本机 EDB Windows 17.11-3 便携包；Compose/CI 为官方 17.11-bookworm 镜像 |
| Redis | 8.2.9-bookworm；Compose/CI 同一官方摘要，本机显式关闭 |

包元数据已由 PyPI/npm 实际查询和安装核验；Python 完整依赖见 backend/uv.lock，前端见 web/pnpm-lock.yaml。TS 采用 5.9.3 满足 openapi-typescript 的 ^5.x peer 约束。Compose/CI 中的摘要是 Docker Hub 对应标签核验的不可变镜像引用；Actions 也固定完整提交 SHA。开发服务器与 CI 均使用 frozen 安装。

本机真实 PG 已完成空库、重复升级、回滚与重新升级。Windows 缺 Docker/WSL 发行版，因此没有本机 Redis 成功连接或 Compose 启动成绩；CI 的实际状态见 PROGRESS.md/PR。API 的同步 psycopg 探测通过线程执行，避免 Windows Proactor 与异步驱动不兼容。

本轮 pip-audit 和 pnpm audit 未检出已知漏洞，只代表查询时已知漏洞库结果。第三方测试客户端仍有两项弃用警告（Starlette httpx/AnyIO），不影响测试成功，未隐藏警告；未来升级时处理。依赖许可各自保留；Redis 8 使用 RSALv2/SSPLv1/AGPLv3 多许可，生产部署需落实选项与履约，不以 BSD 假设发布。

以下为 V01 的历史候选记录；“本轮未安装”等表述只指当时，不覆盖以上 I01 实测。

## V01 候选记录

核验日期：2026-09-20。以下区分本机实测、官方支持说明、项目选择。官方文档可能滚动更新；页面版本提示只是候选，不是已解析安装成功或安全审计结论。I01 重新查包元数据/安全公告并提交完整锁文件，不能直接把 latest 写进部署命令。

## 本机实测

| 命令 | 本次结果 | 对下一步影响 |
|---|---|---|
| python --version | 3.11.9 | 可跑当前标准库脚本；不是计划后端 3.12 |
| node --version | v24.19.0 | 可作为 Node 24 候选，I01 核验补丁与升级 |
| pnpm --version | 11.19.0 | 候选包管理器，I01 packageManager 固定精确版本 |
| uv --version | 0.12.10，构建日期 2026-09-04 | 候选 Python 管理器；I01 固定版本 |
| Get-Command docker,psql | PATH 均未找到 | 仅说明命令不可发现，不能推断机器完全未安装；I01 检查环境再准备 PG/Redis |

本轮未安装、升级或启动任何服务。

## 选择与官方依据

| 组件 | I01 候选 | 核验依据与边界 |
|---|---|---|
| Python | 保留 3.12，I01 固定可用安全补丁 | [官方生命周期](https://devguide.python.org/versions/)：3.12 处于 security 阶段，计划支持至 2028-10；不是最新功能版 |
| Node | 24 LTS，固定安全补丁 | [官方发布表](https://nodejs.org/en/about/previous-releases)：24 为 LTS；不因框架最低要求可用就采用已 EOL 的 Node 20 |
| pnpm | 11.19.0 候选 | [官方兼容表](https://pnpm.io/installation)：pnpm 11 支持 Node 24；本机命令可运行。I01 以锁定安装验证，不自动追随文档 latest |
| uv | 0.12.10 候选 | 本机可运行；[官方平台说明](https://docs.astral.sh/uv/reference/policies/platforms/)核验安装目标；I01 固定工具与 Python 补丁版本 |
| Next.js | 16.x 稳定线；读取文档显示 16.3.5 候选 | [支持政策](https://nextjs.org/support-policy)列 16.x Active LTS；[安装要求](https://nextjs.org/docs/app/getting-started/installation)最低 Node 20.9、TypeScript 5.1；最终由 I01 包元数据、修复公告和构建定版 |
| React / TypeScript | Next 16 匹配的 React 稳定版本 / TypeScript ≥5.1 | [Next 安装说明](https://nextjs.org/docs/app/getting-started/installation)要求配套 react/react-dom；本轮不凭最低版本推定具体 peerDependencies，I01 解析锁定 |
| Tailwind | v4 配置路线候选 | [官方 Next.js 集成](https://tailwindcss.com/docs/installation/framework-guides/nextjs)：使用 @tailwindcss/postcss、postcss 与 CSS import；I01 实际构建核验 |
| FastAPI | 当轮受维护稳定版，配 Pydantic v2 | [官方版本策略](https://fastapi.tiangolo.com/deployment/versions/)建议测试后固定；Starlette 由 FastAPI 依赖解析，再由 uv.lock 锁定，不手动强塞另一版本 |
| Pydantic | v2，官方文档当前显示 2.13.4 候选 | [官方文档](https://docs.pydantic.dev/latest/)说明 Python 3.9+；I01 与 FastAPI 实测及锁定，不启用 v1 兼容层 |
| SQLAlchemy / Alembic | 2.0.x / 1.x；文档显示 2.0.54 / 1.20.0 候选 | [SQLAlchemy 平台说明](https://docs.sqlalchemy.org/en/20/intro.html)、[Alembic 文档](https://alembic.sqlalchemy.org/en/latest/front.html)；I01 使用实际 PG 迁移验证，不把文档版本当已安装版本 |
| PostgreSQL | 17，I01 固定当时安全补丁与镜像摘要 | [官方生命周期](https://www.postgresql.org/support/versioning/)列 17 支持至 2029-11；项目选成熟主版本，开发/CI/生产一致 |
| Redis | 8.x 候选，I01 核验具体维护版本/镜像 | [官方许可表](https://redis.io/legal/licenses/)列 ≥8.0 为 RSALv2/SSPLv1/AGPLv3 多许可选项；不能沿用“所有 Redis 都 BSD”假设，发布时记录选择及履约；不影响先搭建无数据 API |

这份矩阵完成了支持范围与候选方向核验，不宣称整个依赖组合已兼容。FastAPI、React、驱动、测试工具和容器补丁尚未固定，属于下一步的安装/解析产物。

## I01 必须交付

1. Python 3.12 精确补丁、Node 24 精确补丁、uv/pnpm 精确版本记录；包安装使用声明的工具版本。
2. pyproject.toml + uv.lock、package.json + pnpm-lock.yaml；选择稳定安全版本，不复制网页中的未固定 latest 安装命令。
3. PG/Redis 的真实可用环境与版本记录；缺 Docker 时先解决环境，不换 SQLite 或伪造迁移成绩。
4. 后端检查、前端类型/构建、空库迁移、依赖故障 ready=503、生产配置失败行为；实际命令加入 AGENTS。
5. CI 使用锁定安装；具体依赖许可、漏洞和不可变镜像策略按构建结果记录。
