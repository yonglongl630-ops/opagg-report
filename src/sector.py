"""板块行情汇总（Wind 板块口径近似）：东方财富行业/概念板块涨幅榜与跌幅榜。

说明：Wind 终端数据需商业授权，这里以东方财富公开板块行情近似"Wind 板块汇总"，
包含行业/概念两大口径的领涨领跌板块，用于日报头部展示。
"""

from __future__ import annotations

import time
import urllib.parse
from typing import Any, Dict, List

from .common import UA_PC, clean_text, log

API_HOSTS = [
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
]
FIELDS = "f2,f3,f4,f12,f14,f104,f105,f128,f140,f136"
FS_INDUSTRY = "m:90+t:2+f:!50"  # 行业板块
FS_CONCEPT = "m:90+t:3+f:!50"   # 概念板块


class SectorClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        from .common import Session
        self.sess = Session(ua=UA_PC, retries=2)

    def _board_list(self, fs: str, limit: int, order: str = "desc") -> List[Dict[str, Any]]:
        params = urllib.parse.urlencode({
            "pn": 1,
            "pz": limit,
            "po": 1 if order == "desc" else 0,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": fs,
            "fields": FIELDS,
        })
        data = None
        for host in API_HOSTS:
            data = self.sess.get_json(f"{host}/api/qt/clist/get?{params}", referer="https://quote.eastmoney.com/")
            if data:
                break
        if not data:
            return []
        diff = ((data or {}).get("data") or {}).get("diff") or []
        out = []
        for it in diff:
            name = clean_text(it.get("f14", ""), 40)
            if not name:
                continue
            out.append({
                "code": it.get("f12", ""),
                "name": name,
                "price": it.get("f2"),
                "pct": it.get("f3"),
                "change": it.get("f4"),
                "up_count": int(it.get("f104", 0) or 0),
                "down_count": int(it.get("f105", 0) or 0),
                "leader": it.get("f128", ""),
                "leader_code": it.get("f140", ""),
                "leader_pct": it.get("f136"),
            })
        return out

    def collect(self) -> Dict[str, Any]:
        cfg = self.cfg
        industry_limit = int(cfg.get("industry_limit", 8))
        concept_limit = int(cfg.get("concept_limit", 6))
        posts: List[Dict[str, Any]] = []
        errors: List[str] = []
        items: Dict[str, Any] = {}
        try:
            items["industry_up"] = self._board_list(FS_INDUSTRY, industry_limit, "desc")
            items["industry_down"] = self._board_list(FS_INDUSTRY, industry_limit, "asc")
            posts += self._as_posts(items["industry_up"], "板块领涨") + self._as_posts(items["industry_down"], "板块领跌")
        except Exception as e:  # noqa: BLE001
            errors.append(f"行业板块: {e}")
        try:
            items["concept_up"] = self._board_list(FS_CONCEPT, concept_limit, "desc")
            items["concept_down"] = self._board_list(FS_CONCEPT, concept_limit, "asc")
            posts += self._as_posts(items["concept_up"], "概念领涨") + self._as_posts(items["concept_down"], "概念领跌")
        except Exception as e:  # noqa: BLE001
            errors.append(f"概念板块: {e}")
        if not items:
            return {"status": "error", "error": "；".join(errors) or "板块接口无数据", "posts": [], "items": {}}
        return {
            "status": "ok" if not errors else "partial",
            "error": "；".join(errors),
            "posts": posts,
            "items": items,
        }

    @staticmethod
    def _as_posts(boards: List[Dict[str, Any]], tag: str) -> List[Dict[str, Any]]:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        out = []
        for b in boards:
            out.append({
                "source": "sector",
                "source_label": "板块",
                "kind": "sector",
                "title": f"{tag}·{b['name']}",
                "content": (
                    f"{tag}：{b['name']}（{b['code']}）涨跌幅 {b.get('pct')}%，"
                    f"上涨 {b.get('up_count')} 家 / 下跌 {b.get('down_count')} 家，"
                    f"领涨股 {b.get('leader')}"
                ),
                "author": "板块行情",
                "url": f"https://quote.eastmoney.com/bk/{b['code']}.html" if b.get("code") else "",
                "time": now,
                "ts": int(time.time()),
                "likes": 0,
                "comments": 0,
                "views": 0,
                "extra": {"board": b},
            })
        return out
