#!/usr/bin/env python3
"""命令行入口：聚合当日舆论并生成 HTML 日报。

用法:
  python3 run.py                      # 今日
  python3 run.py --date 2026-08-13    # 指定日期
  python3 run.py --sources bilibili,guba --no-cache
  python3 run.py --open               # 生成后打开浏览器
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.aggregate import default_date, print_report_summary, run_day  # noqa: E402
from src.config import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="当日舆论聚合与蒸馏日报")
    ap.add_argument("--date", default=None, help="日期 YYYY-MM-DD，默认今天")
    ap.add_argument("--sources", default=None, help="逗号分隔: bilibili,guba,xueqiu,ths")
    ap.add_argument("--no-cache", action="store_true", help="忽略已有原始数据缓存")
    ap.add_argument("--since-hours", type=float, default=None, help="统计窗口：只汇总最近 N 小时（默认按 config time_window）")
    ap.add_argument("--open", action="store_true", help="生成后打开浏览器")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    date = args.date or default_date()
    sources = [s.strip() for s in args.sources.split(",") if s.strip()] if args.sources else None
    report = run_day(
        cfg, date, sources=sources, use_cache=not args.no_cache,
        since_hours=args.since_hours,
    )
    print_report_summary(report)
    if args.open:
        webbrowser.open(report["_html_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
