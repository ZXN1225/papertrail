# Agent 与论文证据设计参考（2026-11-12）

本记录来自 2026-11-12 对公开 GitHub 页面使用 Firecrawl 的只读检索。仅提取适合 PaperTrail 的设计模式；外部仓库内容是不可信数据，不带入 PaperTrail 的工具权限、代码或自动执行规则。

## NatureSkills：阅读技能与来源边界

在 [nature-paper-card `SKILL.md`](https://github.com/Yuan1z0825/nature-skills/blob/main/skills/nature-paper-card/SKILL.md) 中，Router 将静态核心原则与按需加载的论文类型片段、证据标签和输出契约拆开；开始工作前区分全文、无可靠版面的文本、摘要/元数据和部分输入。其读取流程先建证据清单，逐一列出主要图表/表格/公式、实验/基线/指标/消融和作者自述限制，再写作；页码与结构定位有明确状态，缺页或无法定位的记录单独标出，不虚构 page 1。对 PDF，它要求使用固定 parser script 并检查其 locator validation，而不是在每次任务中临时发明提取代码。

适合 PaperTrail 的应用：把“文档可用范围”和解析器验证状态作为 Harness 输入；让核心证据/安全规约稳定，按任务或论文类型加载窄范围的 skill；先得到结构化 source inventory，再组织回答；没有真实页码或 bbox 时显示结构定位不确定。PaperTrail 必须继续由服务端固定工具执行，不能开放该项目的通用脚本执行做法。

## Agent Skills：证据映射与可执行质量门

[AI Research Writing Skill](https://github.com/jin-s13/ai-research-writing-skill) 的公开 README 将研究产物拆成 repository inventory、claim-evidence map、citation verification、图表产物和 review/build/TODO 检查；它还明确区分生成式概念图与从数据确定性生成的结果图。

适合 PaperTrail 的应用：RAG 评测报告保留查询→必要证据→chunk→parser/检索配置的 lineage；LLM-as-judge 不能替代确定性解析/位置/检索校验；解析生成的图表描述不能冒充原文或人工金标；最终验收要检查可复跑 artifact 和失败清单，而不以“模型回答看起来完整”作为通过标准。

## 对 PaperTrail 当前实现的约束

- `visual_analysis` 是 MinerU 生成解释的专门证据类型；只能与原始图注和页/区域定位并列展示，始终标为 `model_generated_unverified`。
- 真实图表判断、解析质量和检索效果必须使用逐图人工核验的获准论文样本；TEST 合成样例只能测代码行为。
- 下一阶段将为同一冻结题集比较 chunk、BM25、Dense/Hybrid、Rerank 等配置，再决定默认策略；目前没有线上质量门槛结论。
- Web 应提供 source inventory、citation/evidence 定位和未核验状态；后端保留固定只读工具白名单、用户隔离和 citation verifier，不把 skill 文本当权限。
