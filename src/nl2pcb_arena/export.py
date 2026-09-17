"""把一个任务的评测侧目录（bench/）导出成发给 agent 的公开题包（environment/）。

一个任务目录：
    dataset/<id>/
      task.toml                 Harbor 任务配置；[metadata] 里是 Arena 自己的字段
      instruction.md            题面，唯一提示
      bench/                    Bench 任务目录（config.toml、spec.md、cases/），评测侧
      start.kicad_pcb           可选：起手板（修复题）；没有就用骨架
      environment/              ← 本模块生成：Dockerfile、start.kicad_pcb、task/{spec.md,config.toml,assets/}
      solution/solve.sh         oracle：把 solution/reference/answer.kicad_pcb 放进工作区

公开 config.toml 由 bench/config.toml 派生：去掉 [[cases]]；[rules] 只留 rules_public 点名的调用；
默认开启但被列为隐藏的规则写 level = "off"；task.reference 改指 assets/skeleton.kicad_pcb。
bench/assets/ 与 environment/task/assets/ 都由 Bench 的 build_assets 生成（需要 KiCad 的 pcbnew，
所以本模块通常在 agent 镜像里运行：images/export.sh）。

本模块不含评分逻辑；生成后用 nl2pcb 自己的 load_task + collect 复核公开 config 恰好只含公开规则。
"""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

__all__ = ["ExportError", "export_task", "public_config"]

DOCKERFILE = """\
# 由 nl2pcb_arena.export 生成：在共享 agent 镜像上放进本题的公开题包与起手板。
# Harbor 用本目录做构建上下文；这里没有 cases/、完整 config、参考板。
FROM {agent_image}
COPY --chown=root:root task /task
COPY --chown=agent:agent start.kicad_pcb /workspace/answer.kicad_pcb
RUN chmod -R a-w /task
WORKDIR /workspace
"""

HIDDEN_OFF_REASON = "隐藏规则：评分时运行，公开自检不含"


class ExportError(ValueError):
    pass


def read_metadata(task_dir: Path) -> dict[str, Any]:
    config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
    meta = config.get("metadata", {})
    public = list(meta.get("rules_public", []))
    hidden = list(meta.get("rules_hidden", []))
    if set(public) & set(hidden):
        raise ExportError(f"{task_dir.name}: 规则同时在 rules_public 与 rules_hidden：{sorted(set(public) & set(hidden))}")
    return {"public": public, "hidden": hidden, "start_board": meta.get("start_board", ""),
            "agent_image": meta.get("agent_image", "nl2pcb-arena/agent:dev")}


def public_config(bench_config: dict[str, Any], public: list[str], hidden: list[str],
                  default_on: set[str]) -> dict[str, Any]:
    """从完整 config 得到公开 config（纯字典变换，不读文件）。

    规则调用的键 = 条目的 id，缺省为规则名（同 Bench 的 RuleCall.key）。
    默认开启的规则（注册表 level 不是 off）若被列为隐藏且配置里没点名，要显式写 off，否则 Bench 会默认跑它。
    评测侧显式 level = off 且不在公开/隐藏名单里的规则，公开版原样保留（两边都关）。
    """
    out: dict[str, Any] = {}
    for section in ("schema", "task", "assets", "conditions", "output"):
        if section in bench_config:
            out[section] = bench_config[section]
    out["task"] = {**bench_config["task"], "reference": "assets/skeleton.kicad_pcb"}
    rules_out: dict[str, list[dict[str, Any]]] = {}
    for name, entries in bench_config.get("rules", {}).items():
        kept = [e for e in entries if (e.get("id") or name) in public]
        dropped = [e for e in entries if (e.get("id") or name) in hidden]
        off = [e for e in entries if e.get("level") == "off" and (e.get("id") or name) not in public + hidden]
        if kept:
            rules_out[name] = kept
        elif dropped and name in default_on:
            rules_out[name] = [{"level": "off", "reason": HIDDEN_OFF_REASON}]
        elif off:
            rules_out[name] = off   # 评测侧就明确关掉的规则（如选型题的 pcb.drc）：公开版保持关，否则默认规则会重新打开
    for name in hidden:
        if name in default_on and name not in bench_config.get("rules", {}):
            rules_out[name] = [{"level": "off", "reason": HIDDEN_OFF_REASON}]
    if rules_out:
        out["rules"] = rules_out
    return out


def _default_on_rules() -> set[str]:
    from nl2pcb.check import registry
    from nl2pcb.check import rules as _rules  # noqa: F401  完成登记
    return {meta.name for meta in registry.list_rules() if meta.fn is not None and meta.level != "off"
            and registry.find_default_method(meta.name) == meta.method}


def _collect_keys(task_dir: Path) -> set[str]:
    from nl2pcb.check import calls as rule_calls
    from nl2pcb.check import rules as _rules  # noqa: F401  导入即完成规则登记
    from nl2pcb.task import load_task
    return {call.key for call in rule_calls.collect(load_task(task_dir))}


def _replace_dir(target: Path, source: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))


def export_task(task_dir: Path, *, bench_src: Path) -> Path:
    """生成 task_dir/environment/，返回它。bench_src 是 NL2PCB-Bench 源码树（含 parts/ 与 spec/）。"""
    from nl2pcb.assets.builder import build_assets

    task_dir = Path(task_dir).resolve()
    bench = task_dir / "bench"
    if not (bench / "config.toml").is_file():
        raise ExportError(f"{task_dir}: 缺 bench/config.toml")
    meta = read_metadata(task_dir)

    build_assets(bench, parts_root=bench_src / "parts", format_doc=bench_src / "spec" / "mini_kicad.md")
    full_keys = _collect_keys(bench)
    declared = set(meta["public"]) | set(meta["hidden"])
    if declared != full_keys:
        raise ExportError(f"{task_dir.name}: rules_public ∪ rules_hidden = {sorted(declared)}，bench 启用的是 {sorted(full_keys)}")

    env_dir = task_dir / "environment"
    env_dir.mkdir(exist_ok=True)
    public_dir = env_dir / "task"
    if public_dir.exists():
        shutil.rmtree(public_dir)
    public_dir.mkdir()
    shutil.copyfile(bench / "spec.md", public_dir / "spec.md")
    _replace_dir(public_dir / "assets", bench / "assets")
    bench_config = tomllib.loads((bench / "config.toml").read_text(encoding="utf-8"))
    config = public_config(bench_config, meta["public"], meta["hidden"], _default_on_rules())
    (public_dir / "config.toml").write_text(
        "# 公开自检配置，由 nl2pcb_arena.export 从评测侧 config 派生：只含公开规则，不含案例。\n"
        + tomli_w.dumps(config), encoding="utf-8")
    public_keys = _collect_keys(public_dir)
    if public_keys != set(meta["public"]):
        raise ExportError(f"{task_dir.name}: 公开 config 启用了 {sorted(public_keys)}，应为 {sorted(meta['public'])}")

    start = task_dir / meta["start_board"] if meta["start_board"] else bench / "assets" / "skeleton.kicad_pcb"
    if not start.is_file():
        raise ExportError(f"{task_dir.name}: 起手板不存在 {start}")
    shutil.copyfile(start, env_dir / "start.kicad_pcb")
    (env_dir / "Dockerfile").write_text(DOCKERFILE.format(agent_image=meta["agent_image"]), encoding="utf-8")
    (env_dir / ".gitkeep").unlink(missing_ok=True)
    return env_dir
