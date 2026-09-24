# 任务台账

状态：done=验收完成；todo=未开始；blocked=有具体外部阻塞。阶段完成后等待用户确认。

| ID | 任务 | 前置 | 状态 |
|---|---|---|---|
| P01 | 项目章程、迁移评估、来源/Agent/评测边界 | 用户确认方向 | done |
| P02 | 独立应用骨架、锁文件、CI 与启动说明 | P01 用户确认 | done |
| P03 | OpenAlex 固定 API 客户端与契约测试 | P02 | done |
| P04 | 元数据快照、目录、来源 lineage | P03 | done |
| P05 | BM25 与人工检索金标评测 | P04 | done |
| P06 | 受限 Agent 工具循环与引用契约 | P05 BM25 baseline | done |
| P07 | OpenAlex 研究 API 能力补全与 Agent Harness 可观测性 | P03、P06 | done |
| P08 | arXiv 第二来源、ID 归一化与精确 ID 导入 | P04、P07 | done |
| P09 | 全文许可登记和开放许可论文 RAG | P04、P06、P07 | done |
| P10 | Embedding、Hybrid 与排序消融 | P05、P09 | done |
| P11 | 研究工作区 Web UI 与 E2E | P07 | done |
| P12 | 端到端 benchmark、工程指标与作品集交付 | P05、P07、P09、P10、P11 | done |
| P13 | 扩展论文检索评测集与 AI 标注诊断 | P05 | done |
| P14 | 检索方法对照与失败查询诊断 | P13、P10 | done |
| P15 | 简历展示文档、GitHub CI 与收尾回归 | P14 | done |
| P16 | 迁移当前仓库为 PaperTrail 并发布 | P15 | blocked_auth |

P05 的 80 项 qrels 已由用户导入为 human-reviewed v2，且 BM25 候选/人审对照已完成；小样本报告仍为 exploratory-only。细节见 [`research/P05-acceptance.md`](research/P05-acceptance.md) 与 [`research/P05-qrels-review.md`](research/P05-qrels-review.md)。P09 本机验收记录见 [`research/P09-acceptance.md`](research/P09-acceptance.md)。P10 实现、自动测试和用户本机 live smoke 均已完成。已增加本地 qrels 复核包工具，详见 [`research/P05-review-workflow-acceptance.md`](research/P05-review-workflow-acceptance.md) 与 [`research/P10-acceptance.md`](research/P10-acceptance.md)。P12 离线 benchmark、mock Agent 安全评测和作品集文档已完成，结果及 E2E 清理限制见 [`research/P12-acceptance.md`](research/P12-acceptance.md)。

用户已取得 OpenAlex 与 OpenAI Key；OpenAlex Key 已留在本机 `.env`，P03 完成一次真实搜索验证。Key 不通过聊天传递；本轮没有调用 OpenAI。

P13 已建立 100 篇/30 查询/3,000 pair 的候选评测集；按用户选择，生成了 AI 填分副本和探索性 BM25 诊断报告。原人工复核包保持未审核状态，AI 标签不作为人工金标。验收及指标限制见 [`research/P13-acceptance.md`](research/P13-acceptance.md)。

P14 已完成 BM25/Dense/RRF 的同查询对照、分桶指标和失败查询诊断；使用 `text-embedding-3-small` 产生 23,960 输入 tokens。报告仅作 AI-qrels 探索分析，`quality_claim_allowed=false`。详见 [`research/P14-acceptance.md`](research/P14-acceptance.md)。

P15 的 README、架构/评测介绍、CI、全文 PDF 忽略规则与最终回归已完成。P16 已完成本地根目录迁移；远程改名与推送受当前 GitHub 凭据失效和网络访问阻拦。

P11 研究工作区及自动验收已完成，结果见 [P11 验收](research/P11-acceptance.md)。用户确认启动的 P12 已完成，阶段报告见 [P12 验收](research/P12-acceptance.md)。P05 qrels 已由用户复核导入并完成 BM25 对照，但数据集规模较小；P13/P14 标签未经人工核验，仅支持探索诊断，不支持对外质量声明。
