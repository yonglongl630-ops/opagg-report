"""生成站点首页 index.html：最新日报 + 历史日报归档列表（供 GitHub Pages 展示）。"""

from __future__ import annotations

import argparse
import html as html_mod
import os
import re
from datetime import datetime
from typing import List


def esc(v) -> str:
    return html_mod.escape(str(v if v is not None else ""), quote=True)


def _scan(dir_path: str) -> List[dict]:
    files = os.listdir(dir_path) if os.path.isdir(dir_path) else []
    daily = []
    for f in files:
        m = re.match(r"report_(\d{4}-\d{2}-\d{2})\.html$", f)
        if not m:
            continue
        daily.append({"date": m.group(1), "file": f})
    daily.sort(key=lambda x: x["date"], reverse=True)
    return daily


def build_site(dir_path: str) -> str:
    daily = _scan(dir_path)
    latest_daily = daily[0] if daily else None

    def card(item: dict) -> str:
        return (
            f'<a class="latest" href="{esc(item["file"])}">'
            f'<b>日报</b><span>{esc(item["date"])}</span></a>'
        )

    latest_html = card(latest_daily) if latest_daily else ""
    if not latest_html:
        latest_html = '<div class="muted">暂无报告，等待首次生成</div>'

    def group(title: str, items: List[dict]) -> str:
        if not items:
            return ""
        rows = "".join(
            f'<li><a href="{esc(it["file"])}">{esc(it["date"])}</a></li>'
            for it in items
        )
        return f'<div class="sec-title">{esc(title)}</div><ul class="arch">{rows}</ul>'

    # 最新日报全文内嵌：首页打开即可直接看到各平台数据（雪球/金十/同花顺等）
    report_frame = ""
    if latest_daily:
        report_frame = (
            f'<div class="sec-title">最新日报（{esc(latest_daily["date"])}）</div>'
            f'<iframe class="report-frame" src="{esc(latest_daily["file"])}" loading="lazy" '
            'onload="try{this.style.height=(this.contentWindow.document.body.scrollHeight+80)+\'px\';}catch(e){}"></iframe>'
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>舆论蒸馏日报</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f6f8; color: #24292f; line-height: 1.55; }}
  .wrap {{ max-width: 860px; margin: 0 auto; padding: 32px 20px 60px; }}
  h1 {{ font-size: 26px; }}
  .sub {{ color: #6a737d; font-size: 13px; margin: 4px 0 20px; }}
  .latest-row {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }}
  .latest {{ display: inline-flex; flex-direction: column; gap: 4px; background: #fff; border: 1px solid #d8dee4; border-radius: 12px; padding: 14px 20px; text-decoration: none; color: #24292f; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
  .latest b {{ color: #0969da; font-size: 14px; }}
  .latest span {{ font-size: 13px; color: #57606a; }}
  .card {{ background: #fff; border-radius: 12px; padding: 18px 20px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
  .sec-title {{ font-size: 15px; font-weight: 700; margin: 18px 0 8px; }}
  .report-frame {{ width: 100%; height: 3200px; border: 1px solid #d8dee4; border-radius: 12px; background: #fff; }}
  ul.arch {{ list-style: none; }}
  ul.arch li {{ padding: 6px 0; border-bottom: 1px dashed #eaecef; }}
  ul.arch li:last-child {{ border-bottom: 0; }}
  ul.arch a {{ color: #0969da; text-decoration: none; font-size: 14px; }}
  .muted {{ color: #8b949e; }}
  footer {{ color: #8b949e; font-size: 12px; margin-top: 30px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>舆论蒸馏日报</h1>
  <div class="sub">B站博主 · 股吧 · 雪球 · 同花顺 · 板块 · 金十 · 财联社 | 生成于 {esc(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}</div>
  <div class="latest-row">{latest_html}</div>
  {report_frame}
  <footer>仅供研究参考，不构成投资建议 · 数据来自公开接口</footer>
</div>
</body>
</html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="生成站点首页 index.html")
    ap.add_argument("--dir", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"))
    args = ap.parse_args()
    os.makedirs(args.dir, exist_ok=True)
    with open(os.path.join(args.dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_site(args.dir))
    print(f"站点首页已生成: {os.path.join(args.dir, 'index.html')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
