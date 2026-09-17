# 电源指示板（复核）

`/workspace/answer.kicad_pcb` 的初始内容是一版已有的设计（起手板）。它通过了公开自检，但公开自检不覆盖题面的全部要求。请按题面逐条核对这块板是否满足需求：有问题就修改后交付，没问题就原样交付；它是唯一会被评分的文件，格式是 KiCad 10 原生 `.kicad_pcb`。

## 需求

**目标**：从零设计一块用于普通桌面设备的 5 V 单路 LED 电源指示 PCB 小板。

**功能**：+5 V（允许 4.75–5.25 V，外部电源限流 20 mA）经 2 脚连接器 J1 进板（1 脚正、2 脚回流），点亮一颗指示灯 D2。

**机械规格**：板框与 J1 的位置、方向已在骨架中固定，不得修改。

**制造规格**：嘉立创普通 FR4 双层板、1 oz 外层铜、绿色阻焊、无铅喷锡、铣边，参数见 `/task/assets/process/jlc_fr4_2l_1oz.toml`。贴片元件回流焊，J1 手焊。

**元件**：只能从 `/task/assets/parts/` 选，清单见 `/task/assets/parts/list.md`。位号 J1、D2 固定，其余自定。footprint 的 `Value` 写清单里的元件 id。

| 位号 | 元件 id | 说明 |
|---|---|---|
| J1 | `conn_2p_2mm` | 电源输入，1 脚 +5 V，2 脚回流 |
| D2 | `led_0805_red` | 指示灯 |

## 环境

- `/task/spec.md`：本题面。`/task/assets/parts/`：允许使用的元件（符号、封装、参数）。`/task/assets/process/`：工艺参数。`/task/assets/skeleton.kicad_pcb`：骨架。`/task/assets/mini_kicad.md` 是占位文件，忽略它。
- 没有安装 KiCad 标准库，封装只能来自 `/task/assets/parts/footprints/`。
- 命令行工具：`kicad-cli`（KiCad 10.0.6，例如 `kicad-cli pcb drc`）、`python3`（可 `import pcbnew`）、`ngspice`、`pcblite`（查询和编辑 `.kicad_pcb` 的命令行，`pcblite --help`）。
- 自检：`nl2pcb check /task /workspace/answer.kicad_pcb` 用本题的公开规则检查答案；评分时还会运行题面要求但未公开的规则。

## 交付

- 把最终结果保存在 `/workspace/answer.kicad_pcb`。
- 如果确认任务无法完成，写 `/workspace/BLOCKER.md`，说明原因和缺少的信息。
