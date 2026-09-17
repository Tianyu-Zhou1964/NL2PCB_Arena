"""命令行入口。

    nl2pcb-arena export <TASK_DIR>... --bench-src <NL2PCB-Bench 目录>   生成公开题包（需要 KiCad Python）
    nl2pcb-arena report <JOB_DIR>... [--out DIR]                        汇总 Harbor 的 job 结果
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nl2pcb-arena", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    export_parser = commands.add_parser("export", help="从 bench/ 生成 environment/ 公开题包")
    export_parser.add_argument("tasks", type=Path, nargs="+", help="任务目录（含 task.toml 与 bench/）")
    export_parser.add_argument("--bench-src", type=Path, required=True, help="NL2PCB-Bench 源码树（含 parts/ 与 spec/）")

    report_parser = commands.add_parser("report", help="汇总 Harbor job 目录")
    report_parser.add_argument("jobs", type=Path, nargs="+", help="Harbor job 目录（含各 trial 子目录）")
    report_parser.add_argument("--out", type=Path, default=None, help="输出目录（默认第一个 job 目录）")
    report_parser.add_argument("--prices", type=Path, default=None, help="models.toml：按 token 估算成本")

    args = parser.parse_args(argv)
    if args.command == "export":
        from .export import ExportError, export_task
        try:
            for task_dir in args.tasks:
                print(export_task(task_dir, bench_src=args.bench_src.resolve()))
        except ExportError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        return 0
    if args.command == "report":
        from .report import write_report
        out = write_report(args.jobs, out_dir=args.out, prices_path=args.prices)
        print(out)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
