"""财联社采集：官方行情热板块 + 热门文章 TOP10 + 电报资讯榜。

取数路径（财联社官方公开接口）：
- 热门板块（热股来源）：https://x-quote.cls.cn/web_quote/plate/hot_plate
  ?type=industry,concept,area&way=change&rever=1  （官方行情页「热门板块」，
  含板块涨跌幅、主力资金、领涨股，头部卡片热股取各热门板块领涨股）
- 热门文章 TOP10（热门话题）：解析 https://www.cls.cn/ 首页 pageProps.hotArticleData，
  按阅读数（readNum）降序取前 10 条
- 电报资讯榜（分平台详情）：解析 m.cls.cn/telegraph 页面内嵌 __NEXT_DATA__ 的 roll_data，
  按 level 排序（A/B 为 App 内「标红」重点快讯，优先展示），同级别按阅读数降序，
  取前 10 条作为「资讯榜 TOP10」。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List

from .common import UA_MOBILE, UA_PC, clean_text, log

URL = "https://m.cls.cn/telegraph"
HOT_PLATE_URL = "https://x-quote.cls.cn/web_quote/plate/hot_plate"
LEVEL_WEIGHT = {"A": 3, "B": 2, "C": 1}


class ClsClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        from .common import Session
        self.sess = Session(ua=UA_MOBILE, retries=2)
        self.sess_pc = Session(ua=UA_PC, retries=2)

    # ---------- 官方热门板块（热股来源） ----------
    def hot_plate(self) -> Dict[str, Any]:
        params = {
            "type": "industry,concept,area",
            "way": "change",
            "rever": 1,
            "os": "web",
            "sv": "8.7.9",
            "app": "CailianpressWeb",
        }
        data = self.sess_pc.get_json(HOT_PLATE_URL, params=params, referer="https://www.cls.cn/")
        if not data or data.get("code") != 200:
            log.warning("财联社热门板块接口异常: %s", (data or {}).get("msg", "无数据"))
            return {}
        raw = data.get("data") or {}
        out: Dict[str, List[Dict[str, Any]]] = {}
        for plate_type in ("industry", "concept", "area"):
            rows = []
            for it in raw.get(plate_type) or []:
                leaders = [
                    {
                        "name": clean_text(s.get("secu_name", ""), 40),
                        "id": _norm_id(s.get("secu_code", "")),
                        "pct": s.get("change"),
                    }
                    for s in it.get("up_stock") or []
                    if s.get("secu_name")
                ]
                rows.append({
                    "name": clean_text(it.get("secu_name", ""), 40),
                    "code": it.get("secu_code", ""),
                    "plate_type": plate_type,
                    "pct": it.get("change"),
                    "main_fund_diff": it.get("main_fund_diff"),
                    "leaders": leaders,
                })
            if rows:
                out[plate_type] = rows
        return out

    # ---------- 电报资讯榜（热门话题） ----------

    def hot_articles(self, limit: int = 10) -> List[Dict[str, Any]]:
        """财联社官网热门文章排名（首页 hotArticleData），按阅读数降序。"""
        html = self.sess_pc.get_text("https://www.cls.cn/", referer="https://www.cls.cn/")
        if not html:
            return []
        raw = _extract_next_data(html)
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        items = (((payload.get("props") or {}).get("pageProps") or {}).get("hotArticleData")) or []
        items = sorted(items, key=lambda x: int(x.get("readNum", 0) or 0), reverse=True)
        out = []
        for it in items[:limit]:
            title = clean_text(it.get("title") or "", 120)
            if not title:
                continue
            ctime = int(it.get("ctime", 0) or 0)
            out.append({
                "source": "cls",
                "source_label": "财联社",
                "kind": "cls_hot_article",
                "title": title,
                "content": clean_text(it.get("brief") or it.get("title") or "", 400),
                "author": it.get("author") or "财联社",
                "url": f"https://www.cls.cn/detail/{it.get('id', '')}" if it.get("id") else "https://www.cls.cn/",
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ctime)) if ctime else "",
                "ts": ctime or int(time.time()),
                "likes": 0,
                "comments": 0,
                "views": int(it.get("readNum", 0) or 0),
                "extra": {"id": it.get("id"), "stocks": it.get("stocks", "")},
            })
        return out

    def telegraph(self, limit: int = 30) -> List[Dict[str, Any]]:
        html = self.sess.get_text(URL, referer="https://m.cls.cn/")
        if not html:
            return []
        raw = _extract_next_data(html)
        if not raw:
            log.warning("财联社页面未找到 __NEXT_DATA__")
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        roll = (((payload.get("props") or {}).get("initialState") or {}).get("roll_data")) or []
        out = []
        for it in roll[:limit]:
            title = clean_text(it.get("title") or "", 120)
            content = clean_text(it.get("brief") or it.get("content") or title, 400)
            if not content:
                continue
            stocks = []
            for s in it.get("stock_list") or []:
                if s.get("name"):
                    stocks.append({"code": s.get("code", ""), "name": s.get("name", "")})
            subjects = [s.get("subject_name", "") for s in it.get("subjects") or [] if s.get("subject_name")]
            ctime = int(it.get("ctime", 0) or 0)
            out.append({
                "source": "cls",
                "source_label": "财联社",
                "kind": "cls_telegraph",
                "title": title or content[:50],
                "content": content,
                "author": it.get("author", "") or "财联社",
                "url": f"https://www.cls.cn/detail/{it.get('id', '')}" if it.get("id") else "https://www.cls.cn/telegraph",
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ctime)) if ctime else "",
                "ts": ctime or int(time.time()),
                "likes": 0,
                "comments": int(it.get("comment_num", 0) or 0),
                "views": int(it.get("reading_num", 0) or 0),
                "extra": {"id": it.get("id"), "level": it.get("level", ""), "stocks": stocks, "subjects": subjects},
            })
        return out

    def collect(self) -> Dict[str, Any]:
        errors: List[str] = []
        try:
            plates = self.hot_plate()
        except Exception as e:  # noqa: BLE001
            plates = {}
            errors.append(f"热门板块: {e}")
        try:
            articles = self.hot_articles(10)
        except Exception as e:  # noqa: BLE001
            articles = []
            errors.append(f"热门文章: {e}")
        try:
            posts = self.telegraph(self.cfg.get("limit", 30))
        except Exception as e:  # noqa: BLE001
            posts = []
            errors.append(f"电报资讯: {e}")
        items = {
            "hot_plate": plates,
            "hot_articles": articles,
            "telegraph": posts,
        }
        posts = articles + posts
        status = "ok" if (plates or articles or posts) else "error"
        return {
            "status": status,
            "error": "；".join(errors) if status == "error" else "",
            "posts": posts,
            "items": items,
        }


def _extract_next_data(html: str) -> str:
    """按括号深度提取 __NEXT_DATA__ 的 JSON 对象（正确处理字符串内的引号与转义）。"""
    idx = html.find("__NEXT_DATA__")
    if idx < 0:
        return ""
    start = html.find("{", idx)
    if start < 0:
        return ""
    depth = 0
    in_str = False
    quote = ""
    i = start
    while i < len(html):
        ch = html[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                in_str = False
        else:
            if ch in ('"', "'"):
                in_str = True
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return html[start : i + 1]
        i += 1
    return ""


def _norm_id(secu_code: str) -> str:
    """把财联社 secu_code 规范成 SH600519 / SZ000001 格式（sz300394 → SZ300394）。"""
    s = str(secu_code or "").strip().upper()
    if not s:
        return ""
    if s.startswith(("SH", "SZ", "BJ")):
        return s
    if s.startswith(("600", "601", "603", "605", "688", "689")):
        return f"SH{s}"
    if s.startswith(("000", "001", "002", "003", "300", "301")):
        return f"SZ{s}"
    return s
