# 核心数据语义

依据规格 §6—12。T02 已建立商品/来源/证据/事实/报价的强类型契约与 13 张 PG 表，详见 [字段、关系与实现边界](catalog-model.md)。I02 已实现 anonymous_sessions（摘要/到期）、profiles（会话唯一/当前 revision）、profile_revisions（复合主键/JSONB 快照/来源/创建时间）、request_limits（摘要键/分钟窗口/计数），详见 [会话设计](sessions.md)。下表中的总价、兼容性、评分与事务发布仍属后续阶段，尚无真实目录或生产部署。

| 概念 | 语义 / 不变量 |
|---|---|
| SKU 身份 | 厂商料号 + 地区 + 硬件 revision；配置指纹辅助；系列名不能报价；无料号不强行合并 |
| 事实 | SKU + 属性 + 类型化值 + 单位 + 条件 + 证据；冲突保留，不用最后写入覆盖 |
| 证据 | URL/文档、版本、哈希、实际采集时间、页码/段落/选择器、SKU 范围、审核记录 |
| 金额 | 整数分 BIGINT + ISO 币种；未知 null；非负；显示层才换算元 |
| 总价 | 商品数量×选中快照单价 + 已知运费 + 未含税费 + 选定服务费用；必要费用未知则 total_minor=null，保留 known_subtotal_minor |
| 已有件 | 新购成本为 0，但规格仍校验；不与缺价 null 混淆 |
| 报价快照 | listing 与精确 SKU 已匹配；地区、成色、库存、资格、税运费、observed_at/expires_at；默认当前报价最长 24h，来源或活动更早过期优先 |
| 时间 | UTC timestamptz，API ISO 8601 带时区；纯函数显式接收核验时间 |
| 缺失值 | null + not_collected / not_disclosed / conflicting / not_applicable；不填 0 或默认支持 |
| 约束来源 | explicit / inferred / default + message_id / confirmed_at；硬约束只来自明确用户指令或确认 |
| 兼容性 | 每条 pass/fail/unknown/warning + blocking + rule_version + evidence；阻断 fail→incompatible，必要未知/条件未满足→needs_verification，完整执行通过才 validated |
| 评分 | 固定锚点和版本；缺实测给上下界与覆盖度，不编 FPS，不跨条件混跑分 |
| 会话 | owner 服务端推导；revision 不可覆盖；expected_revision 冲突 409；不可见 404 |
| 数据发布 | 原始快照→解析→规范化→校验→待审→原子版本发布→outbox；失败不暴露半批 |
| 合成数据 | synthetic=true + TEST-*；隔离测试数据库；生产发布/推荐索引拒绝 |

关系主线：source → document → evidence → spec_fact → SKU；listing → offer_snapshot → recommendation_item；recommendation 保存画像、数据/规则/评分/报价版本。会话状态、公开知识、长期偏好分离，MVP 不实现自动长期记忆。

MVP 组合：单 CPU/主板/电源/机箱、一套内存、1 SSD、0/1 GPU，散热按包装证据区分自带与单购。内存套装数与条数分开。单零件查询无整机背景时返回“未检查整机”。
