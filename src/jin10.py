"""金十数据采集：快讯流 + 热点头条。

取数路径：
- 快讯流：https://www.jin10.com/flash_newest.js（重要度 ★）
- 热点头条（热门话题）：https://cdn.jin10.com/json/index/hits_rank.json
  的 all.daily.news 前 10 条（与 https://xnews.jin10.com/53 热点头条一致）
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List

from .common import UA_PC, clean_text, log

URL = "https://www.jin10.com/flash_newest.js"
IMPORTANCE = {0: 0, 1: 800, 2: 3000, 3: 8000}  # 重要度 → 热度代理值


class Jin10Client:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        from .common import Session
        self.sess = Session(ua=UA_PC, retries=2)

    def hot_topics(self, limit: int = 10) -> List[Dict[str, Any]]:
        """金十「热点头条」前 N：xnews 热点头条排行 JSON。"""
        data = self.sess.get_json(
            "https://cdn.jin10.com/json/index/hits_rank.json",
            referer="https://xnews.jin10.com/",
        )
        if not data:
            return []
        news = (((data.get("all") or {}).get("daily") or {}).get("news")) or []
        out = []
        for it in news[:limit]:
            title = clean_text(it.get("title") or "", 120)
            if not title:
                continue
            nid = str(it.get("id") or "")
            out.append({
                "source": "jin10",
                "source_label": "金十",
                "kind": "jin10_hot_topic",
                "title": title,
                "content": title,
                "author": "金十热点头条",
                "url": f"https://xnews.jin10.com/details/{nid}" if nid else "https://xnews.jin10.com/",
                "time": "",
                "ts": 0,
                "likes": 0,
                "comments": 0,
                "views": 0,
                "importance": 3,
                "extra": {"news_id": nid, "vip": it.get("vip")},
            })
        return out

    def flash(self, limit: int = 30) -> List[Dict[str, Any]]:
        text = self.sess.get_text(URL, referer="https://www.jin10.com/")
        if not text:
            return []
        m = re.search(r"=\s*(\[.*\])\s*;?\s*$", text, re.S)
        if not m:
            return []
        import json
        try:
            items = json.loads(m.group(1))
        except json.JSONDecodeError:
            return []
        out = []
        for it in items[:limit]:
            d = it.get("data") or {}
            title = clean_text(d.get("title") or "", 120)
            content = clean_text(d.get("content") or title or "", 400)
            if not content:
                continue
            imp = int(it.get("important", 0) or 0)
            tags = it.get("tags") or []
            flash_id = str(it.get("id", ""))
            out.append({
                "source": "jin10",
                "source_label": "金十",
                "kind": "jin10_flash",
                "title": title or content[:50],
                "content": content,
                "author": "金十数据",
                "url": f"https://www.jin10.com/flash/{flash_id}" if flash_id else "https://www.jin10.com/flash/",
                "time": it.get("time", ""),
                "ts": int(time.mktime(time.strptime(it["time"], "%Y-%m-%d %H:%M:%S"))) if it.get("time") else int(time.time()),
                "likes": IMPORTANCE.get(imp, 0),
                "comments": 0,
                "views": 0,
                "importance": imp,
                "extra": {"id": flash_id, "tags": tags, "source": d.get("source", "")},
            })
        return out

    def collect(self) -> Dict[str, Any]:
        errors: List[str] = []
        try:
            topics = self.hot_topics(10)
        except Exception as e:  # noqa: BLE001
            topics = []
            errors.append(f"热点头条: {e}")
        try:
            posts = self.flash(self.cfg.get("limit", 30))
        except Exception as e:  # noqa: BLE001
            posts = []
            errors.append(f"快讯流: {e}")
        items = {
            "hot_topics": topics,
            "flash": posts,
        }
        posts = topics + posts
        status = "ok" if (topics or posts) else "error"
        return {
            "status": status,
            "error": "；".join(errors) if status == "error" else "",
            "posts": posts,
            "items": items,
        }
