#!/usr/bin/env bash
# 在 agent 镜像里运行题包导出（需要 KiCad 的 pcbnew 生成骨架）。
#
#   images/export.sh [tag] [dataset/<task> ...]     默认 tag = dev，默认导出 dataset/ 下全部任务
#
# 以宿主用户身份运行，生成的文件归宿主用户所有。
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tag="${1:-dev}"
shift || true
tasks=("$@")
if [ ${#tasks[@]} -eq 0 ]; then
    for t in "$repo"/dataset/*/task.toml; do tasks+=("dataset/$(basename "$(dirname "$t")")"); done
fi
docker run --rm \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e PYTHONPATH=/repo/src:/opt/nl2pcb-bench/src \
    -v "$repo:/repo" -w /repo \
    "nl2pcb-arena/agent:${tag}" \
    python3 -B -m nl2pcb_arena.cli export "${tasks[@]}" --bench-src /opt/nl2pcb-bench
