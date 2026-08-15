"""同花顺采集：官方热股榜/板块热榜（dq.10jqka.com.cn）+ 圈子帖子流。

取数路径（与同花顺 App「热榜」一致）：
- 热股榜：https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock
  ?stock_type=a&type=hour&list_type=normal  （实时热度榜，含题材归因）
- 板块热榜（热门话题）：.../hot_list/v1/plate?type=concept|industry
  （概念/行业板块热度榜，含涨停家数、连续上榜天数、关联 ETF）
- 圈子帖子流：t.10jqka.com.cn 首页 feed（http 版，https 被 403）
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .common import UA_MOBILE, UA_PC, clean_text, log

HOT_STOCK_URL = "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock"
HOT_PLATE_URL = "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/plate"


class ThsClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        from .common import Session
        self.sess = Session(ua=UA_MOBILE, retries=2)
        self.sess_pc = Session(ua=UA_PC, retries=2)

    # ---------- 官方热股榜 ----------
    def hot_stocks(self, limit: int = 10) -> List[Dict[str, Any]]:
        params = {"stock_type": "a", "type": "hour", "list_type": "normal"}
        data = self.sess.get_json(HOT_STOCK_URL, params=params, referer="https://www.iwencai.com/")
        if not data or data.get("status_code") != 0:
            log.warning("同花顺热股榜接口异常: %s", (data or {}).get("status_msg", "无数据"))
            return []
        out = []
        for it in (data.get("data") or {}).get("stock_list") or []:
            name = clean_text(it.get("name") or "", 40)
            code = str(it.get("code") or "")
            if not name or not code:
                continue
            tag = it.get("tag") or {}
            concept = (tag.get("concept_tag") or [])[:2]
            popularity = tag.get("popularity_tag") or ""
            topic = it.get("topic") or it.get("analyse_title") or ""
            out.append({
                "name": name,
                "code": code,
                "id": _normalize_stock_id(code, it.get("market")),
                "rate": float(it.get("rate") or 0),
                "pct": it.get("rise_and_fall"),
                "rank_chg": int(it.get("hot_rank_chg") or 0),
                "concept": concept,
                "popularity": popularity,
                "topic": clean_text(topic, 80),
                "order": int(it.get("order") or len(out) + 1),
            })
            if len(out) >= limit:
                break
        return out

    # ---------- 官方板块热榜（概念+行业）→ 热门话题 ----------
    def hot_topics(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for plate_type in ("concept", "industry"):
            params = {"type": plate_type}
            data = self.sess.get_json(HOT_PLATE_URL, params=params, referer="https://www.iwencai.com/")
            if not data or data.get("status_code") != 0:
                log.warning("同花顺板块热榜接口异常(%s): %s", plate_type, (data or {}).get("status_msg", "无数据"))
                continue
            for it in (data.get("data") or {}).get("plate_list") or []:
                name = clean_text(it.get("name") or "", 40)
                if not name:
                    continue
                rows.append({
                    "name": name,
                    "code": str(it.get("code") or ""),
                    "plate_type": plate_type,
                    "rate": float(it.get("rate") or 0),
                    "pct": it.get("rise_and_fall"),
                    "tag": it.get("tag") or "",
                    "hot_tag": it.get("hot_tag") or "",
                    "etf_name": it.get("etf_name") or "",
                    "order": int(it.get("order") or len(rows) + 1),
                })
        rows.sort(key=lambda x: x["rate"], reverse=True)
        return rows[:limit]

    # ---------- 圈子帖子流（保留） ----------
    def feed(self, limit: int = 40) -> List[Dict[str, Any]]:
        html = self.sess_pc.get_text(
            "http://t.10jqka.com.cn/", use_http=True, referer="http://t.10jqka.com.cn/"
        )
        if not html:
            return []
        out = []
        for item in re.findall(r'<li class="fl feed-item[^"]*".*?</li>', html, re.S):
            pid = re.search(r'data-pid="(\d+)"', item)
            pid_v = pid.group(1) if pid else ""
            time_m = re.search(r'feed-item-timeline-time">\s*([\d:]+)', item)
            time_v = time_m.group(1).strip() if time_m else ""
            author = ""
            author_m = re.search(r'class="broker-name[^"]*">([^<]+)</', item)
            if author_m:
                author = clean_text(author_m.group(1), 40)
            content = ""
            content_m = re.search(r'class="word-content">(.*?)</div>', item, re.S)
            if content_m:
                content = clean_text(content_m.group(1), 300)
            if not content:
                continue
            title = content[:50]
            views_m = re.search(r"阅读\s*</span>\s*([\d,.万]+)", item)
            views = _cn_num(views_m.group(1)) if views_m else 0
            href_m = re.search(r'class="feed-item-title[^"]*">\s*<a href="([^"]+)"', item)
            # 帖子没有独立详情页，用 pid 构造稳定唯一标识，避免与作者主页混淆导致去重误删
            url = f"http://t.10jqka.com.cn/circle/?pid={pid_v}" if pid_v else (
                href_m.group(1) if href_m else "http://t.10jqka.com.cn/"
            )
            out.append({
                "source": "ths",
                "source_label": "同花顺",
                "kind": "feed",
                "title": title,
                "content": content,
                "author": author or "同花顺圈子",
                "url": url,
                "time": time_v,
                "ts": 0,
                "likes": 0,
                "comments": 0,
                "views": views,
                "extra": {"pid": pid_v},
            })
            if len(out) >= limit:
                break
        return out

    def collect(self) -> Dict[str, Any]:
        errors: List[str] = []
        try:
            stocks = self.hot_stocks(10)
        except Exception as e:  # noqa: BLE001
            stocks = []
            errors.append(f"热股榜: {e}")
        try:
            topics = self.hot_topics(10)
        except Exception as e:  # noqa: BLE001
            topics = []
            errors.append(f"板块热榜: {e}")
        try:
            posts = self.feed(self.cfg.get("feed_limit", 40))
        except Exception as e:  # noqa: BLE001
            posts = []
            errors.append(f"圈子帖流: {e}")
        items = {
            "hot_stocks": stocks,
            "hot_topics": topics,
            "feed": posts,
        }
        status = "ok" if (stocks or topics or posts) else "error"
        return {
            "status": status,
            "error": "；".join(errors) if status == "error" else "",
            "posts": posts,
            "items": items,
        }


def _cn_num(s: str) -> int:
    s = (s or "").strip()
    if not s:
        return 0
    if "万" in s:
        try:
            return int(float(s.replace("万", "")) * 10000)
        except ValueError:
            return 0
    return int(s.replace(",", "")) if s.replace(",", "").isdigit() else 0


def _normalize_stock_id(code: str, market: Any) -> str:
    """把同花顺股票代码规范成 SH600722 / SZ002081 / BJ 格式。"""
    code = str(code or "").strip()
    if not code:
        return ""
    if code.upper().startswith(("SH", "SZ", "BJ")):
        return code.upper()
    m = {"17": "SH", "33": "SZ", "47": "BJ"}.get(str(market or ""))
    if m:
        return f"{m}{code}"
    if code.startswith(("4", "8", "92")):
        return f"BJ{code}"
    if code.startswith("6"):
        return f"SH{code}"
    return f"SZ{code}"
