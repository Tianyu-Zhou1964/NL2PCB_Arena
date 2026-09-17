# NL2PCB-Arena 方案与计划书

2026-09-17 定稿（同日两版：先按自写 runner 写了一版；看过 Harbor 与 EDA-bench 后改为本版）。开发机：`zhou` 服务器 `~/zhoutianyu/NL2PCB-Arena`。

## 0. 一句话

NL2PCB-Bench 回答"这块板对不对"；NL2PCB-Arena 让任意 **基模 + harness** 组合在同一个考场做同一批题，并按统一口径汇总。Arena **不写 runner、不写 agent**：考场（Docker）、agent 适配（Claude Code / Codex / terminus-2 等 40 多个）、ATIF 轨迹、token 与成本记账、并发、重试、独立 verifier 环境全部由 [Harbor](https://github.com/harbor-framework/harbor)（Terminal-Bench 2.0 的官方 harness，0.23）提供。Arena 只做三件事：**题包、判卷、汇总**。同物种的 EDA-bench 就是这样建在 Harbor 上的，我们的结果口径可以和它直接对照。

## 1. 已定决策

| 编号 | 决策 | 结论 |
|---|---|---|
| D1 工具 | 考场提供什么 | 只提供命令行：`kicad-cli`、`pcblite`、公开版 `nl2pcb check`、`python3`（含 pcbnew）、`ngspice`。只要 harness 能执行 shell 就能参赛 |
| D2 自测 | agent 能否自测 | 能。容器内 `nl2pcb check /task /workspace/answer.kicad_pcb` 只跑**公开规则**；评分跑**全部规则**（含隐藏） |
| D3 隔离 | 隔离到什么程度 | Docker。评测侧文件只进 verifier 镜像；Harbor `environment_mode = "separate"` 在**全新、断网**的 verifier 容器里判卷，只有 `artifacts` 声明的 `/workspace` 被搬过去 |
| D4 框架 | 自写 runner 还是用现成 | **用 Harbor**。Arena 仓库 = 一个 Harbor 数据集 + 两个镜像 + 判卷脚本 + 汇总工具 |
| D5 仓库 | 代码放哪 | 新仓库 `NL2PCB-Arena`。Bench 与 pcblite 作为版本锁定的依赖（`scripts/sync_vendor.sh` 复制快照，commit 记进 `vendor/VERSIONS.json`），不改它们的代码 |
| D6 开发机 | 在哪开发 | `zhou`（Ubuntu 22.04 x86_64，256 核 / 377G / 1.5T 空闲 / Docker 28.3 + Compose v2.38）。本机只保留临时编辑镜像并 rsync |

## 2. 调查结论（事实，带出处）

### 2.1 NL2PCB-Bench（判卷器）

- 唯一入口 `nl2pcb check <task_dir> <answer.kicad_pcb> [--json]`，退出码 0 通过 / 1 有 error 级未通过 / 2 配置不合法 / 101 工具崩溃（`src/nl2pcb/cli.py:1-7`）。`--json` 每条 `diagnostic`、`report` 一行，末行 `run`。
- 任务目录可在仓库外；配置里**没有"公开/隐藏规则"概念**，规则调用的键按函数签名严格校验（`check/calls.py:130`）。公开/隐藏由 Arena 派生两份 config。
- 三条后端路径都要进容器：`kicad-cli`、KiCad 的 pcbnew Python（版本须 `10.0.*`，`worker.py:28`）、`ngspice`。
- 退出 101 不一定是环境坏了：损坏的答案文件也会让 `kicad-cli pcb export pos` 非零退出、`layout.fixed` 报 `crashed`。判卷时要拿参考板复核一次再定性（§5）。
- `spec/mini_kicad.md` 仍是占位，`lang/` 未写；题面改为"输出 KiCad 10 原生 `.kicad_pcb`"。

### 2.2 pcblite（agent 的改板工具）

- 用**本体仓库**（`Tianyu-Zhou1964/pcblite`，HEAD `feefd87`）的 `pcblite/` 包：纯标准库、11 个 .py、不 import pcbnew；`kicad-cli` 只在 `--refill`/`--check`/`verify`/老文件升级时用。没有 pyproject，容器里包一层 `/usr/local/bin/pcblite`。
- 31 个子命令：`open/export`、10 个查询、18 个编辑操作、`apply` 批量原子。编辑失败退出码 2 且不落盘。
- 交接包里的 9 个 JSON 工具是"从空板建板"协议（`agent_state.design()` 对存量板抛 `ARCHIVE_NOT_ALLOWED`，且依赖 pcbnew），**不采用**。
- **待验证风险**：`open → export → nl2pcb check` 在 09-14 跑通过，但早于 Bench 合入"封装库一致性 DRC"（PR #13）。verifier 镜像构建自检只验参考板；pcblite 往返要单独测（§8 P3）。

### 2.3 Harbor（考场与 runner）

- 任务 = 目录：`task.toml`（`schema_version = "1.4"`）+ `instruction.md` + `environment/`（agent 镜像构建上下文）+ `solution/solve.sh`（oracle）+ 可选 `tests/`。`harbor run -p <目录>` 直接跑本地任务或任务集合，无需发布。
- **separate verifier**：`[verifier] environment_mode = "separate"` + `[verifier.environment] docker_image = ...`；Harbor 先停 agent 容器，把 `artifacts` 声明的路径搬进新容器（原路径还原），`/logs/verifier` 先清空再跑 `/tests/test.sh`。**`tests/` 目录在 separate 模式下永不上传**，`test.sh` 必须烘进 verifier 镜像（`trial.py:894` `skip_tests_upload=True`）。
- reward：`/logs/verifier/reward.json`（优先）或 `reward.txt`。**pass@k 只在 reward 恰好一个键且值 ∈ {0,1} 时计算**（`utils/pass_at_k.py:44-51`）。
- agent 超时（`AgentTimeoutError`）或非零退出**不会跳过验证**：超时那一刻的工作区照常评分（`single_step.py:75-87`）；环境起不来 / agent 装不上则没有 `verifier_result`。
- 每个 trial 都在容器里装一次 agent CLI（claude-code 走 `bootstrap.sh`，codex 走 nvm + npm），默认安装超时 360 s；但 `install()` 看到 `command -v claude/codex` 成功就跳过 → **agent 镜像预装 node 22 + 两个 CLI**。
- claude-code 以 root 跑时 Harbor 自动 `IS_SANDBOX=1` + `--permission-mode=bypassPermissions`；`[agent].user` 可指定非 root。
- 模型与端点：claude-code 用 `-m <model>` + `--ae ANTHROPIC_API_KEY/ANTHROPIC_BASE_URL`（有自定义端点时模型名原样透传）；codex 用 `-m <model>` + `--ae OPENAI_API_KEY/OPENAI_BASE_URL`（Harbor 写进 `config.toml` 的 `openai_base_url`）；terminus-2（Harbor 自带的最薄 agent，LiteLLM）用 `-m openai/<model> --ak api_base=...`，密钥从**运行 harbor 的宿主环境**读。
- 产物：`jobs/<job>/<trial>/{result.json, agent/trajectory.json, agent/<原生日志>, verifier/{reward.json,test-stdout.txt,…}, artifacts/<声明路径>}`。`result.json` 有 `agent_info{name,version,model_info}`、`agent_result{n_input_tokens,n_cache_tokens,n_output_tokens,cost_usd}`、`verifier_result.rewards`、`exception_info.exception_type`、各阶段计时。内置统计给 mean reward 与 pass@k。
- 网络：`no-network` 不是 `--network none`，而是让容器共用一个 egress sidecar（基础镜像 `gogost/gost`，按内容哈希命名为 `harbor-prebuilt:harbor-docker-egress-control-sidecar--<hash>`）的网络命名空间，由它做 nftables 拦截。Harbor 会先跑 `alpine:3.23.4` 探针测内核，探针失败就**静默降级为 public**；sidecar 基础镜像要从 Docker Hub 拉，拉不到则整个 verifier 阶段报 `RuntimeError`（zhou 上已遇到：两个镜像站都不提供 gost）。对策：`scripts/server/prepare_harbor_sidecar.sh` 用 Harbor 自己的哈希算法算出镜像名、从可用镜像站按同一 digest 拉 gost 后预构建同名镜像（Harbor 见本地已有即复用）；`grader.py` 在判卷容器里实测 DNS 与 HTTP 出网（断网是透明代理，TCP 握手总成功，必须到应用层）并写进 `grading.json.network`，汇总报表把 `isolated=false` 的 trial 单列。
- 陷阱：`harbor run -o` 是 `--jobs-dir`；`-a terminus`/`terminus-1` 不可用，只有 `terminus-2`；多维 reward 文件名是 `reward.json`（模板注释里的 `rewards.json` 是错的）。

### 2.4 EDA-bench（同物种模板）

- 35 个真实开源硬件的重建任务，Harbor 0.19；**一个共享 agent 镜像 + 一个 `FROM agent` 的 verifier 镜像**，verifier 镜像里烘焙 gold、契约、评分代码与 `/tests/test.sh`，任务靠 `[verifier].env` 的 `EDA_BENCH_TASK_ID` 选择；agent 镜像构建上下文只有一个 Dockerfile 目录，物理上放不进 gold。
- `artifacts = ["/workspace/final_project"]` 单向搬运；verifier `no-network`；`grader.py` 写 `reward.json`（数值）+ `grading.json`（全部）+ `work/`。
- 值得抄：verifier `FROM` agent 保证判卷与自检用同一套二进制；相对 gold 的 DRC/ERC 打分吸收 KiCad 版本噪声；诊断项权重 0；DATA_CARD 里逐条写"高分不代表什么"。
- 不抄：全程 root、无 locale、不钉 KiCad 版本、可变镜像 tag、`metric.py` 按位置绑难度、agent 阶段开公网且 gold 公开可搜（他们自己承认）。

### 2.5 容器与服务器

- KiCad 官方镜像 `kicad/kicad:10.0` 只有 amd64；PPA `ppa:kicad/kicad-10.0-releases` 对 Ubuntu 24.04 有 amd64 与 arm64 的 `10.0.6~ubuntu24.04.1`。选 **`ubuntu:24.04` + PPA 锁版**，探针镜像已在服务器构建通过（kicad-cli 10.0.6、pcbnew 10.0.6、ngspice 42、Python 3.12.3，1.1 GB，3 分钟）。
- 服务器网络：Docker Hub 直连超时，`docker.m.daocloud.io` 可用；Ubuntu 源用清华 **http** 镜像（装 ca-certificates 前 https 不可用，已踩坑）；PPA、npm、nodejs.org 可达；GitHub 慢（构建期不 clone，改本地拷贝）；pypi 走清华。
- 本机 Mac 不用于开发：colima VM 已删；`brew` 装的 `colima`、`docker` 两个小包保留，可 `brew uninstall colima docker`。

### 2.6 从 Aspen-Agent 借的机制（只借机制）

| 借 | 落在哪 |
|---|---|
| 评分器只吃一个目录、可离线重跑、全部重算 | `harbor job regrade` + `verifier/grader.py`（separate 模式支持不重跑 agent 只重评） |
| 缺测量 = 失败，绝不视作 0 | 答案缺失/解析失败 = `capability_failed`；评分器崩溃 = `infrastructure_failure`；reward.json 一定落盘 |
| 状态分类，infra 优先级最高、不进能力分母；双分母 | `grading.json.status` + `nl2pcb-arena report`：`planned / scored / passed`，infra 与 not_run 单列 |
| `run_identity` 冻结身份 | Harbor 的 `result.json`（agent 名/版本/模型）+ 镜像内 `/opt/VERSIONS.json`（Bench、pcblite commit）+ `dataset.toml` 的任务 digest + `grading.json.tool_versions` |
| 每层"通过不代表什么" | `task.toml.[metadata].not_implied`，进 README 与 `grading.json` |
| agent 主动报阻塞是一等状态 | 题面约定 `/workspace/BLOCKER.md` → `agent_reported_blocker` |
| 每轮自检留痕 | 容器内 `nl2pcb` 包装脚本记 `/workspace/.arena/verifier_calls.jsonl`，grader 计数；评分不依赖它 |
| 污染审计 | verifier 镜像构建自检 + `tests/test_contamination.py`（agent 镜像里找不到 `cases/`、完整 config、参考板） |

**不借**：评测器往 agent 会话里注入追问、领域教学提示词、AST 白名单沙箱、按参考答案逐值匹配、无预算运行、人工科学评审悬置态、把 L 编号绑进 agent 工作流。

## 3. 评测口径

- **被测对象** = `(harness, model)`；harness 版本由 Harbor 记进 `agent_info.version`。
- **一次 trial** = 一题 × 一个组合 × 一次尝试（`-k` 重复）。
- **状态**（`grading.json.status`，顺序覆盖）：
  1. `passed`：完整规则全部通过（`nl2pcb check` 退出 0）。
  2. `capability_failed`：其余——答案缺失、解析失败、任一 error 级规则 fail / inconclusive、超时时的板子不合格。
  3. `agent_reported_blocker`：`/workspace/BLOCKER.md` 存在。
  4. `infrastructure_failure`：配置不合法（退出 2）、评分超时、工具崩溃且**参考板同样崩溃**；汇总时再并入 Harbor 的环境/安装/端点异常（`AgentAuthenticationError`、`ApiRateLimitError`、`EnvironmentStartTimeoutError`…）。
  5. `not_run`：Harbor 取消。
- **预算命中**单独记：agent 超时 → `budget_hit = "wall_time"`，状态仍由评分决定；`max_turns`/`max_budget_usd` 走各 harness 的 `--ak`。
- **reward**：`{"reward": 0|1}` 单键（保住 Harbor 的 pass@k）；规则通过比例、公开/隐藏是否通过在 `grading.json.scores`。
- **汇总**（`nl2pcb-arena report`，每 `(task, harness, model)`）：`n`、`scored`、`passed`、`pass@1`、`pass^n`、Wilson 95% 区间、逐规则通过率、成本/token/墙钟/轮数/自检次数中位数、infra 与 blocker 计数。交接包实测同配置 token 波动 ±30%，**每格至少 3 次**。
- **通过不代表什么**：L1 选型 ≠ 会布线；L3 修复 ≠ 能从零设计；L4 整板 ≠ 可量产/可靠/EMC；全部 ≠ 真实焊接点亮过，≠ 题面里没有规则的要求（工艺、焊接方式）。`official_score_available = false`：本地 Docker、agent 可联网、未经盲测。

## 4. 仓库与题目形态

```
NL2PCB-Arena/
  README.md  AGENTS.md  docs/PLAN.md  pyproject.toml  .gitignore  .dockerignore（白名单）
  images/agent/Dockerfile        共享 agent 镜像：ubuntu:24.04 + KiCad 10.0.6(PPA) + ngspice + node 22 + claude-code + codex
                                 + pcblite(/opt/pcblite) + nl2pcb(/opt/nl2pcb-bench，公开自检) + 用户 agent(uid 1000)
  images/agent/bin/{pcblite,nl2pcb}  命令包装；nl2pcb 顺手记自检日志
  images/verifier.Dockerfile     FROM agent + /tests/{grader.py,test.sh} + /opt/nl2pcb-arena/dataset（含隐藏 bench/）；构建时自检
  images/build.sh  images/export.sh   agent 镜像 → 在镜像里导出题包 → verifier 镜像
  verifier/grader.py  verifier/test.sh
  src/nl2pcb_arena/{export.py, report.py, cli.py}
  scripts/sync_vendor.sh         vendor/ 快照 + VERSIONS.json
  dataset/dataset.toml           Harbor 数据集清单：harbor dataset init 生成；新题 `harbor add dataset/<id> --to dataset`；`harbor sync` 刷新 digest
  dataset/<task>/
    task.toml                    Harbor 配置；[metadata] 放 tier / rules_public / rules_hidden / start_board / not_implied
    instruction.md               题面（唯一提示）：需求、环境里有什么、交付与 BLOCKER 约定；不含做法
    bench/                       评测侧：Bench 任务目录（config.toml、spec.md、cases/、assets/ 生成）
    start.kicad_pcb              可选：修复题的起手板
    environment/                 ← export 生成，提交进 git：Dockerfile（FROM agent 镜像 + COPY task /task + 起手板）、start.kicad_pcb、task/{spec.md, config.toml(公开), assets/}
    solution/solve.sh + solution/reference/answer.kicad_pcb   oracle
```

`task.toml` 的 Harbor 关键字段：顶层 `artifacts = ["/workspace"]`；`[verifier] environment_mode = "separate"`, `network_mode = "no-network"`, `env = { NL2PCB_TASK_ID = "<id>" }`, `timeout_sec = 900`；`[verifier.environment] docker_image = "nl2pcb-arena/verifier:<tag>"`；`[agent] timeout_sec = 1800`, `user = "agent"`；`[environment] network_mode = "public"`（模型端点要出网）, `workdir = "/workspace"`, `cpus = 4`, `memory_mb = 8192`。

公开 config 派生规则（`export.public_config`，纯函数，有单测）：去掉 `[[cases]]`；`[rules]` 只留 `rules_public` 点名的调用（按 `id` 或规则名）；默认开启但被列为隐藏的规则写 `level = "off"`；`task.reference` 改指 `assets/skeleton.kicad_pcb`。导出后用 Bench 自己的 `load_task + collect` 复核：公开 config 恰好只含公开规则，`public ∪ hidden` 等于 bench 启用的全部。

## 5. 判卷（`verifier/grader.py`）

在 verifier 容器里：读 `NL2PCB_TASK_ID` → `bench/` → 对 `/workspace/answer.kicad_pcb` 跑完整 `nl2pcb check --json`（600 s 超时）→ 写 `/logs/verifier/{reward.json, grading.json, work/}`。退出 101 时再对参考板跑一次：参考板过 → 崩溃是答案引起的（`capability_failed`）；参考板也崩 → `infrastructure_failure`。grader 自身异常也落盘并标 infra。`--selfcheck` 在构建 verifier 镜像时逐题验证：配置能加载、`public ∪ hidden` 覆盖全部规则、起手板/公开包/骨架存在、**参考板能通过完整检查**（每题可解）。

## 6. 运行

```sh
# 一次性
uv tool install harbor
scripts/sync_vendor.sh ../NL2PCB-Bench ../pcblite
BASE_IMAGE=docker.m.daocloud.io/library/ubuntu:24.04 APT_MIRROR=mirrors.tuna.tsinghua.edu.cn images/build.sh dev

# 自洽
harbor run -p dataset/mini-led -a oracle --job-name oracle     # reward 1
harbor run -p dataset/mini-led -a nop    --job-name nop        # reward 0

# 真跑（花钱）
export ANTHROPIC_API_KEY=...; harbor run -p dataset -a claude-code -m claude-sonnet-5 -k 3 -n 4 --ak max_turns=60 --ak max_budget_usd=5
export OPENAI_API_KEY=...;   harbor run -p dataset -a codex -m gpt-6-astra --ae OPENAI_BASE_URL=https://<中转>/v1 -k 3 -n 4
harbor run -p dataset -a terminus-2 -m openai/qwen3.7-plus --ak api_base=https://<端点>/v1 --ak max_turns=60 -k 3

# 汇总 / 查看 / 重评
uv run nl2pcb-arena report jobs/<job>
harbor view jobs
harbor job regrade jobs/<job> -p dataset/mini-led
```

## 7. 第一批题目

| id | 层 | 起手板 | 公开规则 | 隐藏规则 | 参考答案 | 通过不代表 |
|---|---|---|---|---|---|---|
| `mini-led` | L4 整板 | 骨架（板框 + J1） | `pcb.drc`、`layout.fixed` | `electrical.led.current` | Bench baseline（R1 = 5.1 kΩ，D2 ≈ 0.59 mA） | 可量产、可靠 |
| `mini-led-select` | L1 选型 | 骨架 | `layout.fixed`（`pcb.drc` 评测侧显式 off：不要求布线，公开版同样 off） | `electrical.led.current` | baseline | 会布线、铜线连通 |
| `mini-led-repair-open` | L3 修复 | `led-open-circuit`（R1.2–D2.2 缺一段线，公开 DRC 报未连接） | `pcb.drc`、`layout.fixed` | `electrical.led.current` | 用 pcblite `route` 补线并 `export --refill` 的板（`cases/led-open-repaired`，三条规则全过） | 从零设计 |
| `mini-led-repair-overcurrent` | L3 复核 | 47 Ω 板（baseline 改 R1；DRC 干净，D2 ≈ 62 mA > if_max 20 mA） | `pcb.drc`、`layout.fixed` | `electrical.led.current` | 330 Ω 板（≈ 9 mA） | 从零设计；分开"读题算电流"与"看报错改板" |

每题 `bench/` 是完整 Bench 任务目录，评分器不改。后三题共用 8 块案例板（Bench 的 5 块 + 47 Ω、330 Ω、修复板），标注 = 服务器上用完整配置实测的判定 + 物理推理，每条启用规则至少一正一反；`tests/test_grader_cases.py` 逐板核对判卷与标注一致。题面（`instruction.md`）只说范围与起手板来历，不点名隐藏规则：复核题只说"公开自检不覆盖全部要求，请按题面逐条核对"。

## 8. 提交计划（新仓库内原子提交；不推送）

| 步 | 内容 | 验证方式（不花 token） |
|---|---|---|
| P0 | 骨架：`pyproject`、`README`、`AGENTS.md`、`docs/PLAN.md`、`.gitignore`、`.dockerignore`、`scripts/sync_vendor.sh` | `uv sync`、`uv run nl2pcb-arena --help` |
| P1 | 题包导出：`export.py`（`public_config` 纯函数 + `export_task`）、`dataset/mini-led`（task.toml、instruction.md、bench/、solution/） | `pytest tests/test_export.py`；服务器 `images/export.sh` 生成 `environment/`，产物进 git |
| P2 | 镜像：`images/agent/Dockerfile`、`images/verifier.Dockerfile`、`images/build.sh`、`images/export.sh`、`verifier/{grader.py,test.sh}` | 服务器构建；verifier 自检通过；容器内 `claude --version`、`codex --version`、`pcblite --help`、`nl2pcb --help`；`tests/test_contamination.py` |
| P3 | 判卷链路：`harbor run -a oracle` → `passed`；`-a nop` → `capability_failed`；手工把 `j1-shifted` / 47 Ω 板 / `BLOCKER.md` 放进 workspace 走 `harbor job regrade` 或直接起 verifier 容器验证四类状态；**pcblite `open → export` 的板过完整 check** | 全在服务器 Docker 里，零 token |
| P4 | 汇总：`report.py`（状态映射、pass@1 / pass^n / Wilson、逐规则、成本）+ `dataset/dataset.toml`（`harbor sync`） | `pytest tests/test_report.py`（合成 trial 目录）；对 oracle/nop 的 job 出 `REPORT.md` |
| P5 | 分层题：`mini-led-select`、`mini-led-repair-open`、`mini-led-repair-overcurrent` | 每题 oracle 过、nop 不过；verifier 自检通过 |
| P6 | 真跑冒烟（**花钱，留给你触发**） | 先 `terminus-2` × 便宜模型 × `mini-led-select` × 1 次，看轨迹与报表；再上 claude-code / codex |

## 9. 风险与边界

- **pcblite 导出 vs 封装库一致性 DRC**：已实测通过——baseline `pcblite open → export --kicad 10` 往返板三条规则全过、`pcblite verify` 语义一致；修复题的参考答案就是 pcblite `route` + `export --refill` 出来的板。
- **鉴权**：服务器上跑 claude-code 需要 `ANTHROPIC_API_KEY` 或 `claude setup-token` 得到的 `CLAUDE_CODE_OAUTH_TOKEN`（本机订阅 OAuth 不能直接复制）；codex 用 `OPENAI_API_KEY` + `OPENAI_BASE_URL`；terminus-2 的密钥在宿主环境。密钥只从环境变量读，不进仓库、不进日志。
- **网络**：agent 阶段必须出网（模型端点），所以不能声称"agent 无法联网查资料"；报告注明。verifier 阶段 `no-network` 已实测（`grading.json.network`：DNS gaierror、HTTP 被 sidecar 直接断开，`isolated = true`）；每个 trial 都记录，报表把 `false` 的单列。zhou 上 Docker Hub 不通、两个镜像站不提供 `gogost/gost`，sidecar 由 `scripts/server/prepare_harbor_sidecar.sh` 从 `docker.1panel.live` 按同一 digest 预构建（见 2.3）。
- **隔离不是安全沙箱**：容器共享内核；`[agent].user = "agent"` + 只读 `/task` 只挡无意越权；agent 有 sudo。`official_score_available = false` 写进每份 `grading.json`。
- **题量与辨识度**：四道题都是"一电阻一 LED"，L4 会很快饱和；后续接 TPS5430 级别题（交接包有素材），并等 Bench 加放置/阻抗类规则。
- **随机性**：每格至少 3 次，报表始终带区间。
- **Harbor 版本**：0.23 的 `task.toml` schema 1.4；升级前跑 `harbor run --print-config` 与 oracle/nop 回归；升级后 sidecar 镜像名的内容哈希会变，要重跑 `scripts/server/prepare_harbor_sidecar.sh`。
