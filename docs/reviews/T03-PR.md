# T03：人工导入预览、审核与事务发布

此前只有空商品表，无法把人工资料安全变为已发布数据。本轮新增共享导入服务和独立管理员 API/CLI：预览逐行错误与差异，暂存输入快照，审核来源许可、精确身份和事实冲突；批准后在同一事务内追加记录、冻结版本、事实投影、当前指针与 outbox。重复批次/发布幂等，旧父版本拒绝，故障不暴露半批数据。

0004_imports 新增 6 张表并约束投影引用和命名空间。管理员默认禁用，认证独立于用户会话；审核者由服务端推导，限制 JSON 大小、行数、Origin 与写频率。CLI 支持 dry-run/source/resume，manual-v1 不做增量抓取，明确拒绝 since。通知消费提供租约、退避、恢复和唯一持久通知，未声称构建外部索引。

本机真实 PG 129 项后端通过，包括 CLI 和 HTTP 全链、迁移回退、幂等并发、审核冲突、不可覆盖历史、半途故障回滚、鉴权/限流、异常价格提示、未发布引用隔离和 outbox 重试。浏览器 15 项回归通过；前端构建、格式、类型、契约生成及依赖审计通过。[本轮完整 CI](https://github.com/ZXN1225/Agent_Computer_Recommanding_Platform/actions/runs/35601771742) 已通过（实现提交 42b19a7），真实 PG/Redis 下 129 项后端、15 项 E2E 及全部检查成功；文档提交后的最终状态以 PR 当前检查为准。

base 为 codex/t02-evidence-data-model（PR #5），起点 1fa9818；前五轮仍 OPEN，本 PR 只审查第 6 步增量，不合并、不部署。管理员工作台在 T15，公开目录在 T04，报价 Provider 在 T05。管理入口现阶段为后端 /docs 与 CLI。

真实数据验收仍 blocked：没有获得新授权资料/报价；所有测试为 synthetic=true/TEST-* 且在一次性 test_* 库，开发预览仍为空。T03 功能交付不代表真实样本端到端通过。详见 docs/manual-imports.md、docs/reviews/T03-demo.md 与 docs/PROGRESS.md；用户确认前不进入下一步。
