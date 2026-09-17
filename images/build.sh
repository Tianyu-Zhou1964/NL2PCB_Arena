#!/usr/bin/env bash
# 构建两个共享镜像：agent（考场）与 verifier（判卷），中间在 agent 镜像里导出全部题包。
#
#   images/build.sh [tag] [agent|export|verifier|all]     默认 tag = dev，默认 all
#   环境变量：BASE_IMAGE、APT_MIRROR 透传给 agent 镜像的构建参数
#
# agent 镜像的构建上下文只含 vendor/ 与 images/agent（用 tar 拼出来），dataset/ 与 verifier/
# 物理上不在上下文里。verifier 镜像的上下文是仓库根，受 .dockerignore 白名单约束。
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tag="${1:-dev}"
what="${2:-all}"
agent_image="nl2pcb-arena/agent:${tag}"
verifier_image="nl2pcb-arena/verifier:${tag}"

[ -f "$repo/vendor/VERSIONS.json" ] || { echo "先运行 scripts/sync_vendor.sh 生成 vendor/" >&2; exit 1; }

if [ "$what" = agent ] || [ "$what" = all ]; then
    build_args=()
    [ -n "${BASE_IMAGE:-}" ] && build_args+=(--build-arg "BASE_IMAGE=${BASE_IMAGE}")
    [ -n "${APT_MIRROR:-}" ] && build_args+=(--build-arg "APT_MIRROR=${APT_MIRROR}")
    echo "== build $agent_image"
    tar -C "$repo" -c vendor images/agent \
        | docker build "${build_args[@]}" -f images/agent/Dockerfile -t "$agent_image" -
fi

if [ "$what" = export ] || [ "$what" = all ]; then
    echo "== export task packages with $agent_image"
    "$repo/images/export.sh" "$tag"
fi

if [ "$what" = verifier ] || [ "$what" = all ]; then
    echo "== build $verifier_image"
    docker build --build-arg "AGENT_IMAGE=${agent_image}" -f "$repo/images/verifier.Dockerfile" -t "$verifier_image" "$repo"
fi

echo "== images"
docker image inspect --format '{{.RepoTags}} {{.Id}}' "$agent_image" "$verifier_image" 2>/dev/null || true
