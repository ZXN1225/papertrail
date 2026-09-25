# P30 引用扩展终答格式失败诊断

日期：2026-09-25。状态：用户确认引用扩展回答正常，已验收。

## 观测

- 新截图显示 OpenAlex 检索与引用扩展均成功，来源卡片有 6 篇记录，trace 中两次工具调用均为 ok。
- 首次回答带 `structured_output_invalid_json`；单次格式修复完成，最终状态变为 `insufficient_evidence`（没有 `structured_output_repair_failed`）。因此当前拦截点是模型把元数据问题错误标成证据不足，而不是工具/API失败。

## 实施

- 系统与修复提示明确要求：若请求只涉及书目信息或引用关系，成功工具结果中的部分元数据足以回答时，就回答可用部分并标记缺项；缺少全文不构成此类请求的证据不足。对论文 findings/methods 等结论仍要求获准全文。
- 修复提示要求只输出纯 JSON，列出四个 schema 字段及其类型，并禁止 Markdown fence/额外文本。
- 拒绝的回答仅添加固定诊断类别：`structured_output_empty`、`structured_output_invalid_json`、`structured_output_schema_invalid` 或 `structured_output_citation_validation_failed`。不记录回答正文、字段值或论文内容。
- 继续只允许一次无工具修复；修复后仍使用原有 FinalAnswer schema 与来源 allow-list 验证，不降低引用安全要求。

## 验收

- 自动测试验证各诊断类别，提示包含元数据任务充分性规则，且不暴露模型输出文本。
- 用户重启后端，并以之前的 OpenAlex 2022–2024 + 引用补充检索问题重新请求一次。应显示标题/年份/来源链接/关系，且不再把元数据任务标成证据不足；若仍失败，将运行记录状态与诊断 warning 发回。

用户随后确认此工作流已正常，P30 live 验收通过。
