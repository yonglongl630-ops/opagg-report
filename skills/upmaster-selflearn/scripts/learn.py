#!/usr/bin/env python3
"""一键：归档 up主素材 + 生成风格画像。

用法: python3 learn.py --mid 320382958 [--videos 15] [--dynamics 30]
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.upmaster_lib import archive_materials, build_style_profile, load_registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mid", required=True)
    ap.add_argument("--videos", type=int, default=15)
    ap.add_argument("--dynamics", type=int, default=30)
    args = ap.parse_args()
    reg = load_registry()["upmasters"]
    entry = reg.get(str(args.mid), {})
    stats = archive_materials(
        args.mid,
        video_limit=args.videos,
        dynamic_limit=args.dynamics,
        cookie=entry.get("cookie", ""),
    )
    print("归档:", stats)
    profile = build_style_profile(args.mid)
    if profile:
        print("画像:", profile.get("stance"), profile.get("stance_score"), profile.get("keywords"))
        return 0
    print("画像生成失败（无素材）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
