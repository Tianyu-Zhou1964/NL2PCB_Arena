# 元件清单

footprint 的 Value 使用下表的元件 id。只能选择表内元件。
引脚号与名称见 symbols/ 中的对应符号，焊盘几何见 footprints/。

| id | 类别 | 描述 | 符号 | 封装 | 焊接 |
|---|---|---|---|---|---|
| [conn_2p_2mm](components/connector/conn_2p_2mm.toml) | connector | 2 位 2.00 mm 立式针座，通孔 | Connector_Generic:Conn_01x02 | Connector_TE-Connectivity:TE_440054-2_1x02_P2.00mm_Vertical | hand |
| [led_0805_red](components/led/led_0805_red.toml) | led | 红光 LED，0805，正向压降 2.0 V | Device:LED | LED_SMD:LED_0805_2012Metric | reflow |
| [res_0805_47](components/resistor/res_0805_47.toml) | resistor | 厚膜电阻 47Ω 0805 1/8 W | Device:R | Resistor_SMD:R_0805_2012Metric | reflow |
| [res_0805_100](components/resistor/res_0805_100.toml) | resistor | 厚膜电阻 100Ω 0805 1/8 W | Device:R | Resistor_SMD:R_0805_2012Metric | reflow |
| [res_0805_330](components/resistor/res_0805_330.toml) | resistor | 厚膜电阻 330Ω 0805 1/8 W | Device:R | Resistor_SMD:R_0805_2012Metric | reflow |
| [res_0805_1k](components/resistor/res_0805_1k.toml) | resistor | 厚膜电阻 1kΩ 0805 1/8 W | Device:R | Resistor_SMD:R_0805_2012Metric | reflow |
| [res_0805_5k1](components/resistor/res_0805_5k1.toml) | resistor | 厚膜电阻 5k1Ω 0805 1/8 W | Device:R | Resistor_SMD:R_0805_2012Metric | reflow |

## conn_2p_2mm

| 参数 | 值 |
|---|---|
| current_max_a | 3.0 |
| voltage_max_v | 250 |

## led_0805_red

| 参数 | 值 |
|---|---|
| color | red |
| if_max_a | 0.02 |
| vf_v | 2.0 |

## res_0805_47

| 参数 | 值 |
|---|---|
| power_w | 0.125 |
| resistance_ohm | 47 |
| tolerance | 0.005 |

## res_0805_100

| 参数 | 值 |
|---|---|
| power_w | 0.125 |
| resistance_ohm | 100 |
| tolerance | 0.005 |

## res_0805_330

| 参数 | 值 |
|---|---|
| power_w | 0.125 |
| resistance_ohm | 330 |
| tolerance | 0.01 |

## res_0805_1k

| 参数 | 值 |
|---|---|
| power_w | 0.125 |
| resistance_ohm | 1000 |
| tolerance | 0.01 |

## res_0805_5k1

| 参数 | 值 |
|---|---|
| power_w | 0.125 |
| resistance_ohm | 5100 |
| tolerance | 0.01 |
