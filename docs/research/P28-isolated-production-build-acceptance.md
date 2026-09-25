# P28 生产构建与依赖安全审计

日期：2026-09-25。状态：通过。

## 验收条件

- 验证当前 Web 源码可完成 Next.js 优化生产构建和 TypeScript 检查。
- 对当前锁定的 Python 与 JavaScript 依赖执行漏洞审计。
- 不停止或覆盖用户正在使用的开发服务输出目录 `.next`。
- 不将 `.env.local`、依赖目录、缓存或测试产物复制进临时源码副本。
- 构建完成后清理临时副本，不留仓库跟踪文件或临时配置。

## 执行与结果

- 将 `web/` 源码复制到 Git 忽略目录 `.local/p28-build-check`，排除 `.env.local`、`node_modules`、`.next`、`test-results`、`debug.log` 和 TypeScript build cache；依赖通过 junction 复用，构建期间未修改依赖目录。
- 默认 Turbopack 构建因该临时依赖 junction 指向仓库外而拒绝处理。没有改动开发配置或用户服务，改用 Next Webpack 构建器在同一隔离副本运行生产构建。
- Webpack 构建通过：优化编译成功、TypeScript 成功、8 个静态页面生成成功，App Router 所有路由完成产物生成。
- 构建退出后移除并核验临时依赖 junction，再删除整个临时副本；`web/.next` 开发服务目录未访问或改写。
- `pnpm audit --audit-level moderate` 报告未发现已知漏洞。项目虚拟环境未安装 `pip-audit` 命令，因此使用 `uvx --from pip-audit pip-audit --progress-spinner off --path .venv\Lib\site-packages` 临时运行审计器；同样未发现已知漏洞。锁文件未变更。

## 限制

- 此次是隔离副本中的 Webpack 生产构建；没有在用户开发服务目录上运行 Turbopack 构建。
- 依赖审计只表示审计当时公开漏洞数据库未报告已知漏洞，不构成安全保证。
- 本步骤未变更应用代码或项目依赖，也没有访问论文/模型 API。
