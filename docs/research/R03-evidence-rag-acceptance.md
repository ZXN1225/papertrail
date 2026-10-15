# R03：分块与证据级 RAG 验收

更新：2026-10-12。此阶段由确定性契约、synthetic regression 和四篇许可论文合计 10 题的单人候选支持度核验支持；新三篇六题的人审与指定来源 BM25 诊断见 [结果说明](R01-R03-real-evidence-pilot-result.md)。这些不是系统生成答案的盲评，真实语义质量仍需更大许可语料和复核任务集。

## 当前自动验收范围

- PDF/plain-text chunk 的最大跨度改为每块不超过 1,800 UTF-8 bytes；对常见 byte-level BPE tokenizer，这是 token 数量的保守上界，不依赖运行时下载模型词表。
- 检索文本与可引用证据分开保存：BM25/embedding 使用受限章节上下文，答案引用只使用由原文字符范围切出的 `evidence_text`；PDF 子块通过 `parent_element_id` 回连已存解析元素。表格检索上下文可重复标题/表头，但 citation excerpt 不包含合成的标题/表头。旧数据库迁移会将原 `text` 回填到两个新字段，已有向量仍绑定旧内容版本。
- 对 PDF parent element 的命中最多扩展同一元素或相同 section path 的前后相邻 child chunks，可跨页/解析元素；response 总扩展最多 2 个 sibling。按顺序构造最多 5,600 UTF-8 bytes 的上下文。扩展摘录逐项携带 child chunk ID、locator、parent element/page 和原文；Harness 将其加入本轮可验证 quotes 和 citation evidence。普通纯文本 chunk 没有 PDF parent，不做扩展。
- chunker 版本分别记录为 `paragraph-utf8-token-upper-bound-v3` 与 `pdf-element-structure-token-upper-bound-v4`，供重新导入/重建索引时隔离旧版本。数据库 locator 继续使用原文 Unicode 字符 offset，切块不能破坏引用定位。
- 表格块重复表标题和表头；超长数据行可拆分，但保留行 locator 与原文字符范围。
- Agent answer 文本必须与 claims 规范拼接一致；每项 claim 绑定本轮 observation 的论文 ID、准确摘录和 source field/chunk。元数据 abstract 不可冒充全文证据。
- 正文中的 OpenAlex `W123` 与新式/旧式 arXiv ID（含版本后缀）都必须出现在本轮对应 cited-ID 列表内；ID 归一化后仍须有本轮工具 observation，避免正文漏列 arXiv 文献。
- 每个结构化 claim 会对模型提供的逐项已验证 quote 做确定性一致性筛查：显式数字/常见单位必须匹配；若 claim 使用 Group、Condition、Dataset、Method、Model 等可识别标签，标签须出现在 quote，数字还须与该标签落在同一标点分隔片段并匹配；显式上升/下降方向词须有同向 quote 支持，简单否定也需与 quote 一致。错配返回 `unverified_evidence`。7 个 `TEST-*` 端到端合成情形覆盖正确结果、错数字、错单位、方向/否定冲突、错组标签以及数字实际属于另一组。该规则是有限词表的机械筛查，并非完整单位换算或自然语言理解。

新增 CJK 正文/表格行回归覆盖 UTF-8 byte 上界与原文字符 offset。Migration 0009 后 PDF/fulltext/Harness 定向组曾 46 passed；同 parent 扩展定向组曾 37 passed；跨页同 section path 扩展定向组 38 passed。回归确认 retrieval_context 可跨相邻解析元素，excerpt 仍按独立 chunk ID 和源 offset 引用；表格 context 可含标题/表头而 excerpt 精确为原文数据行。正文引用漏列检查覆盖 OpenAlex 和 canonical arXiv ID（含版本）。R03 真实人工抽样标注见 [R03 用户核验包](R03-user-evidence-review-pack.md)，机器可读记录已绑定单篇全文索引哈希；当前全后端 `219 passed, 1` 个 Starlette/AnyIO 上游弃用 warning，执行环境说明见 [R08](R08-acceptance.md)。

## 明确限制与未完成工作

- 1,800 bytes 是保守上界，不是指定 LLM tokenizer 的精确 token 计数；provider usage 仍是运行后得到的观测值。若将来要按具体模型精确计数，应显式固定 tokenizer 版本和离线词表来源。
- 当前 parent 扩展仅取相同 section path 下相邻的最多两个 child；检索排序仍基于命中 child 的 BM25/Dense/Hybrid 分数，不会展开整个 section 或跨不同 section 做语义关联。语义支持判定也仍未实现。
- exact quote/来源/定位绑定和有限词表的数量/单位/方向/组别一致性筛查均不等于语义蕴含。当前规则不执行通用单位换算、复杂否定/比较理解或跨句/跨表格条件推理；真实 evidence recall、数值/单位支持率、可答/不可答任务成功率未评测。
- 四篇真实许可 PDF 的 10 题候选回答支持度由同一用户分两批人工标注；新三篇六题还标注了原文可答性。没有独立双人复核、系统生成回答的盲评或足够样本量。因此仍没有通用 RAG 答案质量结论；40 题 `TEST-*` lexical regression 只验证评测代码和词面行为。
- 三篇新许可 PDF 的 [六题核验包](R01-R03-real-evidence-pilot-review.md) 在人审前冻结问句、候选回答、指定来源和本机只读 BM25 前 8 项（[原 JSON](R01-R03-real-evidence-pilot-v1.json)）。用户标签单独保存在 [审阅 JSON](R01-R03-real-evidence-pilot-human-review-v1.json)，描述性结果见 [结果说明](R01-R03-real-evidence-pilot-result.md)。R1/R4 指定来源未进前 8，不能把候选答案支持判断当检索命中；对照 Skills/多 Agent 还需预先固定模型和预算。
