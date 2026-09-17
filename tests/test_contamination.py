"""污染审计：agent 看到的考场镜像里不能有任何评测侧文件。

每道题从 dataset/<id>/environment/Dockerfile 构建考场镜像（和 Harbor 一样），
再以 agent 用户进去检查：
1. 没有 cases/ 目录、/opt/nl2pcb-arena、/tests；
2. 镜像里任何 .toml / .kicad_pcb 文件的哈希都不等于评测侧的 bench/config.toml 与 bench/cases/*（起手板除外：它本就发给 agent）；
3. /task/config.toml 不出现隐藏规则的名字；
4. /task 对 agent 只读，/workspace/answer.kicad_pcb 可写且等于 environment/start.kicad_pcb；
5. 公开自检 `nl2pcb check` 恰好只报公开规则。
"""

from __future__ import annotations

import json
import subprocess

import pytest

from conftest import AGENT_IMAGE, DATASET, docker_available, docker_run, image_exists, sha256, task_ids, task_meta

pytestmark = pytest.mark.skipif(
    not (docker_available() and image_exists(AGENT_IMAGE)),
    reason=f"需要 Docker 与已构建的 {AGENT_IMAGE}",
)


@pytest.fixture(scope="module", params=task_ids())
def env_image(request):
    task_id = request.param
    tag = f"nl2pcb-arena/env-{task_id}:test"
    build = subprocess.run(["docker", "build", "-q", "-t", tag, str(DATASET / task_id / "environment")],
                           capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    return task_id, tag


def test_no_verifier_paths(env_image):
    _, tag = env_image
    result = docker_run(tag, "sh", "-c",
                        "find / -xdev \\( -path /proc -o -path /sys \\) -prune -o "
                        "\\( -name cases -o -path /opt/nl2pcb-arena -o -path /tests -o -name grader.py \\) -print",
                        user="agent")
    assert result.stdout.strip() == "", f"考场镜像里出现评测侧路径：\n{result.stdout}"


def test_no_verifier_file_contents(env_image):
    task_id, tag = env_image
    bench = DATASET / task_id / "bench"
    forbidden = {sha256(bench / "config.toml"): "bench/config.toml"}
    for board in sorted((bench / "cases").glob("*.kicad_pcb")):
        forbidden[sha256(board)] = f"bench/cases/{board.name}"
    # 起手板本来就发给 agent（修复题的起手板就是某块案例板的原样副本），不算泄漏
    forbidden.pop(sha256(DATASET / task_id / "environment" / "start.kicad_pcb"), None)
    result = docker_run(tag, "sh", "-c",
                        "find / -xdev \\( -path /proc -o -path /sys \\) -prune -o -type f "
                        "\\( -name '*.toml' -o -name '*.kicad_pcb' \\) -print0 | xargs -0 sha256sum",
                        user="agent")
    assert result.returncode == 0, result.stderr
    leaked = [line for line in result.stdout.splitlines() if line.split()[0] in forbidden]
    assert not leaked, "评测侧文件内容泄漏进考场镜像：\n" + "\n".join(
        f"{line}  == {forbidden[line.split()[0]]}" for line in leaked)


def test_public_config_has_no_hidden_rules(env_image):
    task_id, tag = env_image
    hidden = task_meta(task_id)["rules_hidden"]
    result = docker_run(tag, "cat", "/task/config.toml", user="agent")
    assert result.returncode == 0, result.stderr
    for rule in hidden:
        assert rule not in result.stdout, f"公开 config 里出现隐藏规则 {rule}"
    assert "cases" not in result.stdout


def test_task_readonly_and_workspace_writable(env_image):
    task_id, tag = env_image
    start = DATASET / task_id / "environment" / "start.kicad_pcb"
    script = (
        "set -e; "
        "! touch /task/_probe 2>/dev/null; "
        "! touch /task/assets/_probe 2>/dev/null; "
        "test -w /workspace/answer.kicad_pcb; "
        "sha256sum /workspace/answer.kicad_pcb | cut -d' ' -f1; "
        "id -un"
    )
    result = docker_run(tag, "sh", "-c", script, user="agent")
    assert result.returncode == 0, result.stderr
    got_hash, user = result.stdout.split()
    assert got_hash == sha256(start), "起手板与 environment/start.kicad_pcb 不一致"
    assert user == "agent"


def test_public_check_runs_only_public_rules(env_image):
    task_id, tag = env_image
    public = set(task_meta(task_id)["rules_public"])
    result = docker_run(tag, "nl2pcb", "check", "/task", "/workspace/answer.kicad_pcb", "--json", user="agent")
    assert result.returncode in (0, 1), f"公开自检异常退出 {result.returncode}:\n{result.stderr}"
    reported = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        obj = json.loads(line)
        if "report" in obj:
            reported.add(obj["report"]["rule"])
    assert reported == public, f"公开自检跑的规则 {sorted(reported)} != 公开规则 {sorted(public)}"
