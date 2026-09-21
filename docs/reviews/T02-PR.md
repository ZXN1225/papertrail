# T02：可追溯商品与报价数据模型

此前数据库仅保存会话和需求，无法表达精确 SKU 与其来源证据。本轮建立 13 张空领域表和强类型记录契约：事实必须匹配属性类型/单位和 SKU 证据范围，报价必须匹配 listing/地区，未知金额保持 null，重复精确身份及 synthetic 混用由数据库拒绝。

0003_catalog 为冻结、自包含迁移，保留 I02 会话表；ready 要求新版本。OpenAPI Catalog* schemas 与前端类型同步，无新增目录或导入端点。详细字段、ER 图、约束和实现边界见 docs/catalog-model.md。

本机真实 PG 后端 94 项通过，含升级/重复升级/降级重建后画像保留及负面约束；真实 API 浏览器 15 项通过。ruff、格式、类型、生产构建、契约生成及依赖审计通过。测试使用 test_* 库及 synthetic=true/TEST-* 记录，无真实数据导入。本轮 CI 结果在推送后记录。

base 为 codex/i02-sessions-profiles（PR #4），起点 f7dc2b2；前四轮尚未合并，只评审本轮增量。没有生产部署、合并、数据发布、当前报价选择、预算或推荐能力。来源许可/精确资料/真实报价阻塞保持；配置指纹生成和导入/审核/发布在 T03，报价服务在 T05。

手动审查：查看 docs/catalog-model.md 关系图与空值约束；迁移后 `/api/v1/health/ready` 应为 200，`/docs` 可展开 CatalogSKU/CatalogFact/CatalogOffer，目录路由仍 404。首页需求保存/恢复仍可用，状态保持数据准备中。完成后等待用户确认 T03。
