# 由 nl2pcb_arena.export 生成：在共享 agent 镜像上放进本题的公开题包与起手板。
# Harbor 用本目录做构建上下文；这里没有 cases/、完整 config、参考板。
FROM nl2pcb-arena/agent:dev
COPY --chown=root:root task /task
COPY --chown=agent:agent start.kicad_pcb /workspace/answer.kicad_pcb
RUN chmod -R a-w /task
WORKDIR /workspace
