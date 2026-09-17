# NL2PCB-Arena verifier 镜像：FROM agent 镜像，再放进评测侧文件。
#
# 评分与 agent 用同一套 kicad-cli / ngspice / nl2pcb 二进制，所以 agent 自检到的结果和评分一致，
# 只差评分多跑隐藏规则。这里多出来的东西（dataset/*/bench 里的 cases、完整 config、参考板，
# 以及 grader）永远不进 agent 镜像：agent 镜像的构建上下文里根本没有 dataset/。
#
# 构建上下文 = 仓库根（.dockerignore 白名单只放行 dataset/ 与 verifier/）。
ARG AGENT_IMAGE=nl2pcb-arena/agent:dev
FROM ${AGENT_IMAGE}

COPY dataset /opt/nl2pcb-arena/dataset
COPY verifier/grader.py verifier/test.sh /tests/
RUN chmod 755 /tests/test.sh \
    && python3 /tests/grader.py --selfcheck

WORKDIR /workspace
