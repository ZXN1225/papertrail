# 开发环境与后续部署

I01 compose.yml 提供 PostgreSQL 17.11 与 Redis 8.2.9，版本和镜像摘要固定，端口仅绑定本机。API/web 在本机运行，命令见 [开发指南](../docs/development.md)。本轮本机采用便携 PG，CI 用真实 PG/Redis；未执行本机 Compose 启动或生产部署。

开发 Redis 无密码，不可对公网开放。Redis 8 的 RSALv2/SSPLv1/AGPLv3 许可选项须在部署阶段按用途明确，不按旧版 BSD 处理。凭据、数据库与原始数据不入库。

P7 计划为 Nginx、web、api、worker、PG、Redis；部署前确定服务器、域名、TLS、凭据、数据权限、会话密钥和管理员身份。本轮没有生产镜像或 Nginx 配置。

发布顺序：备份→独立迁移→启动→ready→隔离合成冒烟→切流→观测。SSE 关闭代理缓冲；应用回滚不自动降级数据库，迁移先扩展后收缩。规划 RPO 24h/RTO 4h 须经恢复演练验证，当前没有恢复和性能实测。
