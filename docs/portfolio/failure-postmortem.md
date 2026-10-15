# PaperTrail 失败复盘

更新时间：2026-10-13。只记录确实发生且影响验收口径的事件；它们是工程排障记录，不是质量成绩。

| 事件 | 影响 | 处理 | 剩余限制 |
|---|---|---|---|
| v14 许可 PDF 抽样发现 Table II strict 表头错位、Table 2 跨列拆分和 IVIM 下标错序；后续完整图注又发现 `(d)` / 70 nm 信息不完整 | 仅依赖合成边界测试会漏掉真实版面的表格与图注错误 | v15 修复表头、合并逻辑列并按 bbox 重提单元格；图注另以独立 parser 版本修复；用户对照原 PDF 核验指定样本，并统一四篇活动索引 | 指定样本通过不代表整体准确率；跨布局统计、OCR、图像像素语义未完成/不支持 |
| Playwright 首轮 12/15，三个失败来自页面重复呈现同一文本导致 locator strict-mode 冲突 | 测试无法稳定定位用户可见结果 | 将断言改为稳定且语义明确的 locator 后重新运行 15 项 | E2E 使用 mock 后端 |
| 受限沙箱中的 pytest TestClient socketpair 请求会停在测试开头 | 沙箱权限不足时，超时不能被当作通过或应用失败 | 在可用本机 socket 环境运行完整后端回归；当前 291 passed / 0 failed（另有 45 项因该环境无法使用 pytest 临时目录而报 error） | 有一个 Starlette/AnyIO 上游弃用 warning；复现时需说明执行环境 |
| v27 修复"丢词回挂"的首版按**单行**判断"这个词在不在" | 已在相邻行的表头词被当成缺失复制一份（`2607.24663` p10 行数 8→9、表头词重复） | 用全语料 v26↔v27 版本对比抓到；改为以整表文本为参照集，并补合成用例 `test_word_present_in_another_row_is_never_duplicated_into_an_empty_row` | 单行判定这类错误不会由单测暴露，必须做跨版本全语料对比 |
| 接着尝试的"整表字符预算贪心遍历"方案 | 解析文本里同名长词吃掉预算，正文单元格出现重复标签（`XAFPAY XAFPAY`、`CG-OMatG-IRL CG-OMatG-IRL`） | 相邻重复扫描发现后整条回退，改用"单字符按目标单元格预算、多字符按整表"的折中规则 | 说明字符级预算在有长词的解析文本上不可靠；已写入代码注释与升级记录 |
| 独立 AI 复核发现 `2610.12662` p15 有一个由 **Figure 2 图形文字层冒充的 `table` 元素**（带伪造 `Table 1` 标题、把坐标轴数字切成 `63`/`16`） | 一个看起来完全可信的结构化表格其实是假数据，且没有任何"这不是表格"的告警 | 新增规则：无 `Table N:` 标题且 bbox 完全落在图形区域内的表格候选一律拒绝并记 `table_inside_figure_region_rejected`；`2610.12662` 表格数 6→4 | 假表检测依赖图形区域bbox质量；纯矢量图仍可能无 image_region |
| AI 标注评测的首批 45 条可答题中有 1 条引用**不是逐字原文**（Agent 自称已自检通过） | 若照单全收，该题会被当作"检索失败"，污染指标 | 构建器按"引用必须在所指 chunk 中逐字存在"机械复核，丢弃并打印 `quote_not_verbatim`（最终 44/45 入库） | 说明生成方自检不能替代独立的机械校验层 |
| Web 安全审计发现 Next.js 锁定版本存在已知漏洞 | 依赖存在高危安全风险 | 升级至审计无已知漏洞的 Next.js 版本并更新 sharp/source-map-js 锁定版本，复跑 Web build/E2E/audit | 漏洞数据库会更新，需要 CI 持续审计 |
| CI 的 pnpm 固定安装版本与 Web `packageManager`/锁文件版本不一致；CI 未执行依赖 audit | 本机通过不保证 GitHub workflow 可复现同一依赖集或安全检查 | 将 CI 版本对齐 pnpm 11.25.0，增加 Python `pip-audit` 与 `pnpm audit` 门禁 | 本地等价命令通过；未提交，GitHub Actions 尚未运行 |
| 隔离后端新环境缺少 `pywin32` 和 `ruff` wheel 的本地缓存 | 离线同步无法从锁文件安装完整项目 | 按用户目标使用受控包源补齐锁定包；此前 clean-env pytest 176 项通过，本轮本机回归 183 项通过 | 首次冷启动需要网络或预热缓存 |

详细代码范围和测试命令见 [R00](../research/R00-acceptance.md)、[R02 PDF 结构验收](../research/R02-pdf-structure-acceptance.md) 和 [R04](../research/R04-agent-runs-acceptance.md)。
