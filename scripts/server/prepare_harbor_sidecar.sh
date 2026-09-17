#!/usr/bin/env bash
# 为 Harbor 预构建"出口控制 sidecar"镜像（拉不到 Docker Hub 的机器用，比如 zhou）。
#
# Harbor 的 no-network / 白名单出网都靠一个 sidecar 容器（基础镜像 gogost/gost）实现。
# Harbor 会按 Dockerfile 里钉死的 digest 从 Docker Hub 拉基础镜像来构建 sidecar；
# 拉不到就整个判卷阶段报 RuntimeError（见 docs/PLAN.md 风险表）。
# 本脚本：
#   1. 从可用镜像站按同一个 digest 拉 gost（digest 相同即内容相同）；
#   2. 用 Harbor 自己的哈希算法算出它期望的 sidecar 镜像名，用镜像站地址替换 FROM 后构建同名镜像。
# Harbor 构建前会先查本地有无同名镜像，有就直接复用，之后 harbor run 不再需要 Docker Hub。
#
# 用法：scripts/server/prepare_harbor_sidecar.sh [镜像站前缀]   默认 docker.1panel.live
# 注意：升级 Harbor 后要重跑（sidecar 的 Dockerfile 变了，镜像名的哈希就变）。
set -euo pipefail

mirror="${1:-docker.1panel.live}"
harbor_bin="$(command -v harbor)" || { echo "找不到 harbor（uv tool install harbor）" >&2; exit 1; }
harbor_py="$(dirname "$(readlink -f "$harbor_bin")")/python"

info="$("$harbor_py" - <<'PY'
import asyncio
from harbor.environments.docker.docker import DockerEnvironment as D
from harbor.environments.docker.utils import _compute_image_name, default_docker_platform
from harbor.utils.container_cache import docker_build_context_hash

ctx = D._EGRESS_CONTROL_SIDECAR_CONTEXT_PATH
platform = asyncio.run(default_docker_platform())
key = docker_build_context_hash(context=ctx, dockerfile_path=ctx / "Dockerfile", build_args={}, platform=platform)
print(ctx)
print(_compute_image_name(D._EGRESS_CONTROL_SIDECAR_DOCKER_NAME, key))
print(platform)
PY
)"
context="$(sed -n 1p <<<"$info")"
image="$(sed -n 2p <<<"$info")"
platform="$(sed -n 3p <<<"$info")"

if docker image inspect "$image" >/dev/null 2>&1; then
    echo "已存在：$image"
    exit 0
fi

base="$(sed -n 's/^FROM[[:space:]]\{1,\}//p' "$context/Dockerfile" | head -1)"   # gogost/gost:TAG@sha256:...
[[ "$base" == *@sha256:* ]] || { echo "sidecar Dockerfile 的 FROM 没有钉 digest：$base" >&2; exit 1; }
digest_ref="${base%%:*}@${base##*@}"                                              # gogost/gost@sha256:...

echo "== 拉基础镜像：$mirror/$digest_ref"
docker pull --platform "$platform" "$mirror/$digest_ref"

echo "== 构建 $image（FROM 改走镜像站）"
sed "0,/^FROM[[:space:]]/s|^FROM[[:space:]].*|FROM $mirror/$digest_ref|" "$context/Dockerfile" \
    | docker build --platform "$platform" -t "$image" -f - "$context"
echo "完成：$image"
