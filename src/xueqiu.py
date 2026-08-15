"""雪球采集：登录 cookie（解阿里云 WAF）+ 热帖/热股接口。

雪球使用阿里云 WAF（acw_sc__v2 JS 挑战），匿名访问热帖接口会被拦截。
解法：把浏览器登录态下的完整 Cookie 字符串填入 config.json 的
xueqiu.cookie（含 acw_sc__v2、xq_a_token、u 等），客户端会在建会话时带上。

命令行：
  python3 -m src.xueqiu --set-cookie "acw_sc__v2=...; xq_a_token=...; u=..."   # 写入 config 并保存到 registry
  python3 -m src.xueqiu --test                                                # 验证当前 cookie 是否可用
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from typing import Any, Dict, List

from .common import UA_PC, clean_text, log
from .config import CONFIG_PATH, load_config

SECRETS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "secrets.json")


def _load_cookie(cfg: Dict[str, Any]) -> str:
    """优先取 config.json 的 cookie；其次环境变量 XUEQIU_COOKIE（GitHub Actions）；
    最后读 gitignore 的 data/secrets.json。"""
    env_cookie = (os.environ.get("XUEQIU_COOKIE") or "").strip()
    if env_cookie:
        return env_cookie
    cookie = str(cfg.get("cookie", "") or "").strip()
    if cookie:
        return cookie
    try:
        with open(SECRETS_PATH, encoding="utf-8") as f:
            secrets = json.load(f)
        return str(secrets.get("xueqiu_cookie", "") or "").strip()
    except (OSError, json.JSONDecodeError):
        return ""


class XueqiuClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        from .common import Session
        self.sess = Session(ua=UA_PC, retries=2)
        cookie = _load_cookie(cfg)
        if cookie:
            self.sess.set_cookie_str(str(cookie))

    def _ensure_session(self) -> bool:
        try:
            self.sess.get_text("https://xueqiu.com/", referer="https://xueqiu.com/")
            # cookie 在 init 时已设置；这里再确认一次（兼容配置后置写入）
            cookie = _load_cookie(self.cfg)
            if cookie:
                self.sess.set_cookie_str(cookie)
            return bool(self.sess.cookies)
        except Exception as e:  # noqa: BLE001
            log.warning("雪球会话初始化失败: %s", e)
            return False

    def validate_cookie(self) -> Dict[str, Any]:
        """验证当前 cookie 是否能通过 WAF 并取到热帖。"""
        ok_home = bool(self._ensure_session())
        posts = []
        stocks = []
        error = ""
        try:
            posts = self.hot_posts(3)
        except Exception as e:  # noqa: BLE001
            error = str(e)
        try:
            stocks = self.hot_stocks(3)
        except Exception as e:  # noqa: BLE001
            error = error or str(e)
        has_token = bool(self.sess.cookies.get("xq_a_token"))
        has_acw = bool(self.sess.cookies.get("acw_sc__v2"))
        return {
            "homepage_ok": ok_home,
            "has_xq_a_token": has_token,
            "hot_posts_ok": len(posts) > 0,
            "hot_stocks_ok": len(stocks) > 0,
            "has_acw_sc_v2": has_acw,
            "error": error or (
                "" if (posts or stocks) else
                "登录 cookie 已生效（xq_a_token 有值），热帖仍被 WAF 挑战拦截："
                "请在浏览器打开雪球后，从开发者工具 Application→Cookies→xueqiu.com "
                "复制 acw_sc__v2 的值，用 --set-cookie 一起更新"
            ),
        }

    def hot_posts(self, limit: int = 30) -> List[Dict[str, Any]]:
        if not self._ensure_session():
            return []
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": "https://xueqiu.com",
            "X-Requested-With": "XMLHttpRequest",
        }
        data = None
        for host in ("https://api.xueqiu.com", "https://xueqiu.com"):
            url = f"{host}/statuses/hot/listV2.json?since_id=-1&max_id=-1&size={limit}"
            data = self.sess.get_json(url, headers=headers, referer="https://xueqiu.com/")
            if data and data.get("items"):
                break
        items = (data or {}).get("items") or []
        out = []
        for it in items[:limit]:
            st = it.get("original_status") or it.get("data") or it
            user = st.get("user") or {}
            target = st.get("target") or ""
            if not target.startswith("http"):
                target = "https://xueqiu.com" + target
            title = clean_text(st.get("title") or st.get("rawTitle") or "", 120)
            text = clean_text(st.get("description") or st.get("text") or title, 400)
            if not title and not text:
                continue
            created = int(st.get("created_at", 0) or 0)
            if created > 10**12:
                created = created // 1000
            out.append({
                "source": "xueqiu",
                "source_label": "雪球",
                "kind": "hot_post",
                "title": title or text[:50],
                "content": text,
                "author": user.get("screen_name", ""),
                "url": target,
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created)) if created else "",
                "ts": created,
                "likes": int(st.get("like_count", 0) or 0),
                "comments": int(st.get("reply_count", 0) or 0),
                "views": int(st.get("view_count", 0) or 0),
                "extra": {
                    "status_id": st.get("id"),
                    "user_id": st.get("user_id"),
                    "fav_count": st.get("fav_count"),
                },
            })
        return out

    def hot_stocks(self, limit: int = 30) -> List[Dict[str, Any]]:
        if not self._ensure_session():
            return []
        url = f"https://stock.xueqiu.com/v5/stock/hot_stock/list.json?size={limit}&_type=10&type=10"
        data = self.sess.get_json(url, headers={"Accept": "application/json"}, referer="https://xueqiu.com/")
        items = (((data or {}).get("data") or {}).get("items")) or []
        out = []
        for it in items[:limit]:
            symbol = it.get("symbol", "") or it.get("code", "")
            name = it.get("name", "")
            heat = int(it.get("value", 0) or 0)
            out.append({
                "source": "xueqiu",
                "source_label": "雪球",
                "kind": "hot_stock",
                "title": name,
                "content": f"雪球热门股票：{name}（{symbol}）热度 {heat}",
                "author": "雪球热股",
                "url": f"https://xueqiu.com/S/{symbol}" if symbol else "",
                "time": "",
                "ts": 0,
                "likes": heat,
                "comments": 0,
                "views": heat,
                "extra": {
                    "code": it.get("code", ""),
                    "percent": it.get("percent"),
                    "current": it.get("current"),
                    "chg": it.get("chg"),
                    "increment": it.get("increment"),
                    "rank_change": it.get("rank_change"),
                },
            })
        return out

    def hot_topics(self, limit: int = 10) -> List[Dict[str, Any]]:
        """雪球官网右侧「热门话题」：https://xueqiu.com/hot_event/list.json（无需 token）。"""
        if not self._ensure_session():
            return []
        url = f"https://xueqiu.com/hot_event/list.json?count={limit}"
        data = self.sess.get_json(url, headers={"Accept": "application/json"}, referer="https://xueqiu.com/")
        items = (data or {}).get("list") or []
        out = []
        for it in items[:limit]:
            tag = clean_text(it.get("tag") or "", 80).strip("#").strip()
            if not tag:
                continue
            out.append({
                "source": "xueqiu",
                "source_label": "雪球",
                "kind": "hot_topic",
                "title": tag,
                "content": clean_text(it.get("content") or tag, 300),
                "author": "雪球热门话题",
                "url": f"https://xueqiu.com/search?q={urllib.parse.quote(tag)}",
                "time": "",
                "ts": 0,
                "likes": 0,
                "comments": 0,
                "views": int(it.get("status_count", 0) or 0),
                "extra": {
                    "event_id": it.get("id"),
                    "hot": it.get("hot"),
                    "status_count": it.get("status_count"),
                },
            })
        return out

    def collect(self) -> Dict[str, Any]:
        posts: List[Dict[str, Any]] = []
        errors: List[str] = []
        items: Dict[str, Any] = {}
        limit = self.cfg.get("hot_limit", 30)
        try:
            items["hot_posts"] = self.hot_posts(limit)
            posts += items["hot_posts"]
        except Exception as e:  # noqa: BLE001
            errors.append(f"热帖: {e}")
        try:
            items["hot_stocks"] = self.hot_stocks(limit)
            posts += items["hot_stocks"]
        except Exception as e:  # noqa: BLE001
            errors.append(f"热股: {e}")
        try:
            items["hot_topics"] = self.hot_topics(10)
            posts += items["hot_topics"]
        except Exception as e:  # noqa: BLE001
            errors.append(f"热门话题: {e}")
        if not posts:
            errors.append(
                "雪球接口仍被 WAF 拦截：登录 cookie 已生效但缺少 acw_sc__v2 "
                "（浏览器访问雪球后从 Application→Cookies 复制该值，再用 --set-cookie 更新）"
            )
        status = "error" if not posts else ("partial" if errors else "ok")
        return {"status": status, "error": "；".join(errors), "posts": posts, "items": items}


def save_cookie(raw: str, path: str = CONFIG_PATH) -> bool:
    """把雪球 cookie 写入 config.json 与 gitignore 的 data/secrets.json。"""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        cfg = load_config()
    cfg.setdefault("xueqiu", {})["cookie"] = raw.strip()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    os.makedirs(os.path.dirname(SECRETS_PATH), exist_ok=True)
    secrets = {}
    try:
        with open(SECRETS_PATH, encoding="utf-8") as f:
            secrets = json.load(f)
    except (OSError, json.JSONDecodeError):
        secrets = {}
    secrets["xueqiu_cookie"] = raw.strip()
    with open(SECRETS_PATH + ".tmp", "w", encoding="utf-8") as f:
        json.dump(secrets, f, ensure_ascii=False, indent=1)
    os.replace(SECRETS_PATH + ".tmp", SECRETS_PATH)
    return True


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="雪球 cookie 管理")
    ap.add_argument("--set-cookie", default="", help="完整 Cookie 字符串（含 acw_sc__v2/xq_a_token/u）")
    ap.add_argument("--test", action="store_true", help="验证当前配置的 cookie 是否可用")
    args = ap.parse_args(argv)
    if args.set_cookie:
        save_cookie(args.set_cookie)
        print("cookie 已写入 config.json → xueqiu.cookie")
    cfg = load_config()
    client = XueqiuClient(cfg.get("xueqiu", {}))
    if args.test or args.set_cookie:
        result = client.validate_cookie()
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0 if result.get("hot_posts_ok") else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
