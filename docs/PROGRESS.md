# 项目进度

更新日期：2026-09-21。当前交付：步骤 06 / T03。分支：codex/t03-reviewed-imports；起点：1fa9818。最终提交以 git log -1 为准。

## 本轮成果与边界

- 用户确认 T02 后继续一个步骤；额度中断后续完成同一 T03，未进入 T04/T05。
- 新增受控 manual-v1 人工导入服务、管理员 API 与 CLI，依次执行预览、暂存、审核和发布。HTTP/CLI 复用同一领域服务；没有任意 SQL、shell 或 URL 抓取入口。
- 0004_imports 新增任务快照、数据版本、双命名空间当前指针、规范事实投影、outbox 与通知表。发布用单个 PG 事务：重验、追加记录、冻结版本、事实选择、切换指针与写 outbox 同成同败。
- 管理员使用独立 Bearer 摘要配置；默认禁用。审核人从服务端配置推导，普通会话 cookie 不能访问。请求上限 1 MiB、500 行、每管理员 30 次/分钟，跨来源写入拒绝。
- 预览与发布拒绝无许可来源、待确认 SKU、未匹配 listing、错误证据/单位、伪造审核、未来观察时间、旧父版本和未发布引用。冲突事实须人工选择；缺失事实/费用、历史报价、价格显著变化保留为警告，不假装可推荐。
- 测试合成批次只接受 APP_ENV=test 与一次性 test_* 数据库；真实与测试版本指针隔离。开发库已升级但确认 dataset_versions 为 0；未导入商品、报价或来源资料。
- [人工导入操作与边界](manual-imports.md)、[验收](research/T03-acceptance.md)、[演示记录](reviews/T03-demo.md)、[PR 说明](reviews/T03-PR.md) 可审查；PROJECT_SPEC 原文保留。

## 验证记录

- 本机真实 PostgreSQL：129 项后端通过，无跳过。覆盖 I02/T02 回归，以及迁移升级/回退、预览无写入、CLI/HTTP 完整流程、幂等/并发、审核冲突选择、旧版本保留、故障回滚、通知租约重试、权限/Origin/体积/限流、单位换算、测试命名空间与未发布引用隔离。第三方测试客户端两项弃用警告保留。
- 真实 API 浏览器 15 项通过，375/768/1440；本轮未改变用户页面。测试固定 3001/8001 和独立 test_* 库，未复用预览；导入样例均 synthetic=true、TEST-*。
- ruff 检查/格式、前端格式/类型/生产构建、OpenAPI/类型生成、基础与来源记录一致性检查、git diff --check 通过。pip-audit 与 pnpm audit 未检出已知漏洞；来源检查不等于来源授权。
- [本轮完整 CI](https://github.com/ZXN1225/Agent_Computer_Recommanding_Platform/actions/runs/35601771742) 已通过（实现提交 42b19a7），包含真实 PG/Redis、129 项后端、15 项浏览器回归、锁定安装、契约生成无差异及依赖审计。本地开发库已升至 0004_imports、dataset_versions=0；本机 Redis 显式关闭。文档提交后的最终结果以 PR 当前检查为准。

## Git 与接续

本轮基于 T02 已确认内容，保护中断前已有改动。#1—#5 仍 OPEN、未合并；[PR #6](https://github.com/ZXN1225/Agent_Computer_Recommanding_Platform/pull/6) base 为 codex/t02-evidence-data-model，只审查第 6 步增量。实现提交 42b19a7；未合并、未生产部署。

本地开发库已升级到 0004_imports，确认没有数据版本。首页 http://127.0.0.1:3000、API 8000 与 /docs 的最终重启验证在 PR 前完成；预览 PID 位于忽略入库的 .local/preview-pids.json。管理认证保持未配置，预览不接受导入。

## 下一轮（必须等待确认）

步骤 07 / T04/T05：只读目录查询、规格适配器及报价快照/总价函数。D01 使用许可、D02 精确身份/BIOS、D03 真实报价仍未解除；公开真实目录验收继续受阻，不能以合成数据抵消。本轮完成后停止，不自动进入下一步。
