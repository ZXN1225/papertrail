# API 交付边界

**所有接口目前均未实现。** 完整拟建路由见 PROJECT_SPEC §13；P1 起由服务代码导出 OpenAPI，前端客户端由契约生成，本文只记录边界，不维护第二份手写完整 Schema。

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
