"""每日聚合流水线：采集 → 缓存 → 蒸馏 → 日报渲染。"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterable, List

from . import distill
from .common import load_json, log, now_str, save_json
from .config import ROOT, load_config

DATA_DIR = os.path.join(ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
SUMMARY_DIR = os.path.join(DATA_DIR, "summary")
OUTPUT_DIR = os.path.join(ROOT, "output")
STATE_DIR = os.path.join(DATA_DIR, "state")

SOURCE_LABELS = {
    "bilibili": "B站",
    "guba": "股吧",
    "xueqiu": "雪球",
    "ths": "同花顺",
    "sector": "板块",
    "jin10": "金十",
    "cls": "财联社",
    "em": "东方财富",
}


def collect_day(
    config: Dict[str, Any],
    date_str: str,
    sources: Iterable[str] | None = None,
    use_cache: bool = True,
    since_ts: int | None = None,
    seen: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    raw_path = os.path.join(RAW_DIR, f"{date_str}.json")
    cached: Dict[str, Any] = {}
    if os.path.exists(raw_path):
        cached = load_json(raw_path) or {}
    enabled = [s for s, v in config.items() if isinstance(v, dict) and v.get("enabled")]
    enabled = [s for s in enabled if s in SOURCE_LABELS]
    if sources is not None:
        requested = set(sources)
        enabled = [s for s in enabled if s in requested]
    result: Dict[str, Any] = {
        "date": date_str,
        "collected_at": cached.get("collected_at") or now_str(),
        "posts": list(cached.get("posts", []) or []),
        "items": dict(cached.get("items", {}) or {}),
        "sources": dict(cached.get("sources", {}) or {}),
    }
    need = []
    if use_cache:
        for name in enabled:
            if name in result["sources"]:
                log.info("使用缓存: %s", name)
                continue
            need.append(name)
    else:
        # --no-cache：重取所有启用源，但保留其他源的历史缓存（避免误删）
        refetch = set(enabled)
        result["posts"] = [p for p in result["posts"] if (p.get("source") or "") not in refetch]
        need = list(enabled)
    for name in need:
        t0 = time.time()
        try:
            if name == "bilibili":
                from .bilibili import BilibiliClient
                out = BilibiliClient(config.get("bilibili", {})).collect(since_ts=since_ts, seen=seen)
            elif name == "guba":
                from .guba import GubaClient
                out = GubaClient(config.get("guba", {})).collect(config)
            elif name == "xueqiu":
                from .xueqiu import XueqiuClient
                out = XueqiuClient(config.get("xueqiu", {})).collect()
            elif name == "ths":
                from .ths import ThsClient
                out = ThsClient(config.get("ths", {})).collect()
            elif name == "sector":
                from .sector import SectorClient
                out = SectorClient(config.get("sector", {})).collect()
            elif name == "jin10":
                from .jin10 import Jin10Client
                out = Jin10Client(config.get("jin10", {})).collect()
            elif name == "cls":
                from .cls import ClsClient
                out = ClsClient(config.get("cls", {})).collect()
            elif name == "em":
                from .em import EmClient
                out = EmClient(config.get("em", {})).collect()
            else:
                continue
        except Exception as e:  # noqa: BLE001
            out = {"status": "error", "error": str(e), "posts": [], "items": {}}
        posts = out.get("posts", []) or []
        result["posts"] += posts
        result["items"][name] = out.get("items", {}) or {}
        result["sources"][name] = {
            "label": SOURCE_LABELS.get(name, name),
            "status": out.get("status", "ok"),
            "error": out.get("error", ""),
            "count": len(posts),
            "elapsed_ms": int((time.time() - t0) * 1000),
        }
        # 持续取数兜底：本次采集失败/无数据时，回退到上次成功的缓存，避免日报数据被清空
        if (not posts or out.get("status") == "error") and name in cached.get("sources", {}):
            cached_posts = [
                p for p in (cached.get("posts", []) or [])
                if p.get("source") == name
            ]
            cached_items = (cached.get("items", {}) or {}).get(name, {}) or {}
            if cached_posts or cached_items:
                log.warning("数据源 %s 本次采集失败（%s），回退到上次缓存 %d 条", name, out.get("status"), len(cached_posts))
                result["posts"] = [p for p in result["posts"] if p.get("source") != name] + cached_posts
                result["items"][name] = cached_items
                result["sources"][name] = {
                    "label": SOURCE_LABELS.get(name, name),
                    "status": "partial",
                    "error": (out.get("error") or "") + "（已回退上次缓存）",
                    "count": len(cached_posts),
                    "elapsed_ms": int((time.time() - t0) * 1000),
                }
                posts = cached_posts
        log.info("%s 采集完成: %s (%d 条)", name, out.get("status"), len(posts))
    if need:
        result["collected_at"] = now_str()
        save_json(raw_path, result)
    elif cached:
        log.info("全部命中缓存: %s", raw_path)
    return result


def run_day(
    config: Dict[str, Any],
    date_str: str,
    sources: Iterable[str] | None = None,
    use_cache: bool = True,
    since_hours: float | None = None,
    last_run_ts: float | None = None,
    incremental: bool = False,
) -> Dict[str, Any]:
    since_ts, until_ts, window_mode = compute_window(config, date_str, since_hours, last_run_ts)
    seen_state: Dict[str, Any] = {}
    if incremental:
        seen_path = os.path.join(STATE_DIR, f"seen_{date_str}.json")
        seen_state = load_json(seen_path, {}) or {}
    raw = collect_day(config, date_str, sources=sources, use_cache=use_cache, since_ts=since_ts, seen=seen_state if incremental else None)
    if incremental:
        raw = _filter_seen(raw, seen_state)
        _save_seen_state(raw, date_str, seen_state)
    upmasters = ((raw.get("items", {}) or {}).get("bilibili", {}) or {}).get("upmasters", []) or []
    upmasters = _merge_registry_profile(upmasters)
    distilled = distill.distill_day(
        raw.get("posts", []), upmasters, config, date_str=date_str,
        since_ts=since_ts, until_ts=until_ts,
    )
    report = dict(raw)
    report["distilled"] = distilled
    report["deduped_count"] = sum(distilled.get("source_counts", {}).values())
    report["window"] = {
        "since": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(since_ts)),
        "until": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(until_ts)),
        "mode": window_mode,
        "since_ts": int(since_ts),
    }
    summary_path = os.path.join(SUMMARY_DIR, f"{date_str}.json")
    save_json(summary_path, report)
    from .report import render_report
    html = render_report(report, config)
    html_path = os.path.join(OUTPUT_DIR, f"report_{date_str}.html")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    from .site import build_site
    build_site(OUTPUT_DIR)
    log.info("日报生成: %s", html_path)
    report["_html_path"] = html_path
    report["_summary_path"] = summary_path
    return report


def compute_window(
    config: Dict[str, Any],
    date_str: str,
    since_hours: float | None = None,
    last_run_ts: float | None = None,
) -> tuple[int, int, str]:
    """计算统计窗口：显式 since_hours > config.time_window > 默认当天 00:00。"""
    now = time.time()
    b = config.get("bilibili", {}) or {}
    tw = b.get("time_window", {}) or {}
    mode = str(tw.get("mode", "today") or "today")
    if since_hours:
        since = now - float(since_hours) * 3600
        mode = f"过去{since_hours:g}小时"
    elif mode == "hours":
        since = now - float(tw.get("hours", 24) or 24) * 3600
        mode = f"过去{tw.get('hours', 24):g}小时"
    elif mode == "last_run" and last_run_ts:
        since = float(last_run_ts)
        mode = "上次运行起"
    else:
        since = time.mktime(time.strptime(date_str, "%Y-%m-%d"))
        mode = "当天 00:00 起"
    return int(since), int(now), mode


def _save_seen_state(raw: Dict[str, Any], date_str: str, prev: Dict[str, Any]) -> None:
    """增量模式：把本次采集到的 up主 动态/视频 id 记入当日 seen 状态。"""
    ups = ((raw.get("items", {}) or {}).get("bilibili", {}) or {}).get("upmasters", []) or []
    state = dict(prev or {})
    for up in ups:
        mid = str(up.get("mid") or up.get("uid") or "")
        if not mid:
            continue
        entry = state.setdefault(mid, {"dynamics": [], "videos": []})
        entry["dynamics"] = list(dict.fromkeys(entry.get("dynamics", []) or []))
        entry["videos"] = list(dict.fromkeys(entry.get("videos", []) or []))
        for d in up.get("dynamics", []) or []:
            dyn_id = (d.get("extra") or {}).get("dyn_id", "")
            if dyn_id:
                entry["dynamics"].append(dyn_id)
        for v in up.get("videos", []) or []:
            bvid = (v.get("extra") or {}).get("bvid", "")
            if bvid:
                entry["videos"].append(bvid)
    os.makedirs(STATE_DIR, exist_ok=True)
    save_json(os.path.join(STATE_DIR, f"seen_{date_str}.json"), state)


def _filter_seen(raw: Dict[str, Any], seen: Dict[str, Any]) -> Dict[str, Any]:
    """增量模式：把已上报过的 up主 动态/视频（及其评论）从结果中剔除。

    既处理缓存路径（collect 未执行），也与 collect 内的 seen 过滤叠加（幂等）。
    """
    ups = ((raw.get("items", {}) or {}).get("bilibili", {}) or {}).get("upmasters", []) or []
    keep_dyn: set[str] = set()
    keep_vids: set[str] = set()
    for up in ups:
        mid = str(up.get("mid") or up.get("uid") or "")
        entry = (seen or {}).get(mid, {})
        seen_dyn = set(entry.get("dynamics", []) or [])
        seen_vid = set(entry.get("videos", []) or [])
        up["dynamics"] = [
            d for d in (up.get("dynamics", []) or [])
            if (d.get("extra") or {}).get("dyn_id", "") not in seen_dyn
        ]
        up["videos"] = [
            v for v in (up.get("videos", []) or [])
            if (v.get("extra") or {}).get("bvid", "") not in seen_vid
        ]
        keep_dyn |= {(d.get("extra") or {}).get("dyn_id", "") for d in up["dynamics"]}
        keep_vids |= {(v.get("extra") or {}).get("bvid", "") for v in up["videos"]}
    posts = []
    for p in raw.get("posts", []) or []:
        if p.get("kind") == "up_dynamic":
            if (p.get("extra") or {}).get("dyn_id", "") not in keep_dyn:
                continue
        elif p.get("kind") == "comment":
            if (p.get("extra") or {}).get("bvid", "") not in keep_vids:
                continue
        elif p.get("kind") == "up_video":
            if (p.get("extra") or {}).get("bvid", "") not in keep_vids:
                continue
        posts.append(p)
    raw["posts"] = posts
    return raw


def _merge_registry_profile(upmasters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把 data/upmasters/registry.json 中的档案字段（本地头像/cookie/备注）合并进采集结果。"""
    from .upmaster_lib import load_registry
    reg = load_registry().get("upmasters", {})
    out = []
    for up in upmasters:
        mid = str(up.get("mid") or up.get("uid") or "")
        r = reg.get(mid, {})
        merged = dict(up)
        for k in ("avatar_local", "avatar_remote", "cookie", "notes", "tags", "sign", "fans", "last_refresh", "stats"):
            if r.get(k) not in (None, ""):
                merged[k] = r[k]
        out.append(merged)
    return out


def default_date() -> str:
    return time.strftime("%Y-%m-%d")


def print_report_summary(report: Dict[str, Any]) -> None:
    sources = report.get("sources", {})
    distilled = report.get("distilled", {})
    lines = [
        f"日期: {report.get('date')}  采集于: {report.get('collected_at')}",
        "数据源: " + " | ".join(
            f"{s.get('label')} {s.get('count')}条[{s.get('status')}]" for s in sources.values()
        ),
        f"情绪: {distilled.get('sentiment', {}).get('label')} ({distilled.get('sentiment', {}).get('score', 0):+.2f})",
        "热词 TOP5: " + "、".join(k["text"] for k in distilled.get("keywords", [])[:5]),
        "梗 TOP5: " + "、".join(m["text"] for m in distilled.get("memes", [])[:5]),
        f"HTML: {report.get('_html_path')}",
    ]
    print("\n".join(lines))
