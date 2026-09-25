# P20 Agent 代理超时验收

## 问题与验收条件

本机日志显示 Web `POST /api/agent` 固定在 15 秒返回 503，而后端 Agent 允许默认 45 秒、配置最高 120 秒。验收要求：

- Agent 代理等待时限覆盖服务端最大 Agent deadline，并留出响应序列化余量。
- 其他 Web 后端代理继续使用 15 秒上限。
- Agent 请求 schema、工具权限与后端 deadline 不变。

## 实施

- 为 `backendRequest` 增加可选超时参数，默认保持 15 秒。
- Agent 路由指定 125 秒上限，对齐后端 120 秒配置上限并留 5 秒余量。

## 验证

- `pnpm run format:check`：通过。
- `pnpm run typecheck`：通过。
- `pnpm run build`：通过。
- `git diff --check`：通过。
- `pnpm run test:e2e`：未完成。Playwright 的 Next dev server 启动遇到用户现有服务持有的共享 `.next` 开发锁；未停止该服务。
- `/api/status` 与后端 `/api/health/ready`：均返回 `ready`。用户随后提交实际研究问题并成功收到种子论文与双向引用候选完整答复，P20 长请求本机验收通过。
