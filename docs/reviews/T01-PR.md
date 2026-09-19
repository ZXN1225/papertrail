# T01：建立项目执行计划与基础文件

## 问题与成果

初始仓库只有空 README，缺少可执行的阶段安排和接续记录。本次归档用户规格，建立 17 步执行计划、T01—T16 台账、核心 ADR、数据/API 语义、来源与人工采集模板，以及模块职责和基础配置。

本 PR 仅交付第一步 T01；P0 来源核验、P1 运行环境和业务功能均未完成。没有真实商品、报价或已授权数据源，不复制参考仓库代码。

## 验证

- `python scripts/check_foundation.py`：检查基础文件、JSON 模板和空凭据默认值。
- `git diff --check`：检查补丁空白错误。
- 原始附件与 `docs/PROJECT_SPEC.md` 的 SHA-256 对照。

实际结果见 `docs/PROGRESS.md`。未执行应用构建、数据库迁移、业务或 UI 测试，因为相关服务尚未创建。

## 审查重点

确认第一步边界、下一步数据核验安排、17 步验收节奏与默认 CN/CNY 范围。不要把模板发布到真实目录。

## 手动 GitHub 操作

若本轮已推送，GitHub 切换到 `codex/t01-project-foundation` 查看文件；进入 Pull requests 创建或查看相同分支到 `main` 的 PR，正文使用本文件。先检查 Files changed 与验证记录，再由用户决定合并。PR 创建不代表已合并。

若尚未推送，在根目录运行 `git status`，确认自己的改动后精确暂存本轮文件并提交；再执行 `git push -u origin codex/t01-project-foundation`。GitHub CLI 可用时执行：

```powershell
gh pr create --base main --head codex/t01-project-foundation --title "docs: establish project plan and foundation" --body-file docs/reviews/T01-PR.md
```

继续开发前先确认本轮；下一任务 V01，不自动执行后续工程搭建。
