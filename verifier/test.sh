#!/bin/bash
# Harbor 在 verifier 容器里执行 /tests/test.sh；任务由 NL2PCB_TASK_ID 选择（task.toml 的 [verifier].env）。
# grader 自己处理评分失败并总是写出 /logs/verifier/reward.json；这里不加 -e，让退出码原样传回。
set -uo pipefail
python3 /tests/grader.py
