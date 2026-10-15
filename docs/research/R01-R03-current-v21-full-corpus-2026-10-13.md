# v21 九篇全文的全库 BM25 诊断

日期：2026-10-13。范围：9 篇已许可全文、217 页、4,871 chunks。六题沿用单人选定 reference，只做定位诊断；`gold_standard=false`、`quality_claim_allowed=false`。无模型或 embedding 调用。

## 修复和防错

原 SQL `LIMIT 2000` 会在排名前截断语料，扩库后部分来源无法进入候选。现在检索与 embedding 索引枚举均读取完整选定范围，硬保护值为 50,000 chunks；超限拒绝输出部分排名。该值尚未经过规模性能测试。

评测器核对活动 arXiv 来源集合与冻结清单完全一致，逐来源核对许可/内容/parser lineage；结果逐项核对来源及 hash，校验扫描数量和截断标记。repository 支持仅限定 source_type 的内部全库诊断，公共证据 API 仍要求 source_type/source_id 成对。

## 结果

| 任务 | 单篇限定排名 | 九篇全库排名 |
|---|---:|---:|
| R1 | 5 | 前 8 未命中 |
| R2 | 1 | 前 8 未命中 |
| R3 | 1 | 1 |
| R4 | 1 | 2 |
| R5 | 2 | 4 |
| R6 | 3 | 3 |

每题扫描 4,871 chunks、`truncated=false`。全库已选参考命中 4/6；不能解释为人工 gold recall，亦不能从本样本推出扩库质量收益。R1/R2 漏命中保留，不修改参考或题目以获得更高分。

清单：`backend/data/evaluation/arxiv-r01-r03-current-v21-full-corpus-v1.json`，SHA-256 `8ace61cd67ad078cf981e22efd26f01703aa237b61a432d5491505eebce78856`。

本机忽略报告：`backend/reports/current-index-full-corpus-v21-final.json` 和 `current-index-full-corpus-v21-final-replay.json`；字节一致，SHA-256 `eccc6fd5f8f5e4cf0ab552686d05577ff709ee51531c54bbd3a612ae386d95ff`。历史报告未覆盖。

## 复现与工程验收

在 backend 目录运行（输出必须使用新文件名）：

```powershell
.venv\Scripts\python.exe -m app.cli.evaluate_fulltext_retrieval --dataset data/evaluation/arxiv-r01-r03-current-v21-full-corpus-v1.json --output reports/full-corpus-new-replay.json
```

- 完整后端：304 passed，1 条既有 Starlette/AnyIO 弃用 warning。使用项目 venv、`-p no:cacheprovider --basetemp tmp/full-corpus-final-tests-2`；本机 socket 测试经受控提权运行。
- 新增 2,001 chunk 合成回归，证明尾部可检索；边界与超限拒绝、语料集合遗漏、结果来源错配、扫描数量不足有测试覆盖。
- 首轮完整测试 303 passed/1 failed，发现公共 API 部分过滤参数行为变化，补回参数成对校验后全量通过。
- Ruff check、84 文件格式检查通过；OpenAPI SHA 保持 `be007df662be75f9df7e1d480baee2c7284cd02714227d504d57d20324e0c258`。
- Web 未修改，本轮未重复 Web 验收；未调用外部模型、未提交/上传。

剩余：新增 PDF 抽样人审、第十篇兼容许可全文、独立问题集与 holdout、全库漏命中诊断。解析 lineage 核对成功不等于内容准确率通过。
