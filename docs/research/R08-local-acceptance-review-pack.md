# PaperTrail 本机最终验收核对包

日期：2026-10-13。**用户已明确回复“本机验收通过”**；下文保留验收时交付的固定摘要，不把它扩展为更大质量集或 GitHub 发布的验收。本文件只摘录结论和测试记录，不包含论文全文、模型生成答案、密钥或数据库。详细依据见 [六题最终结果](R06-R07-live-postfix-result.md)、[工程验收记录](R08-acceptance.md)与 [最终验收清单](R08-final-user-acceptance.md)。

## 1. 六题三臂最终结果

固定范围：三篇逐篇确认 CC BY 4.0 的论文、R1–R6 六题各一次、Skills 关闭/开启/双 worker 三臂。18/18 个运行项与 48/48 次模型请求完成；本地保守费用估算 USD 1.219042，服务商最终账单未知。原始 JSON 报告仅留本机 Git 忽略目录，SHA-256 为 `3e60cdfdcda8068348f04eb2c4a95d53226a68818484fb23302fad822042d5f2`。

| 题目 | Skills 关闭 | Skills 开启 | 双 worker |
| --- | --- | --- | --- |
| R1 | insufficient_evidence | completed | conflict |
| R2 | completed | completed | conflict |
| R3 | completed | completed | consensus |
| R4 | completed | unverified_evidence | insufficient_workers |
| R5 | unverified_evidence | unverified_evidence | insufficient_workers |
| R6 | unverified_evidence | completed | insufficient_workers |

`completed` 是机器证据门禁状态，`consensus` 还要求两个 worker 的文本与引用 ID 完全相同；它们都不是人工语义正确标签。用户对 A–E 五组、共 8 个**机器选定答案**核对原 PDF，均标为 `supported`：A=R1 Skills 开启，B=R2 关闭/开启，C=R3 三臂，D=R4 关闭，E=R6 开启。其余 10 个运行项没有人工正确/错误标签。D 的**旧** quote 缺 `(d)` 且误标 `paragraph`，即使答案事实获支持，旧引用仍不完整；E 的 PDF 视觉空格/换行与解析器文本严格同形未独立证明。人审标签见 [无生成正文的 JSON](R06-R07-postfix-human-review-v1.json)。

按“机器选定且用户确认回答支持”计算：关闭 3/6、开启 4/6、双 worker 1/6；若要求旧引用图注类型与标签也完整，关闭为 2/6。双 worker/关闭的费用估算比约 2.20，超过预定的 1.5 启用门槛，因此 R07 保持生产默认关闭。六题单次样本不足以证明一般准确率或 Skills/多 Agent 收益。冻结旧版 R1/R4 指定直接 chunk 未进入 BM25 前 8 条，未回填成检索成功。

## 2. Figure 5 修复与人工核对

用户已确认 [修复后图注核验片段](../../backend/reports/live_eval/figure5-v14-final-check.md)完整对应 `arXiv:2608.02037` PDF 第 9 页 Figure 5，没有混入正文；`(d)` 接 70 nm、`(e)` 接 220 nm。`figure_caption` 类型、bbox `[72.0,666.27,523.26,759.92]`、半开字符范围 `[0,767)` 与 PDF SHA-256 也获核对。解析器 v14 已本机重导入当前版本，R4 同题只读 BM25 检索前 8 条中的完整图注排第 1。这是新索引 smoke，不是旧试验的事后改分，也没有新模型请求。

## 3. 工程验收记录

以下是 2026-10-13 当前源码的本机检查记录；命令、环境差异和历史失败见 [R08 工程验收记录](R08-acceptance.md)。

| 检查 | 本机结果 | 限制 |
| --- | --- | --- |
| 后端锁定环境 `uv run --locked pytest` | 250 passed、1 条已有 Starlette/AnyIO 弃用 warning | 合成/自动测试不等于真实 PDF 准确率 |
| Ruff check 与源目录 format | 通过；`app tests tools` 共 79 个源文件格式合规 | 根目录 `ruff format --check .` 受不可读 `.pytest-tmp` 阻碍 |
| OpenAPI 导出 | 通过；契约 SHA-256 `3245c0037d716bf67c79d8dd2b9495f1524dbe3ef373eac09cfd32d967c6c9cb` | 无接口差异 |
| Web format、typecheck、生产 build | 通过 | 本机 pnpm `.bin` 缺失，以同一锁定依赖的 Node 入口运行 |
| Playwright E2E | 18/18 通过，正常退出 | 覆盖 375/768/1440 视口；人工偏好仍需检查 |
| 后端 `pip-audit`、Web `pnpm audit` | 退出码均 0、无已知漏洞 | 仅覆盖当时锁定依赖与审计数据库 |
| `git diff --check` | 通过 | 远端 GitHub Actions 尚未运行 |

本轮为便于人工 UI 验收，已启动本机预览：`http://127.0.0.1:3000/` 首页 HTTP 200，`/api/status` HTTP 200、`status=ready`、SQLite available。此预览的 LLM 与 embedding provider 均为 `disabled`，不会因浏览页面而调用付费模型。服务进程仅供这次检查，若之后不可访问，按 [开发说明](../development.md)重新启动或通知我恢复。

## 4. 尚未覆盖的范围和下一步

- OCR、扫描 PDF 及图像像素语义理解没有实现；目前图表检索依据结构化表格、图注和位置。
- 三篇新增许可 PDF 与既有单篇的人工核对仍是小样本，不能外推跨版式的总体正确率。
- R04 的多轮正文只在请求内存中，重启后的完整历史自动重放未实现；R07 保持生产默认关闭。
- 远端 GitHub Actions 未运行，因为用户要求最终验收前不上传 GitHub。

验收前曾请用户核对本文件第 1、3 节及本机界面；用户已明确回复“本机验收通过”。该回复只确认本机结果，**不构成上传 GitHub、创建 PR 或合并的授权**。
