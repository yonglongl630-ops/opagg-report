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
    senti = w.get("sentiment", {})
    score = senti.get("score", 0)
    senti_color = "#d93026" if score >= 0.15 else ("#0f8a4d" if score <= -0.15 else "#777")
    kw_html = "".join(
        f'<div class="kw"><b>{esc(k["text"])}</b><span class="muted">{k["freq"]}次 · {"、".join(k.get("sources", []))}</span></div>'
        for k in (w.get("keywords") or [])[:14]
    )
    meme_html = "".join(
        f'<div class="kw"><b>{esc(m["text"])}</b><span class="muted">{m["freq"]}次</span>'
        f'<div class="muted">{esc(m.get("example", ""))[:80]}</div></div>'
        for m in (w.get("memes") or [])[:10]
    )
    topics_html = ""
    for t in (w.get("topics") or [])[:8]:
        posts = "".join(
            f'<li><a href="{esc(p.get("url", "#"))}" target="_blank" rel="noopener">[{esc(p.get("source", ""))}] {esc(p.get("title", ""))}</a></li>'
            for p in t.get("top_posts", [])[:3]
        )
        topics_html += (
            f'<div class="card"><div class="th"><b>{esc(t.get("label", ""))}</b>'
            f'<span class="muted">{t.get("count", 0)}条 · {esc(t.get("sentiment", ""))}</span></div>'
            f'<ul class="pl">{posts}</ul></div>'
        )
    senti_rows = ""
    if w.get("daily_sentiment"):
        maxv = max(0.01, max(abs(x["score"]) for x in w["daily_sentiment"]))
        for x in w["daily_sentiment"]:
            wdt = abs(x["score"]) / maxv * 100
            color = "#d93026" if x["score"] >= 0 else "#0f8a4d"
            senti_rows += (
                f'<div class="srow"><span class="sdate">{x["date"][5:]}</span>'
                f'<div class="sbar"><div style="width:{wdt:.0f}%;background:{color}" class="sfill"></div></div>'
                f'<span class="muted">{x["score"]:+.2f} {esc(x["label"])}</span></div>'
            )
    up_html = ""
    for u in (w.get("upmasters") or []):
        avatar_local = u.get("avatar_local") or ""
        avatar = ("../" + avatar_local.lstrip("/")) if avatar_local else (u.get("avatar") or "")
        av = f'<img class="avatar" src="{esc(avatar)}" alt="">' if avatar else '<div class="avatar"></div>'
        trend = "".join(
            f'<span class="td" title="{ds}">{esc(d.get("stance", "中性")[0])}</span>'
            for ds, d in sorted((u.get("days") or {}).items())
        )
        quotes = "".join(
            f'<div class="quote">“{esc(q.get("text", ""))}”<span class="muted">—— {fmt_num(q.get("likes"))}赞</span></div>'
            for q in (u.get("quotes") or [])[:4]
        )
        up_html += f"""
        <div class="card">
          <div class="uhead">{av}<div><b>{esc(u.get("name", ""))}</b>
          <div class="muted">周观点 {esc(u.get("stance", "中性"))}（{u.get("stance_score", 0):+.2f}）· 周播放 {fmt_num(u.get("total_views"))} · 动态 {u.get("total_dynamics", 0)}</div>
          <div class="muted">每日观点：{trend}</div></div></div>
          <div class="quotes">{quotes or '<div class="muted">本周暂无高赞金句</div>'}</div>
        </div>"""
    day_links = "".join(
        f'<a class="daylink" href="{esc(d.get("html", ""))}">{esc(d.get("date", ""))[5:]}</a>'
        for d in (w.get("day_reports") or [])
    )
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
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 20px 0; }}
  .stat {{ background: #fff; border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
  .stat b {{ font-size: 24px; display: block; }}
  .stat span {{ color: #6a737d; font-size: 12px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.06); margin-bottom: 16px; }}
  .sec-title {{ font-size: 15px; font-weight: 700; margin-bottom: 10px; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 800px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}
  .kw {{ padding: 6px 0; border-bottom: 1px dashed #eaecef; font-size: 13px; }}
  .kw:last-child {{ border-bottom: 0; }}
  .muted {{ color: #6a737d; font-size: 12px; }}
  .th {{ display: flex; align-items: baseline; gap: 8px; }}
  .pl {{ list-style: none; margin-top: 6px; }}
  .pl li {{ padding: 3px 0; font-size: 13px; }}
  .pl a {{ color: #0969da; text-decoration: none; }}
  .srow {{ display: flex; align-items: center; gap: 8px; padding: 4px 0; }}
  .sdate {{ width: 42px; font-size: 12px; }}
  .sbar {{ flex: 1; background: #f0f1f3; height: 10px; border-radius: 5px; overflow: hidden; }}
  .sfill {{ height: 100%; }}
  .avatar {{ width: 40px; height: 40px; border-radius: 50%; object-fit: cover; background: #f0f1f3; }}
  .uhead {{ display: flex; gap: 10px; align-items: center; margin-bottom: 8px; }}
  .td {{ display: inline-block; min-width: 18px; text-align: center; border-radius: 4px; background: #f0f1f3; color: #57606a; font-size: 11px; margin-right: 3px; }}
  .quote {{ padding: 4px 0; font-size: 13px; }}
  .daylink {{ display: inline-block; background: #fff; border: 1px solid #d0d7de; border-radius: 999px; padding: 4px 12px; font-size: 12px; color: #0969da; text-decoration: none; margin-right: 6px; }}
  .summary-box {{ background: linear-gradient(135deg,#eef4ff,#fff); border: 1px solid #cfe0ff; border-radius: 10px; padding: 16px; margin-bottom: 20px; }}
  footer {{ color: #8b949e; font-size: 12px; margin-top: 30px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>舆论蒸馏周报</h1>
  <div class="sub">{esc(w["monday"])} ~ {esc(w["sunday"])} · 生成于 {esc(w.get("generated_at", ""))} · 覆盖 {w.get("days_count", 0)} 个交易日报告</div>
  <div class="daylinks" style="margin-top:10px">{day_links or '<span class="muted">本周暂无日报</span>'}</div>

  <div class="cards">
    <div class="stat"><b>{w.get("total_posts", 0)}</b><span>本周聚合内容</span></div>
    <div class="stat"><b style="color:{senti_color}">{esc(senti.get("label", "中性"))}</b><span>周度情绪（{score:+.2f}）</span></div>
    <div class="stat"><b>{len(w.get("keywords", []))}</b><span>热词</span></div>
    <div class="stat"><b>{len(w.get("upmasters", []))}</b><span>跟踪 up主</span></div>
  </div>

  <div class="summary-box"><div class="sec-title">周报摘要</div><p>{esc(w.get("summary", ""))}</p></div>

  <div class="grid2">
    <div class="card"><div class="sec-title">周度热词</div>{kw_html or '<div class="muted">暂无</div>'}</div>
    <div class="card"><div class="sec-title">周度高频短语 / 梗</div>{meme_html or '<div class="muted">暂无</div>'}</div>
  </div>

  <div class="card"><div class="sec-title">每日情绪走势</div>{senti_rows or '<div class="muted">暂无数据</div>'}</div>

  <div class="sec-title" style="margin-top:6px">周度主题</div>
  <div class="grid2">{topics_html or '<div class="card muted">暂无主题</div>'}</div>

  <div class="sec-title" style="margin-top:6px">up主周报</div>
  {up_html or '<div class="card muted">未配置 up主</div>'}

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
