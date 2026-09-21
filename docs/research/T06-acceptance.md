# T06 验收（实施前固定）

步骤 08 只实现 CPU、主板、内存的 C001—C003；不做候选搜索、排序、Agent 解释或 C004—C012 的兼容结论。

- 输入为至多一个 CPU、一个主板和一套内存的精确已发布 SKU；内存 `quantity` 是套装数量，单套条数与容量从有证据的规格事实读取。
- C001：`socket` 事实缺失为 blocking `unknown`；明确不同为 blocking `fail`；完全一致才 `pass`。
- C002：只接受该主板精确 SKU/revision 的 `cpu_support_entry` 事实。条目必须精确指向 CPU SKU，并附 `conditions.board_revision` 与 `conditions.minimum_bios`；当前 BIOS 缺失或格式无法比较为 blocking `unknown`，低于最低版本为 blocking `fail`。同 socket 不可替代此检查。
- C003：CPU/主板/内存的内存代际、主板插槽数、CPU/主板容量上限、内存套装条数和容量均必须有已选择的当前事实。缺失为 blocking `unknown`；代际不符、总条数超插槽或总容量超任一上限为 blocking `fail`。
- 每条结果返回规则版本、状态、阻断性、只用到的事实 ID 和机器可读细节；不从模型记忆或自由文本推导规格。
- T06 报告必须列出 C004—C012 未执行，且除明确失败外总状态始终为 `needs_verification`，不能因为前三条通过而标 `validated`。
- HTTP `POST /api/v1/compatibility/check` 复用受会话保护的领域服务；类别/槽位不符、重复槽位、未发布 SKU 和非严格整数数量拒绝。
- 测试仅在隔离 test_* PostgreSQL 以 synthetic/TEST-* 数据验证：socket 不同、同 socket BIOS 过低/未知、内存代际不同、容量/套装数量越界、全通过但整体仍待核实、版本变更及 HTTP 身份/CSRF 反例。
