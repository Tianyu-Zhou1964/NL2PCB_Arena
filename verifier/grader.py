#!/usr/bin/env python3
"""NL2PCB-Arena 判卷：在 verifier 容器里对 agent 的答案跑完整的 nl2pcb check。

输入（全部来自镜像与环境变量，不访问网络）：
  NL2PCB_TASK_ID                             由 task.toml 的 [verifier].env 注入
  /opt/nl2pcb-arena/dataset/<id>/task.toml   [metadata] 里有 rules_public / rules_hidden / tier
  /opt/nl2pcb-arena/dataset/<id>/bench/      Bench 任务目录：完整 config.toml、cases/、assets/
  /opt/nl2pcb-arena/dataset/<id>/environment/start.kicad_pcb   agent 的起手板
  /workspace/answer.kicad_pcb                agent 的答案，Harbor 按 task.toml 的 artifacts 搬进来
  /workspace/BLOCKER.md                      可选：agent 声明无法完成
  /workspace/.arena/verifier_calls.jsonl     可选：agent 自检记录（只作指标）

输出：
  /logs/verifier/reward.json    只有 {"reward": 0|1}。Harbor 只在 reward 恰好一个键且值 ∈ {0,1} 时算 pass@k，
                                所以其余数值（规则通过比例、公开/隐藏是否通过）都放 grading.json。
  /logs/verifier/grading.json   全部细节：status、逐规则状态、诊断、哈希、自检次数、工具版本、
                                network（判卷容器是否真的断网，只记录不判分）
  /logs/verifier/work/          nl2pcb check 的原始 JSON Lines 与 stderr

status 的判定顺序（后者覆盖前者）：
  passed / capability_failed  ← nl2pcb check 退出 0 / 非 0（含答案缺失、解析失败）
  agent_reported_blocker      ← 存在 BLOCKER.md
  infrastructure_failure      ← 评分器自身失败：配置错误(退出 2)、超时、工具崩溃且参考板同样崩溃

“工具崩溃”(退出 101) 不直接归 infrastructure：一份损坏的答案也会让 kicad-cli 退出非 0。
所以退出 101 时再对参考板跑一次同样的检查——参考板过则崩溃是答案引起的（capability_failed），
参考板也崩才是环境问题。缺测量绝不视作通过。

退出码：0 评分完成（不论答案对错）；1 评分器自身失败（reward.json 仍会写出，verifier_ok = 0）。

`python3 grader.py --selfcheck` 在构建 verifier 镜像时运行：逐题检查配置能加载、公开/隐藏规则
覆盖全部启用规则、起手板与参考板存在、参考板能通过完整检查。
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

BENCH_SRC = Path("/opt/nl2pcb-bench/src")
DATASET = Path("/opt/nl2pcb-arena/dataset")
WORKSPACE = Path("/workspace")
LOGS = Path("/logs/verifier")
CHECK_TIMEOUT_S = 600
EXIT_OK, EXIT_FAIL, EXIT_PARSE, EXIT_CRASH = 0, 1, 2, 101

sys.path.insert(0, str(BENCH_SRC))


def sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def read_task_meta(task_dir: Path) -> dict:
    config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
    meta = config.get("metadata", {})
    return {
        "name": config["task"]["name"],
        "tier": meta.get("tier"),
        "rules_public": list(meta.get("rules_public", [])),
        "rules_hidden": list(meta.get("rules_hidden", [])),
        "not_implied": list(meta.get("not_implied", [])),
    }


def run_check(bench: Path, answer: Path, work: Path, label: str) -> dict:
    """跑一次 nl2pcb check --json，返回 {exit, rules, diagnostics, run, timed_out, error}。"""
    work.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(BENCH_SRC), "NL2PCB_CALL_LOG": str(work / "unused.jsonl")}
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-B", "-m", "nl2pcb.cli", "check", str(bench), str(answer), "--json"],
            capture_output=True, text=True, timeout=CHECK_TIMEOUT_S, env=env, cwd=str(work),
        )
    except subprocess.TimeoutExpired:
        return {"exit": None, "rules": {}, "diagnostics": [], "run": None,
                "timed_out": True, "error": f"nl2pcb check 超过 {CHECK_TIMEOUT_S}s", "seconds": time.monotonic() - started}
    except OSError as error:
        return {"exit": None, "rules": {}, "diagnostics": [], "run": None,
                "timed_out": False, "error": f"无法启动 nl2pcb: {error}", "seconds": time.monotonic() - started}
    (work / f"{label}.jsonl").write_text(proc.stdout, encoding="utf-8")
    (work / f"{label}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    rules: dict[str, dict] = {}
    diagnostics: list[dict] = []
    run = None
    for line in proc.stdout.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "report" in obj:
            report = obj["report"]
            rules[report["rule"]] = {"status": report["status"], "code": report["code"],
                                     "method": report["method"], "level": report["level"],
                                     "reason": report.get("reason")}
        elif "diagnostic" in obj:
            diagnostics.append(obj["diagnostic"])
        elif "run" in obj:
            run = obj["run"]
    return {"exit": proc.returncode, "rules": rules, "diagnostics": diagnostics, "run": run,
            "timed_out": False, "error": proc.stderr.strip() if proc.returncode == EXIT_PARSE else None,
            "seconds": time.monotonic() - started}


def count_verifier_calls(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            if "check" in json.loads(line).get("argv", []):
                count += 1
        except (json.JSONDecodeError, AttributeError):
            continue
    return count


def tool_versions() -> dict:
    out = {}
    for key, cmd in (("kicad-cli", ["kicad-cli", "version"]), ("ngspice", ["ngspice", "--version"])):
        try:
            text = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
            out[key] = next((l.strip() for l in text.splitlines() if l.strip() and not l.startswith("*")), text.strip()[:80])
        except (OSError, subprocess.TimeoutExpired) as error:
            out[key] = f"unavailable: {error}"
    try:
        out["vendor"] = json.loads(Path("/opt/VERSIONS.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        out["vendor"] = None
    return out


def network_probe() -> dict:
    """判卷容器应当断网。这里只记录事实、不影响判分。

    Harbor 的 no-network 是透明代理：nftables 把全部 TCP 重定向到 sidecar 里的 gost，gost 按（空）白名单
    决定是否转发，所以 TCP 握手总能成功、数据却出不去；探针必须做到应用层——真的发一个 HTTP 请求看有没有回应。
    Harbor 的内核探针失败时会静默关掉出口控制，判卷容器就能上网，这个字段能把它暴露出来
    （汇总工具会统计 isolated=False 的 trial）。"""
    result: dict = {"dns": None, "http": None}
    try:
        socket.gethostbyname("example.com")
        result["dns"] = "resolved"
    except OSError as error:
        result["dns"] = f"blocked: {type(error).__name__}"
    try:
        with urllib.request.urlopen("http://1.1.1.1/", timeout=5) as response:
            result["http"] = f"reached: HTTP {response.status}"
    except urllib.error.HTTPError as error:          # 有 HTTP 回应就说明数据出去了
        result["http"] = f"reached: HTTP {error.code}"
    except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
        reason = getattr(error, "reason", error)
        result["http"] = f"blocked: {type(reason).__name__}"
    result["isolated"] = result["dns"].startswith("blocked") and result["http"].startswith("blocked")
    return result


def reference_board(bench: Path) -> Path:
    config = tomllib.loads((bench / "config.toml").read_text(encoding="utf-8"))
    return bench / config["task"]["reference"]


def grade(task_id: str) -> tuple[dict, dict]:
    task_dir = DATASET / task_id
    bench = task_dir / "bench"
    meta = read_task_meta(task_dir)
    answer = WORKSPACE / "answer.kicad_pcb"
    blocker = WORKSPACE / "BLOCKER.md"
    work = LOGS / "work"
    work.mkdir(parents=True, exist_ok=True)

    grading: dict = {
        "schema_version": "0.1",
        "task_id": task_id, "task_name": meta["name"], "tier": meta["tier"],
        "rules_public": meta["rules_public"], "rules_hidden": meta["rules_hidden"],
        "not_implied": meta["not_implied"],
        "submission_exists": answer.is_file(),
        "answer_sha256": sha256(answer), "answer_bytes": answer.stat().st_size if answer.is_file() else 0,
        "start_sha256": sha256(task_dir / "environment" / "start.kicad_pcb"),
        "blocker": blocker.read_text(encoding="utf-8", errors="replace")[:4000] if blocker.is_file() else None,
        "verifier_calls": count_verifier_calls(WORKSPACE / ".arena" / "verifier_calls.jsonl"),
        "tool_versions": tool_versions(),
        "network": network_probe(),
        "check": None, "reference_check": None,
        "status": None, "infrastructure_reason": None,
        "official_score_available": False,
        "official_score_reason": "本地 Docker 运行，未经第三方盲测；agent 阶段可联网。",
    }
    grading["answer_changed"] = (grading["answer_sha256"] != grading["start_sha256"]) if answer.is_file() else False

    verifier_ok = True
    infra_reason = None
    if not answer.is_file():
        check = {"exit": EXIT_FAIL, "rules": {}, "diagnostics": [], "run": None, "timed_out": False,
                 "error": "答案文件不存在：/workspace/answer.kicad_pcb", "seconds": 0.0}
    else:
        check = run_check(bench, answer, work, "answer")
        if check["timed_out"] or check["exit"] is None:
            verifier_ok, infra_reason = False, check["error"]
        elif check["exit"] == EXIT_PARSE:
            verifier_ok, infra_reason = False, f"任务配置不合法: {check['error']}"
        elif check["exit"] == EXIT_CRASH:
            reference = run_check(bench, reference_board(bench), work, "reference")
            grading["reference_check"] = {k: reference[k] for k in ("exit", "rules", "timed_out", "error", "seconds")}
            if reference["exit"] != EXIT_OK:
                verifier_ok = False
                crashed = [name for name, r in reference["rules"].items() if r["status"] == "crashed"]
                infra_reason = f"参考板同样无法检查（退出 {reference['exit']}，崩溃规则 {crashed}）"
    grading["check"] = check

    rules = check["rules"]
    passed = verifier_ok and check["exit"] == EXIT_OK
    if not verifier_ok:
        status = "infrastructure_failure"
    elif blocker.is_file():
        status = "agent_reported_blocker"
    elif passed:
        status = "passed"
    else:
        status = "capability_failed"
    grading["status"] = status
    grading["infrastructure_reason"] = infra_reason
    grading["verifier_ok"] = verifier_ok

    expected = meta["rules_public"] + meta["rules_hidden"]
    rule_status = {name: rules.get(name, {}).get("status", "missing") for name in expected}
    grading["rule_status"] = rule_status
    n_pass = sum(1 for s in rule_status.values() if s == "pass")
    public_pass = all(rule_status[n] == "pass" for n in meta["rules_public"]) if meta["rules_public"] else True
    hidden_pass = all(rule_status[n] == "pass" for n in meta["rules_hidden"]) if meta["rules_hidden"] else True

    grading["scores"] = {
        "rule_pass_fraction": (n_pass / len(expected)) if expected else 0.0,
        "public_pass": bool(verifier_ok and public_pass),
        "hidden_pass": bool(verifier_ok and hidden_pass),
    }
    reward = {"reward": 1.0 if status == "passed" else 0.0}
    return reward, grading


def selfcheck() -> int:
    from nl2pcb.check import calls as rule_calls
    from nl2pcb.check import rules as _rules  # noqa: F401  完成登记
    from nl2pcb.task import load_task

    problems: list[str] = []
    task_dirs = sorted(p for p in DATASET.iterdir() if (p / "task.toml").is_file())
    if not task_dirs:
        problems.append(f"{DATASET} 下没有任务")
    for task_dir in task_dirs:
        name = task_dir.name
        try:
            meta = read_task_meta(task_dir)
            bench = task_dir / "bench"
            task = load_task(bench)
            keys = {call.key for call in rule_calls.collect(task)}
            declared = set(meta["rules_public"]) | set(meta["rules_hidden"])
            if declared != keys:
                problems.append(f"{name}: task.toml 的 rules_public ∪ rules_hidden = {sorted(declared)}，bench 启用的是 {sorted(keys)}")
            if set(meta["rules_public"]) & set(meta["rules_hidden"]):
                problems.append(f"{name}: 规则同时出现在 public 与 hidden")
            for rel in ("environment/start.kicad_pcb", "environment/task/config.toml", "environment/task/assets/skeleton.kicad_pcb", "bench/assets/skeleton.kicad_pcb"):
                if not (task_dir / rel).is_file():
                    problems.append(f"{name}: 缺 {rel}")
            reference = reference_board(bench)
            result = run_check(bench, reference, Path("/tmp/selfcheck") / name, "reference")
            if result["exit"] != EXIT_OK:
                problems.append(f"{name}: 参考板 {reference.name} 未通过完整检查（退出 {result['exit']}）：{result['rules']}")
            else:
                print(f"ok {name}: rules={sorted(keys)} reference={reference.name} {result['seconds']:.1f}s")
        except Exception as error:  # noqa: BLE001 —— 自检要把每一题的问题都列出来
            problems.append(f"{name}: {type(error).__name__}: {error}")
    for problem in problems:
        print("selfcheck:", problem, file=sys.stderr)
    return 1 if problems else 0


def main() -> int:
    if "--selfcheck" in sys.argv[1:]:
        return selfcheck()
    task_id = os.environ["NL2PCB_TASK_ID"]
    LOGS.mkdir(parents=True, exist_ok=True)
    try:
        reward, grading = grade(task_id)
    except Exception as error:  # noqa: BLE001 —— 评分器自己炸了也要落盘，并标成 infrastructure
        grading = {"schema_version": "0.1", "task_id": task_id, "status": "infrastructure_failure",
                   "infrastructure_reason": f"grader 异常: {type(error).__name__}: {error}", "verifier_ok": False}
        reward = {"reward": 0.0}
    (LOGS / "grading.json").write_text(json.dumps(grading, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    (LOGS / "reward.json").write_text(json.dumps(reward, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"task_id": task_id, "status": grading["status"], "reward": reward["reward"],
                      "rule_status": grading.get("rule_status")}, ensure_ascii=False))
    return 0 if grading.get("verifier_ok") else 1


if __name__ == "__main__":
    sys.exit(main())
