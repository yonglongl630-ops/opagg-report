"""东方财富股吧采集：个股最新帖（服务端渲染） + 个股热帖 JSONP。"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List

from .common import UA_PC, clean_text, log
from .config import stock_name_map

EDITOR_HINTS = ("资讯", "小编", "官方", "东方财富", "证券日报", "交易所", "公告", "数据")


def _jsonp(text: str) -> Any:
    if not text:
        return None
    m = re.match(r"^[^=]+=(.*)$", text.strip(), re.S)
    body = m.group(1).strip() if m else text.strip()
    return json.loads(body)


class GubaClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.sess = None
        from .common import Session
        self.sess = Session(ua=UA_PC, retries=2)

    def stock_posts(self, code: str, limit: int = 40) -> List[Dict[str, Any]]:
        url = f"https://guba.eastmoney.com/list,{code}.html"
        html = self.sess.get_text(url, referer="https://guba.eastmoney.com/")
        if not html:
            return []
        out = []
        for row in re.findall(r'<tr class="listitem">(.*?)</tr>', html, re.S):
            read = _div(row, "read")
            reply = _div(row, "reply")
            title = _div(row, "title")
            author = _div(row, "author")
            update = _div(row, "update")
            if not title:
                continue
            postid = ""
            m = re.search(r'data-postid="(\d+)"', title)
            if m:
                postid = m.group(1)
            href = re.search(r'href="([^"]+)"', title)
            link = ""
            if href:
                href_v = href.group(1)
                link = href_v if href_v.startswith("http") else "https://guba.eastmoney.com" + href_v
            title_text = clean_text(title, 120)
            author_text = clean_text(author, 40)
            out.append({
                "source": "guba",
                "source_label": "股吧",
                "kind": "stock_post",
                "title": title_text,
                "content": f"[{code}] {title_text}",
                "author": author_text,
                "url": link or f"https://guba.eastmoney.com/news,{code},{postid}.html",
                "time": update or "",
                "ts": 0,
                "likes": int(_num(reply)),
                "comments": int(_num(reply)),
                "views": int(_num(read)),
                "is_editor": any(h in author_text for h in EDITOR_HINTS),
                "extra": {"code": code, "postid": postid, "read": read, "reply": reply},
            })
            if len(out) >= limit:
                break
        return out

    def hot_topics(self, codes: List[str], limit: int = 5) -> List[Dict[str, Any]]:
        if not codes:
            return []
        codes_s = ",".join(codes)
        url = (
            "https://gbcdn.dfcfw.com/rank/interface/GetData.js"
            f"?needClick=1&codes={codes_s}"
            "&path=newtopic/api/Topic/GubaCodeHotTopicNewRead&cb=topicList"
        )
        text = self.sess.get_text(url, referer="https://guba.eastmoney.com/rank/")
        data = _jsonp(text) if text else None
        if not data or not isinstance(data, list):
            return []
        out = []
        for wrapper in data:
            for code, topics in (wrapper or {}).get("re", {}).items():
                for t in (topics or [])[:limit]:
                    posts = []
                    for p in (t.get("essen_postinfo") or [])[:3]:
                        posts.append({
                            "title": p.get("title", ""),
                            "url": p.get("gubaUrl", ""),
                        })
                    out.append({
                        "source": "guba",
                        "source_label": "股吧",
                        "kind": "hot_topic",
                        "title": t.get("name", ""),
                        "content": t.get("summary", "") or t.get("name", ""),
                        "author": f"股吧热帖·{code}",
                        "url": "",
                        "time": "",
                        "ts": 0,
                        "likes": int(t.get("participantCount", 0) or 0),
                        "comments": int(t.get("num", 0) or 0),
                        "views": int(t.get("clickCount", 0) or 0),
                        "extra": {"code": code, "htid": t.get("htid"), "posts": posts},
                    })
        return out

    def collect(self, cfg_all: Dict[str, Any]) -> Dict[str, Any]:
        watch = cfg_all.get("watchlist", [])
        g = self.cfg
        posts: List[Dict[str, Any]] = []
        errors: List[str] = []
        items: Dict[str, Any] = {}
        codes = [str(s.get("code", "")) for s in watch if s.get("code")]
        for s in watch:
            code = str(s.get("code", ""))
            try:
                rows = self.stock_posts(code, g.get("post_limit_per_stock", 40))
                posts += rows
                items.setdefault("stock_posts", {})[code] = rows
            except Exception as e:  # noqa: BLE001
                errors.append(f"{code}: {e}")
        try:
            topics = self.hot_topics(codes, g.get("hot_topic_limit", 5))
            posts += topics
            items["hot_topics"] = topics
        except Exception as e:  # noqa: BLE001
            errors.append(f"热帖: {e}")
        status = "error" if (not posts and errors) else ("partial" if errors else "ok")
        return {"status": status, "error": "；".join(errors), "posts": posts, "items": items}


def _div(row: str, cls: str) -> str:
    m = re.search(r'<div class="' + cls + r'">(.*?)</div>', row, re.S)
    return m.group(1) if m else ""


def _num(s: str) -> int:
    m = re.search(r"[\d,]+", s or "")
    return int(m.group(0).replace(",", "")) if m else 0
