# V01 数据来源可行性报告

检查日期：2026-09-20。方式：通过网页检索工具少量读取官方公开页面，人工核对；没有开发爬虫、登录账号、调用价格 API 或下载原始数据集。日期是本次工具检查日期，不代表搜索引擎抓取时间或厂商资料更新日期。工具未返回原站 HTTP 状态码，因此不杜撰 403/404。

本报告只保存自己的核验结论、来源链接和最小定位元数据，不保存厂商原文、图片、手册全文或可导入商品事实。机器可读记录见 [v01-source-review.json](../../data/manifests/v01-source-review.json)。全部 `publishable=false`，已发布 SKU/报价仍为 0。

## 结论与进入下一阶段的条件

| 类别 | 本次结果 | 权限与发布结果 | 决定 |
|---|---|---|---|
| AMD CPU | 5 个型号页面可读，盒装料号及主要字段可定位 | 未取得本项目公开再分发授权 | 保留为规格核验候选；不启用自动采集、不导入生产 |
| ASUS 主板 | 1 个产品规格页可读；随后发现条款限制自动采集 | 自动通道停止，不能按“5 个成功样本”计数 | 使用条款作为明确失败证据；后续取得允许使用的厂商/供应商资料再接入 |
| Lenovo PSREF 笔记本 | 5 个精确型号详情尝试：1 个空正文、4 个工具 Internal Error | CN 身份/字段闭环未完成；PSREF 适用授权未确认 | 通道失败报告；搜索摘要不代替精确 SKU 事实；后续人工核验/允许使用的规格文件 |
| 京东报价 | 门户正文仅 1 行，不能确认价格接口；无项目授权凭据 | 未调用 API，没有取得任何报价 | 明确选择人工报价维护路径；API 保持未配置 |

V01 完成的是“可行性研究和失败证据”，不是“四类来源全部接通”。可以进入 I01 空数据工程搭建；T03/T04 的真实数据验收仍依赖取得可用资料、完整 SKU 身份和发布权限。不会把其它地区笔记本或 CPU 全球规格直接当成中国零售 SKU。

## CPU：5 个规格页样本

以下只验证来源与字段位置，不提供采购建议、现价或跑分。盒装与 tray 料号不同，P2 必须分别处理包装、散热器与地区销售身份。

| 记录 | 官方页面 | 页面中盒装料号 | 字段可读性 | 关键缺口 |
|---|---|---|---|---|
| CPU-01 | [Ryzen 5 9600X](https://www.amd.com/en/products/processors/desktops/ryzen/9000-series/amd-ryzen-5-9600x.html) | 100-100001405WOF | socket、内存类型/上限、Default TDP、图形、包装散热字段 | CN listing、实际功率配置、发布权限 |
| CPU-02 | [Ryzen 7 9700X](https://www.amd.com/en/products/processors/desktops/ryzen/9000-series/amd-ryzen-7-9700x.html) | 100-100001404WOF | 同上 | 同上 |
| CPU-03 | [Ryzen 9 9900X](https://www.amd.com/en/products/processors/desktops/ryzen/9000-series/amd-ryzen-9-9900x.html) | 100-100000662WOF | 同上 | 同上 |
| CPU-04 | [Ryzen 9 9950X](https://www.amd.com/en/products/processors/desktops/ryzen/9000-series/amd-ryzen-9-9950x.html) | 100-100001277WOF | 同上 | 同上 |
| CPU-05 | [Ryzen 5 7600](https://www.amd.com/en/products/processors/desktops/ryzen/7000-series/amd-ryzen-5-7600.html) | 100-100001015BOX | 同上 | 同上 |

定位：General Specifications → CPU Socket / Default TDP / Thermal Solution (PIB)；Connectivity → System Memory Type / Max. Memory；Graphics Capabilities；Product IDs → Product ID Boxed。页面标题和盒装料号可确认，硬件 revision 与 CN 商家匹配未确认；不是 5 个已审核 CN 零售 SKU。

语义发现：包装散热信息可以区分自带/不自带；功率字段标的是 Default TDP，不能转称 CPU 最大功耗或整机峰值。内存速度带条数和 rank 条件，不能只保留一个最高值。以上语义需在 T02/T06 对应建模。

## 主板：可读样本与通道停止依据

已读取 [TUF GAMING B650-PLUS WIFI 规格页](https://www.asus.com/motherboards-components/motherboards/tuf-gaming/tuf-gaming-b650-plus-wifi/techspec/)。Model、CPU socket、内存槽/类型与输出接口可定位；页面要求另查 CPU 支持清单。未核验精确零售料号、板 revision、最低 BIOS、出厂 BIOS 与完整手册条件，因此不能判整机兼容。

随后读取 [ASUS 官方条款](https://www.asus.com/terms_of_use_notice_privacy_policy/official-site/) §1.8.4（自动数据获取限制）和 §5.1（有限使用许可），据此停止该自动通道，不继续凑 5 条。该项以实际条款作为“明确失败证据”验收，不宣称网站封禁，也不把某个技术错误当作授权限制。

## 笔记本：5 个详情页失败记录

候选型号来自 [PSREF 官方型号列表](https://psref.lenovo.com/Product/ThinkPad_E16_Gen_2_Intel?tab=spec) 与 [精确型号搜索结果](https://psref.lenovo.com/Detail/ThinkPad/ThinkPad_E16_Gen_2_Intel?M=21MA001PGQ)。只将它们作为探测目标；列表中的日区等海外型号不算 CN 覆盖。

| 记录 | 尝试的精确详情链接 | 本次工具结果 | 可用事实 |
|---|---|---|---|
| LAP-01 | [21MA001PGQ](https://psref.lenovo.com/Detail/ThinkPad/ThinkPad_E16_Gen_2_Intel?M=21MA001PGQ) | 0 行正文；搜索摘要有部分字段 | 未完成详情核验，不采纳摘要数值 |
| LAP-02 | [21MA00ANJP](https://psref.lenovo.com/Detail/ThinkPad/ThinkPad_E16_Gen_2_Intel?M=21MA00ANJP) | Internal Error | 无 |
| LAP-03 | [21MA00APJP](https://psref.lenovo.com/Detail/ThinkPad/ThinkPad_E16_Gen_2_Intel?M=21MA00APJP) | Internal Error | 无 |
| LAP-04 | [21MA00AQJP](https://psref.lenovo.com/Detail/ThinkPad/ThinkPad_E16_Gen_2_Intel?M=21MA00AQJP) | Internal Error | 无 |
| LAP-05 | [21MA00ARJP](https://psref.lenovo.com/Detail/ThinkPad/ThinkPad_E16_Gen_2_Intel?M=21MA00ARJP) | Internal Error | 无 |

Internal Error 是工具报告，原因未证实，不能说网站不存在或明确要求登录。未绕过限制或猜测内部 API。下一次解锁需要可阅读的精确型号文件/页面、CN 地区与对应屏幕/内存等字段，并确认允许用途；平台规格表不得替代 SKU 配置。

## 访问约定和权限记录

| 来源 | 条款核验 | robots 核验 | 权限结论 / 操作 |
|---|---|---|---|
| AMD | [条款](https://www.amd.com/en/legal/copyright.html) 限定使用范围，未提供本项目公开再分发授权 | [robots](https://www.amd.com/robots.txt) 可读；有路径限制，不是内容许可证 | `permission_required`；仅报告核验位置，不发布规格集 |
| ASUS | [条款](https://www.asus.com/terms_of_use_notice_privacy_policy/official-site/) 限制自动数据获取 | [robots](https://www.asus.com/robots.txt) 可读；列搜索/筛选路径限制 | `automated_collection_restricted`；停止自动接入 |
| Lenovo | 初次 terms-of-use URL 工具失败；[US 条款页](https://www.lenovo.com/us/en/legal/) 可读，但其适用范围不能自动等同 PSREF/CN | [PSREF robots](https://psref.lenovo.com/robots.txt) 工具 Internal Error | `not_verified`；不推定不存在限制或已获许可 |
| 京东 | [开放门户](https://open.jd.com/) 本次正文不足，未确认当前具体价格接口合同 | [robots](https://open.jd.com/robots.txt) 工具 Internal Error | `not_configured`；不调用未授权 API |

授权缓存期限、采集频率和再分发字段范围均为未知，不能把项目建议的 24h 报价 TTL 当作来源许可。本轮没有批量调度。以后自动来源启用前必须填写明确频率、范围和凭据引用。

## 报价：失败证据与替代路径

[京东商家帮助中心的 API 调用指南](https://help.jd.com/oapihelp/question-460.html) 展示需要授权得到的商家 Key，但内容为旧接口示例，不能证明现行价格 API 名称、权限范围或获取任何商品价格的资格。没有使用示例 Key，没有测试订单接口，也没有将京东到家/健康等其它业务平台文档冒充零售报价合同。

当前失败条件为：门户不足以定位可用价格接口；项目未提供获授权应用/凭据；无 5 条真实供应商报价文件。因此真实报价样本数为 0，以来源级失败记录 OFFER-01 验收，不制造 5 条相同失败冒充商品样本。

确定采用 [人工报价维护流程](../manual-offer-workflow.md)，后续实现 `ManualOfferProvider`。该路径并不自动解决资料许可；真实录入方仍需提供可用证据及允许展示范围。无真实报价时应用显示空数据或缺价，不填示例现价。

## 尚未解决、但不阻塞 I01 的事项

1. 三类规格来源的实际公开展示范围与自动采集权限；至少一个可靠规格适配器在 T04 前仍需落实。
2. CN 笔记本精确 SKU、板 revision/BIOS 支持链、GPU/机箱/PSU 等其它类别尚未核验。
3. 人工报价来源、审核人和有效期；T03/T05 前须提供可使用的真实资料。
4. 本轮仅 AM5 CPU 小样本，不满足最终至少两个桌面平台的数据目标。

所有问题保留在任务台账，不以 V01 完成掩盖 T03/T04 真实数据门槛。
