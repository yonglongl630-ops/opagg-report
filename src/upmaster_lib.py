"""up主档案库：注册表 + 素材归档 + 风格画像自学。

目录结构（data/upmasters/）：
  registry.json              全局注册表（uid/cookie/账号信息/头像/标签/备注）
  <mid>/
    avatar.<ext>             本地头像图片
    archive/
      videos.json            历史视频素材（标题/简介/播放/评论摘要）
      dynamics.json          历史动态素材
      comments.json          评论素材汇总
      corpus.json            蒸馏语料（按时间排序的全文本）
    learn/
      style_profile.json     自学风格画像（立场/关键词/口头禅/金句/标题模式）

用法：
  python3 -m src.upmaster_lib list
  python3 -m src.upmaster_lib add --name "小Lin说" --mid 1131770799 --tags 财经
  python3 -m src.upmaster_lib update --mid 320382958 --notes "..."
  python3 -m src.upmaster_lib refresh --mid 320382958 --videos 10 --dynamics 20
  python3 -m src.upmaster_lib profile --mid 320382958
  python3 -m src.upmaster_lib sync-config
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.request
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common import clean_text, load_json, log, save_json  # noqa: E402
from src.config import CONFIG_PATH, ROOT, load_config  # noqa: E402
from src.distill import GENERIC_MEME, _valid_gram, extract_keywords, ngrams, sentiment  # noqa: E402

UP_DIR = os.path.join(ROOT, "data", "upmasters")
REGISTRY_PATH = os.path.join(UP_DIR, "registry.json")


# ---------- 注册表 ----------

def load_registry() -> Dict[str, Any]:
    reg = load_json(REGISTRY_PATH) or {}
    reg.setdefault("updated_at", "")
    reg.setdefault("upmasters", {})
    return reg


def save_registry(reg: Dict[str, Any]) -> None:
    reg["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_json(REGISTRY_PATH, reg)


def _mid_key(mid: Any) -> str:
    return str(mid or "").strip()


def upsert_upmaster(entry: Dict[str, Any]) -> Dict[str, Any]:
    reg = load_registry()
    mid = _mid_key(entry.get("mid") or entry.get("uid"))
    if not mid:
        raise ValueError("mid/uid 不能为空")
    cur = reg["upmasters"].setdefault(mid, {})
    for k, v in entry.items():
        if v not in (None, ""):
            cur[k] = v
    cur.setdefault("name", entry.get("name", f"mid:{mid}"))
    cur.setdefault("url", f"https://space.bilibili.com/{mid}")
    cur.setdefault("tags", [])
    cur.setdefault("notes", "")
    cur.setdefault("enabled", True)
    save_registry(reg)
    return cur


def sync_registry_from_config() -> int:
    cfg = load_config()
    reg = load_registry()
    n = 0
    for up in cfg.get("bilibili", {}).get("upmasters", []):
        mid = _mid_key(up.get("mid") or up.get("uid"))
        if not mid:
            continue
        cur = reg["upmasters"].setdefault(mid, {})
        for k in ("name", "uid", "url", "avatar", "cookie", "tags", "notes", "enabled", "mid"):
            v = up.get(k)
            if v not in (None, ""):
                cur[k] = v
        cur.setdefault("enabled", True)
        n += 1
    save_registry(reg)
    return n


# ---------- 博主信息表（xlsx）同步 ----------

_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
XLSX_MASTER = os.path.join(UP_DIR, "B站博主信息管理系统.xlsx")


def _col_idx(letter: str) -> int:
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def _col_name(idx: int) -> str:
    s = ""
    idx += 1
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(ord("A") + r) + s
    return s


def read_xlsx_table(path: str) -> List[List[str]]:
    """只读 .xlsx 第一个工作表（标准库实现，支持共享字符串/内联字符串/数字）。"""
    with zipfile.ZipFile(path) as zf:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        sheet = wb.find("m:sheets/m:sheet", _NS)
        if sheet is None:
            return []
        rid = sheet.get(f'{{{_NS["r"]}}}id', "")
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        target = ""
        for rel in rels.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
            if rel.get("Id") == rid:
                target = rel.get("Target", "")
                break
        if not target:
            return []
        sst: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            ss = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss.findall("m:si", _NS):
                sst.append("".join(t.text or "" for t in si.iter(f'{{{_NS["m"]}}}t')))
        sheet_path = "xl/" + target.lstrip("/")
        root = ET.fromstring(zf.read(sheet_path))
    rows: List[List[str]] = []
    for row in root.iter(f'{{{_NS["m"]}}}row'):
        cells: Dict[str, str] = {}
        for c in row.findall("m:c", _NS):
            ref = c.get("r", "")
            letter = "".join(ch for ch in ref if ch.isalpha())
            if not letter:
                continue
            t = c.get("t", "")
            v = c.find("m:v", _NS)
            is_ = c.find("m:is", _NS)
            if t == "s" and v is not None and v.text is not None:
                val = sst[int(v.text)] if int(v.text) < len(sst) else ""
            elif t == "inlineStr" and is_ is not None:
                val = "".join(x.text or "" for x in is_.iter(f'{{{_NS["m"]}}}t'))
            elif v is not None:
                val = v.text or ""
            else:
                val = ""
            cells[letter] = val
        if cells:
            width = max(_col_idx(k) for k in cells) + 1
            rows.append([cells.get(_col_name(i), "") for i in range(width)])
    return rows


def sync_xlsx(path: str = XLSX_MASTER, replace: bool = True) -> int:
    """从博主信息表（xlsx）同步 upmaster 到 config.json 与注册表。

    表头约定：博主UID / 博主名称 / 博主主页 / 所属赛道 / 当前粉丝数 / 合作报价 / 最新视频动态 / 备注 / 录入人。
    replace=True 时以表格为唯一主源（保留原同 uid 的 cookie）；False 时仅合并新增。
    """
    rows = read_xlsx_table(path)
    if not rows:
        raise ValueError(f"无法读取 {path} 的工作表")
    header = [str(h).strip() for h in rows[0]]
    def col(*names: str) -> int:
        for n in names:
            for i, h in enumerate(header):
                if h == n:
                    return i
        return -1
    i_uid = col("博主UID", "UID", "uid")
    i_name = col("博主名称", "名称", "name")
    i_url = col("博主主页", "主页", "url")
    i_cat = col("所属赛道", "赛道", "分类")
    i_fans = col("当前粉丝数", "粉丝数", "粉丝")
    i_price = col("合作报价", "报价")
    i_latest = col("最新视频动态", "最新动态")
    i_note = col("备注")
    if i_uid < 0 or i_name < 0:
        raise ValueError("表格缺少 博主UID/博主名称 列")
    cfg = load_config()
    old = {str(u.get("mid") or u.get("uid")): u for u in cfg.get("bilibili", {}).get("upmasters", [])}
    new_list = []
    n = 0
    for r in rows[1:]:
        uid_s = str(r[i_uid]).strip()
        name = str(r[i_name]).strip()
        if not uid_s or not name or uid_s.lower() in ("nan", "none", ""):
            continue
        mid = int(float(uid_s)) if uid_s.replace(".", "", 1).isdigit() else uid_s
        mid_s = str(mid)
        url = str(r[i_url]).strip() if i_url >= 0 and i_url < len(r) else ""
        if not url and mid_s.isdigit():
            url = f"https://space.bilibili.com/{mid_s}"
        tags = []
        if i_cat >= 0 and i_cat < len(r) and str(r[i_cat]).strip():
            tags = [t.strip() for t in str(r[i_cat]).split("/") if t.strip()]
        fans = 0
        if i_fans >= 0 and i_fans < len(r):
            try:
                fans = int(float(str(r[i_fans]).replace(",", "")))
            except ValueError:
                fans = 0
        note_parts = []
        if i_note >= 0 and i_note < len(r) and str(r[i_note]).strip():
            note_parts.append(str(r[i_note]).strip())
        latest = str(r[i_latest]).strip() if i_latest >= 0 and i_latest < len(r) else ""
        price = str(r[i_price]).strip() if i_price >= 0 and i_price < len(r) else ""
        entry = {
            "name": name,
            "mid": mid,
            "uid": mid,
            "url": url,
            "tags": tags,
            "notes": "；".join(note_parts),
            "enabled": True,
        }
        if latest:
            entry["latest_video"] = latest
        if price:
            entry["cooperation_price"] = price
        old_entry = old.get(mid_s, {})
        if old_entry.get("cookie"):
            entry["cookie"] = old_entry["cookie"]
        new_list.append(entry)
        # 写入注册表
        reg_entry = {
            "mid": mid,
            "uid": mid,
            "name": name,
            "url": url,
            "tags": tags,
            "notes": entry["notes"],
            "fans": fans,
            "enabled": True,
        }
        if latest:
            reg_entry["latest_video"] = latest
        if price:
            reg_entry["cooperation_price"] = price
        upsert_upmaster(reg_entry)
        n += 1
    cfg["bilibili"]["upmasters"] = new_list if replace else old + new_list
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    return n


# ---------- 头像 ----------

def download_avatar(mid: Any, remote: str) -> Optional[str]:
    if not remote:
        return None
    folder = os.path.join(UP_DIR, _mid_key(mid))
    os.makedirs(folder, exist_ok=True)
    ext = os.path.splitext(urllib.parse.urlparse(remote).path)[1] or ".jpg"
    if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg"
    dest = os.path.join(folder, f"avatar{ext}")
    try:
        req = urllib.request.Request(remote, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            with open(dest + ".tmp", "wb") as f:
                shutil.copyfileobj(resp, f)
        os.replace(dest + ".tmp", dest)
        return os.path.relpath(dest, ROOT)
    except Exception as e:  # noqa: BLE001
        log.warning("头像下载失败 %s: %s", remote, e)
        return None
# ---------- 素材归档 ----------

def archive_materials(
    mid: Any,
    *,
    video_limit: int = 10,
    dynamic_limit: int = 20,
    comment_limit: int = 20,
    cookie: str = "",
) -> Dict[str, Any]:
    from src.bilibili import BilibiliClient

    cfg = load_config()
    bcfg = dict(cfg.get("bilibili", {}))
    if cookie:
        bcfg["cookie"] = cookie
    bcfg["up_video_limit"] = video_limit
    bcfg["up_dynamic_limit"] = dynamic_limit
    bcfg["comment_limit_per_video"] = comment_limit
    client = BilibiliClient(bcfg)

    mid_s = _mid_key(mid)
    folder = os.path.join(UP_DIR, mid_s)
    arch_dir = os.path.join(folder, "archive")
    os.makedirs(arch_dir, exist_ok=True)

    card = client.user_card(int(mid_s))
    videos = client.up_videos(card.get("name", "") if card else "", int(mid_s), video_limit)
    enriched: List[Dict[str, Any]] = []
    comments_all: List[Dict[str, Any]] = []
    for v in videos:
        bvid = v.get("extra", {}).get("bvid", "")
        info = None
        for _ in range(2):
            info = client.video_info(bvid) if bvid else None
            if info and info.get("data"):
                break
            time.sleep(1.5)
        time.sleep(1.0)
        aid = ((info or {}).get("data") or {}).get("aid", 0)
        cs = client.comments(aid, comment_limit) if aid else []
        time.sleep(1.0)
        comments_all += cs
        enriched.append({
            "bvid": bvid,
            "title": v.get("title", ""),
            "desc": v.get("content", ""),
            "pubdate": v.get("time", ""),
            "ts": v.get("ts", 0),
            "views": v.get("views", 0),
            "comments_count": len(cs) or v.get("comments", 0),
            "url": v.get("url", ""),
            "top_comments": [
                {"content": c.get("content", ""), "likes": c.get("likes", 0), "author": c.get("author", "")}
                for c in sorted(cs, key=lambda x: x.get("likes", 0), reverse=True)[:8]
            ],
        })
    dynamics = client.dynamics(int(mid_s), dynamic_limit)

    videos_old = load_json(os.path.join(arch_dir, "videos.json")) or []
    videos_merged = _merge_unique(enriched, videos_old, "bvid")
    save_json(os.path.join(arch_dir, "videos.json"), videos_merged)

    dyn_old = load_json(os.path.join(arch_dir, "dynamics.json")) or []
    dyn_merged = _merge_unique(dynamics, dyn_old, "url")
    save_json(os.path.join(arch_dir, "dynamics.json"), dyn_merged)

    com_old = load_json(os.path.join(arch_dir, "comments.json")) or []
    com_merged = _merge_unique(comments_all, com_old, "url")
    save_json(os.path.join(arch_dir, "comments.json"), com_merged)

    corpus = _build_corpus(videos_merged, dyn_merged, com_merged)
    save_json(os.path.join(arch_dir, "corpus.json"), corpus)

    stats = {
        "videos": len(videos_merged),
        "dynamics": len(dyn_merged),
        "comments": len(com_merged),
        "corpus_entries": len(corpus),
    }
    reg = load_registry()
    entry = reg["upmasters"].setdefault(mid_s, {})
    entry.update({
        "name": (card or {}).get("name", entry.get("name", f"mid:{mid_s}")),
        "mid": int(mid_s),
        "uid": int(mid_s),
        "avatar_remote": (card or {}).get("avatar", entry.get("avatar_remote", "")),
        "sign": (card or {}).get("sign", entry.get("sign", "")),
        "fans": (card or {}).get("fans", entry.get("fans", 0)),
        "last_refresh": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stats": stats,
    })
    if card and card.get("avatar"):
        local = download_avatar(mid_s, card["avatar"])
        if local:
            entry["avatar_local"] = local
    save_registry(reg)
    return stats


def _merge_unique(new_items: List[Dict[str, Any]], old_items: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in old_items + new_items:
        k = it.get(key) or it.get("url") or it.get("bvid")
        if k and k in seen:
            continue
        if k:
            seen.add(k)
        out.append(it)
    return out


def _build_corpus(videos: List[Dict[str, Any]], dynamics: List[Dict[str, Any]], comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    corpus: List[Dict[str, Any]] = []
    for v in videos:
        corpus.append({
            "type": "video",
            "title": v.get("title", ""),
            "content": v.get("desc", ""),
            "time": v.get("pubdate", ""),
            "ts": v.get("ts", 0),
            "likes": 0,
            "url": v.get("url", ""),
        })
        for c in v.get("top_comments", []):
            corpus.append({
                "type": "comment",
                "title": "",
                "content": c.get("content", ""),
                "time": "",
                "ts": 0,
                "likes": c.get("likes", 0),
                "url": v.get("url", ""),
            })
    for d in dynamics:
        corpus.append({
            "type": "dynamic",
            "title": d.get("title", ""),
            "content": d.get("content", ""),
            "time": d.get("time", ""),
            "ts": d.get("ts", 0),
            "likes": d.get("likes", 0),
            "url": d.get("url", ""),
        })
    for c in comments:
        corpus.append({
            "type": "comment",
            "title": "",
            "content": c.get("content", ""),
            "time": c.get("time", ""),
            "ts": c.get("ts", 0),
            "likes": c.get("likes", 0),
            "url": c.get("url", ""),
        })
    corpus.sort(key=lambda x: x.get("ts", 0))
    return corpus


# ---------- 风格画像自学 ----------

def build_style_profile(mid: Any) -> Optional[Dict[str, Any]]:
    mid_s = _mid_key(mid)
    corpus = load_json(os.path.join(UP_DIR, mid_s, "archive", "corpus.json")) or []
    if not corpus:
        return None
    posts = [
        {"source": "corpus", "title": c.get("title", ""), "content": c.get("content", ""), "likes": c.get("likes", 0)}
        for c in corpus
    ]
    keywords = extract_keywords(posts, top_k=15)
    scores = [sentiment(c.get("content", ""))["score"] for c in corpus if c.get("content")]
    overall = round(sum(scores) / len(scores), 3) if scores else 0.0
    stance = "看多" if overall >= 0.15 else ("看空" if overall <= -0.15 else "中性")
    catch = _catchphrases(corpus, top_k=10)
    quotes = _top_quotes(corpus, top_k=10)
    patterns = _title_patterns(corpus, top_k=6)
    profile = {
        "upmaster": mid_s,
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "corpus_size": len(corpus),
        "stance": stance,
        "stance_score": overall,
        "keywords": [k["text"] for k in keywords[:10]],
        "catchphrases": catch,
        "top_quotes": quotes,
        "title_patterns": patterns,
    }
    learn_dir = os.path.join(UP_DIR, mid_s, "learn")
    os.makedirs(learn_dir, exist_ok=True)
    save_json(os.path.join(learn_dir, "style_profile.json"), profile)
    return profile


def _catchphrases(corpus: List[Dict[str, Any]], top_k: int = 10) -> List[str]:
    counter: Counter = Counter()
    for c in corpus:
        text = c.get("content", "") + c.get("title", "")
        for n in (3, 4, 5):
            for g in ngrams(text, n):
                if _valid_gram(g) and g not in GENERIC_MEME:
                    counter[g] += 1
    return [g for g, _ in counter.most_common(top_k)]


def _top_quotes(corpus: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, str]]:
    ranked = sorted(
        [c for c in corpus if c.get("content") and c.get("likes", 0) > 0],
        key=lambda c: c.get("likes", 0),
        reverse=True,
    )
    out = []
    for c in ranked[:top_k]:
        out.append({
            "text": clean_text(c.get("content", ""), 150),
            "likes": c.get("likes", 0),
            "type": c.get("type", ""),
        })
    return out


def _title_patterns(corpus: List[Dict[str, Any]], top_k: int = 6) -> List[Dict[str, Any]]:
    titles = [c.get("title", "") for c in corpus if c.get("type") == "video" and c.get("title")]
    starts: Counter = Counter()
    for t in titles:
        for n in (2, 4):
            if len(t) >= n:
                starts[t[:n]] += 1
    return [{"prefix": p, "count": c} for p, c in starts.most_common(top_k)]


# ---------- 展示 ----------

def print_upmaster(mid_s: str) -> None:
    reg = load_registry()
    entry = reg["upmasters"].get(mid_s)
    profile = load_json(os.path.join(UP_DIR, mid_s, "learn", "style_profile.json"))
    stats = entry.get("stats", {}) if entry else {}
    print(f"=== {entry.get('name', mid_s) if entry else mid_s} ===")
    print(f"mid/uid: {entry.get('mid', mid_s) if entry else mid_s}  url: {entry.get('url', '') if entry else ''}")
    print(f"粉丝: {entry.get('fans', 0) if entry else 0}  标签: {'、'.join(entry.get('tags', [])) if entry else ''}")
    print(f"素材: 视频{stats.get('videos', 0)} 动态{stats.get('dynamics', 0)} 评论{stats.get('comments', 0)}")
    print(f"最近刷新: {entry.get('last_refresh', '-') if entry else '-'}")
    if profile:
        print(f"风格: {profile['stance']} ({profile['stance_score']:+.2f})")
        print("关键词: " + "、".join(profile.get("keywords", [])))
        print("口头禅: " + "、".join(profile.get("catchphrases", [])))
        print("标题模式: " + " | ".join(p["prefix"] for p in profile.get("title_patterns", [])))
        for q in profile.get("top_quotes", [])[:3]:
            print(f"金句[{q['likes']}赞]: {q['text'][:80]}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="up主档案库管理")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出全部 up主")
    p_list.add_argument("--json", action="store_true")

    p_add = sub.add_parser("add", help="新增/更新 up主档案")
    for name in ("--name", "--mid", "--uid", "--url", "--avatar", "--cookie", "--tags", "--notes"):
        p_add.add_argument(name, default="")
    p_add.add_argument("--disable", action="store_true")

    p_upd = sub.add_parser("update", help="更新字段")
    p_upd.add_argument("--mid", required=True)
    for name in ("--name", "--url", "--avatar", "--cookie", "--tags", "--notes"):
        p_upd.add_argument(name, default="")
    p_upd.add_argument("--enable", dest="enabled", action="store_true")
    p_upd.add_argument("--disable", dest="disabled", action="store_true")

    p_ref = sub.add_parser("refresh", help="归档 up主素材")
    p_ref.add_argument("--mid", required=True)
    p_ref.add_argument("--videos", type=int, default=10)
    p_ref.add_argument("--dynamics", type=int, default=20)
    p_ref.add_argument("--comments", type=int, default=20)

    p_prof = sub.add_parser("profile", help="生成/展示风格画像")
    p_prof.add_argument("--mid", required=True)

    p_sync = sub.add_parser("sync-config", help="从 config.json 同步注册表")

    p_xlsx = sub.add_parser("sync-xlsx", help="从博主信息表(xlsx)同步 upmaster")
    p_xlsx.add_argument("--xlsx", default=XLSX_MASTER, help="博主信息表路径")
    p_xlsx.add_argument("--merge", action="store_true", help="追加合并而不是整体替换")

    args = ap.parse_args(argv)
    if args.cmd == "list":
        reg = load_registry()
        ups = reg.get("upmasters", {})
        if args.json:
            print(json.dumps(ups, ensure_ascii=False, indent=1))
            return 0
        for mid_s, e in ups.items():
            stats = e.get("stats", {})
            flag = "" if e.get("enabled", True) else " [停用]"
            print(f"{mid_s}\t{e.get('name', '')}\t粉丝{e.get('fans', 0)}\t"
                  f"视频{stats.get('videos', 0)} 动态{stats.get('dynamics', 0)}{flag}")
        return 0
    if args.cmd == "add":
        entry = {k: v for k, v in vars(args).items() if k not in ("cmd",) and v not in (None, "")}
        if args.disable:
            entry["enabled"] = False
        upsert_upmaster(entry)
        print("已写入注册表:", args.mid or args.uid or args.name)
        return 0
    if args.cmd == "update":
        entry = {k: v for k, v in vars(args).items() if k in ("name", "url", "avatar", "cookie", "tags", "notes") and v}
        if args.enabled:
            entry["enabled"] = True
        if args.disabled:
            entry["enabled"] = False
        upsert_upmaster({"mid": args.mid, **entry})
        print("已更新:", args.mid)
        return 0
    if args.cmd == "refresh":
        reg = load_registry()
        e = reg["upmasters"].get(str(args.mid), {})
        stats = archive_materials(
            args.mid,
            video_limit=args.videos,
            dynamic_limit=args.dynamics,
            comment_limit=args.comments,
            cookie=e.get("cookie", ""),
        )
        print("素材归档完成:", stats)
        profile = build_style_profile(args.mid)
        print("风格画像已生成:", bool(profile))
        return 0
    if args.cmd == "profile":
        profile = build_style_profile(args.mid)
        if not profile:
            print("暂无素材，请先 refresh")
            return 1
        print_upmaster(str(args.mid))
        return 0
    if args.cmd == "sync-config":
        n = sync_registry_from_config()
        print(f"已同步 {n} 个 up主")
        return 0
    if args.cmd == "sync-xlsx":
        n = sync_xlsx(args.xlsx, replace=not args.merge)
        print(f"已从表格同步 {n} 个博主到 config.json 与注册表")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
