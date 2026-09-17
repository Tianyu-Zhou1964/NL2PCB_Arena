"""把 Harbor 的 job 结果汇总成我们的口径。

读每个 trial 目录：
  result.json            Harbor 的 TrialResult：task_name、agent_info、verifier_result.rewards、
                         exception_info、agent_result（token / cost）、各阶段计时
  verifier/grading.json  我们的 grader 写的：status、rule_status、verifier_calls、answer_changed
  agent/trajectory.json  ATIF：final_metrics.total_steps 当作轮数（有就用）

状态口径（顺序覆盖）：
  grading.json 的 status（passed / capability_failed / agent_reported_blocker / infrastructure_failure）
  → Harbor 异常属于环境/端点/评分器故障 → infrastructure_failure
  → Harbor 异常是取消 → not_run
  → 没有 grading.json 也没有 reward → infrastructure_failure
agent 超时（AgentTimeoutError）不是基础设施故障：超时那一刻的板子照常评分，只记 budget_hit = "wall_time"。

汇总按 (task, agent, model) 分格：n、scored（去掉 infra 与 not_run）、passed、pass@1、pass^n、
Wilson 95% 区间、逐规则通过率、成本/token/墙钟/轮数/自检次数的中位数。基础设施故障单列，不进分母。
"""

from __future__ import annotations

import json
import math
import statistics
import tomllib
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

__all__ = ["Trial", "load_trials", "aggregate", "write_report"]

INFRASTRUCTURE_EXCEPTIONS = {
    "AgentAuthenticationError", "ApiRateLimitError", "ApiUsageLimitError", "ApiOverloadedError",
    "ModelNotFoundError", "NetworkConnectionError", "AgentSetupTimeoutError",
    "EnvironmentStartTimeoutError", "VerifierTimeoutError", "RewardFileNotFoundError",
    "RewardFileEmptyError", "VerifierOutputParseError", "AddTestsDirError",
    "DownloadVerifierDirError", "RuntimeError", "FileNotFoundError",
}
NOT_RUN_EXCEPTIONS = {"CancelledError"}
STATUSES = ("passed", "capability_failed", "agent_reported_blocker", "infrastructure_failure", "not_run")


@dataclass
class Trial:
    trial_dir: str
    task: str
    agent: str
    agent_version: str | None
    model: str | None
    status: str
    reward: float | None
    exception: str | None
    budget_hit: str | None
    rule_status: dict[str, str] = field(default_factory=dict)
    tokens_input: int | None = None
    tokens_cache: int | None = None
    tokens_output: int | None = None
    cost_usd: float | None = None
    wall_sec: float | None = None
    steps: int | None = None
    verifier_calls: int | None = None
    answer_changed: bool | None = None
    infrastructure_reason: str | None = None
    verifier_isolated: bool | None = None   #: grading.json network.isolated；False 表示判卷容器能上网


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _seconds(timing: dict | None) -> float | None:
    if not timing or not timing.get("started_at") or not timing.get("finished_at"):
        return None
    from datetime import datetime
    start = datetime.fromisoformat(timing["started_at"])
    end = datetime.fromisoformat(timing["finished_at"])
    return (end - start).total_seconds()


def load_trial(trial_dir: Path) -> Trial | None:
    result = _load_json(trial_dir / "result.json")
    if result is None:
        return None
    grading = _load_json(trial_dir / "verifier" / "grading.json") or {}
    trajectory = _load_json(trial_dir / "agent" / "trajectory.json") or {}
    agent_info = result.get("agent_info") or {}
    model_info = agent_info.get("model_info") or {}
    exception = (result.get("exception_info") or {}).get("exception_type")
    rewards = (result.get("verifier_result") or {}).get("rewards") or {}
    reward = rewards.get("reward")

    status = grading.get("status")
    infra_reason = grading.get("infrastructure_reason")
    budget_hit = None
    if exception == "AgentTimeoutError":
        budget_hit = "wall_time"
    if exception in NOT_RUN_EXCEPTIONS:
        status = "not_run"
    elif exception in INFRASTRUCTURE_EXCEPTIONS:
        status, infra_reason = "infrastructure_failure", f"harbor: {exception}"
    elif status is None:
        if reward is None:
            status, infra_reason = "infrastructure_failure", f"no grading.json / reward (exception={exception})"
        else:
            status = "passed" if reward == 1 else "capability_failed"

    agent_result = result.get("agent_result") or {}
    metrics = trajectory.get("final_metrics") or {}
    return Trial(
        trial_dir=str(trial_dir), task=result.get("task_name", trial_dir.name.split("__")[0]),
        agent=agent_info.get("name", "?"), agent_version=agent_info.get("version"),
        model=model_info.get("name"), status=status, reward=reward, exception=exception,
        budget_hit=budget_hit, rule_status=grading.get("rule_status") or {},
        tokens_input=agent_result.get("n_input_tokens"), tokens_cache=agent_result.get("n_cache_tokens"),
        tokens_output=agent_result.get("n_output_tokens"), cost_usd=agent_result.get("cost_usd"),
        wall_sec=_seconds(result.get("agent_execution")), steps=metrics.get("total_steps"),
        verifier_calls=grading.get("verifier_calls"), answer_changed=grading.get("answer_changed"),
        infrastructure_reason=infra_reason,
        verifier_isolated=(grading.get("network") or {}).get("isolated"),
    )


def load_trials(job_dirs: Iterable[Path]) -> list[Trial]:
    trials: list[Trial] = []
    for job_dir in job_dirs:
        for trial_dir in sorted(p for p in Path(job_dir).iterdir() if (p / "result.json").is_file()):
            trial = load_trial(trial_dir)
            if trial is not None:
                trials.append(trial)
    return trials


def wilson(passed: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = passed / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, center - half), min(1.0, center + half))


def _median(values: list[float | int | None]) -> float | None:
    present = [v for v in values if v is not None]
    return statistics.median(present) if present else None


def aggregate(trials: list[Trial]) -> dict[str, Any]:
    cells: dict[tuple[str, str, str | None], list[Trial]] = defaultdict(list)
    for trial in trials:
        cells[(trial.task, trial.agent, trial.model)].append(trial)
    rows = []
    for (task, agent, model), items in sorted(cells.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] or "")):
        counts = {status: sum(1 for t in items if t.status == status) for status in STATUSES}
        scored = [t for t in items if t.status not in ("infrastructure_failure", "not_run")]
        passed = sum(1 for t in scored if t.status == "passed")
        rule_names = sorted({name for t in scored for name in t.rule_status})
        rule_pass = {name: (sum(1 for t in scored if t.rule_status.get(name) == "pass") / len(scored)) if scored else None
                     for name in rule_names}
        rows.append({
            "task": task, "agent": agent, "model": model,
            "n": len(items), "scored": len(scored), "passed": passed, "counts": counts,
            "pass_at_1": (passed / len(scored)) if scored else None,
            "pass_all": (passed == len(scored)) if scored else None,
            "wilson_95": wilson(passed, len(scored)),
            "rule_pass_rate": rule_pass,
            "budget_hits": sum(1 for t in items if t.budget_hit),
            "verifier_not_isolated": sum(1 for t in items if t.verifier_isolated is False),
            "median_cost_usd": _median([t.cost_usd for t in scored]),
            "median_tokens_input": _median([t.tokens_input for t in scored]),
            "median_tokens_output": _median([t.tokens_output for t in scored]),
            "median_wall_sec": _median([t.wall_sec for t in scored]),
            "median_steps": _median([t.steps for t in scored]),
            "median_verifier_calls": _median([t.verifier_calls for t in scored]),
            "infrastructure_reasons": sorted({t.infrastructure_reason for t in items if t.infrastructure_reason and t.status == "infrastructure_failure"}),
        })
    return {"cells": rows, "n_trials": len(trials), "official_score_available": False,
            "official_score_reason": "本地 Docker 运行、agent 阶段可联网、未经第三方盲测；对比须固定镜像、题包 digest、Harbor 版本与重复次数。"}


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "–"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(summary: dict[str, Any], trials: list[Trial]) -> str:
    lines = ["# NL2PCB-Arena 汇总", "",
             f"trial 总数 {summary['n_trials']}。`official_score_available = false`：{summary['official_score_reason']}", "",
             "| 任务 | harness | 模型 | n | 计分 | 通过 | pass@1 | 95% CI | 全过 | infra | blocker | 预算命中 | 中位成本 $ | 中位输入 tok | 中位墙钟 s | 中位轮数 | 中位自检 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for row in summary["cells"]:
        ci = row["wilson_95"]
        lines.append("| " + " | ".join([
            row["task"], row["agent"], row["model"] or "–", str(row["n"]), str(row["scored"]), str(row["passed"]),
            _fmt(row["pass_at_1"]), f"{ci[0]:.2f}–{ci[1]:.2f}" if ci else "–", _fmt(row["pass_all"]),
            str(row["counts"]["infrastructure_failure"]), str(row["counts"]["agent_reported_blocker"]),
            str(row["budget_hits"]), _fmt(row["median_cost_usd"], 3), _fmt(row["median_tokens_input"], 0),
            _fmt(row["median_wall_sec"], 0), _fmt(row["median_steps"], 0), _fmt(row["median_verifier_calls"], 0),
        ]) + " |")
    lines += ["", "## 逐规则通过率（只算计分的 trial）", ""]
    for row in summary["cells"]:
        rates = ", ".join(f"{name}: {_fmt(rate)}" for name, rate in row["rule_pass_rate"].items()) or "–"
        lines.append(f"- {row['task']} / {row['agent']} / {row['model'] or '–'}: {rates}")
    infra = [t for t in trials if t.status == "infrastructure_failure"]
    if infra:
        lines += ["", "## 基础设施故障（不进分母）", ""]
        for t in infra:
            lines.append(f"- {t.task} / {t.agent} / {t.model}: {t.infrastructure_reason} （{t.trial_dir}）")
    leaky = [t for t in trials if t.verifier_isolated is False]
    if leaky:
        lines += ["", "## 判卷容器没有断网（结果可疑：Harbor 的出口控制可能被静默关闭）", ""]
        for t in leaky:
            lines.append(f"- {Path(t.trial_dir).name}: {t.status} （{t.trial_dir}）")
    lines += ["", "## 逐 trial", "", "| trial | 状态 | reward | 规则 | 异常 | 成本 $ | 输入 tok | 输出 tok | 墙钟 s | 轮数 | 自检 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in trials:
        rules = ", ".join(f"{k}={v}" for k, v in t.rule_status.items()) or "–"
        lines.append("| " + " | ".join([
            Path(t.trial_dir).name, t.status, _fmt(t.reward, 0), rules, t.exception or "–",
            _fmt(t.cost_usd, 3), _fmt(t.tokens_input, 0), _fmt(t.tokens_output, 0), _fmt(t.wall_sec, 0),
            _fmt(t.steps, 0), _fmt(t.verifier_calls, 0),
        ]) + " |")
    return "\n".join(lines) + "\n"


def write_report(job_dirs: list[Path], *, out_dir: Path | None = None, prices_path: Path | None = None) -> Path:
    trials = load_trials(job_dirs)
    if prices_path is not None:
        _estimate_costs(trials, tomllib.loads(prices_path.read_text(encoding="utf-8")))
    summary = aggregate(trials)
    out = Path(out_dir or job_dirs[0])
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps({**summary, "trials": [asdict(t) for t in trials]},
                                                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "REPORT.md").write_text(render_markdown(summary, trials), encoding="utf-8")
    return out / "REPORT.md"


def _estimate_costs(trials: list[Trial], prices: dict[str, Any]) -> None:
    """models.toml：[models."<name>"] input_per_mtok / cache_per_mtok / output_per_mtok。只补没有自报成本的 trial。"""
    table = prices.get("models", {})
    for trial in trials:
        if trial.cost_usd is not None or trial.model not in table:
            continue
        price = table[trial.model]
        if trial.tokens_input is None and trial.tokens_output is None:
            continue
        cache = trial.tokens_cache or 0
        uncached = max(0, (trial.tokens_input or 0) - cache)
        trial.cost_usd = (uncached * price.get("input_per_mtok", 0) + cache * price.get("cache_per_mtok", 0)
                          + (trial.tokens_output or 0) * price.get("output_per_mtok", 0)) / 1e6
