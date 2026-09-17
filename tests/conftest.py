"""Docker 相关测试的共用工具。

本机没有 Docker 或没构建过镜像时，这些测试整体跳过；在 zhou 服务器上
`images/build.sh dev all` 之后 `uv run pytest` 即可全跑。
镜像 tag 用环境变量 NL2PCB_ARENA_TAG 覆盖，默认 dev。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATASET = REPO / "dataset"
TAG = os.environ.get("NL2PCB_ARENA_TAG", "dev")
AGENT_IMAGE = f"nl2pcb-arena/agent:{TAG}"
VERIFIER_IMAGE = f"nl2pcb-arena/verifier:{TAG}"


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def image_exists(image: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0


def task_ids() -> list[str]:
    if not DATASET.exists():
        return []
    return sorted(p.name for p in DATASET.iterdir() if (p / "task.toml").exists())


def read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def task_meta(task_id: str) -> dict:
    return read_toml(DATASET / task_id / "task.toml")["metadata"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def docker_run(image: str, *cmd: str, user: str | None = None, network: str = "none",
               env: dict[str, str] | None = None, timeout: int = 900) -> subprocess.CompletedProcess:
    """跑一次性容器；默认断网，和评测时一样。"""
    args = ["docker", "run", "--rm", "--network", network]
    if user:
        args += ["--user", user]
    for key, value in (env or {}).items():
        args += ["-e", f"{key}={value}"]
    args += [image, *cmd]
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
