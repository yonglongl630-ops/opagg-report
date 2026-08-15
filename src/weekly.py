"""周报生成：聚合一周内各日 summary，产出趋势、热词、主题与 up主周报。"""

from __future__ import annotations

import html as html_mod
import os
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from . import distill
from .common import load_json, log, save_json
from .config import ROOT, load_config

SUMMARY_DIR = os.path.join(ROOT, "data", "summary")
OUTPUT_DIR = os.path.join(ROOT, "output")


def week_range(d: str) -> tuple[str, str]:
    """返回 d 所在周（周一至周日）的日期字符串。"""
    dt = datetime.strptime(d, "%Y-%m-%d").date()
    monday = dt - timedelta(days=dt.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def _day_list(monday: str, sunday: str) -> List[str]:
    out = []
    cur = datetime.strptime(monday, "%Y-%m-%d").date()
    end = datetime.strptime(sunday, "%Y-%m-%d").date()
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def load_week_summaries(anchor: str) -> List[Dict[str, Any]]:
    monday, sunday = week_range(anchor)
    days = []
    for ds in _day_list(monday, sunday):
        p = os.path.join(SUMMARY_DIR, f"{ds}.json")
        data = load_json(p)
        if data:
            days.append(data)
    return days


def build_weekly(anchor: str | None = None, cfg: Dict[str, Any] | None = None) -> Dict[str, Any]:
    anchor = anchor or date.today().isoformat()
    cfg = cfg or load_config()
    days = load_week_summaries(anchor)
    monday, sunday = week_range(anchor)
    posts: List[Dict[str, Any]] = []
    source_counts: Counter = Counter()
    daily_sentiment: List[Dict[str, Any]] = []
    up_by_name: Dict[str, Dict[str, Any]] = {}
    day_reports: List[Dict[str, Any]] = []
    for d in days:
        ds = d.get("date", "")
        posts += d.get("posts", []) or []
        for src, n in (d.get("distilled", {}) or {}).get("source_counts", {}).items():
            source_counts[src] += n
        senti = (d.get("distilled", {}) or {}).get("sentiment", {})
        daily_sentiment.append({"date": ds, "label": senti.get("label", "中性"), "score": senti.get("score", 0)})
        day_reports.append({
            "date": ds,
            "html": f"report_{ds}.html",
            "summary": (d.get("distilled", {}) or {}).get("summary", ""),
        })
        for up in ((d.get("distilled", {}) or {}).get("upmasters", [])) or []:
            name = up.get("name", "")
            u = up_by_name.setdefault(name, {
                "name": name,
                "mid": up.get("mid", ""),
                "url": up.get("url", ""),
                "avatar": up.get("avatar_remote") or up.get("avatar_local") or up.get("avatar", ""),
                "avatar_local": up.get("avatar_local", ""),
                "fans": up.get("fans", 0),
                "tags": up.get("tags", []),
                "stance": up.get("stance", "中性"),
                "stance_score": up.get("stance_score", 0),
                "total_views": 0,
                "total_dynamics": 0,
                "quotes": [],
                "days": {},
            })
            u["total_views"] += up.get("total_views", 0)
            u["total_dynamics"] += up.get("total_dynamics", 0)
            u["days"][ds] = {"stance": up.get("stance", "中性"), "score": up.get("stance_score", 0)}
            for q in (up.get("quotes", []) or [])[:2]:
                u["quotes"].append(q)
    # 只保留当前配置中的 up主（历史日报里可能残留已移除的博主）
    cfg_mids = {str(x.get("mid") or x.get("uid")) for x in cfg.get("bilibili", {}).get("upmasters", [])}
    if cfg_mids:
        up_by_name = {k: v for k, v in up_by_name.items() if str(v.get("mid", "")) in cfg_mids}
    for u in up_by_name.values():
        u["quotes"] = sorted(u["quotes"], key=lambda q: q.get("likes", 0), reverse=True)[:6]

    distilled = distill.distill_day(posts, [], cfg)
    weekly = {
        "type": "weekly",
        "monday": monday,
        "sunday": sunday,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "days_count": len(days),
        "total_posts": len(posts),
        "source_counts": dict(source_counts),
        "keywords": distilled.get("keywords", []),
        "memes": distilled.get("memes", []),
        "sentiment": distilled.get("sentiment", {}),
        "topics": distilled.get("topics", []),
        "daily_sentiment": daily_sentiment,
        "upmasters": list(up_by_name.values()),
        "day_reports": day_reports,
    }
    weekly["summary"] = _weekly_summary(weekly)
    return weekly


def _weekly_summary(w: Dict[str, Any]) -> str:
    lines = []
    total = w.get("total_posts", 0)
    counts = "、".join(f"{k} {v}" for k, v in (w.get("source_counts") or {}).items())
    senti = w.get("sentiment", {})
    lines.append(f"本周（{w['monday']} 至 {w['sunday']}）共聚合 {total} 条内容（{counts}）。")
    lines.append(f"周度情绪{senti.get('label', '中性')}（指数 {senti.get('score', 0):+.2f}）。")
    kws = [k["text"] for k in (w.get("keywords") or [])[:6]]
    if kws:
        lines.append("周度热词：" + "、".join(kws) + "。")
    topics = [t["label"] for t in (w.get("topics") or [])[:4]]
    if topics:
        lines.append("周度主题：" + "；".join(topics) + "。")
    ups = w.get("upmasters", [])
    if ups:
        lines.append("up主周评：" + "；".join(f"{u['name']} {u['stance']}（{u['stance_score']:+.2f}）" for u in ups))
    return "".join(lines)


def esc(v: Any) -> str:
    return html_mod.escape(str(v if v is not None else ""), quote=True)


def fmt_num(v: Any) -> str:
    try:
        n = int(v or 0)
    except (TypeError, ValueError):
        return str(v or "")
    if n >= 100000000:
        return f"{n / 100000000:.2f}亿"
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    return str(n)


def render_weekly_html(w: Dict[str, Any]) -> str:
    days = (w.get("day_reports") or [])
    day_links = "".join(
        f'<a class="daylink" href="{esc(d.get("html", ""))}">{esc(d.get("date", ""))[5:]}</a>'
        for d in days
    )
    day_blocks = "".join(
        f"""
        <details class="day-detail" open>
          <summary>日报 {esc(d.get("date", ""))} · {esc(d.get("summary", ""))[:60]}…</summary>
          <iframe class="day-frame" src="{esc(d.get("html", ""))}" loading="lazy"></iframe>
        </details>"""
        for d in sorted(days, key=lambda x: x.get("date", ""), reverse=True)
    ) or '<div class="card muted">本周暂无日报</div>'
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>舆论蒸馏周报 · {esc(w["monday"])} ~ {esc(w["sunday"])}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f6f8; color: #24292f; line-height: 1.55; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px 18px 60px; }}
  h1 {{ font-size: 24px; }}
  .sub {{ color: #6a737d; font-size: 13px; margin-top: 4px; }}
  .daylinks {{ margin: 12px 0 18px; }}
  .daylink {{ display: inline-block; background: #fff; border: 1px solid #d0d7de; border-radius: 999px; padding: 5px 14px; font-size: 13px; color: #0969da; text-decoration: none; margin-right: 8px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 0 0 18px; }}
  .stat {{ background: #fff; border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
  .stat b {{ font-size: 24px; display: block; }}
  .stat span {{ color: #6a737d; font-size: 12px; }}
  .summary-box {{ background: linear-gradient(135deg,#eef4ff,#fff); border: 1px solid #cfe0ff; border-radius: 10px; padding: 16px; margin-bottom: 18px; }}
  .sec-title {{ font-size: 15px; font-weight: 700; margin: 18px 0 10px; }}
  .day-detail {{ background: #fff; border-radius: 10px; padding: 12px 16px; box-shadow: 0 1px 3px rgba(0,0,0,.06); margin-bottom: 14px; }}
  .day-detail summary {{ cursor: pointer; font-size: 15px; font-weight: 700; color: #0969da; }}
  .day-frame {{ width: 100%; height: 2400px; border: 0; margin-top: 10px; background: #fff; border-radius: 8px; }}
  .muted {{ color: #6a737d; font-size: 12px; }}
  footer {{ color: #8b949e; font-size: 12px; margin-top: 30px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>舆论蒸馏周报</h1>
  <div class="sub">{esc(w["monday"])} ~ {esc(w["sunday"])} · 生成于 {esc(w.get("generated_at", ""))} · 汇总本周 {w.get("days_count", 0)} 份日报</div>
  <div class="daylinks">{day_links or '<span class="muted">本周暂无日报</span>'}</div>

  <div class="cards">
    <div class="stat"><b>{w.get("days_count", 0)}</b><span>覆盖日报天数</span></div>
    <div class="stat"><b>{w.get("total_posts", 0)}</b><span>本周聚合内容</span></div>
    <div class="stat"><b>{len(w.get("upmasters", []))}</b><span>跟踪 up主</span></div>
  </div>

  <div class="summary-box"><div class="sec-title">周报摘要</div><p>{esc(w.get("summary", ""))}</p></div>

  <div class="sec-title">本周日报（逐日全文，与日报界面一致，点击标题可展开/收起）</div>
  {day_blocks}

  <footer>仅供研究参考，不构成投资建议 · 数据来自公开接口 · 生成于 {esc(w.get("generated_at", ""))}</footer>
</div>
</body>
</html>"""


def save_weekly(w: Dict[str, Any]) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    html_path = os.path.join(OUTPUT_DIR, f"report_{w['sunday']}_weekly.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_weekly_html(w))
    from .site import build_site
    build_site(OUTPUT_DIR)
    data_path = os.path.join(SUMMARY_DIR, f"weekly_{w['sunday']}.json")
    save_json(data_path, w)
    log.info("周报生成: %s", html_path)
    return html_path
