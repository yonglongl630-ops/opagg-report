"""HTML 日报渲染：纯内联 CSS，无外部依赖。"""

from __future__ import annotations

import html as html_mod
import base64
import math as _math
import os
import re
from collections import Counter as _Counter
from typing import Any, Dict, List

from .aggregate import SOURCE_LABELS
from .config import ROOT


PLAT_COLORS = {
    "雪球": "#3a8ee6",
    "同花顺": "#f0a020",
    "金十": "#e8a33d",
    "财联社": "#1f9d8a",
    "东方财富": "#e0322b",
    "B站": "#fb7299",
    "股吧": "#e6532a",
}

SRC_TO_LABEL = {
    "xueqiu": "雪球",
    "ths": "同花顺",
    "jin10": "金十",
    "cls": "财联社",
    "em": "东方财富",
    "bilibili": "B站",
    "guba": "股吧",
}


def _src_chips(keys: List[str]) -> str:
    """把 source key 渲染成平台彩色标签（图2样式）。"""
    out = []
    for k in keys or []:
        label = SRC_TO_LABEL.get(k, "")
        if not label:
            continue
        out.append(
            f'<span class="plat-chip" style="background:{PLAT_COLORS.get(label, "#888")}">{esc(label)}</span>'
        )
    return "".join(out)


def _avatar_data_uri(path: str) -> str:
    """把本地头像读成 base64 data URI，避免 file:// 下相对路径子资源被浏览器拦截。"""
    if not path:
        return ""
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    try:
        with open(p, "rb") as f:
            raw = f.read()
    except OSError:
        return ""
    low = path.lower()
    if low.endswith(".webp"):
        mime = "image/webp"
    elif low.endswith(".png"):
        mime = "image/png"
    else:
        mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


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


def _source_color(src: str) -> str:
    return {
        "bilibili": "#fb7299",
        "guba": "#e6532a",
        "xueqiu": "#3a8ee6",
        "ths": "#f0a020",
        "sector": "#5b6ee8",
        "jin10": "#e8a33d",
        "cls": "#1f9d8a",
        "em": "#e0322b",
    }.get(src, "#888")


def _stance_badge(label: str) -> str:
    color = {"看多": "#d93026", "看空": "#0f8a4d", "中性": "#777"}.get(label, "#777")
    return f'<span class="badge" style="background:{color}">{esc(label)}</span>'


def _status_chip(status: str) -> str:
    color = {"ok": "#1a9d57", "partial": "#d9822b", "error": "#c0392b"}.get(status, "#777")
    txt = {"ok": "正常", "partial": "部分", "error": "失败"}.get(status, status)
    return f'<span class="chip" style="border-color:{color};color:{color}">{txt}</span>'


def _dyn_html(d: Dict[str, Any]) -> str:
    badge = ""
    if (d.get("extra") or {}).get("charge_exclusive"):
        badge = '<span class="chip" style="border-color:#9a6b1f;color:#9a6b1f">🔒充电专属</span>'
    return (
        f'<div class="dyn-item"><b>{esc(d.get("title", "") or d.get("content", ""))[:60]}</b>{badge}'
        f'<div class="dyn-meta">{esc(d.get("time", ""))} · 赞{fmt_num(d.get("likes"))} · '
        f'评{fmt_num(d.get("comments"))} · {esc(d.get("stance", ""))}</div>'
        f'<div class="dyn-body">{esc(d.get("content", ""))[:220]}</div></div>'
    )


def _pct_badge(pct: Any) -> str:
    try:
        v = float(pct or 0)
    except (TypeError, ValueError):
        return ""
    color = "#d93026" if v > 0 else ("#0f8a4d" if v < 0 else "#777")
    return f'<span class="pct" style="color:{color}">{v:+.2f}%</span>'


def _mention_heat(posts: List[Dict[str, Any]], names: List[str], limit: int = 10) -> List[Dict[str, Any]]:
    """从平台内容中识别自选股：按帖子热度（阅读/赞/评论）加权统计提及热度。"""
    heat: _Counter = _Counter()
    examples: Dict[str, str] = {}
    for p in posts:
        text = ((p.get("title") or "") + " " + (p.get("content") or ""))
        w = (
            _math.log1p(int(p.get("views", 0) or 0)) * 0.5
            + _math.log1p(int(p.get("likes", 0) or 0))
            + _math.log1p(int(p.get("comments", 0) or 0)) * 0.8
        )
        for n in names:
            if n and n in text:
                heat[n] += w + 1
                examples.setdefault(n, (p.get("title") or p.get("content", ""))[:50])
    return [
        {"text": n, "heat": round(heat[n], 1), "example": examples.get(n, "")}
        for n, _ in heat.most_common(limit)
    ]


def _hrow(idx: int, name: str, meta: str = "", title: str = "") -> str:
    t = f' title="{esc(title)}"' if title else ""
    return (
        f'<div class="hrow"{t}>'
        f'<span class="hrow-idx">{idx}</span>'
        f'<span class="hrow-name">{esc(name)}</span>'
        f'<span class="hrow-meta">{meta}</span>'
        f"</div>"
    )


def _hot_card(title: str, accent: str, stocks: List[Dict[str, Any]], topics: List[Dict[str, Any]], foot: str = "") -> str:
    """头部信息卡：统一展示 热股 TOP10 + 热门话题 TOP10。"""
    stock_html = "".join(
        _hrow(i + 1, s.get("text", ""), s.get("meta", ""), s.get("example", ""))
        for i, s in enumerate(stocks[:10])
    ) or '<div class="muted">暂无热股数据</div>'
    topic_html = "".join(
        _hrow(i + 1, t.get("text", ""), t.get("meta", ""), t.get("example", ""))
        for i, t in enumerate(topics[:10])
    ) or '<div class="muted">暂无话题数据</div>'
    inner = (
        f'<div class="hcard-sub">热股 TOP10</div>{stock_html}'
        f'<div class="hcard-sub">热门话题 TOP10</div>{topic_html}'
    )
    return _header_card(title, inner, accent=accent, foot=foot)


def _header_card(title: str, inner: str, accent: str = "#5b6ee8", foot: str = "") -> str:
    return f"""
    <div class="hcard">
      <div class="hcard-title" style="border-color:{accent}">{esc(title)}</div>
      <div class="hcard-body">{inner}</div>
      {f'<div class="hcard-foot">{foot}</div>' if foot else ""}
    </div>"""


def render_report(report: Dict[str, Any], config: Dict[str, Any]) -> str:
    d = report.get("distilled", {})
    sources = report.get("sources", {})
    posts = report.get("posts", [])
    date_str = report.get("date", "")
    senti = d.get("sentiment", {})
    keywords = d.get("keywords", [])
    topics = d.get("topics", [])
    upmasters = d.get("upmasters", [])
    items = report.get("items", {}) or {}
    top_n = int((config.get("distill", {}) or {}).get("top_per_source", 8))

    total = report.get("deduped_count") or len(posts)
    ok_sources = sum(1 for s in sources.values() if s.get("status") == "ok")
    total_sources = len(sources)
    senti_score = senti.get("score", 0)
    senti_color = "#d93026" if senti_score >= 0.15 else ("#0f8a4d" if senti_score <= -0.15 else "#777")
    pos_n = senti.get("pos_posts", 0)
    neg_n = senti.get("neg_posts", 0)
    neu_n = senti.get("neutral_posts", 0)
    senti_sum = pos_n + neg_n + neu_n or 1
    pos_w = pos_n / senti_sum * 100
    neg_w = neg_n / senti_sum * 100
    neu_w = neu_n / senti_sum * 100

    source_chips = "".join(
        f'<span class="src-chip" style="border-color:{_source_color(name)}">'
        f'{esc(s.get("label", name))} {_status_chip(s.get("status", ""))}</span>'
        for name, s in sources.items()
    )

    # 关键词 / 梗
    kw_max = max((k.get("freq", 0) or 0) for k in keywords) or 1
    kw_html = "".join(
        f"""
        <div class="rank-row">
          <div class="rank-name">{esc(k['text'])}</div>
          <div class="rank-bar"><div class="rank-fill" style="width:{max(2, k['freq'] / kw_max * 100):.1f}%"></div></div>
          <div class="rank-num">{k['freq']}次</div>
        </div>"""
        for k in sorted(keywords, key=lambda x: x.get("freq", 0), reverse=True)[:16]
    )
    guba_hot_topics = ((items.get("guba", {}) or {}).get("hot_topics", []) or [])

    # 分平台
    guba = items.get("guba", {}) or {}
    xueqiu = items.get("xueqiu", {}) or {}
    ths = items.get("ths", {}) or {}

    guba_topics = "".join(
        f"""
        <div class="card mini-card">
          <div class="topic-head"><b>{esc(t.get("title", ""))}</b><span class="muted">{t.get("views", 0)}点击 · {t.get("likes", 0)}参与</span></div>
          <div class="topic-sum">{esc(t.get("content", ""))[:120]}</div>
        </div>"""
        for t in guba_hot_topics[:6]
    )
    ths_feed = "".join(
        f'<li><b>{esc(f.get("title", ""))}</b><div class="muted">{esc(f.get("author", ""))} · {esc(f.get("time", ""))}'
        + (f' · 阅读{fmt_num(f.get("views"))}' if f.get("views") else "")
        + '</div>'
        f'<div class="muted">{esc(f.get("content", ""))[:120]}</div></li>'
        for f in sorted(ths.get("feed", []) or [], key=lambda x: x.get("views", 0), reverse=True)[:top_n]
    ) if "feed" in ths else "".join(
        f'<li><b>{esc(f.get("title", ""))}</b><div class="muted">{esc(f.get("author", ""))} · {esc(f.get("time", ""))}</div></li>'
        for f in (ths.get("feed", []) or ths.get("posts", []))[:top_n]
    )
    xq_posts = "".join(
        f'<li><a href="{esc(x.get("url", "#"))}" target="_blank" rel="noopener">{esc(x.get("title", ""))}</a>'
        f'<span class="muted"> {esc(x.get("author", ""))} · 赞{fmt_num(x.get("likes"))} 评{fmt_num(x.get("comments"))}</span>'
        f'<div class="muted">{esc(x.get("content", ""))[:90]}</div></li>'
        for x in sorted(
            (xueqiu.get("hot_posts", []) or []),
            key=lambda x: (x.get("likes", 0) or 0) * 2 + (x.get("comments", 0) or 0) * 3 + (x.get("views", 0) or 0),
            reverse=True,
        )[:top_n]
    )

    # up主：底部汇总分析（先汇总一行，再折叠展开视频/动态/金句）
    up_summary_rows = ""
    up_details = ""
    for u in upmasters:
        vids = "".join(
            f"""
            <div class="up-video">
              <div class="up-video-title"><a href="{esc(v.get('url', '#'))}" target="_blank" rel="noopener">{esc(v.get('title', ''))}</a></div>
              <div class="muted">播放{fmt_num(v.get('views'))} · {esc(v.get('pubdate', ''))}</div>
              <div class="up-video-meta">{_stance_badge(v.get('stance', ''))} <span class="muted">{"、".join(v.get('keywords', [])[:4])}</span></div>
            </div>"""
            for v in u.get("videos", [])[:4]
        )
        quotes = "".join(
            f'<div class="quote"><span class="quote-q">“{esc(q.get("text", ""))}”</span><span class="muted">—— {fmt_num(q.get("likes"))}赞 · {esc(q.get("video", ""))}</span></div>'
            for q in u.get("quotes", [])[:4]
        )
        avatar_local = u.get("avatar_local") or ""
        avatar_src = _avatar_data_uri(avatar_local) or (u.get("avatar_remote") or u.get("avatar") or "")
        avatar_html = f'<img class="up-avatar" src="{esc(avatar_src)}" alt="">' if avatar_src else '<div class="up-avatar"></div>'
        tags_html = "".join(f'<span class="chip" style="border-color:#bbb;color:#555">{esc(t)}</span>' for t in (u.get("tags") or [])[:4])
        dyn_all = sorted(
            (u.get("dynamics") or []),
            key=lambda x: (x.get("time", "") or ""),
            reverse=True,
        )[:3]
        dyns = "".join(
            _dyn_html(d)
            for d in dyn_all
        )
        charging = u.get("charging") or {}
        charge_dyns = [
            d for d in (u.get("dynamics") or [])
            if (d.get("extra") or {}).get("charge_exclusive")
        ]
        charge_dyn_n = len(charge_dyns)
        charge_dyn_likes = sum(int(d.get("likes", 0) or 0) for d in charge_dyns)
        charge_dyn_comments = sum(int(d.get("comments", 0) or 0) for d in charge_dyns)
        charging_html = ""
        if charging:
            charging_html = (
                f'<div class="muted">本月充电 <b>{fmt_num(charging.get("total"))}</b> 人次'
                + (
                    f" · 窗口内充电专属动态 {charge_dyn_n} 条"
                    + (f"（赞 {fmt_num(charge_dyn_likes)} · 评 {fmt_num(charge_dyn_comments)}）" if charge_dyn_n else "")
                    if charge_dyn_n
                    else " · 窗口内暂无充电专属动态"
                )
                + "</div>"
            )
        elif u.get("mid"):
            charging_html = '<div class="muted">充电榜不可用（风控或未配置 cookie）</div>'
        ca = u.get("comment_analysis") or {}
        ca_html = ""
        if ca.get("n"):
            cs = ca.get("sentiment") or {}
            tot = (cs.get("pos", 0) + cs.get("neutral", 0) + cs.get("neg", 0)) or 1
            cpw = cs.get("pos", 0) / tot * 100
            cnw = cs.get("neutral", 0) / tot * 100
            cgw = cs.get("neg", 0) / tot * 100
            ca_users = "".join(
                f'<div class="cc-user"><b>{esc(x.get("author", ""))}</b> {_stance_badge(x.get("stance", ""))} '
                f'<span class="muted">{x.get("n", 0)}条 · {fmt_num(x.get("likes"))}赞</span>'
                f'<div class="muted">“{esc(x.get("top_comment", ""))[:80]}”</div></div>'
                for x in (ca.get("top_commenters") or [])[:5]
            )
            ca_kw = "、".join(esc(x) for x in (ca.get("keywords") or [])[:8])
            ca_html = (
                f'<div>评论情绪 {_stance_badge(cs.get("label", "中性"))}（指数 {cs.get("score", 0):+.2f}）</div>'
                f'<div class="sentibar"><div class="pos" style="width:{cpw:.1f}%"></div>'
                f'<div class="neu" style="width:{cnw:.1f}%"></div>'
                f'<div class="neg" style="width:{cgw:.1f}%"></div></div>'
                f'<div class="muted">看多 {cs.get("pos", 0)} / 中性 {cs.get("neutral", 0)} / 看空 {cs.get("neg", 0)}</div>'
                f'<div class="muted" style="margin-top:6px">评论热点词：{ca_kw or "无"}</div>'
                f'<div class="cc-users">{ca_users or "无"}</div>'
            )
        else:
            ca_html = '<div class="muted">窗口内暂无评论数据</div>'
        style_kw = "、".join(esc(k) for k in (u.get("style_keywords") or [])[:8])
        cookie_flag = '<span class="chip" style="border-color:#1a9d57;color:#1a9d57">已配置 cookie</span>' if u.get("cookie_configured") else ""
        up_summary_rows += f"""
        <div class="up-summary-row">
          {avatar_html}
          <div class="up-summary-main">
            <div><b>{esc(u.get('name', ''))}</b> {tags_html} {cookie_flag}</div>
            <div class="up-meta">{_stance_badge(u.get('stance', ''))} 观点指数 {u.get('stance_score', 0):+.2f} · 粉丝 {fmt_num(u.get('fans'))} · 近视频总播放 {fmt_num(u.get('total_views'))} · 动态 {u.get('total_dynamics', 0)} 条</div>
            {charging_html}
            {'<div class="muted">风格关键词：' + style_kw + '</div>' if style_kw else ''}
          </div>
        </div>"""
        up_details += f"""
        <details class="up-detail">
          <summary><b>{esc(u.get('name', ''))}</b> — 视频分析 / 最近动态(近3条) / 评论汇总 / 充电分析</summary>
          <div class="up-tabs">视频分析（窗口内近期视频）</div>
          <div class="up-grid">
            <div>{vids}</div>
            <div>{ca_html}</div>
          </div>
          <div class="up-tabs">最近动态（近3条 · 含充电内容与正文）</div>
          {dyns or '<div class="muted">无</div>'}
          <div class="up-tabs">高赞金句</div>
          {quotes or '<div class="muted">无</div>'}
          <div class="up-tabs">充电信息分析</div>
          {charging_html or '<div class="muted">无</div>'}
        </details>"""
    up_html = f"""
    <div class="card up-card">
      <div class="sec-title">up主动态与观点蒸馏汇总</div>
      {up_summary_rows or '<div class="muted">未配置 up主（config.json → bilibili.upmasters）</div>'}
    </div>
    {up_details}"""

    error_detail = "".join(
        f'<div class="src-error"><b>{esc(s.get("label", name))}</b>：{esc(s.get("error", "未知错误"))}</div>'
        for name, s in sources.items()
        if s.get("status") == "error" and s.get("error")
    )

    # ---------- 头部 4 卡片：雪球 / 同花顺 / 金十 / 财联社（热股 TOP10 + 热门话题 TOP10） ----------
    watch_names = [str(s.get("name", "")) for s in config.get("watchlist", []) if s.get("name")]

    xueqiu = items.get("xueqiu", {}) or {}
    xq_stocks = xueqiu.get("hot_stocks", []) or []
    xq_topics_raw = xueqiu.get("hot_topics", []) or []
    xq_posts_h = xueqiu.get("hot_posts", []) or []
    xq_stock_rows = [
        {"text": s.get("title", ""), "meta": f"热度 {fmt_num(s.get('views'))}",
         "example": s.get("content", "")[:60]}
        for s in xq_stocks[:10]
    ]
    xq_topic_rows = [
        {"text": t.get("title", "")[:30],
         "meta": f"{fmt_num(t.get('views'))}讨论",
         "example": t.get("content", "")[:60]}
        for t in xq_topics_raw[:10]
    ]
    xq_card = _hot_card(
        "雪球热榜", "#3a8ee6", xq_stock_rows, xq_topic_rows,
        foot="热股=雪球官方热股榜；话题=雪球官网右侧「热门话题」(hot_event)",
    )

    ths = items.get("ths", {}) or {}
    ths_stocks_raw = ths.get("hot_stocks", []) or []
    ths_stock_rows = [
        {
            "text": s.get("name", ""),
            "meta": _pct_badge(s.get("pct")),
            "example": "、".join(
                x for x in [s.get("popularity", ""), "、".join(s.get("concept", []) or [])] if x
            ) or s.get("topic", ""),
        }
        for s in ths_stocks_raw[:10]
    ]
    ths_topics_raw = ths.get("hot_topics", []) or []
    ths_topic_rows = [
        {
            "text": t.get("name", ""),
            "meta": _pct_badge(t.get("pct")),
            "example": " · ".join(x for x in [t.get("tag", ""), t.get("hot_tag", ""), f"热度{fmt_num(t.get('rate'))}"] if x),
        }
        for t in ths_topics_raw[:10]
    ]
    ths_card = _hot_card(
        "同花顺热榜", "#f0a020", ths_stock_rows, ths_topic_rows,
        foot="同花顺官方热股榜 / 板块热榜（实时，A股）",
    )

    jin10 = items.get("jin10", {}) or {}
    jin10_flash = jin10.get("flash", []) or []
    jin10_topics_raw = jin10.get("hot_topics", []) or []
    jin10_flash_h = sorted(
        jin10_flash,
        key=lambda x: (int(x.get("importance", 0) or 0), x.get("ts", 0)),
        reverse=True,
    )
    jin10_stock_rows = [
        {"text": m["text"], "meta": f"热度 {m['heat']:g}", "example": m["example"]}
        for m in _mention_heat(jin10_flash_h, watch_names)
    ]
    jin10_topic_rows = [
        {"text": t.get("title", "")[:24],
         "meta": "热点头条",
         "example": t.get("content", "")[:70]}
        for t in jin10_topics_raw[:10]
    ]
    jin10_card = _hot_card(
        "金十快讯", "#e8a33d", jin10_stock_rows, jin10_topic_rows,
        foot="热股=快讯关联股；话题=金十热点头条 TOP10 (xnews.jin10.com)",
    )

    cls = items.get("cls", {}) or {}
    cls_tele = cls.get("telegraph", []) or []
    cls_articles = cls.get("hot_articles", []) or []
    # 热股：财联社 App 热股榜为签名私有接口，公开渠道无个股热股榜 → 不展示（显示「暂无热股数据」，与金十一致）
    cls_plates = cls.get("hot_plate", {}) or {}
    cls_stock_rows = []
    cls_topic_rows = [
        {
            "text": a.get("title", "")[:24],
            "meta": f"{fmt_num(a.get('views'))}阅",
            "example": a.get("content", "")[:70],
        }
        for a in cls_articles[:10]
    ]
    cls_card = _hot_card(
        "财联社热榜", "#1f9d8a", cls_stock_rows, cls_topic_rows,
        foot="热股=暂无（App 热股榜为签名私有接口，公开渠道无个股热股榜）；话题=财联社热门文章 TOP10",
    )

    em = items.get("em", {}) or {}
    em_stocks_raw = em.get("hot_stocks", []) or []
    em_concepts_raw = em.get("hot_concepts", []) or []
    em_keywords_raw = em.get("hot_keywords", []) or []
    em_stock_rows = [
        {
            "text": s.get("title", ""),
            "meta": _pct_badge((s.get("extra") or {}).get("pct")),
            "example": f"东方财富人气榜第{s.get('views')}名",
        }
        for s in em_stocks_raw[:10]
    ]
    em_topic_rows = [
        {
            "text": c.get("title", ""),
            "meta": _pct_badge((c.get("extra") or {}).get("pct")),
            "example": f"领涨股 {(c.get('extra') or {}).get('leader', '')}",
        }
        for c in em_concepts_raw[:10]
    ]
    em_keyword_rows = [
        {"text": k.get("title", "")[:30], "meta": "热门搜索", "example": "东方财富搜索框热门关键词"}
        for k in em_keywords_raw[:10]
    ]
    em_card = _hot_card(
        "东方财富热榜", "#e0322b", em_stock_rows, em_topic_rows,
        foot="热股=东财人气榜TOP10；话题=领涨概念TOP10(so.eastmoney.com)",
    )
    header_cards = xq_card + ths_card + jin10_card + cls_card + em_card

    def _plat_chips(platforms: List[str]) -> str:
        return "".join(
            f'<span class="plat-chip" style="background:{PLAT_COLORS.get(p, "#888")}">{esc(p)}</span>'
            for p in platforms
        )

    # ---------- 今日热门板块：官方板块榜（同花顺/财联社/东财）+ 雪球热榜 ----------
    official_boards: List[Dict[str, Any]] = []
    seen_board = set()
    for s in xq_stocks[:3]:
        n = str(s.get("title", "") or "").strip()
        if not n or n in seen_board:
            continue
        seen_board.add(n)
        official_boards.append({
            "text": n,
            "platforms": ["雪球"],
            "meta": f"热度 {fmt_num(s.get('views'))}",
            "example": "雪球官方热股榜",
        })
    for t in xq_topics_raw[:3]:
        n = str(t.get("title", "") or "").strip()
        if not n or n in seen_board:
            continue
        seen_board.add(n)
        official_boards.append({
            "text": n[:20],
            "platforms": ["雪球"],
            "meta": f"{fmt_num(t.get('views'))}讨论",
            "example": t.get("content", "")[:80],
        })
    for t in ths_topics_raw[:8]:
        n = str(t.get("name", "") or "").strip()
        if not n or n in seen_board:
            continue
        seen_board.add(n)
        official_boards.append({
            "text": n,
            "platforms": ["同花顺"],
            "meta": _pct_badge(t.get("pct")),
            "example": " · ".join(x for x in [t.get("tag", ""), t.get("hot_tag", "")] if x),
        })
    cls_board_n = 0
    for plate_type in ("industry", "concept", "area"):
        if cls_board_n >= 6:
            break
        for p in cls_plates.get(plate_type, []) or []:
            if cls_board_n >= 6:
                break
            n = str(p.get("name", "") or "").strip()
            if not n or n in seen_board:
                continue
            seen_board.add(n)
            fund = int(p.get("main_fund_diff", 0) or 0)
            fund_txt = ""
            if abs(fund) >= 100000000:
                fund_txt = f"主力{'净流入' if fund > 0 else '净流出'} {abs(fund) / 100000000:.1f}亿"
            elif abs(fund) >= 10000:
                fund_txt = f"主力{'净流入' if fund > 0 else '净流出'} {abs(fund) / 10000:.0f}万"
            leader_txt = (p.get("leaders") or [{}])[0].get("name", "")
            official_boards.append({
                "text": n,
                "platforms": ["财联社"],
                "meta": _pct_badge(p.get("pct")),
                "example": " · ".join(x for x in [fund_txt, f"领涨股 {leader_txt}" if leader_txt else ""] if x),
            })
            cls_board_n += 1
    for c in em_concepts_raw[:8]:
        n = str(c.get("title", "") or "").strip()
        if not n or n in seen_board:
            continue
        seen_board.add(n)
        leader = (c.get("extra") or {}).get("leader", "")
        official_boards.append({
            "text": n,
            "platforms": ["东方财富"],
            "meta": _pct_badge((c.get("extra") or {}).get("pct")),
            "example": f"领涨股 {leader}",
        })
    # 金十：快讯关联股 + 热点头条 并入板块/热榜汇总
    for t in (jin10_stock_rows + jin10_topic_rows)[:10]:
        n = str(t.get("text", "") or "").strip()
        if not n or n in seen_board:
            continue
        seen_board.add(n)
        official_boards.append({
            "text": n,
            "platforms": ["金十"],
            "meta": t.get("meta", ""),
            "example": t.get("example", "")[:80],
        })
    # 板块/热榜合并汇总：五大平台各取最多 4 条（同内容已去重），共 20 条编号列表
    ordered_boards: List[Dict[str, Any]] = []
    seen_ordered = set()
    for plat in ("雪球", "同花顺", "金十", "财联社", "东方财富"):
        picked = 0
        for b in official_boards:
            if b["text"] in seen_ordered or b["platforms"][0] != plat:
                continue
            seen_ordered.add(b["text"])
            ordered_boards.append(b)
            picked += 1
            if picked >= 4:
                break
    board_rows = "".join(
        f'<div class="hrow" title="{esc(b.get("example", ""))}">'
        f'<span class="hrow-idx">{i + 1}</span>'
        f'<span class="hrow-name">{esc(b["text"])}</span>'
        f'<span class="hrow-meta">{_plat_chips(b["platforms"])}{b.get("meta", "")}</span></div>'
        for i, b in enumerate(ordered_boards[:20])
    ) or '<div class="muted">暂无官方板块数据</div>'
    board_section = f"""
    <div class="card board-panel">
      <div class="sec-title">今日热门板块 / 热榜（官方板块榜 + 雪球热榜）</div>
      <div class="board-list">{board_rows}</div>
      <div class="muted" style="margin-top:6px">口径：雪球热股/热门话题 + 同花顺板块热榜 + 金十快讯关联股/热点头条 + 财联社热门板块（含主力资金/领涨股）+ 东方财富领涨概念榜（跨平台合并去重，TOP 20）</div>
    </div>"""

    # ---------- 综合热榜：五平台 热股/话题 跨平台合并去重 ----------
    def _tag_rows(rows: List[Dict[str, Any]], platform: str) -> List[Dict[str, Any]]:
        out = []
        for r in rows or []:
            x = dict(r)
            x["platform"] = platform
            out.append(x)
        return out

    def _aggregate_rank(groups: List[List[Dict[str, Any]]], limit: int = 10) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for rows in groups:
            for i, r in enumerate(rows or []):
                name = str(r.get("text", "") or "").strip()
                if not name:
                    continue
                e = merged.setdefault(
                    name,
                    {"text": name, "platforms": set(), "meta": "", "example": ""},
                )
                e["platforms"].add(r.get("platform", ""))
                e["weight"] = e.get("weight", 0) + max(1, 11 - i)
                if not e.get("meta") and r.get("meta"):
                    e["meta"] = r["meta"]
                if not e.get("example") and r.get("example"):
                    e["example"] = r["example"]
        out = sorted(merged.values(), key=lambda x: x["weight"], reverse=True)
        for e in out:
            e["platforms"] = sorted(e["platforms"])
        return out[:limit]

    stock_groups = [
        _tag_rows(xq_stock_rows, "雪球"),
        _tag_rows(ths_stock_rows, "同花顺"),
        _tag_rows(jin10_stock_rows, "金十"),
        _tag_rows(cls_stock_rows, "财联社"),
        _tag_rows(em_stock_rows, "东方财富"),
    ]
    topic_groups = [
        _tag_rows(xq_topic_rows, "雪球"),
        _tag_rows(ths_topic_rows, "同花顺"),
        _tag_rows(jin10_topic_rows, "金十"),
        _tag_rows(cls_topic_rows, "财联社"),
        _tag_rows(em_topic_rows, "东方财富"),
        _tag_rows(em_keyword_rows, "东方财富"),
    ]
    agg_stocks = _aggregate_rank(stock_groups, 10)
    agg_topics = _aggregate_rank(topic_groups, 10)

    agg_stock_html = "".join(
        f'<div class="hrow" title="{esc(s.get("example", ""))}">'
        f'<span class="hrow-idx">{i + 1}</span>'
        f'<span class="hrow-name">{esc(s["text"])}</span>'
        f'<span class="hrow-meta">{_plat_chips(s["platforms"])}{s.get("meta", "")}</span></div>'
        for i, s in enumerate(agg_stocks)
    ) or '<div class="muted">暂无</div>'
    agg_topic_html = "".join(
        f'<div class="hrow" title="{esc(t.get("example", ""))}">'
        f'<span class="hrow-idx">{i + 1}</span>'
        f'<span class="hrow-name">{esc(t["text"])}</span>'
        f'<span class="hrow-meta">{_plat_chips(t["platforms"])}{t.get("meta", "")}</span></div>'
        for i, t in enumerate(agg_topics)
    ) or '<div class="muted">暂无</div>'

    plat_hot_words = "".join(
        f'<span class="board-chip">{esc(t["text"])}{_plat_chips(t["platforms"])}</span>'
        for t in agg_topics[:10]
    ) or '<div class="muted">暂无</div>'

    merged_panel_html = f"""
    <div class="card merge-panel">
      <div class="sec-title">综合热榜（雪球 / 同花顺 / 金十 / 财联社 / 东方财富 热股 TOP10 汇总）</div>
      <div class="hcard-sub">热股 TOP10（跨平台合并去重）</div>
      {agg_stock_html}
    </div>"""

    # ---------- 各平台聚合 TOP10 话题总结（替代逐平台原始帖流） ----------
    top10_topics_html = "".join(
        f"""
        <div class="topic-summary-row">
          <span class="hrow-idx">{i + 1}</span>
          <div class="topic-summary-main">
            <div><b>{esc(t["text"])}</b> {_plat_chips(t["platforms"])} <span class="muted">{t.get("meta", "")}</span></div>
            <div class="muted">{esc(t.get("example", ""))[:100]}</div>
          </div>
        </div>"""
        for i, t in enumerate(agg_topics[:10])
    ) or '<div class="muted">暂无话题数据</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>当日舆论蒸馏日报 · {esc(date_str)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f6f8; color: #24292f; line-height: 1.55; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px 18px 60px; }}
  header {{ margin-bottom: 20px; }}
  h1 {{ font-size: 24px; }}
  .sub {{ color: #6a737d; font-size: 13px; margin-top: 4px; }}
  .chips {{ margin-top: 10px; display: flex; flex-wrap: wrap; gap: 8px; }}
  .src-chip {{ border: 1px solid; border-radius: 999px; padding: 3px 10px; font-size: 12px; }}
  .refresh-btn {{ border: 1px solid #5b6ee8; color: #5b6ee8; background: #fff; border-radius: 999px; padding: 5px 14px; font-size: 12px; cursor: pointer; }}
  .refresh-btn:hover {{ background: #f0f4ff; }}
  .refresh-btn:disabled {{ opacity: .6; cursor: wait; }}
  .refresh-link {{ color: #5b6ee8; text-decoration: none; font-weight: 700; }}
  .chip {{ display: inline-block; border: 1px solid; border-radius: 4px; padding: 0 6px; font-size: 11px; margin-left: 4px; }}
  .badge {{ display: inline-block; border-radius: 4px; color: #fff; padding: 1px 8px; font-size: 12px; }}
  .header-cards {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 20px; }}
  @media (max-width: 1100px) {{ .header-cards {{ grid-template-columns: repeat(3, 1fr); }} }}
  @media (max-width: 640px) {{ .header-cards {{ grid-template-columns: 1fr; }} }}
  .hcard {{ background: #fff; border-radius: 10px; padding: 12px 14px; box-shadow: 0 1px 3px rgba(0,0,0,.06); min-height: 240px; display: flex; flex-direction: column; }}
  .hcard-title {{ font-size: 13px; font-weight: 700; padding-bottom: 8px; margin-bottom: 8px; border-bottom: 2px solid; display: flex; align-items: center; gap: 6px; }}
  .hcard-body {{ flex: 1; font-size: 12px; max-height: 380px; overflow-y: auto; }}
  .hcard-sub {{ font-size: 11px; font-weight: 700; color: #57606a; margin: 8px 0 4px; padding-top: 6px; border-top: 1px dashed #eaecef; }}
  .hcard-sub:first-child {{ margin-top: 0; padding-top: 0; border-top: 0; }}
  .hcard-foot {{ color: #8b949e; font-size: 10px; margin-top: 8px; border-top: 1px dashed #eaecef; padding-top: 6px; }}
  .hrow {{ display: flex; justify-content: space-between; align-items: baseline; gap: 6px; padding: 4px 0; border-bottom: 1px dashed #f0f1f3; }}
  .hrow:last-child {{ border-bottom: 0; }}
  .hrow.dim {{ opacity: .72; }}
  .hrow-name {{ flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .hrow-idx {{ color: #8b949e; font-size: 11px; min-width: 18px; text-align: right; }}
  .hrow-meta {{ color: #57606a; font-size: 11px; text-align: right; white-space: nowrap; }}
  .topic-block {{ margin: 6px 0; padding: 7px 9px; background: #fafbfc; border: 1px solid #eef0f2; border-radius: 8px; }}
  .topic-block .hrow {{ padding: 3px 0; border-bottom: 0; }}
  .pct {{ font-weight: 700; font-size: 12px; min-width: 52px; text-align: right; }}
  .imp {{ color: #e8a33d; font-size: 11px; min-width: 22px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 20px; }}
  .stat {{ background: #fff; border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
  .stat b {{ font-size: 24px; display: block; }}
  .stat span {{ color: #6a737d; font-size: 12px; }}
  .sentibar {{ display: flex; height: 10px; border-radius: 5px; overflow: hidden; margin: 8px 0; }}
  .pos {{ background: #d93026; }} .neu {{ background: #c8c8c8; }} .neg {{ background: #0f8a4d; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 800px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}
  .card {{ background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.06); margin-bottom: 16px; }}
  .sec-title {{ font-size: 15px; font-weight: 700; margin-bottom: 10px; }}
  .rank-row {{ display: flex; align-items: center; gap: 8px; margin: 6px 0; }}
  .rank-name {{ width: 96px; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .rank-bar {{ flex: 1; background: #f0f1f3; border-radius: 4px; height: 12px; }}
  .rank-fill {{ height: 100%; border-radius: 4px; background: linear-gradient(90deg,#f6a05f,#e6532a); }}
  .rank-num {{ width: 56px; font-size: 12px; color: #6a737d; text-align: right; }}
  .meme-item {{ padding: 8px 0; border-bottom: 1px dashed #eaecef; }}
  .meme-item:last-child {{ border-bottom: 0; }}
  .meme-head {{ display: flex; justify-content: space-between; align-items: baseline; }}
  .meme-meta {{ font-size: 12px; color: #6a737d; }}
  .meme-ex {{ font-size: 12px; color: #6a737d; margin-top: 2px; }}
  .topic-head {{ display: flex; align-items: center; gap: 8px; }}
  .topic-phrases {{ color: #57606a; font-size: 12px; margin: 4px 0 8px; }}
  .post-list {{ list-style: none; }}
  .post-list li {{ padding: 4px 0; font-size: 13px; border-bottom: 1px solid #f0f1f3; }}
  .post-list a {{ color: #0969da; text-decoration: none; }}
  .hot-row {{ display: flex; gap: 8px; padding: 5px 0; font-size: 13px; border-bottom: 1px solid #f0f1f3; }}
  .hot-idx {{ color: #e6532a; font-weight: 700; width: 20px; }}
  .muted {{ color: #6a737d; font-size: 12px; }}
  .mini-card {{ margin-bottom: 10px; padding: 12px; }}
  .topic-sum {{ font-size: 12px; color: #57606a; margin-top: 4px; }}
  .up-grid {{ display: grid; grid-template-columns: 1.3fr 1fr; gap: 14px; margin-top: 10px; }}
  @media (max-width: 800px) {{ .up-grid {{ grid-template-columns: 1fr; }} }}
  .up-video {{ padding: 6px 0; border-bottom: 1px dashed #eaecef; }}
  .up-video-title a {{ color: #0969da; text-decoration: none; font-size: 13px; }}
  .up-video-meta {{ margin-top: 2px; }}
  .quote {{ padding: 6px 0; font-size: 13px; border-bottom: 1px dashed #eaecef; }}
  .quote-q {{ color: #24292f; }}
  .up-head-row {{ display: flex; align-items: center; gap: 10px; }}
  .up-avatar {{ width: 44px; height: 44px; border-radius: 50%; object-fit: cover; background: #f0f1f3; }}
  .up-meta {{ color: #6a737d; font-size: 12px; margin-top: 2px; }}
  .dyn-item {{ padding: 6px 0; border-bottom: 1px dashed #eaecef; font-size: 13px; }}
  .dyn-item:last-child {{ border-bottom: 0; }}
  .dyn-meta {{ color: #6a737d; font-size: 11px; margin-top: 2px; }}
  .dyn-body {{ color: #57606a; font-size: 12px; margin-top: 3px; }}
  .cc-users {{ margin-top: 8px; }}
  .cc-user {{ padding: 5px 0; border-bottom: 1px dashed #eaecef; font-size: 12px; }}
  .cc-user:last-child {{ border-bottom: 0; }}
  .up-tabs {{ display: flex; gap: 12px; margin: 10px 0 4px; font-size: 13px; font-weight: 700; color: #57606a; }}
  .topic-chip {{ padding: 7px 0; border-bottom: 1px dashed #eaecef; }}
  .topic-chip:last-child {{ border-bottom: 0; }}
  .board-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .board-list {{ margin-top: 4px; }}
  .board-chip {{ display: inline-flex; align-items: baseline; gap: 6px; background: #f0f4ff; border: 1px solid #d9e2ff; border-radius: 8px; padding: 5px 10px; font-size: 12px; }}
  .up-summary-row {{ display: flex; gap: 10px; align-items: center; padding: 8px 0; border-bottom: 1px dashed #eaecef; }}
  .up-summary-row:last-child {{ border-bottom: 0; }}
  .up-summary-main {{ flex: 1; }}
  .up-detail {{ background: #fff; border-radius: 10px; padding: 12px 16px; box-shadow: 0 1px 3px rgba(0,0,0,.06); margin-bottom: 12px; }}
  .up-detail summary {{ cursor: pointer; font-size: 14px; color: #24292f; }}
  .up-detail[open] summary {{ margin-bottom: 6px; }}
  .merge-panel {{ background: linear-gradient(180deg,#fff, #fbfcff); }}
  .merge-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
  @media (max-width: 800px) {{ .merge-grid {{ grid-template-columns: 1fr; }} }}
  .plat-chip {{ display: inline-block; border-radius: 4px; color: #fff; font-size: 10px; padding: 1px 5px; margin-right: 3px; }}
  .hrow-meta .plat-chip {{ margin-left: 2px; }}
  .topic-summary-row {{ display: flex; gap: 10px; align-items: baseline; padding: 7px 0; border-bottom: 1px dashed #eaecef; }}
  .topic-summary-row:last-child {{ border-bottom: 0; }}
  .topic-summary-main {{ flex: 1; }}
  .src-error {{ color: #c0392b; font-size: 12px; margin-top: 6px; }}
  footer {{ color: #8b949e; font-size: 12px; margin-top: 30px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>当日舆论蒸馏日报</h1>
    <div style="margin-top:8px">
      <button class="refresh-btn" id="refresh-btn" onclick="refreshData('all')">🔄 立即刷新</button>
      <span class="muted" style="margin-left:8px">停止定时任务后，点击可实时重采集全部平台并更新日报</span>
    </div>
    <div class="sub">{esc(date_str)} · 采集于 {esc(report.get('collected_at', ''))} · 数据源 {ok_sources}/{total_sources} 正常</div>
    <div class="sub" style="color:#9a6b1f">统计窗口：{esc((report.get('window') or {}).get('since', ''))} → {esc((report.get('window') or {}).get('until', ''))}（{esc((report.get('window') or {}).get('mode', ''))}）</div>
    <div class="chips">{source_chips}</div>
  </header>

  <div class="header-cards">{header_cards}</div>

  {board_section}

  {merged_panel_html}

  <div class="card">
    <div class="sec-title">五大平台热词 TOP10（雪球/同花顺/金十/财联社/东方财富 话题聚合）</div>
    <div class="board-row">{plat_hot_words}</div>
  </div>

  <div class="card">
    <div class="sec-title">各平台聚合 TOP10 话题（雪球 / 同花顺 / 金十 / 财联社 / 东方财富）</div>
    {top10_topics_html}
  </div>

  <div class="sec-title" style="margin-top:6px">up主动态与观点蒸馏</div>
  {up_html or '<div class="card muted">未配置 up主（config.json → bilibili.upmasters）</div>'}

  {error_detail and f'<div class="card"><div class="sec-title">数据源异常</div>{error_detail}</div>'}

  <footer>仅供研究参考，不构成投资建议 · 数据来自公开接口，时效与准确性以原平台为准 · 生成于 {esc(report.get('collected_at', ''))} · <a href="https://yonglongl630-ops.github.io/opagg-report/" style="color:#8b949e">在线版</a></footer>
  <script>
  function refreshBase() {{
    return (location.protocol === 'http:' || location.protocol === 'https:') ? location.origin : 'http://127.0.0.1:8651';
  }}
  function refreshData(source) {{
    var btn = document.getElementById('refresh-btn');
    var links = document.querySelectorAll('.refresh-link');
    for (var i = 0; i < links.length; i++) {{ links[i].style.pointerEvents = 'none'; links[i].textContent = '刷新中…'; }}
    if (btn) {{ btn.disabled = true; btn.textContent = '刷新中…（约1-2分钟）'; }}
    fetch(refreshBase() + '/api/refresh?source=' + encodeURIComponent(source || 'all'), {{ method: 'POST' }})
      .then(function (r) {{ return r.json(); }})
      .then(function (j) {{
        if (j && j.ok) {{ pollRefresh(); }}
        else {{ alert('刷新启动失败：' + (j && j.error ? j.error : '未知错误')); resetRefreshBtns(); }}
      }})
      .catch(function () {{
        alert('无法连接刷新服务。请先运行 python3 -m src.serve，再通过 http://127.0.0.1:8651 打开日报');
        resetRefreshBtns();
      }});
  }}
  function pollRefresh() {{
    var base = refreshBase();
    var t = setInterval(function () {{
      fetch(base + '/api/status').then(function (r) {{ return r.json(); }}).then(function (j) {{
        if (j && !j.running) {{ clearInterval(t); location.reload(); }}
      }}).catch(function () {{ clearInterval(t); resetRefreshBtns(); }});
    }}, 2500);
  }}
  function resetRefreshBtns() {{
    var btn = document.getElementById('refresh-btn');
    if (btn) {{ btn.disabled = false; btn.textContent = '🔄 立即刷新'; }}
    var links = document.querySelectorAll('.refresh-link');
    for (var i = 0; i < links.length; i++) {{ links[i].style.pointerEvents = ''; links[i].textContent = '🔄 立即刷新'; }}
  }}
  </script>
</div>
</body>
</html>"""
