"""公开 config 派生的纯函数测试：不需要 KiCad。"""

from nl2pcb_arena.export import HIDDEN_OFF_REASON, public_config

BENCH = {
    "schema": "0.1",
    "task": {"id": "mini-led", "reference": "cases/baseline.kicad_pcb"},
    "assets": {"parts": ["conn_2p_2mm"], "skeleton": ["J1"]},
    "conditions": {"process": "jlc", "supply": [{"ref": "J1", "pad": "1", "return_pad": "2", "voltage_v": 5.0}]},
    "rules": {
        "layout.fixed": [{"same_as": "assets/skeleton.kicad_pcb", "tol_mm": 0.01}],
        "electrical.led.current": [{"ref": "D2", "min": 0.0001}],
    },
    "output": {"help": False},
    "cases": [{"board": "cases/baseline.kicad_pcb", "pass": ["layout.fixed"], "reason": "x"}],
}


def test_public_keeps_public_rules_and_drops_cases():
    out = public_config(BENCH, ["pcb.drc", "layout.fixed"], ["electrical.led.current"], {"pcb.drc"})
    assert "cases" not in out
    assert out["task"]["reference"] == "assets/skeleton.kicad_pcb"
    assert out["task"]["id"] == "mini-led"
    assert out["rules"] == {"layout.fixed": [{"same_as": "assets/skeleton.kicad_pcb", "tol_mm": 0.01}]}
    assert out["conditions"] == BENCH["conditions"]


def test_hidden_default_on_rule_is_switched_off():
    out = public_config(BENCH, ["layout.fixed"], ["pcb.drc", "electrical.led.current"], {"pcb.drc"})
    assert out["rules"]["pcb.drc"] == [{"level": "off", "reason": HIDDEN_OFF_REASON}]
    assert "electrical.led.current" not in out["rules"]


def test_hidden_default_on_rule_mentioned_in_bench_is_switched_off():
    bench = {**BENCH, "rules": {**BENCH["rules"], "pcb.drc": [{"level": "warning", "reason": "宽松"}]}}
    out = public_config(bench, ["layout.fixed"], ["pcb.drc", "electrical.led.current"], {"pcb.drc"})
    assert out["rules"]["pcb.drc"] == [{"level": "off", "reason": HIDDEN_OFF_REASON}]


def test_calls_are_keyed_by_id_when_present():
    bench = {**BENCH, "rules": {"layout.fixed": [
        {"id": "fixed-a", "same_as": "assets/a.kicad_pcb"},
        {"id": "fixed-b", "same_as": "assets/b.kicad_pcb"},
    ]}}
    out = public_config(bench, ["fixed-a"], ["fixed-b"], set())
    assert out["rules"]["layout.fixed"] == [{"id": "fixed-a", "same_as": "assets/a.kicad_pcb"}]


def test_explicitly_off_rule_stays_off_in_public_config():
    """选型题：评测侧把默认开启的 pcb.drc 关掉，它既不公开也不隐藏；公开版必须保留这个关，否则默认规则会重新打开。"""
    bench = {**BENCH, "rules": {**BENCH["rules"], "pcb.drc": [{"level": "off", "reason": "不要求布线"}]}}
    out = public_config(bench, ["layout.fixed"], ["electrical.led.current"], {"pcb.drc"})
    assert out["rules"]["pcb.drc"] == [{"level": "off", "reason": "不要求布线"}]
    assert "electrical.led.current" not in out["rules"]
