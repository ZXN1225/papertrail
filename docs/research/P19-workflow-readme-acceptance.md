# P19 验收：研究工作流闭环与 README

## 目标

让 Agent 能将自然语言研究问题转成可追踪的发现流程：初始检索、有限引用网络拓展、筛选/比较候选、按需读取已批准全文证据，最后给出带来源或明确缺口的综合回答。同步将 README 更新为准确说明实际能力、方法选择原因与评测边界的项目展示页。不制作演示图片或视频。

## 验收标准

- [x] 新增有界 OpenAlex 引用拓展能力，支持读取一个种子论文的参考文献与反向被引作品；固定官方 Works API、合法 Work ID、每个方向最多 10 个候选，不接受 URL、任意 filter 或任意字段。
- [x] OpenAlex Agent 搜索能结构化应用用户提出的发表年份范围与开放获取筛选；未给出约束时不擅自添加。开放获取标记不代表全文许可。
- [x] 每个候选返回与种子之间的关系方向/ID、OpenAlex 来源 URL 和必要元数据；引用边只表示 OpenAlex 收录的元数据关系，不推断论文支持/反驳关系。
- [x] Agent Harness 说明研究工作流策略：先搜索明确意图，需要拓展时沿引用图扩展并去重/比较，论文发现与论文结论分开，需要结论时仅从批准全文证据取证；检索失败/证据不足时如实报告。
- [x] 合成离线工作流测试验证“主题发现 → 引用拓展 → 有引用的回答”决策链、参数拒绝与无结果；HTTP 客户端 MockTransport 测试覆盖上游错误映射。不访问用户数据库或真实模型。
- [x] README 介绍用户工作流、引用拓展与事实边界、Harness/策略选型及原因、项目检索演进证据和评测限制；区分 P05 人工复核小样本与 P13/P14 AI 标签诊断，不声称未经证实的质量提升，不添加演示素材。
- [x] 更新 TASKS、PROGRESS、PROJECT_SPEC 与阶段记录；Agent Tool 暴露于既有 Agent API schema 中，公开 HTTP API/OpenAPI 无变化。保留本轮开始时已有工作区更改。
- [x] 后端全量测试 106 passed；Ruff check/format、OpenAPI 导出、Web Prettier/typecheck/build 与 Playwright 15/15 通过。根基础与来源审核脚本因当前检出缺失而无法运行；`git diff --check` 在最终检查中执行。

## 边界

- 不新增需要用户手工逐条判定的大规模数据集；不把 LLM 自动判断称为人工标注或 gold。
- LLM-as-judge 只有在能校准、能复现且不混同真实人工标签时才考虑；本阶段优先用确定性工作流契约评测，若无可校准 judgedataset，不新增貌似权威的质量分数。
- 不调用 OpenAI 模型或 Embedding API，不下载/导入新论文全文，不修改用户本机数据库或报告。
- 不推送、创建 PR、合并或部署。

## 当前状态

验收条件先于实现记录。本阶段已完成。

## 执行结果

- Agent 工具新增 `expand_openalex_citations`，引用方向 `references`、`cited_by` 或 `both`，每方向最多 10 条、一跳；候选携带 relationship provenance，摘要截断为 1,000 字符以满足 observation 预算。
- OpenAlex Works 搜索和引用拓展支持明确的年份范围与 `open_access_only` 白名单字段；未指定时不附加过滤。OA 标记只表示 OpenAlex 元数据状态，不充当全文许可。
- 新增客户端、工具参数与完整 Harness 流程回归；网络均用 MockTransport，未调用真实 API/LLM。
- README 展示 BM25 → 全文 RAG → Dense/Hybrid → Agent citation expansion 的能力演进，比较同题集 Small/Large 指标与估算费用，并说明 AI qrels 限制、未校准所以不使用 LLM-as-judge。
- OpenAlex 用法参考其[官方 API recipes](https://help.openalex.org/how-to/api-recipes/)与[官方过滤文档](https://help.openalex.org/api/filtering/)。
