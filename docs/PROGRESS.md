# 项目进度

更新日期：2026-09-20。当前交付：步骤 04 / I02 + T11 基础。分支：codex/i02-sessions-profiles；起点：f108a2f。最终提交以 git log -1 为准。

## 本轮成果与边界

- 用户已确认 I01，授权继续一个步骤。完成匿名身份、24 小时需求保存、revision 历史、资源隔离、并发冲突、新需求/删除与过期清理入口。
- 0002_sessions 新增会话、画像、历史和共享限流表；服务集中校验严格整数分、用途/费用范围及模式条件。切换设备保留通用约束、清除不适用条件。
- HttpOnly/SameSite/生产 Secure 与 __Host- cookie；签名与摘要存储；精确 Origin、CSRF、JSON、16 KiB 请求上限；PG 原子共享限流，配置的 Redis 故障时拒绝写入。
- 首页可保存和刷新恢复；跨标签冲突不自动覆盖，失败不显示已保存；开始新需求/删除通过真实 API 清除旧画像。
- 没有商品表、真实 SKU/报价、推荐、管理员写接口或模型调用。T11 的 Agent 状态机、自由约束/锁定 SKU 等在 P5 扩展；不是本轮已完成的能力。
- 文档：sessions.md、development.md、research/I02-acceptance.md；PROJECT_SPEC 原文保留。

## 验证记录

- 本机真实 PG 后端 30 项通过：原基础测试 + 严格金额、cookie、CSRF/Origin、隔离/伪造/过期、快照/保留字段、切换模式、并发 2/409、删除、限流、Redis 故障拒绝。第三方客户端仍有两项已知弃用警告，未隐藏。
- 真实 API 浏览器 15 项通过，375/768/1440；桌面与手机截图已检查。测试入口强制 test_* 库和独立 3001/8001，不写用户预览数据库。TEST-I02 场景记录 synthetic=true；不接触真实商品索引。
- 最终本机复验：ruff 检查/格式、前端格式/类型/生产构建、OpenAPI/生成类型、基础与来源记录检查均通过；pip-audit/pnpm audit 未检出已知漏洞。首次浏览器失败来自名称不够精确同时匹配两个按钮/Next 播报节点，修正定位后全量通过，没有删除断言。
- [完整 GitHub CI](https://github.com/ZXN1225/Agent_Computer_Recommanding_Platform/actions/runs/35533228341) 已通过（实现提交 be36091）：30 项后端、15 项 E2E、真实 PG/Redis、锁定安装、契约无差异、格式/类型/构建和审计均通过。本机 Redis 显式关闭，成功连接证据来自 CI。后续文档提交以 PR 当前检查为准。
- 暂存补丁与 git diff --check 通过；本机随机凭据与跟踪文件比对通过，.env/.local/数据库未入库。

## Git 与接续

开始时工作区干净，#1/#2/#3 均 OPEN，未合并。本轮从 f108a2f 创建独立分支，[PR #4](https://github.com/ZXN1225/Agent_Computer_Recommanding_Platform/pull/4) base 为 codex/i01-engineering-foundation，只审阅第 4 步增量。实现提交 be36091，最终文档提交以 git log 为准。合并仍需用户另行授权，后续按顺序核对 base/diff。

本机预览已升级到 0002_sessions 并启动于 http://127.0.0.1:3000，API 8000 的 ready=200，便携 PG 55432；无生产部署。重启和升级先运行 alembic upgrade head。PID 文件在 .local/preview-pids.json（忽略入库）。测试使用 3001/8001，禁止复用可能过期的预览进程。

## 下一轮（必须等待确认）

步骤 05 / T02：商品精确 SKU、来源、事实、证据、报价关系与领域迁移，完善数据字典/约束/测试。D01 使用权限、D02 精确身份/BIOS、D03 真实报价仍未解除；不通过虚构商品补齐。后续生产配置、网关限流、周期过期清理、备份恢复仍在对应阶段落实。本轮停止，不自动进入 T02。
