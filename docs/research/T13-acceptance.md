# T13 验收（实施前固定）

步骤 14 的第一部分实现审核手册文本的人工摄取、BM25 检索和可追溯引用；不接入向量库、网页抓取、用户上传文件或自动写入硬件事实。

- 管理员只能为当前发布目录内的来源文档暂存文本。来源必须处于 allowed/restricted，并同时有 `public_display` 与 `excerpt_storage` 许可；文本先进入 pending，只有独立审核批准后才可检索。
- 文档保存关联的 source document、冻结 data version、URL、标题、语言、地区、SKU 范围和 SHA-256；切片保留顺序 locator。原文以人工 JSON 输入提交，不发生网络请求。
- 检索只读 approved 文档且只读当前数据版本，按地区和精确 SKU 范围过滤。BM25 以型号/英文词元和中文双字词元计算，稳定排序；零命中返回业务状态，不补造引用。
- 每个引用返回 document/chunk/source-document ID、URL、locator、片段、分数和数据版本。片段用于定位证据，不能直接修改规格、报价、兼容性规则或推荐结论。
- Agent 新增只读 `retrieve_knowledge` 工具；它复用同一服务且仍受 Harness 白名单、参数校验与观察大小限制。
- 数据库变更使用 0006 迁移。测试覆盖精确料号排序、中文词元、零命中和稳定平分；真实 PG 环境覆盖许可、pending 排除、当前版本过滤和管理 API。
