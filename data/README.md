# 数据目录

manifests/source.template.json 是空的来源登记模板；samples/collection.template.json 是空采集单。它们包含 is_template=true、publishable=false，不能进入商品目录。当前没有可导入的真实或合成商品数据。

manifests/v01-source-review.json 是 V01 研究元数据（4 来源、12 次页面探测），保存来源定位、可读性和失败观察，record_kind=feasibility_review_not_catalog、publishable=false；不是商品数据集或导入请求。即使包含真实型号定位，也不可直接进入推荐索引。

P2 建立 schemas 下的正式导入 Schema；Schema 未实现前不要把模板直接当 API 请求。真实样本只有完成来源权限和事实审核后才入库/发布；原始资料、私密数据和索引置于被 Git 忽略的目录，保留期限遵守许可。

未来自动测试夹具必须使用 synthetic=true、TEST-* 和独立测试数据库，不能作为真实数据样本交付。
