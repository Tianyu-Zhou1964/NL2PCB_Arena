# NL2PCB-Arena

让任意"基模 + harness"组合在同一个考场做 NL2PCB-Bench 的题，并把结果按统一口径汇总。
考场、agent 适配、轨迹、并发由 [Harbor](https://github.com/harbor-framework/harbor) 提供；本仓库只做三件事：

1. **题包**：`dataset/<task>/` 是一个 Harbor 任务。评测侧的 `bench/`（NL2PCB-Bench 任务目录：完整 `config.toml`、`cases/`）只进 verifier 镜像；发给 agent 的 `environment/`（题面、元件、工艺、骨架、公开自检配置）由 `nl2pcb-arena export` 生成。
2. **判卷**：`verifier/grader.py` 在独立、断网的 verifier 容器里跑完整的 `nl2pcb check`，写 `reward.json`（0/1）与 `grading.json`（逐规则状态、四类结果状态）。
3. **汇总**：`nl2pcb-arena report` 把 Harbor 的 job 结果按 任务 × harness × 模型 汇总成 pass@1、pass^k、规则级通过率、成本与轮数；基础设施故障不进能力分母。

## 快速开始（服务器，Docker 可用）

```sh
uv tool install harbor                                   # 0.23
scripts/sync_vendor.sh ../NL2PCB-Bench ../pcblite        # 依赖快照 + commit 记录
BASE_IMAGE=docker.m.daocloud.io/library/ubuntu:24.04 APT_MIRROR=mirrors.tuna.tsinghua.edu.cn \
    images/build.sh dev                                  # agent 镜像 → 导出题包 → verifier 镜像
scripts/server/prepare_harbor_sidecar.sh                 # 拉不到 Docker Hub 的机器：预构建 Harbor 的断网 sidecar
harbor run -p dataset/mini-led -a oracle                 # 参考答案应得 reward 1
harbor run -p dataset/mini-led -a nop                    # 什么都不做应得 0
harbor run -p dataset -a claude-code -m anthropic/claude-sonnet-5 -k 3 -n 4   # 真跑（花钱）
uv run nl2pcb-arena report jobs/<job>                    # 汇总
harbor add dataset/<新题> --to dataset && (cd dataset && harbor sync)   # 新题入清单、刷新 digest
```

## 考场里有什么

`kicad-cli`（KiCad 10.0.6，PPA 锁版）、`python3` + `pcbnew`、`ngspice`、`pcblite`（查询/编辑 `.kicad_pcb` 的命令行）、`nl2pcb check /task /workspace/answer.kicad_pcb`（公开规则自检）。没有 KiCad 标准库，封装只来自题包。agent 阶段可联网（模型端点需要），verifier 阶段断网。

## 题目

| 任务 | 层 | 起手板 | 公开规则 | 隐藏规则 |
|---|---|---|---|---|
| `mini-led` | L4 整板 | 骨架 | `pcb.drc`、`layout.fixed` | `electrical.led.current` |
| `mini-led-select` | L1 选型 | 骨架 | `layout.fixed`（`pcb.drc` 关：不要求布线） | `electrical.led.current` |
| `mini-led-repair-open` | L3 修复 | 开路板（缺一段走线，公开 DRC 报未连接） | `pcb.drc`、`layout.fixed` | `electrical.led.current` |
| `mini-led-repair-overcurrent` | L3 复核 | 47 Ω 板（DRC 干净，LED 约 62 mA） | `pcb.drc`、`layout.fixed` | `electrical.led.current` |

**通过不代表什么**（每题 `task.toml` 的 `not_implied` 也写了）：
L1 选型通过不代表会布线；L3 修复通过不代表能从零设计；L4 整板通过不代表可量产、可靠、EMC 合规；所有题的通过都只针对已配置的规则，不覆盖题面里没有对应规则的要求（工艺、焊接方式），也不代表真实焊接点亮过。

## 结果状态

| 状态 | 判定 |
|---|---|
| `passed` | 完整规则全部通过（`nl2pcb check` 退出 0） |
| `capability_failed` | 其余：答案缺失、解析失败、任一规则 fail/inconclusive |
| `agent_reported_blocker` | agent 写了 `/workspace/BLOCKER.md` |
| `infrastructure_failure` | 评分器自身失败（配置错误、超时、参考板也无法检查）、Harbor 报环境/agent 安装异常 |

`grading.json` 的 `network.isolated` 记录判卷容器是否真的断网（Harbor 的出口控制在内核探针失败时会静默关闭）；汇总报表会把 `false` 的 trial 单列出来。

`official_score_available = false`：本地 Docker 运行、agent 可联网、未经第三方盲测。正式对比要固定镜像 digest、题包 digest（`dataset.toml`）、Harbor 版本、重复次数与网络策略。

## 目录

```
dataset/<task>/          Harbor 任务：task.toml、instruction.md、bench/（评测侧）、environment/（生成）、solution/
images/agent/Dockerfile  共享 agent 镜像
images/verifier.Dockerfile  FROM agent + grader + dataset/*/bench
verifier/grader.py       判卷
src/nl2pcb_arena/        export（题包导出）、report（汇总）
vendor/                  NL2PCB-Bench、pcblite 快照（不提交，VERSIONS.json 记 commit）
docs/PLAN.md             方案与计划书
```
