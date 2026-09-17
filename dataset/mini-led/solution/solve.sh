#!/bin/bash
# oracle：把参考答案放进工作区。Harbor 以 --agent oracle 运行时把 solution/ 挂到 /solution。
set -euo pipefail
cp /solution/reference/answer.kicad_pcb /workspace/answer.kicad_pcb
