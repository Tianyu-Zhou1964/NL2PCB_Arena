"""判卷一致性：把 Bench 专家标注的案例板逐个喂给判卷镜像，判定必须与标注一致。

案例来自 dataset/<id>/bench/config.toml 的 [[cases]]：pass 列表里的规则必须判 pass，
fail 列表里的必须判 fail，unlabeled 不做断言。另外验证：
- reward.json 只有一个键 reward，值 ∈ {0, 1}，且 reward == 1 当且仅当 status == passed；
- [task].reference 参考板必须 passed；
- 没交答案 → capability_failed；写了 BLOCKER.md → agent_reported_blocker。
判卷容器和评测时一样断网跑。
"""

from __future__ import annotations

import json

import pytest

from conftest import DATASET, VERIFIER_IMAGE, docker_available, docker_run, image_exists, read_toml, sha256, task_ids

pytestmark = pytest.mark.skipif(
    not (docker_available() and image_exists(VERIFIER_IMAGE)),
    reason=f"需要 Docker 与已构建的 {VERIFIER_IMAGE}",
)

STATUSES = {"passed", "capability_failed", "agent_reported_blocker", "infrastructure_failure"}


def grade_in_container(task_id: str, setup: str) -> tuple[dict, dict, int]:
    """在判卷容器里执行 setup（准备 /workspace），跑 /tests/test.sh，取回 grading/reward。"""
    script = (
        f"{setup}; /tests/test.sh >/logs/test.out 2>&1; code=$?; "
        "cat /logs/verifier/grading.json; echo '@@@'; cat /logs/verifier/reward.json; echo '@@@'; echo $code"
    )
    result = docker_run(VERIFIER_IMAGE, "bash", "-c", script, env={"NL2PCB_TASK_ID": task_id})
    assert result.returncode == 0, result.stderr
    grading_text, reward_text, code = result.stdout.split("@@@")
    return json.loads(grading_text), json.loads(reward_text), int(code)


def _cases():
    for task_id in task_ids():
        config = read_toml(DATASET / task_id / "bench" / "config.toml")
        for case in config.get("cases", []):
            yield pytest.param(task_id, case, id=f"{task_id}:{case['board']}")


def _assert_reward_contract(grading: dict, reward: dict) -> None:
    assert set(reward) == {"reward"}, "reward.json 必须只有 reward 一个键（Harbor 才算 pass@k）"
    assert reward["reward"] in (0.0, 1.0)
    assert grading["status"] in STATUSES
    assert (reward["reward"] == 1.0) == (grading["status"] == "passed")


@pytest.mark.parametrize("task_id,case", list(_cases()))
def test_annotated_case(task_id, case):
    board = f"/opt/nl2pcb-arena/dataset/{task_id}/bench/{case['board']}"
    grading, reward, code = grade_in_container(task_id, f"cp {board} /workspace/answer.kicad_pcb")
    assert code == 0 and grading["verifier_ok"], grading.get("infrastructure_reason")
    assert grading["status"] != "infrastructure_failure", grading.get("infrastructure_reason")
    _assert_reward_contract(grading, reward)
    rule_status = grading["rule_status"]
    for rule in case.get("pass", []):
        assert rule_status.get(rule) == "pass", f"{case['board']}: 标注 {rule} 应 pass，判卷给 {rule_status.get(rule)}"
    for rule in case.get("fail", []):
        assert rule_status.get(rule) == "fail", f"{case['board']}: 标注 {rule} 应 fail，判卷给 {rule_status.get(rule)}"
    # 起手板本身也是案例板之一（修复题），交它上去 answer_changed 必然为假
    start = DATASET / task_id / "environment" / "start.kicad_pcb"
    assert grading["answer_changed"] == (sha256(DATASET / task_id / "bench" / case["board"]) != sha256(start))


@pytest.mark.parametrize("task_id", task_ids())
def test_reference_board_passes(task_id):
    reference = read_toml(DATASET / task_id / "bench" / "config.toml")["task"]["reference"]
    board = f"/opt/nl2pcb-arena/dataset/{task_id}/bench/{reference}"
    grading, reward, _ = grade_in_container(task_id, f"cp {board} /workspace/answer.kicad_pcb")
    assert grading["status"] == "passed", grading["rule_status"]
    assert reward == {"reward": 1.0}
    assert all(v == "pass" for v in grading["rule_status"].values())


@pytest.mark.parametrize("task_id", task_ids())
def test_missing_submission(task_id):
    grading, reward, code = grade_in_container(task_id, "rm -f /workspace/answer.kicad_pcb")
    assert code == 0
    assert grading["submission_exists"] is False
    assert grading["status"] == "capability_failed"
    assert reward == {"reward": 0.0}


@pytest.mark.parametrize("task_id", task_ids())
def test_blocker_reported(task_id):
    grading, reward, _ = grade_in_container(task_id, "printf '缺少 D2 的封装\\n' > /workspace/BLOCKER.md")
    assert grading["status"] == "agent_reported_blocker"
    assert "D2" in (grading.get("blocker") or "")
    assert reward == {"reward": 0.0}
