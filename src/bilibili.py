"""B站采集：热搜、全站排行、WBI 搜索、up主空间视频、视频详情与评论。"""

from __future__ import annotations

import hashlib
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from .common import Session, UA_PC, clean_text, log

API = "https://api.bilibili.com"


class BilibiliClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.sess = Session(ua=UA_PC, retries=2)
        import os
        cookie = cfg.get("cookie") or os.environ.get("BILI_COOKIE", "")
        if cookie:
            self.sess.set_cookie_str(str(cookie))
        self._mixin_key: Optional[str] = None
        self._ready = False

    # ---------- 基础 ----------

    def _ensure(self) -> bool:
        if self._ready:
            return True
        try:
            self.sess.get_text("https://www.bilibili.com/", referer="https://www.bilibili.com/")
            spi = self.sess.get_json(f"{API}/x/frontend/finger/spi")
            if spi and spi.get("data"):
                d = spi["data"]
                self.sess.cookies["buvid3"] = d.get("b_3", self.sess.cookies.get("buvid3", ""))
                self.sess.cookies["buvid4"] = d.get("b_4", self.sess.cookies.get("buvid4", ""))
            nav = self.sess.get_json(f"{API}/x/web-interface/nav", referer="https://www.bilibili.com/")
            if nav and nav.get("data", {}).get("wbi_img"):
                img = nav["data"]["wbi_img"]
                ik = img["img_url"].split("/")[-1].split(".")[0]
                sk = img["sub_url"].split("/")[-1].split(".")[0]
                self._mixin_key = (ik + sk)[:32]
            self._ready = bool(self._mixin_key)
            return self._ready
        except Exception as e:  # noqa: BLE001
            log.warning("B站会话初始化失败: %s", e)
            return False

    def _signed(self, base: str, params: Dict[str, Any]) -> str:
        params = dict(params)
        params["wts"] = int(time.time())
        q = urllib.parse.urlencode(sorted(params.items()))
        if self._mixin_key:
            q += "&w_rid=" + hashlib.md5((q + self._mixin_key).encode()).hexdigest()
        return base + "?" + q

    def _get_json(self, url: str, referer: str = "https://www.bilibili.com/") -> Optional[Any]:
        return self.sess.get_json(url, referer=referer)

    # ---------- 数据 ----------

    def hot_search(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self._ensure():
            return []
        data = self._get_json(f"{API}/x/web-interface/search/square?limit={limit}")
        out = []
        for it in (data or {}).get("data", {}).get("trending", {}).get("list", [])[:limit]:
            kw = it.get("show_name") or it.get("keyword") or ""
            if kw:
                out.append({
                    "source": "bilibili",
                    "source_label": "B站",
                    "kind": "hot_search",
                    "title": kw,
                    "content": f"B站热搜：{kw}",
                    "author": "B站热搜",
                    "url": f"https://search.bilibili.com/all?keyword={urllib.parse.quote(kw)}",
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "ts": int(time.time()),
                    "likes": int(it.get("heat_score") or 0),
                    "comments": 0,
                    "views": 0,
                })
        return out

    def ranking(self, limit: int = 30) -> List[Dict[str, Any]]:
        if not self._ensure():
            return []
        data = self._get_json(f"{API}/x/web-interface/ranking/v2?rid=0&type=all")
        out = []
        for it in (data or {}).get("data", {}).get("list", [])[:limit]:
            out.append(self._video_item(it, "ranking"))
        return out

    def search_videos(self, keyword: str, limit: int = 6) -> List[Dict[str, Any]]:
        if not self._ensure():
            return []
        url = self._signed(f"{API}/x/web-interface/search/type", {
            "search_type": "video", "keyword": keyword, "page": 1,
        })
        data = self._get_json(url)
        results = (data or {}).get("data", {}).get("result") or []
        out = []
        for it in results[:limit]:
            title = re.sub(r"</?em[^>]*>", "", it.get("title", ""))
            out.append(self._video_item({
                "bvid": it.get("bvid", ""),
                "title": title,
                "author": it.get("author", ""),
                "mid": it.get("mid", 0),
                "play": it.get("play", 0),
                "video_review": it.get("video_review", 0),
                "pubdate": it.get("pubdate", 0),
                "desc": it.get("description", ""),
            }, "search", keyword=keyword))
        return out

    def space_videos(self, mid: int, limit: int = 10) -> List[Dict[str, Any]]:
        if not self._ensure():
            return []
        url = f"{API}/x/space/arc/search?mid={mid}&ps={min(limit, 30)}&pn=1&order=pubdate"
        data = self._get_json(url)
        vlist = ((data or {}).get("data", {}) or {}).get("list", {}).get("vlist") or []
        if not vlist:
            log.warning("空间接口未返回视频 (mid=%s, code=%s)，等待后重试一次", mid, (data or {}).get("code"))
            time.sleep(2.5)
            data = self._get_json(url)
            vlist = ((data or {}).get("data", {}) or {}).get("list", {}).get("vlist") or []
        out = []
        for it in vlist[:limit]:
            out.append(self._video_item({
                "bvid": it.get("bvid", ""),
                "title": it.get("title", ""),
                "author": it.get("author", ""),
                "mid": it.get("mid", mid),
                "play": it.get("play", 0),
                "video_review": it.get("comment", 0),
                "pubdate": it.get("created", 0),
                "desc": it.get("description", ""),
            }, "up_video"))
        return out

    def user_card(self, mid: int) -> Optional[Dict[str, Any]]:
        """up主主页信息：昵称、头像、签名、粉丝数等。"""
        if not mid or not self._ensure():
            return None
        data = self._get_json(f"{API}/x/web-interface/card?mid={mid}", referer="https://space.bilibili.com/")
        card = ((data or {}).get("data") or {}).get("card") or {}
        if not card:
            return None
        follower = (((data or {}).get("data") or {}).get("follower") or 0)
        return {
            "mid": mid,
            "name": card.get("name", ""),
            "avatar": card.get("face", ""),
            "sign": clean_text(card.get("sign", ""), 200),
            "fans": int(follower or 0),
            "archive_count": int(card.get("archive_count", 0) or 0),
            "official": ((card.get("Official") or {}).get("title", "") or ""),
        }

    def dynamics(
        self,
        mid: int,
        limit: int = 10,
        since_ts: Optional[int] = None,
        stats: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """up主最近动态（文字/图文/转发/投稿/充电专属），带 WBI 签名。

        since_ts 非空时只返回窗口内的动态，避免混入历史信息。
        stats 非空时填充 {"ok": bool, "error": str, "charge_count": int}。
        """
        if stats is not None:
            stats["ok"] = False
            stats["error"] = ""
            stats["charge_count"] = 0
        if not mid or not self._ensure():
            if stats is not None:
                stats["error"] = "B站会话初始化失败"
            return []
        out: List[Dict[str, Any]] = []
        offset = ""
        charge_count = 0
        hard_fail = False
        pages = 0
        max_total = max(limit, limit * 3) if since_ts else limit
        while len(out) < max_total and pages < 8:
            pages += 1
            params = {
                "host_mid": mid,
                "timezone_offset": -480,
                "page": 1,
                "offset": offset,
                "features": "itemOpusStyle,listOnlyfans,opusBigCover,onlyfansVote,decorationCard",
            }
            if not offset:
                params.pop("offset")
            url = self._signed(f"{API}/x/polymer/web-dynamic/v1/feed/space", params)
            items = []
            d = {}
            for attempt in range(4):
                data = self._get_json(url, referer=f"https://space.bilibili.com/{mid}/dynamic")
                d = (data or {}).get("data") or {}
                items = d.get("items") or []
                if items:
                    break
                code = (data or {}).get("code")
                if code == -352 or data is None:
                    hard_fail = True
                    time.sleep(2.0 + attempt)
                else:
                    time.sleep(1.5)
            if not items:
                if hard_fail and stats is not None:
                    stats["error"] = "动态接口被风控拦截（-352），未取到动态"
                break
            for it in items:
                basic = it.get("basic") or {}
                pub_ts_it = int((((it.get("modules") or {}).get("module_author") or {}).get("pub_ts", 0) or 0))
                in_window = (not since_ts) or (pub_ts_it >= since_ts)
                if basic.get("is_only_fans") and in_window:
                    charge_count += 1
                post = self._dynamic_item(it, mid)
                if post:
                    if since_ts and int(post.get("ts", 0) or 0) < since_ts:
                        continue
                    out.append(post)
                if len(out) >= max_total:
                    break
            offset = d.get("offset", "")
            if not d.get("has_more") or not offset:
                break
            time.sleep(1.0)
        if stats is not None:
            stats["ok"] = bool(out) or not hard_fail
            stats["charge_count"] = charge_count
        return out

    @staticmethod
    def _dynamic_item(it: Dict[str, Any], mid: int) -> Optional[Dict[str, Any]]:
        mods = it.get("modules", {}) or {}
        author = (mods.get("module_author") or {})
        desc = (mods.get("module_desc") or {}).get("text", "") or ""
        if not desc:
            # module_dynamic.desc 是富文本节点列表时的兜底
            rich = (mods.get("module_dynamic") or {}).get("desc") or []
            if isinstance(rich, list):
                desc = "".join((x or {}).get("text", "") for x in rich)
        dyn = (mods.get("module_dynamic") or {})
        major = dyn.get("major") or {}
        mtype = major.get("type", "")
        basic = it.get("basic") or {}
        is_only_fans = bool(basic.get("is_only_fans"))
        title = ""
        archive_url = ""
        imgs: List[str] = []
        if mtype == "MAJOR_TYPE_ARCHIVE":
            arc = major.get("archive") or {}
            title = clean_text(arc.get("title", ""), 120)
            if not desc:
                desc = f"投稿了视频《{title}》"
            bvid = arc.get("bvid", "")
            if bvid:
                archive_url = f"https://www.bilibili.com/video/{bvid}"
            cover = arc.get("cover", "")
            if cover:
                imgs.append(cover)
        elif mtype == "MAJOR_TYPE_DRAW":
            draw_items = (major.get("draw") or {}).get("items", []) or []
            for x in draw_items:
                src = x.get("src", "")
                if src:
                    imgs.append(src)
            if not desc:
                desc = f"发布了一条图文动态（{len(draw_items)} 张图片）"
        elif mtype == "MAJOR_TYPE_OPUS":
            summary = ((major.get("opus") or {}).get("summary") or {}).get("text", "") or ""
            if summary and not desc:
                desc = summary
        elif mtype == "MAJOR_TYPE_BLOCKED" or is_only_fans:
            if not desc:
                desc = "充电专属动态（仅充电用户可见）"
        text = clean_text(desc, 300)
        if not text and not title and not imgs:
            return None
        pub_ts = int(author.get("pub_ts", 0) or 0)
        stat = mods.get("module_stat") or {}
        id_str = str(it.get("id_str", ""))
        return {
            "source": "bilibili",
            "source_label": "B站",
            "kind": "up_dynamic",
            "title": clean_text(title or text[:50], 120) or ("图文动态" if imgs else "动态"),
            "content": text or title or "（图文动态）",
            "author": author.get("name", ""),
            "url": f"https://t.bilibili.com/{id_str}" if id_str else "",
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(pub_ts)) if pub_ts else "",
            "ts": pub_ts,
            "likes": int(((stat.get("like") or {}).get("count") or 0)),
            "comments": int(((stat.get("comment") or {}).get("count") or 0)),
            "views": int(((stat.get("forward") or {}).get("count") or 0)),
            "extra": {
                "mid": mid,
                "dyn_type": it.get("type", ""),
                "dyn_id": id_str,
                "is_only_fans": is_only_fans,
                "charge_exclusive": is_only_fans or mtype == "MAJOR_TYPE_BLOCKED",
                "archive_url": archive_url,
                "imgs": imgs[:4],
            },
        }

    def charging_rank(self, mid: int, limit: int = 10) -> Optional[Dict[str, Any]]:
        """up主本月充电榜：充电人次 + 榜单位（实时月榜，不存在历史混入问题）。"""
        if not mid or not self._ensure():
            return None
        data = self._get_json(
            f"{API}/x/ugcpay-rank/elec/month/up?up_mid={mid}",
            referer=f"https://space.bilibili.com/{mid}/dynamic",
        )
        d = (data or {}).get("data") or {}
        if not d:
            return None
        return {
            "total": int(d.get("total_count") or d.get("total") or 0),
            "count": int(d.get("count") or 0),
            "top": [
                {
                    "uname": x.get("uname", ""),
                    "rank": int(x.get("rank", 0) or 0),
                    "message": clean_text(x.get("message", ""), 60),
                }
                for x in (d.get("list") or [])[:limit]
                if x.get("uname")
            ],
            "available": True,
        }

    def up_videos(self, name: str, mid: int, limit: int = 4) -> List[Dict[str, Any]]:
        """优先空间接口，失败回退到搜索接口（按作者过滤），均带节流。"""
        videos: List[Dict[str, Any]] = []
        if mid:
            videos = self.space_videos(mid, limit)
            time.sleep(1.2)
        if not videos and name:
            log.info("up主 %s 空间接口不可用，改用搜索发现视频", name)
            found = self.search_videos(name, 10)
            # B站昵称可能带前缀/后缀（如“硬核的半佛仙人”），用子串匹配并优先精确匹配
            exact = [v for v in found if v.get("author") == name]
            fuzzy = [v for v in found if v.get("author") != name and name in (v.get("author") or "")]
            videos = (exact + fuzzy)[:limit]
            time.sleep(1.2)
        return videos

    def video_info(self, bvid: str) -> Optional[Dict[str, Any]]:
        if not bvid:
            return None
        if not self._ensure():
            return None
        return self._get_json(f"{API}/x/web-interface/view?bvid={bvid}")

    def comments(self, aid: int, limit: int = 20) -> List[Dict[str, Any]]:
        if not aid or not self._ensure():
            return []
        data = self._get_json(f"{API}/x/v2/reply/main?type=1&oid={aid}&mode=3&ps={min(limit, 20)}")
        out = []
        for r in (data or {}).get("data", {}).get("replies") or []:
            content = clean_text((r.get("content") or {}).get("message", ""), 300)
            if not content:
                continue
            out.append({
                "source": "bilibili",
                "source_label": "B站",
                "kind": "comment",
                "title": content[:60],
                "content": content,
                "author": (r.get("member") or {}).get("uname", ""),
                "url": "",
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r.get("ctime", 0))),
                "ts": int(r.get("ctime", 0)),
                "likes": int(r.get("like", 0)),
                "comments": 0,
                "views": 0,
            })
        return out

    @staticmethod
    def _video_item(it: Dict[str, Any], kind: str, keyword: str = "") -> Dict[str, Any]:
        bvid = it.get("bvid", "")
        title = clean_text(it.get("title", ""), 120)
        desc = clean_text(it.get("desc", ""), 300)
        pub = int(it.get("pubdate", 0) or 0)
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(pub)) if pub else ""
        return {
            "source": "bilibili",
            "source_label": "B站",
            "kind": kind,
            "title": title,
            "content": desc or title,
            "author": it.get("author", ""),
            "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            "time": time_str,
            "ts": pub,
            "likes": 0,
            "comments": int(it.get("video_review", 0) or 0),
            "views": int(it.get("play", 0) or 0),
            "extra": {"bvid": bvid, "mid": it.get("mid", 0), "keyword": keyword},
        }

    # ---------- 聚合 ----------

    def collect(
        self,
        since_ts: Optional[int] = None,
        seen: Optional[Dict[str, Dict[str, List[str]]]] = None,
    ) -> Dict[str, Any]:
        """采集 B站当日内容。

        since_ts: 统计窗口起点（时间戳），up主视频/动态只保留窗口内内容。
        seen:     增量去重状态 {mid: {"dynamics": [id], "videos": [bvid]}}，
                  loop 盘中模式传入，避免同一内容被重复上报。
        """
        b = self.cfg
        posts: List[Dict[str, Any]] = []
        items: Dict[str, Any] = {}
        errors: List[str] = []
        seen = seen or {}

        if not self._ensure():
            return {"status": "error", "error": "B站会话初始化失败（风控）", "posts": [], "items": {}}

        try:
            items["hot_search"] = self.hot_search(b.get("hot_search_limit", 20))
            posts += items["hot_search"]
        except Exception as e:  # noqa: BLE001
            errors.append(f"热搜: {e}")

        try:
            items["ranking"] = self.ranking(b.get("ranking_limit", 30))
            posts += items["ranking"]
        except Exception as e:  # noqa: BLE001
            errors.append(f"排行: {e}")

        try:
            search_items: List[Dict[str, Any]] = []
            for kw in b.get("search_keywords", []):
                search_items += self.search_videos(kw, b.get("search_limit", 6))
            items["search"] = search_items
            posts += search_items
        except Exception as e:  # noqa: BLE001
            errors.append(f"搜索: {e}")

        try:
            up_data = []
            interval = float(b.get("request_interval", 1.2))
            video_limit = int(b.get("up_video_limit", 3))
            dynamic_limit = int(b.get("up_dynamic_limit", 8))
            charging_limit = int(b.get("charging_limit", 10))
            global_cookie = str(b.get("cookie", "") or "")
            # 档案库注册表允许为单个 up主 配置独立 cookie（动态/评论稳定采集用）
            registry_cookies: Dict[str, str] = {}
            try:
                from .upmaster_lib import load_registry
                for mid_s, entry in load_registry().get("upmasters", {}).items():
                    ck = str(entry.get("cookie", "") or "").strip()
                    if ck:
                        registry_cookies[str(mid_s)] = ck
            except Exception:  # noqa: BLE001
                registry_cookies = {}
            def _collect_one(up: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                """采集单个 up主（视频+评论+动态+充电）；失败由调用方隔离。"""
                nonlocal posts
                mid = up.get("mid")
                name = up.get("name", "")
                if not mid:
                    return None
                up_cookie = str(up.get("cookie", "") or "").strip() or registry_cookies.get(str(mid), "")
                client = self
                if up_cookie and up_cookie != global_cookie:
                    client = BilibiliClient({**b, "cookie": up_cookie})
                card = client.user_card(mid) if mid else None
                time.sleep(0.8)
                videos = client.up_videos(name, mid, video_limit)
                if since_ts:
                    before = len(videos)
                    videos = [v for v in videos if int(v.get("ts", 0) or 0) >= since_ts]
                    if before > len(videos):
                        log.info("up主 %s 窗口过滤视频: %d -> %d", name, before, len(videos))
                seen_mid = seen.get(str(mid), {})
                seen_vids = set(seen_mid.get("videos", []) or [])
                videos = [v for v in videos if (v.get("extra", {}) or {}).get("bvid", "") not in seen_vids]
                enriched = []
                for v in videos:
                    bvid = v.get("extra", {}).get("bvid", "")
                    info = None
                    for attempt in range(2):
                        try:
                            info = client.video_info(bvid)
                            if info and info.get("data"):
                                break
                            time.sleep(1.5)
                        except Exception:  # noqa: BLE001
                            time.sleep(1.5)
                    time.sleep(interval)
                    if not info or not info.get("data"):
                        log.warning("视频详情获取失败，跳过: %s", bvid)
                        continue
                    aid = ((info or {}).get("data") or {}).get("aid", 0)
                    comments: List[Dict[str, Any]] = []
                    for attempt in range(2):
                        comments = client.comments(aid, b.get("comment_limit_per_video", 20))
                        if comments or attempt == 2:
                            break
                        time.sleep(1.5)
                    for c in comments:
                        c.setdefault("extra", {})["bvid"] = bvid
                    time.sleep(interval)
                    v["comments_list"] = comments
                    v["comments"] = len(comments) or int((info.get("data") or {}).get("stat", {}).get("reply", 0) or 0)
                    v["extra"]["aid"] = aid
                    v["extra"]["stat"] = ((info or {}).get("data") or {}).get("stat", {})
                    enriched.append(v)
                    posts.append(v)
                    posts += comments
                dyn_posts: List[Dict[str, Any]] = []
                dyn_stats: Dict[str, Any] = {"ok": True, "error": "", "charge_count": 0}
                if mid:
                    try:
                        # up主 卡片展示“近 N 条动态（不限当天，含充电）”；全局舆论统计只纳入当天窗口
                        dyn_posts = client.dynamics(mid, dynamic_limit, since_ts=None, stats=dyn_stats)
                        seen_dyns = set(seen_mid.get("dynamics", []) or [])
                        dyn_posts = [
                            d for d in dyn_posts
                            if (d.get("extra", {}) or {}).get("dyn_id", "") not in seen_dyns
                        ]
                        if since_ts:
                            posts += [
                                d for d in dyn_posts
                                if int(d.get("ts", 0) or 0) >= since_ts
                            ]
                        else:
                            posts += dyn_posts
                    except Exception as e:  # noqa: BLE001
                        log.warning("up主 %s 动态采集失败: %s", name, e)
                        dyn_stats["ok"] = False
                        dyn_stats["error"] = str(e)
                    time.sleep(interval)
                charging = None
                if mid:
                    try:
                        charging = client.charging_rank(mid, charging_limit)
                    except Exception as e:  # noqa: BLE001
                        log.warning("up主 %s 充电榜采集失败: %s", name, e)
                    time.sleep(interval)
                return {
                    "name": name or f"mid:{mid}",
                    "mid": mid,
                    "uid": up.get("uid") or mid,
                    "cookie": up.get("cookie", ""),
                    "cookie_configured": bool(up_cookie),
                    "url": up.get("url", "") or (f"https://space.bilibili.com/{mid}" if mid else ""),
                    "avatar": (card or {}).get("avatar", "") or up.get("avatar", ""),
                    "sign": (card or {}).get("sign", ""),
                    "fans": (card or {}).get("fans", 0),
                    "tags": up.get("tags", []),
                    "notes": up.get("notes", ""),
                    "enabled": up.get("enabled", True),
                    "keywords": up.get("keywords", []),
                    "videos": enriched,
                    "dynamics": dyn_posts,
                    "charging": charging,
                    "dynamics_ok": dyn_stats.get("ok", True),
                    "dynamics_error": dyn_stats.get("error", ""),
                    "charge_dyn_count": int(dyn_stats.get("charge_count", 0) or 0),
                }

            for up in b.get("upmasters", []):
                try:
                    entry = _collect_one(up)
                    if entry:
                        up_data.append(entry)
                except Exception as e:  # noqa: BLE001
                    log.warning("up主 %s 采集失败，跳过: %s", up.get("name", ""), e)
                    errors.append(f"up主 {up.get('name', '')}: {e}")
            items["upmasters"] = up_data
        except Exception as e:  # noqa: BLE001
            errors.append(f"up主: {e}")

        status = "error" if (not posts and errors) else ("partial" if errors else "ok")
        return {"status": status, "error": "；".join(errors), "posts": posts, "items": items}
