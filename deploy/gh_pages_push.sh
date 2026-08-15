#!/bin/bash
# 把本地最新日报/周报发布到 GitHub Pages（gh-pages 分支）
# 用法: bash deploy/gh_pages_push.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ORIGIN="$(git remote get-url origin)"
if [ -z "$ORIGIN" ]; then
  echo "未配置 git remote origin，请先: git remote add origin https://github.com/<用户名>/opagg-report.git"
  exit 1
fi

# 1) 确保首页最新
python3 src/site.py --dir output

# 2) 打包数据存档（周报/缓存用）
mkdir -p output
tar -czf output/data.tar.gz -C . data/raw data/summary data/trading_calendar.json 2>/dev/null || true

# 3) 同步到 gh-pages 分支
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
if ! git clone --depth 1 --branch gh-pages "$ORIGIN" "$WORK" 2>/dev/null; then
  git init -b gh-pages "$WORK" >/dev/null 2>&1
fi
cd "$WORK"
find . -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
cp -R "$ROOT/output/." .
git add -A
git -c user.name="opagg-bot" -c user.email="opagg-bot@users.noreply.github.com" \
  commit -m "日报/周报更新 $(date '+%Y-%m-%d %H:%M')" --allow-empty >/dev/null
git push origin gh-pages 2>&1 | tail -3
echo "已发布: $ORIGIN (gh-pages)"
