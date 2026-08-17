"""配置加载：config.json + 内置默认值。"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")
FALLBACK_CONFIG_PATH = os.path.join(ROOT, "config.workflow.json")

DEFAULTS: Dict[str, Any] = {
    "watchlist": [{"code": "600519", "name": "贵州茅台"}],
    "bilibili": {
        "enabled": True,
        "cookie": "",
        "hot_search_limit": 20,
        "ranking_limit": 30,
        "search_keywords": ["A股", "股市"],
        "search_limit": 6,
        "comment_limit_per_video": 20,
        "up_video_limit": 3,
        "up_dynamic_limit": 8,
        "charging_limit": 10,
        "time_window": {"mode": "today", "hours": 24},
        "incremental_updates": False,
        "upmasters": [],
    },
    "guba": {"enabled": True, "post_limit_per_stock": 40, "hot_topic_limit": 5},
    "xueqiu": {"enabled": True, "hot_limit": 30, "cookie": ""},
    "ths": {"enabled": True, "feed_limit": 40},
    "sector": {"enabled": False, "industry_limit": 8, "concept_limit": 6},
    "jin10": {"enabled": True, "limit": 30},
    "cls": {"enabled": True, "limit": 30},
    "em": {"enabled": True, "hot_limit": 10},
    "scheduler": {
        "daily_enabled": False,   # 停止每日自动采集（用日报页「立即刷新」手动更新）
        "weekly_enabled": True,   # 保留周日周报
    },
    "distill": {
        "top_keywords": 24,
        "top_memes": 16,
        "min_meme_freq": 2,
        "top_posts_per_source": 10,
        "top_comments_per_video": 8,
        "top_per_source": 8,
        "exclude_authors_from_topics": [],
    },
}


def deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | None = None) -> Dict[str, Any]:
    """读取配置：优先 config.json（本地，含敏感 cookie，已 gitignore），
    缺失时回退 config.workflow.json（仓库内脱敏配置，供 GitHub Actions 使用）。"""
    p = path or (CONFIG_PATH if os.path.exists(CONFIG_PATH) else FALLBACK_CONFIG_PATH)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            user_cfg = json.load(f)
        return deep_merge(DEFAULTS, user_cfg)
    return json.loads(json.dumps(DEFAULTS))


def stock_name_map(cfg: Dict[str, Any]) -> Dict[str, str]:
    out = {}
    for s in cfg.get("watchlist", []):
        code = str(s.get("code", "")).strip()
        name = str(s.get("name", "")).strip()
        if code:
            out[code] = name
        if name:
            out[name] = code
    return out
