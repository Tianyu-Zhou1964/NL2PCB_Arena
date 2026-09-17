# 电源指示板

**目标**：从零设计一块用于普通桌面设备的5V单路LED电源指示PCB小板。

**功能**：+5 V （允许4.75–5.25V，外部电源限流20mA）经 2 脚连接器 J1 进板（1 脚正、2 脚回流），点亮一颗指示灯 D2。

**机械规格**：板框与 J1 的位置、方向已在 `assets/skeleton.kicad_pcb` 固定，不得修改。

**制造规格**：嘉立创普通 FR4 双层板、1 oz 外层铜、绿色阻焊、无铅喷锡、铣边，参数见 `assets/process/jlc_fr4_2l_1oz.toml`。贴片元件回流焊，J1 手焊。

**元件**：只能从 `assets/parts/` 选，清单见 `assets/parts/list.md`。位号 J1、D2 固定，其余自定。footprint 的 `Value` 写清单里的元件 id。

| 位号 | 元件 id | 说明 |
|---|---|---|
| J1 | `conn_2p_2mm` | 电源输入，1 脚 +5 V，2 脚回流 |
| D2 | `led_0805_red` | 指示灯 |

**输出**：在骨架上完成设计，输出 `answer.kicad_pcb`，格式见 `assets/mini_kicad.md`。
