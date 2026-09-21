# API 交付边界

**I01 健康/状态、I02 会话/画像与 T03 管理员导入接口已实现，其余为后续计划。** 服务代码导出 [OpenAPI](openapi.json)，前端类型由契约生成；本文只记录边界，不维护第二份完整 Schema。

| 已实现接口（均带 /api/v1 前缀） | 语义 |
|---|---|
| GET /health/live | 200 alive，不依赖数据库 |
| GET /health/ready | 200 ready 或 503 not_ready，checks.database/redis 表示依赖状态 |
| GET /platform/status | 正常时 200 foundation/not_initialized、recommendation_available=false、data_version=null；依赖异常 503 标准错误 |
| POST /sessions | 首次签发匿名身份，已有有效 cookie 则复用；返回 expires_at/csrf_token/profile |
| GET /sessions/current | 恢复当前会话和最新画像；不存在/过期为 404，不自动创建 |
| POST /sessions/reset | 校验 CSRF，事务内删除旧内容并创建空会话，旧 cookie 立即失效 |
| DELETE /sessions/current | 删除当前会话与所有画像历史，204 并清 cookie |
| POST /profiles | 创建当前会话唯一画像，201 revision=1；已有画像为 409 |
| GET /profiles/{id} | 当前会话的最新版本；不存在/越权统一 404 |
| GET /profiles/{id}/revisions/{revision} | 当前会话的不可变历史快照 |
| PATCH /profiles/{id} | expected_revision + patch；保留未修改字段，冲突 409，不自动覆盖 |

0004_imports 在商品/证据领域表基础上建立版本发布表；not_initialized 描述公开目录能力尚未开放。Catalog*、Import* 等契约由服务生成。ready 不是可推荐状态。生产缺关键配置启动失败；开发 Redis 未配置时返回 disabled。

| 管理员接口（/api/v1/admin 前缀） | 语义 |
|---|---|
| POST /imports/preview | 不持久化的逐行验证、差异、冲突与发布门禁预览 |
| POST /imports | 幂等暂存，含快照哈希、问题与检查点 |
| GET /imports/{id} | 恢复持久任务与预览 |
| POST /imports/{id}/review | 绑定内容哈希/父版本、说明与事实选择；批准或拒绝 |
| POST /imports/{id}/publish | 批准后重验，原子追加并切换版本；重试返回原版本 |

管理接口使用独立 HTTP Bearer，不接受普通会话 cookie；未配置 503，无凭据/错误凭据 401。写请求 JSON、最多 1 MiB/500 行，管理员每分钟 30 次；浏览器校验 Origin。CLI 共用同一服务；操作规范与单管理员、人工整批等边界见 [manual-imports.md](manual-imports.md)。公开目录 API 仍未提供。

会话写接口要求 application/json、精确 Origin；除首次 bootstrap 外还要求 X-CSRF-Token 与 cookie 匹配。JSON 请求体最大 16 KiB，超限 413；非 JSON 415；来源/CSRF 拒绝 403。服务从 cookie 推导 owner，输入额外字段（如 owner_id）422。预算为严格整数分，范围 1—1,000,000,000；不接收浮点数、字符串或布尔值。画像字段、模式切换和来源元数据边界见 [会话设计](sessions.md)。

cookie 为 HttpOnly/SameSite=Lax，生产 Secure 且采用 __Host- 前缀，固定 24 小时过期。bootstrap 不续期，GET 不创建或修改画像。写限额为 SESSION_WRITE_LIMIT 次/分钟/会话，另有 peer 与 bootstrap 上限，429 带 Retry-After。敏感响应不缓存，不把身份放进 URL 或 localStorage。

后端响应设置 X-Request-ID 和 Cache-Control: no-store。健康检查 503 保留诊断结构，其余已实现业务错误使用 error{code,message,details,request_id}，422 不回显输入。尚未实现的路由维持框架 404。Next 只桥接白名单会话/画像方法与固定状态 GET，保留 cookie/Origin/CSRF/Retry-After，不接受任意 host 或 URL。

前缀 `/api/v1`。公开目录、受会话保护的画像/推荐/比较/导出、Agent 运行事件、管理员导入发布四类权限分开。工具与 API 使用共享服务。

| 阶段 | 路由组 |
|---|---|
| P1 | GET /health/live、GET /health/ready；匿名会话创建机制；POST /profiles、PATCH /profiles/{id} |
| P2 | GET /catalog/products 及详情/报价；GET /sources/evidence/{id}；管理员 imports / publish / data-quality |
| P3 | POST /compatibility/check |
| P4 | POST/GET /recommendations；修订、比较、Markdown/JSON 导出 |
| P5 | POST /agent/sessions；runs、events、轮询、cancel；DELETE session |

业务错误结构：`error{code,message,details,request_id}`。422 校验、409 revision/幂等冲突、404 不可见、429 限流带 Retry-After、503 依赖不可用；无候选是 200 业务状态。列表默认 20，最大 100，游标分页。

推荐和运行创建接受 Idempotency-Key，作用域 owner+path+key+body hash；相同键不同 body 返回 409。总价缺失时 budget_satisfied 不得为 true。SSE 只先传状态，候选必须校验后展示；event_id/run_id/revision 支持恢复并拒绝旧 revision 覆盖。

P1 的空数据页面必须诚实显示未准备好；若尚未实现推荐 API，不应返回模拟推荐来填满页面。正式接口以对应阶段验收为准。
