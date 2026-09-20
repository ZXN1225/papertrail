# API 交付边界

**I01 已实现三个 GET 接口，其余为后续计划。** 服务代码导出 [OpenAPI](openapi.json)，前端类型由契约生成；本文只记录边界，不维护第二份完整 Schema。

| 已实现接口（均带 /api/v1 前缀） | 语义 |
|---|---|
| GET /health/live | 200 alive，不依赖数据库 |
| GET /health/ready | 200 ready 或 503 not_ready，checks.database/redis 表示依赖状态 |
| GET /platform/status | 正常时 200 foundation/not_initialized、recommendation_available=false、data_version=null；依赖异常 503 标准错误 |

当前只有 Alembic 版本表，没有商品表；not_initialized 描述未具备目录能力，不通过商品数量推断。ready 不是可推荐状态。生产缺关键配置启动失败；开发 Redis 未配置时返回 disabled。

后端响应设置 X-Request-ID 和 Cache-Control: no-store。健康检查 503 保留诊断结构，平台 503 和通用 500 使用 error{code,message,details,request_id}。尚未实现的路由维持框架 404，不代表业务权限/错误契约已全部实现。Next 只桥接固定状态 GET，故障时返回通用 503，不透出上游异常。

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
