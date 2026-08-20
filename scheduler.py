#!/usr/bin/env python3
"""定时/循环调度入口：供 Codex 自动化、launchd 或 cron 调用。

用法:
  python3 scheduler.py --once                         # 采集一次并生成日报
  python3 scheduler.py --weekly --date 2026-08-16     # 生成指定周（周日为锚点）的周报
  python3 scheduler.py --is-trading-day               # 判断今天是否 A股交易日（0=是，1=否）
  python3 scheduler.py --next-run                     # 预览 8:00/18:00 日报与周日 15:00 周报
  python3 scheduler.py --interval-minutes 60          # 每 60 分钟循环采集（盘中刷新）
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.aggregate import OUTPUT_DIR, default_date, print_report_summary, run_day  # noqa: E402
from src.common import save_json  # noqa: E402
from src.config import ROOT, load_config  # noqa: E402
from src.common import load_json  # noqa: E402

LOG_DIR = os.path.join(ROOT, "data", "logs")
LAST_RUN = os.path.join(ROOT, "data", "last_run.json")
TRADING_CAL = os.path.join(ROOT, "data", "trading_calendar.json")

DAILY_TIMES = ("08:00", "18:00")
WEEKLY_TIME = "15:00"


def setup_logging() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    logfile = os.path.join(LOG_DIR, f"opagg_{time.strftime('%Y-%m-%d')}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(logfile, encoding="utf-8")],
    )


def run_once(sources=None, use_cache=True, since_hours=None, incremental=False, last_run_ts=None) -> dict:
    cfg = load_config()
    date = default_date()
    report = run_day(
        cfg, date, sources=sources, use_cache=use_cache,
        since_hours=since_hours, incremental=incremental, last_run_ts=last_run_ts,
    )
    if not (report.get("posts") or []):
        raise RuntimeError("所有数据源均未采集到内容，本次日报未生成（网络或风控问题，保留旧日报）")
    print_report_summary(report)
    save_json(LAST_RUN, {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "date": date,
        "sources": {k: v.get("status") for k, v in report.get("sources", {}).items()},
        "html": report.get("_html_path"),
    })
    return report


def run_weekly(anchor: str | None = None) -> str:
    from src.weekly import build_weekly, save_weekly

    cfg = load_config()
    weekly = build_weekly(anchor, cfg)
    html = save_weekly(weekly)
    save_json(LAST_RUN, {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "type": "weekly",
        "range": f"{weekly['monday']} ~ {weekly['sunday']}",
        "html": html,
    })
    print(weekly.get("summary", ""))
    print(f"周报: {html}")
    return html


def is_trading_day(d: date | None = None) -> bool:
    """A股交易日 = 周一至周五且不在休市日历中。"""
    d = d or date.today()
    if d.weekday() >= 5:
        return False
    cal = load_json(TRADING_CAL) or {}
    holidays = set(cal.get("holidays", []) or [])
    return d.isoformat() not in holidays


def next_run_preview(include_daily: bool = True) -> str:
    """预览未来 8:00/18:00 日报（若启用）与周日 15:00 周报。"""
    now = datetime.now()
    runs: List[str] = []
    day = now.date()
    horizon = 21
    for i in range(horizon + 1):
        d = day + timedelta(days=i)
        if include_daily and is_trading_day(d):
            for hm in DAILY_TIMES:
                dt = datetime.combine(d, datetime.strptime(hm, "%H:%M").time())
                if dt > now:
                    runs.append(f"日报 {dt.strftime('%Y-%m-%d %H:%M')}（交易日）")
        if d.weekday() == 6:
            dt = datetime.combine(d, datetime.strptime(WEEKLY_TIME, "%H:%M").time())
            if dt > now:
                runs.append(f"周报 {dt.strftime('%Y-%m-%d %H:%M')}（周日）")
        if len(runs) >= 4:
            break
    today = "交易日" if is_trading_day(day) else "非交易日"
    lines = [f"今天: {day.isoformat()}（{['周一','周二','周三','周四','周五','周六','周日'][day.weekday()]}，{today}）"]
    if not include_daily:
        lines.append("日报定时任务: 已停用（config.scheduler.daily_enabled=false，用日报页「立即刷新」）")
    lines += runs or ["未来 3 周内没有安排"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="舆论聚合调度器")
    ap.add_argument("--once", action="store_true", help="只运行一次")
    ap.add_argument("--interval-minutes", type=int, default=0, help="循环间隔（分钟）")
    ap.add_argument("--loops", type=int, default=0, help="循环次数，0=无限")
    ap.add_argument("--sources", default=None, help="逗号分隔: bilibili,guba,xueqiu,ths")
    ap.add_argument("--weekly", action="store_true", help="生成周报")
    ap.add_argument("--date", default=None, help="周报锚点日期 YYYY-MM-DD（默认今天，自动落到所在周）")
    ap.add_argument("--is-trading-day", action="store_true", help="判断今天是否交易日")
    ap.add_argument("--next-run", action="store_true", help="预览下次运行时间")
    ap.add_argument("--require-trading-day", action="store_true", help="非交易日直接跳过（供 launchd 每天触发用）")
    ap.add_argument("--refresh-upmasters", action="store_true", help="采集前先归档 up主素材并刷新风格画像")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--force", action="store_true", help="忽略 config.scheduler.daily_enabled=false，强制执行日报")
    args = ap.parse_args()
    setup_logging()
    logging.info("调度器启动: once=%s interval=%s", args.once, args.interval_minutes)
    sources = [s.strip() for s in args.sources.split(",") if s.strip()] if args.sources else None

    if args.is_trading_day:
        ok = is_trading_day()
        print("TRADING_DAY" if ok else "NOT_TRADING_DAY")
        return 0 if ok else 1
    if args.next_run:
        cfg0 = load_config()
        print(next_run_preview(include_daily=bool((cfg0.get("scheduler", {}) or {}).get("daily_enabled", False))))
        return 0
    if args.weekly:
        run_weekly(args.date)
        return 0
    cfg = load_config()
    sched_cfg = cfg.get("scheduler", {}) or {}
    if not args.force and not sched_cfg.get("daily_enabled", False):
        logging.info("定时日报已停用（config.scheduler.daily_enabled=false），保留周报生成")
        print("DAILY_DISABLED skip（周报不受影响：python3 scheduler.py --weekly）")
        return 0
    if args.require_trading_day and not is_trading_day():
        logging.info("今天非交易日，跳过采集")
        print("NOT_TRADING_DAY skip")
        return 0
    if args.refresh_upmasters:
        from src.upmaster_lib import archive_materials, build_style_profile, load_registry
        for mid_s, entry in load_registry()["upmasters"].items():
            if not entry.get("enabled", True):
                continue
            try:
                stats = archive_materials(mid_s, video_limit=6, dynamic_limit=12, cookie=entry.get("cookie", ""))
                build_style_profile(mid_s)
                logging.info("up主素材归档: %s %s", entry.get("name", mid_s), stats)
            except Exception as e:  # noqa: BLE001
                logging.warning("up主归档失败 %s: %s", mid_s, e)

    if args.once or args.interval_minutes <= 0:
        run_once(sources=sources, use_cache=not args.no_cache)
        return 0

    loop = 0
    last_ts = None
    while args.loops == 0 or loop < args.loops:
        loop += 1
        logging.info("第 %d 轮采集开始", loop)
        try:
            # 盘中循环模式：窗口覆盖到上一轮，并开启增量去重，避免重复上报
            run_once(
                sources=sources,
                use_cache=False,
                since_hours=max(1.0, args.interval_minutes / 60.0),
                incremental=True,
                last_run_ts=last_ts,
            )
            last_ts = time.time()
        except Exception as e:  # noqa: BLE001
            logging.exception("本轮采集失败: %s", e)
        if args.loops != 0 and loop >= args.loops:
            break
        time.sleep(args.interval_minutes * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
