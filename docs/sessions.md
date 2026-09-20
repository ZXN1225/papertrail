# I02 匿名会话与画像版本

这是步骤 04 的实现边界。没有账号、长期偏好、商品、真实报价、推荐或 Agent 运行。本轮不需要模型密钥。

## 用户行为

首页首次打开只读取已有会话；首次点击“保存需求”才创建匿名身份。可保存预算、多个用途、费用范围、排除品牌及当前设备字段。刷新从服务器恢复，未点击保存的修改仍只在页面内。保存成功显示版本号和会话到期时间。

两个标签页修改同一旧版本，只允许一个提交成功。另一页收到冲突并保留本地编辑，用户选择“读取最新需求”后替换本地内容，再决定如何修改，不自动重放旧 patch。网络异常时不宣称保存成功；先读取确认服务器状态，避免超时后的盲目重试。

“开始新需求”经界面确认后创建新的空会话并删除旧会话全部画像版本；“删除已保存需求”删除内容且清 cookie。其它旧标签页仍可保留本地文字，但旧身份/CSRF/资源已失效，不能继续写入旧数据。没有跨会话继承，也没有跨设备同步。

## 身份与请求保护

- 随机 256 位 token + HMAC-SHA256 签名；数据库只保存随机 token 的 SHA-256 摘要，不保存 cookie 原文。CSRF 为独立用途 HMAC，绑定完整会话 cookie。
- HttpOnly、SameSite=Lax、Path=/、无 Domain、Max-Age=86400；生产 Secure 与 __Host-computer_session，开发使用 computer_session。身份不出现在 API JSON、URL、localStorage 或日志中。
- 24 小时为固定会话有效期，不随读取/保存延长。服务端每次事务都检查 UTC expires_at；客户端 cookie 过期不是唯一防线。签名密钥轮换会使已有身份失效。
- 精确 Origin 校验先于解析；拒绝 null/缺失/未知 Origin 与 cross-site。全部会话写接口要求 JSON；bootstrap 也受 Origin/JSON 保护，其余写接口还要 X-CSRF-Token。允许域名不能随客户端 Host 头变化。
- Next 开发桥只接受固定路径/方法。转发原始 Origin、cookie、CSRF；不信任客户端 X-Forwarded-For，不开放任意 URL、SQL 或 shell。
- 流式读取限制 16 KiB。业务校验失败不回显原始输入，数据库异常为通用 503，返回 request_id 以便定位。
- SESSION_SIGNING_SECRET 少于 32 字符时，即使在开发模式也禁止会话读写（健康接口仍可用）；已有 init_env.py 会生成足够强度的随机密钥。

## 共享服务、版本与金额

HTTP 路由调用 app/profiles/service.py；未来 Agent 必须调用同一服务，不能直接更新 JSONB。每会话只建一个画像，revision 从 1 开始递增。所有写入在 PG 事务内先锁定会话行，然后校验所有者/expected_revision 并追加 revision；并发失败不会追加历史。旧快照不 update。

ProfileInput 使用 extra=forbid 和受限枚举，预算严格整数分，1—1,000,000,000；布尔值、字符串、浮点值与 null 均不可作为已确认预算。表单用十进制文本转换，6000.01 元准确变为 600001 分，不用浮点数累加预算。用途/费用范围无重复，排除品牌最多 20 个，每个最多 80 字符。未知预算需用户补填，不默认为 0。

当前字段为 mode、budget_max_minor、workloads、budget_scope、market=CN、currency=CNY、excluded_brands、pc_constraints.wifi_required、laptop_constraints.max_weight_g、component_category。PC/笔记本/零件模式各需 tower/laptop/component 基础费用范围；component 必须明确类别。

PATCH 仅改传入字段，嵌套条件合并；null 只允许清除可选字段，不能清除预算/模式/用途。设备切换保留预算、用途、地区和排除品牌，清除旧设备条件并将费用范围重置为新设备基础项，调用方可以明确提交新范围。未提供新的零件类别时切换 component 被拒绝。已有件/锁定 SKU、自由格式 hard_constraints、权重/优先级、推断确认以及 Agent 状态机在后续步骤扩展，本轮不把无法核验的商品 ID 保存为已确认锁定件。

每个顶层字段保存 origin=explicit/default、source=form/system、message_id=null、confirmed_at。保留字段的来源不变；自动重置为 default；用户提交为 explicit。嵌套条件在当前界面作为整组提交/确认，未来细粒度 Agent 修改需扩展来源结构，不把 inferred 自动当成硬约束。

## 数据库与限流

0002_sessions 从 0001_baseline 升级，建立 anonymous_sessions、profiles、profile_revisions、request_limits。身份→画像→历史使用 ON DELETE CASCADE，session_id 唯一保证每会话单画像。ready 只接受当前迁移版本。

写限流采用 PostgreSQL 原子 upsert 的共享分钟计数：每会话默认 60 次，bootstrap 每 peer 120 次，所有写入每 peer 300 次；超过返回 429/Retry-After。SESSION_WRITE_LIMIT 调整会话基数（1—600），其它两项按 2 倍/5 倍。即使请求被拒绝也提交计数。peer 使用 HMAC 摘要且不存原始 IP，不信任转发头；经 Next 代理时多个浏览器共享同一 peer 限额，是保守保护。生产网关可信代理/IP 策略与高负载优化仍在 P7 实现。

开发可关闭 Redis，但限流继续由 PG 执行；配置了 Redis 时其故障令会话读写返回 503，不退为无限制。没有以进程内字典代替多实例限流。限流旧窗口在后续写请求中清理；不依赖该表保存用户行为历史。

## 过期、清理与回滚

过期会话立即不可访问，但数据库实体需要执行清理命令才能物理删除。从 backend 工作目录运行：

```powershell
uv run --frozen python -m tools.cleanup_sessions
```

命令仅删除 expires_at 已到期的会话，级联画像历史，并只输出数量。本轮不创建系统定时任务；生产部署阶段配置周期执行。用户主动删除立即清除在线数据库内容，不声称能立即删除所有历史备份。

升级：停止旧预览 API，执行 `uv run --directory backend --frozen alembic upgrade head`，再启动新版本。新增表不修改 I01 基线或商品数据。只有隔离测试库演练 downgrade；对已有用户画像执行 downgrade 会丢失本轮数据，因此生产应用回滚不自动数据库降级，先保留/备份数据再决定。

## 验证范围

backend 的 test_profiles.py 使用 TEST-I02-PROFILE、synthetic=true 场景元数据及独立 test_i02_* 库，验证隔离、伪造/过期、CSRF/Origin、严格金额、历史、模式切换、并发、删除、限流与依赖失败。浏览器测试使用独立 test_computer，端口 3001/8001，不复用 3000/8000 的用户预览；每个场景记录 synthetic=true，品牌占位为 TEST-BRAND。不写真实目录或索引。

P1 的上述测试不替代 P7 的完整安全审计、压测、网关部署、备份恢复或全辅助技术验收。
