# AGENTS.md

本仓库延用 NL2PCB-Bench 的协作规矩（一个提交只做一件事、设计决策给选项、先查证再下结论、讲解用能运行的最小例子）。补充三条：

1. **评测侧与考场分开。** `dataset/<task>/bench/`、`verifier/`、`solution/` 是评测侧；`dataset/<task>/environment/` 与 `images/agent/` 是考场。改动前先问：这个文件会不会进 agent 镜像？`images/build.sh` 用 tar 拼 agent 镜像的上下文，`.dockerignore` 白名单约束 verifier 镜像的上下文，两处都不要绕过。
2. **不自己写 runner。** 容器、agent 适配、轨迹、并发、重试都交给 Harbor；本仓库只有题包导出、判卷、汇总三件事。想加"agent 侧"的机制（反馈压缩、重试策略、提示词），那是被测 harness 的事，不进本仓库。
3. **规则在 NL2PCB-Bench 里。** 需要新检查项时去 Bench 提 PR；本仓库不重写规则。`vendor/` 是快照，改动只能通过 `scripts/sync_vendor.sh` 更新并记录 commit。
