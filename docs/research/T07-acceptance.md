# T07 验收（实施前固定）

步骤 09 完成 C004—C012 与整机聚合。每项只使用当前发布版本的已选择事实；缺少布局、尺寸、连接器、端口、包装或硬需求事实时返回 blocking `unknown`，不以默认值通过。

- C004/C007：主板和电源外形必须在机箱支持集合内。
- C005：GPU 尺寸必须不超过当前机箱限制；布局事实缺失为 unknown。
- C006：散热器支持 CPU socket；扣具或尺寸资料缺失为 unknown。
- C008：以 CPU/GPU 功率、75W 其它设备基线和 1.25 工程系数计算需求功率；PCIe 连接器也必须足够。
- C009：存储协议必须在主板支持集合内；插槽 key、长度或端口共享资料缺失不得判通过。
- C010：没有独显时，CPU 核显和主板输出均须明确可用。
- C011：仅检查请求中明确的 Wi-Fi、USB、PCIe 槽硬需求；没有明确需求返回非阻断 warning。
- C012：CPU、主板、内存、存储、电源和机箱均为必要件；CPU 不含散热器时必须有独立散热器。
- 聚合：任一 blocking fail 为 incompatible；否则任一 blocking unknown 为 needs_verification；所有 C001—C012 通过或非阻断 warning 才可为 validated。
