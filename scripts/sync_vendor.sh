#!/usr/bin/env bash
# 把本地 checkout 的 NL2PCB-Bench 与 pcblite 复制成 vendor/ 快照，并记录 commit。
# vendor/ 不进 git（只提交 VERSIONS.json）；镜像构建从 vendor/ 拷贝，不在构建期访问网络。
#
# 用法：scripts/sync_vendor.sh <NL2PCB-Bench 目录> <pcblite 仓库目录>
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench_src="${1:?NL2PCB-Bench 目录}"
pcblite_src="${2:?pcblite 仓库目录}"

rm -rf "$repo/vendor/NL2PCB-Bench" "$repo/vendor/pcblite"
mkdir -p "$repo/vendor/NL2PCB-Bench" "$repo/vendor/pcblite"
rsync -a --delete \
    --include='src/***' --include='parts/***' --include='spec/***' --include='tasks/***' \
    --include='pyproject.toml' --include='README.md' --include='AGENTS.md' \
    --exclude='*' \
    "$bench_src/" "$repo/vendor/NL2PCB-Bench/"
rsync -a --delete "$pcblite_src/pcblite/" "$repo/vendor/pcblite/pcblite/"
find "$repo/vendor" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$repo/vendor/NL2PCB-Bench/tasks" -path '*/assets' -type d -prune -exec rm -rf {} + 2>/dev/null || true

bench_commit="$(git -C "$bench_src" rev-parse HEAD)"
pcblite_commit="$(git -C "$pcblite_src" rev-parse HEAD)"
# 只统计被复制的子树是否有未提交改动；仓库其他部分（语料、报告）与镜像无关。
bench_dirty="$(git -C "$bench_src" status --porcelain -- src parts spec tasks pyproject.toml | wc -l | tr -d ' ')"
pcblite_dirty="$(git -C "$pcblite_src" status --porcelain -- pcblite | wc -l | tr -d ' ')"
cat > "$repo/vendor/VERSIONS.json" <<EOF
{
  "NL2PCB-Bench": {"commit": "$bench_commit", "dirty_files": $bench_dirty, "source": "$bench_src"},
  "pcblite": {"commit": "$pcblite_commit", "dirty_files": $pcblite_dirty, "source": "$pcblite_src"},
  "synced_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
cat "$repo/vendor/VERSIONS.json"
