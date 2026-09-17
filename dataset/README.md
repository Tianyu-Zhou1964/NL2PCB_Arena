# nl2pcb/nl2pcb-arena

Harbor 数据集清单 `dataset.toml` 由 `harbor dataset init` 生成，新题用 `harbor add dataset/<id> --to dataset` 加入，`harbor sync` 刷新 digest；每个子目录是一道 Harbor 任务。
题目形态、公开/隐藏规则与"通过不代表什么"见仓库根 `README.md` 与 `docs/PLAN.md`。

| 任务 | 层 | 起手板 | 公开规则 | 隐藏规则 |
|---|---|---|---|---|
| `mini-led` | L4 整板 | 骨架 | `pcb.drc`、`layout.fixed` | `electrical.led.current` |
| `mini-led-select` | L1 选型 | 骨架 | `layout.fixed`（`pcb.drc` 关：不要求布线） | `electrical.led.current` |
| `mini-led-repair-open` | L3 修复 | 开路板（缺一段走线） | `pcb.drc`、`layout.fixed` | `electrical.led.current` |
| `mini-led-repair-overcurrent` | L3 复核 | 47 Ω 板（DRC 干净但 LED 约 62 mA） | `pcb.drc`、`layout.fixed` | `electrical.led.current` |
