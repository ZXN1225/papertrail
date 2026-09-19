# 部署计划（待实现）

P1 提供开发 PostgreSQL/Redis Compose 和迁移命令；API/web 可本地运行。当前未创建 Compose 或 Dockerfile，因为运行时版本尚未核验。

P7 最小服务为 Nginx、web、api、worker、PostgreSQL、Redis；数据库和 Redis 不暴露公网。部署前确定平台、域名、TLS、凭据、数据许可、会话密钥和管理员身份。

发布顺序：备份→独立迁移→启动→ready→隔离合成冒烟→切流→观测。SSE 关闭代理缓冲。应用回滚不自动降级数据库；迁移先扩展后收缩。

规划 RPO 24h、RTO 4h，必须经隔离恢复演练验证；当前没有备份、恢复或性能实测。未配置管理员认证时写接口禁用，生产缺数据库或会话密钥必须失败。
