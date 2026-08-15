"""东方财富采集：个股人气榜 + 领涨概念 + 搜索框热门关键词。

取数路径（东方财富官方公开接口）：
- 热门个股（图1 搜索框/人气榜）：https://emappdata.eastmoney.com/stockrank/getAllCurrentList
  POST {"appId":"appId01","globalId":"786e4c21-70dc-435a-93bb-38",...}，
  再用 push2 ulist 补名称/涨跌幅（与 guba.eastmoney.com/rank 人气榜一致）
- 领涨概念 TOP10（so.eastmoney.com 右侧同源）：
  https://push2.eastmoney.com/api/qt/clist/get?fs=m:90+t:3&fid=f3&po=1
- 搜索框热门搜索关键词：https://searchadapter.eastmoney.com/api/hotkeyword/get
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List

from .common import UA_PC, clean_text, log

RANK_URL = "https://emappdata.eastmoney.com/stockrank/getAllCurrentList"
QUOTE_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
)
CONCEPT_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
)
KEYWORD_URL = "https://searchadapter.eastmoney.com/api/hotkeyword/get"

APP_ID = "appId01"
GLOBAL_ID = "786e4c21-70dc-435a-93bb-38"


class EmClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        from .common import Session
        self.sess = Session(ua=UA_PC, retries=2)

    # ---------- 热门个股（人气榜） ----------
    def hot_stocks(self, limit: int = 10) -> List[Dict[str, Any]]:
        payload = {
            "appId": APP_ID,
            "globalId": GLOBAL_ID,
            "marketType": "",
            "pageNo": 1,
            "pageSize": max(limit, 10),
        }
        data = self.sess.post_json(RANK_URL, payload, referer="https://guba.eastmoney.com/rank/")
        rows = (data or {}).get("data") or []
        if not rows:
            log.warning("东财人气榜接口无数据")
            return []
        secids = []
        for it in rows[:limit]:
            sc = str(it.get("sc") or "")
            if sc.startswith("SH"):
                secids.append("1." + sc[2:])
            elif sc.startswith("SZ"):
                secids.append("0." + sc[2:])
        quotes = {}
        if secids:
            params = {
                "fltt": 2,
                "invt": 2,
                "secids": ",".join(secids),
                "fields": "f2,f3,f12,f14",
            }
            q = None
            for host in QUOTE_HOSTS:
                q = self.sess.get_json(f"{host}/api/qt/ulist.np/get", params=params, referer="https://quote.eastmoney.com/")
                if q:
                    break
            for it in ((q or {}).get("data") or {}).get("diff") or []:
                if isinstance(it, dict) and it.get("f12"):
                    quotes[str(it.get("f12"))] = it
        out = []
        for i, it in enumerate(rows[:limit]):
            sc = str(it.get("sc") or "")
            code = sc[2:] if len(sc) > 2 else sc
            q = quotes.get(code, {})
            name = clean_text(q.get("f14") or "", 40)
            if not name:
                name = clean_text(code, 40)
            out.append({
                "source": "em",
                "source_label": "东方财富",
                "kind": "em_hot_stock",
                "title": name,
                "content": f"东方财富人气榜：{name}（{sc}）第{it.get('rk', i + 1)}名",
                "author": "东方财富人气榜",
                "url": f"https://quote.eastmoney.com/{code}.html" if code else "https://www.eastmoney.com/",
                "time": "",
                "ts": 0,
                "likes": 0,
                "comments": 0,
                "views": int(it.get("rk", i + 1) or i + 1),
                "extra": {
                    "code": sc,
                    "rank": it.get("rk"),
                    "rank_chg": it.get("rc"),
                    "his_rank_chg": it.get("hisRc"),
                    "pct": q.get("f3"),
                    "price": q.get("f2"),
                },
            })
        return out

    # ---------- 领涨概念 TOP10（so.eastmoney.com 同源） ----------
    def hot_concepts(self, limit: int = 10) -> List[Dict[str, Any]]:
        params = {
            "pn": 1,
            "pz": limit,
            "po": 1,
            "np": 1,
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:90+t:3",
            "fields": "f2,f3,f12,f14,f128,f136",
        }
        data = None
        for host in CONCEPT_HOSTS:
            data = self.sess.get_json(f"{host}/api/qt/clist/get", params=params, referer="https://so.eastmoney.com/")
            if data:
                break
        diff = ((data or {}).get("data") or {}).get("diff") or []
        out = []
        for it in diff[:limit]:
            name = clean_text(it.get("f14") or "", 40)
            if not name:
                continue
            leader = clean_text(it.get("f128") or "", 40)
            out.append({
                "source": "em",
                "source_label": "东方财富",
                "kind": "em_hot_concept",
                "title": name,
                "content": f"东方财富领涨概念：{name}（{it.get('f12')}）涨跌幅 {it.get('f3')}%，领涨股 {leader}",
                "author": "东方财富领涨概念",
                "url": f"https://quote.eastmoney.com/bk/{it.get('f12')}.html" if it.get("f12") else "https://so.eastmoney.com/",
                "time": "",
                "ts": 0,
                "likes": 0,
                "comments": 0,
                "views": int((it.get("f2") or 0) if it.get("f2") is not None else 0),
                "extra": {
                    "code": it.get("f12"),
                    "pct": it.get("f3"),
                    "leader": leader,
                    "leader_pct": it.get("f136"),
                },
            })
        return out

    # ---------- 搜索框热门搜索关键词 ----------
    def hot_keywords(self, limit: int = 10) -> List[Dict[str, Any]]:
        params = {"count": max(limit, 10), "token": "32A8A21716361A5A387B0D85259A0037"}
        data = self.sess.get_json(KEYWORD_URL, params=params, referer="https://so.eastmoney.com/")
        rows = (data or {}).get("Data") or []
        out = []
        for it in rows[:limit]:
            kw = clean_text(it.get("KeyPhrase") or "", 60)
            if not kw:
                continue
            out.append({
                "source": "em",
                "source_label": "东方财富",
                "kind": "em_hot_keyword",
                "title": kw,
                "content": f"东方财富热门搜索：{kw}",
                "author": "东方财富热门搜索",
                "url": it.get("JumpAddress") or "https://so.eastmoney.com/",
                "time": "",
                "ts": 0,
                "likes": 0,
                "comments": 0,
                "views": 0,
                "extra": {"status": it.get("HotKeywordStatus"), "color": it.get("Color")},
            })
        return out

    def collect(self) -> Dict[str, Any]:
        errors: List[str] = []
        items: Dict[str, Any] = {}
        posts: List[Dict[str, Any]] = []
        for key, fn in (
            ("hot_stocks", self.hot_stocks),
            ("hot_concepts", self.hot_concepts),
            ("hot_keywords", self.hot_keywords),
        ):
            try:
                rows = fn(10)
                items[key] = rows
                posts += rows
            except Exception as e:  # noqa: BLE001
                errors.append(f"{key}: {e}")
        status = "ok" if posts else "error"
        return {
            "status": status,
            "error": "；".join(errors) if status == "error" else "",
            "posts": posts,
            "items": items,
        }
