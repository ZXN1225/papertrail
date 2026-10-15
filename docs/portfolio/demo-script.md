# PaperTrail 演示脚本

建议时长：3—5 分钟。演示分为离线可复现部分和可选真实服务部分；不要在未获授权时调用付费模型或导入未经逐篇许可检查的全文。

## 1. 离线展示（无 API Key、无网络）

在 `backend/` 使用锁定开发环境运行：

```powershell
uv run --locked python -m app.cli.evaluate_research_tasks
uv run --locked python -m app.cli.evaluate_p12
uv run --locked python -m app.cli.audit_fulltext_lineage `
  --pdf "2609.27579=../integration of RAG.pdf" `
  --pdf "2608.02037=../A  Heterogeneous 200 mm Silicon.pdf" `
  --pdf "2607.24663=../A corrective agentic hybrid RAG.pdf" `
  --pdf "2608.20519=../An integrated diffusion-weighted.pdf" `
  --pdf "2609.39773=../riemannian flow models with.pdf" `
  --pdf "2610.06874=../statistical turbulence and.pdf" `
  --pdf "2610.09789=../cooperation, Defection, and the commons.pdf" `
  --pdf "2610.10204=../Three-dimensional Largrangian.pdf" `
  --pdf "2610.12662=../evaluating llms for translating.pdf"
uv run --locked python -m app.cli.evaluate_ai_labeled_tasks `
  --dataset data/evaluation/ai-labeled-licensed-v1.json `
  --output ../data/storage/ai-labeled-v1-report.json
uv run --locked python -m app.cli.evaluate_multi_agent `
  --input data/evaluation/TEST-multi-agent-paired-v1.json `
  --dataset data/evaluation/TEST-multi-agent-taskset-v1.json `
  --output reports/TEST-multi-agent-paired-report.json
```

展示生成的报告：40 个 `TEST-*` synthetic tasks、P12 的未授权工具拦截与 mock token/状态、只读核对本机 PDF 与当前索引的 lineage（九篇 / 3,294 chunks / `pdfplumber-layout-v27`）、AI 标注的 53 题真实语料检索诊断（命中 @1 59.1% / @8 88.6%，明确标为 **AI 标注、非人工金标**），以及同题重复 trial 的单/多 Agent 成功率与成本比。Lineage 审计需要这九篇本机 PDF，但只计算文件 SHA 并核对索引元数据，不读取/打印论文摘录。Multi-agent 报告使用手写 synthetic fixture。明确指出这些是评测管线、安全契约和来源版本完整性回归，不是语义问答质量、真实模型表现或人工金标。

## 2. 工程实现 walkthrough

按以下路径打开源码和验收文件：

1. `backend/app/agent/harness.py`：预算、白名单、工具循环和终答校验。
2. `backend/app/agent/skills.py` 与 `backend/app/agent/skill_specs/`：Skill registry/hash 与权限约束。
3. `backend/app/mcp_server.py`：固定只读 MCP stdio 工具面。
4. `backend/app/retrieval/pdf_parser.py`、`backend/app/retrieval/fulltext.py`：PDF 结构元素、表格行、chunk locator 与许可全文检索。
5. `docs/research/R04-agent-runs-acceptance.md` 和 `R07-multi-agent-experiment.md`：运行状态与禁用的多 Agent 对照框架，以及明确的评测限制。

源码与测试覆盖“没有证据就拒答”、MCP 工具错误、Skill 不能扩大工具权限、Multi-agent 分歧不合并及 worker 失败隔离；这些项目如现场演示，应明确标注为 synthetic/mock 契约，不暗示是真实模型质量结果。

## 3. 可选本机 Web 演示

遵照 [`development.md`](../development.md) 启动后端和 Web。默认 SQLite 是空目录，因此不保证本地论文列表有内容。联网搜索 OpenAlex/arXiv 需要网络；真实 Agent 需要明确配置模型凭据，可能产生费用。没有模型时不要演示为 Agent 成功问答。

真实 PDF 演示使用前需确认每篇材料已登记许可并存在本地索引；当前九篇许可全文和 `pdfplumber-layout-v27` parser 只支持已验收的文本/表格/图注样例，不能把样例验收说成通用解析准确率——已实测的表头切词/错列与个别单字符丢失就是反例。扫描件 OCR、图像像素语义目前不支持。禁止用公开网页“能下载”推断全文许可证。

## 4. 结束时讲清的限制

- RAG 的自动确定性检查绑定来源、摘录和位置，不证明语义蕴含。
- 九篇获准 PDF 的指定版面样本已对照核验（其中 v27 的 16 项由独立 AI Agent 复核，**不是人工金标**）；未做随机/跨布局准确率测量，不支持 OCR 或图像像素语义读取。
- MCP 已通过 SDK/stdio 协议测试；用户在一个桌面 Host 中发现 5 个工具并成功检索一篇许可论文。其他 Host、重启持久连接和总体检索质量未覆盖。
- Skills 与 Multi-agent 已有六题单次真实对照和 PDF 人审，但样本极小；Skills 严格引用有效完成数为 2/6 vs 4/6，多 Agent 仅 1/6 consensus 且成本比约 2.20。不能宣称一般收益；Multi-agent 默认关闭。
- 后端当前全量 **291 passed、0 failed**（336 项被收集；45 个 error 来自本执行环境无法使用 pytest 临时目录），一个既有上游弃用 warning。远端 GitHub Actions 未运行，发布未授权。R01–R03 已在 9 篇真实语料上建成 53 题 AI 标注评测，但仍是 AI 标注而非独立人工质量门槛。
- 项目展示的是可复现的研究工作流工程，不是已证明达到统计质量目标的生产服务。
