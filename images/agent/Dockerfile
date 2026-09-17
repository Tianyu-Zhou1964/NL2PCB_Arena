# NL2PCB-Arena 共享 agent 镜像。
#
# 所有任务的 agent 阶段都从这个镜像派生（dataset/<task>/environment/Dockerfile 只再拷一份公开题包）。
# 里面只有 agent 需要的东西：KiCad 10.0.6（kicad-cli + pcbnew Python）、ngspice、pcblite 命令行、
# 公开自检用的 nl2pcb。评测侧文件（cases/、完整 config、参考板、grader）不在这里，
# 它们只进 images/verifier.Dockerfile（FROM 本镜像）。
#
# 构建参数：
#   BASE_IMAGE   基础镜像；国内服务器可换成 docker.m.daocloud.io/library/ubuntu:24.04
#   APT_MIRROR   Ubuntu 源镜像主机名，如 mirrors.tuna.tsinghua.edu.cn；留空用官方源（必须 http，装 ca-certificates 前 https 不可用）
#   KICAD_VERSION  PPA 里的完整版本串，锁死补丁版本
ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG APT_MIRROR=""
ARG KICAD_VERSION=10.0.6~ubuntu24.04.1
# 预装两个 harness 的 CLI：Harbor 每个 trial 都会在容器里装 agent，但看到 `command -v claude/codex`
# 成功就跳过；预装省掉每次 trial 的联网安装（bootstrap.sh / nvm + npm，慢网下常超 360 s 安装超时）。
# 用 `--ak version=X` 钉了别的版本时 Harbor 会重装，所以这里的版本要和 suite 配置一致。
ARG NODE_VERSION=22.22.2
ARG NODE_MIRROR=https://nodejs.org/dist
ARG NPM_REGISTRY=https://registry.npmjs.org
ARG CLAUDE_CODE_VERSION=2.1.274
ARG CODEX_VERSION=0.154.0

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# KiCad 10.0.6 来自官方 PPA（amd64 与 arm64 都有），不装 kicad-library-*：封装只来自题包。
RUN if [ -n "${APT_MIRROR}" ]; then \
        sed -i "s|http://archive.ubuntu.com/ubuntu|http://${APT_MIRROR}/ubuntu|g; s|http://security.ubuntu.com/ubuntu|http://${APT_MIRROR}/ubuntu|g" /etc/apt/sources.list.d/ubuntu.sources; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl git jq procps ripgrep sudo less nano xz-utils tmux \
        software-properties-common gnupg \
        python3 python3-venv python3-tomli-w \
    && add-apt-repository -y ppa:kicad/kicad-10.0-releases \
    && apt-get update \
    && apt-get install -y --no-install-recommends "kicad=${KICAD_VERSION}" ngspice \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# node 22 + claude-code + codex（版本见上面的 ARG）。
RUN arch="$(dpkg --print-architecture)" \
    && case "$arch" in amd64) narch=x64 ;; arm64) narch=arm64 ;; *) echo "unsupported arch $arch" >&2; exit 1 ;; esac \
    && curl -fsSL "${NODE_MIRROR}/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${narch}.tar.xz" -o /tmp/node.tar.xz \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 --exclude='CHANGELOG.md' --exclude='README.md' --exclude='LICENSE' \
    && rm /tmp/node.tar.xz \
    && npm config set registry "${NPM_REGISTRY}" --location=global \
    && npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force \
    && node --version && claude --version && codex --version

# pcblite：纯标准库，直接放源码树；命令行包装成 `pcblite`。
COPY vendor/pcblite/pcblite /opt/pcblite/pcblite
# nl2pcb：源码树 + parts/ + spec/，包装成 `nl2pcb`。同一份代码在 verifier 镜像里判分，agent 用它自检公开规则。
COPY vendor/NL2PCB-Bench/src /opt/nl2pcb-bench/src
COPY vendor/NL2PCB-Bench/parts /opt/nl2pcb-bench/parts
COPY vendor/NL2PCB-Bench/spec /opt/nl2pcb-bench/spec
COPY vendor/VERSIONS.json /opt/VERSIONS.json
COPY images/agent/bin/pcblite images/agent/bin/nl2pcb /usr/local/bin/
RUN chmod 755 /usr/local/bin/pcblite /usr/local/bin/nl2pcb \
    && python3 -c "import pcbnew; v = pcbnew.GetBuildVersion(); assert v.startswith('10.0.'), v" \
    && PYTHONPATH=/opt/nl2pcb-bench/src python3 -c "import nl2pcb.cli" \
    && PYTHONPATH=/opt/pcblite python3 -m pcblite --help > /dev/null \
    && kicad-cli version && ngspice --version | head -2

# 非 root 用户：ubuntu:24.04 自带的 ubuntu(uid 1000) 换成 agent(uid 1000)。
# 不在这里切 USER：Harbor 以 root 装 agent CLI，再按 task.toml 的 [agent].user 执行。
RUN userdel -r ubuntu 2>/dev/null || true \
    && groupadd --gid 1000 agent \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash agent \
    && echo 'agent ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/agent \
    && mkdir -p /task /workspace /logs \
    && chown agent:agent /workspace /logs

ENV KICAD_CLI=/usr/bin/kicad-cli \
    NL2PCB_KICAD_CLI=/usr/bin/kicad-cli \
    NL2PCB_NGSPICE=/usr/bin/ngspice

WORKDIR /workspace
