#!/bin/bash
# 把本地最新日报发布到 GitHub Pages（gh-pages 分支）
# 用法: bash deploy/gh_pages_push.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ORIGIN="$(git remote get-url origin)"
if [ -z "$ORIGIN" ]; then
  echo "未配置 git remote origin，请先: git remote add origin https://github.com/<用户名>/opagg-report.git"
  exit 1
fi
GITEE_URL="$(git remote get-url gitee 2>/dev/null || true)"

# 1) 确保首页最新
python3 src/site.py --dir output

# 2) 打包数据存档（缓存用）
mkdir -p output
tar -czf output/data.tar.gz -C . data/raw data/summary data/trading_calendar.json 2>/dev/null || true

# 3) 同步到 gh-pages 分支
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
CLONE_OK=0
for i in 1 2 3; do
  if git clone --depth 1 --branch gh-pages "$ORIGIN" "$WORK" >/dev/null 2>&1; then
    CLONE_OK=1
    break
  fi
  sleep $((i * 5))
done
if [ "$CLONE_OK" != "1" ]; then
  git init -b gh-pages "$WORK" >/dev/null 2>&1
fi
cd "$WORK"
find . -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
cp -R "$ROOT/output/." .
git add -A
git -c user.name="opagg-bot" -c user.email="opagg-bot@users.noreply.github.com" \
  commit -m "日报更新 $(date '+%Y-%m-%d %H:%M')" --allow-empty >/dev/null

# 4) 推送（本机到 GitHub 偶发 TLS 抖动，最多重试 3 次）
PUSH_OK=0
for i in 1 2 3; do
  echo "推送 gh-pages（第 $i 次）..."
  if git push origin gh-pages 2>&1 | tail -3; then
    PUSH_OK=1
    break
  fi
  sleep $((i * 8))
done
if [ "$PUSH_OK" != "1" ]; then
  echo "推送失败（已重试 3 次），请稍后手动运行 bash deploy/gh_pages_push.sh"
  exit 1
fi
echo "已发布: $ORIGIN (gh-pages)"

# 5) 可选：镜像到 Gitee 仓库（Gitee Pages 已停服，仅作代码备份/国内拉取源）
if [ -n "$GITEE_URL" ]; then
  echo "检测到 Gitee 远程，开始镜像推送…"
  for i in 1 2 3; do
    if git push "$GITEE_URL" gh-pages:gh-pages 2>&1 | tail -3; then
      echo "已镜像到 Gitee: $GITEE_URL (gh-pages)"
      break
    fi
    sleep $((i * 5))
  done
fi
