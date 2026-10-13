from __future__ import annotations

import sys


def register(subparsers) -> None:
    roast_parser = subparsers.add_parser("roast-context", help="Summarize metadata collected by the roast monitor")
    roast_parser.add_argument("--hours", type=float, default=24.0, help="How far back to look (default: 24)")
    roast_parser.add_argument("--tail", type=int, default=10, help="Per-minute rows to include (default: 10)")

    subparsers.add_parser("roast-events", help="Open the roast event panel without the monitor")


def handle(args) -> bool:
    """处理 roast 相关子命令；不是这里的命令就返回 False"""
    if args.command == "roast-context":
        from .context import summarize

        # Windows 控制台默认编码可能不是 UTF-8，吐槽文本里有中文
        sys.stdout.reconfigure(encoding="utf-8")
        print(summarize(hours=args.hours, tail=args.tail))
        return True

    if args.command == "roast-events":
        from .event_panel import launch_event_panel

        launch_event_panel()
        return True

    return False
