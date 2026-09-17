"""汇总工具测试：用合成的 Harbor trial 目录，不需要 Docker。"""

import json
from pathlib import Path

from nl2pcb_arena.report import aggregate, load_trials, render_markdown, wilson


def _trial(root: Path, name: str, *, reward, status=None, exception=None, rules=None, cost=0.5,
           tokens=(1000, 200, 300), agent="claude-code", model="claude-sonnet-5", task="nl2pcb/mini-led",
           isolated=True):
    trial = root / name
    (trial / "verifier").mkdir(parents=True)
    (trial / "agent").mkdir()
    result = {
        "task_name": task,
        "agent_info": {"name": agent, "version": "2.1.274", "model_info": {"name": model, "provider": "anthropic"}},
        "agent_result": {"n_input_tokens": tokens[0], "n_cache_tokens": tokens[1], "n_output_tokens": tokens[2], "cost_usd": cost},
        "verifier_result": {"rewards": {"reward": reward}} if reward is not None else None,
        "exception_info": {"exception_type": exception} if exception else None,
        "agent_execution": {"started_at": "2026-09-17T10:00:00+00:00", "finished_at": "2026-09-17T10:05:00+00:00"},
    }
    (trial / "result.json").write_text(json.dumps(result), encoding="utf-8")
    if status is not None:
        grading = {"status": status, "rule_status": rules or {}, "verifier_calls": 2, "answer_changed": True,
                   "network": {"isolated": isolated},
                   "infrastructure_reason": "参考板也崩" if status == "infrastructure_failure" else None}
        (trial / "verifier" / "grading.json").write_text(json.dumps(grading), encoding="utf-8")
    (trial / "agent" / "trajectory.json").write_text(json.dumps({"final_metrics": {"total_steps": 12}}), encoding="utf-8")
    return trial


def test_status_mapping_and_aggregation(tmp_path):
    ok = {"pcb.drc": "pass", "layout.fixed": "pass", "electrical.led.current": "pass"}
    bad = {"pcb.drc": "pass", "layout.fixed": "pass", "electrical.led.current": "fail"}
    _trial(tmp_path, "mini-led__a", reward=1.0, status="passed", rules=ok)
    _trial(tmp_path, "mini-led__b", reward=0.0, status="capability_failed", rules=bad, isolated=False)
    _trial(tmp_path, "mini-led__c", reward=0.0, status="capability_failed", rules=bad, exception="AgentTimeoutError")
    _trial(tmp_path, "mini-led__d", reward=None, status=None, exception="AgentAuthenticationError")
    _trial(tmp_path, "mini-led__e", reward=0.0, status="agent_reported_blocker", rules=bad)
    _trial(tmp_path, "mini-led__f", reward=None, status=None, exception="CancelledError")

    trials = load_trials([tmp_path])
    by_name = {Path(t.trial_dir).name: t for t in trials}
    assert by_name["mini-led__a"].status == "passed"
    assert by_name["mini-led__c"].status == "capability_failed" and by_name["mini-led__c"].budget_hit == "wall_time"
    assert by_name["mini-led__d"].status == "infrastructure_failure"
    assert by_name["mini-led__e"].status == "agent_reported_blocker"
    assert by_name["mini-led__f"].status == "not_run"
    assert by_name["mini-led__a"].steps == 12 and by_name["mini-led__a"].wall_sec == 300.0

    summary = aggregate(trials)
    assert len(summary["cells"]) == 1
    cell = summary["cells"][0]
    assert cell["n"] == 6 and cell["scored"] == 4 and cell["passed"] == 1
    assert cell["pass_at_1"] == 0.25 and cell["pass_all"] is False
    assert cell["counts"]["infrastructure_failure"] == 1 and cell["counts"]["not_run"] == 1
    assert cell["rule_pass_rate"]["electrical.led.current"] == 0.25
    assert cell["rule_pass_rate"]["pcb.drc"] == 1.0
    assert cell["budget_hits"] == 1
    assert cell["median_steps"] == 12
    assert cell["verifier_not_isolated"] == 1
    assert by_name["mini-led__b"].verifier_isolated is False and by_name["mini-led__a"].verifier_isolated is True
    markdown = render_markdown(summary, trials)
    assert "判卷容器没有断网" in markdown and "mini-led__b" in markdown


def test_reward_without_grading_falls_back_to_reward_value(tmp_path):
    _trial(tmp_path, "t__1", reward=1.0, status=None)
    _trial(tmp_path, "t__2", reward=0.0, status=None)
    trials = load_trials([tmp_path])
    assert sorted(t.status for t in trials) == ["capability_failed", "passed"]


def test_wilson_interval_bounds():
    low, high = wilson(1, 4)
    assert 0.0 <= low < 0.25 < high <= 1.0
    assert wilson(0, 0) is None
