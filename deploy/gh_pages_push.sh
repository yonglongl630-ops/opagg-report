#!/bin/bash
# 把本地最新日报发布到 GitHub Pages（gh-pages 分支）
# 用法: bash deploy/gh_pages_push.sh
set -euo pipefail

# 本机到 GitHub 的链路偶发 TLS 挂起：给 git 加低速/连接超时，避免无限等待
GIT_TIMEOUT_CFG="-c http.lowSpeedLimit=1000 -c http.lowSpeedTime=20 -c http.connectTimeout=15"

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

# 2) 打包数据存档（缓存用，含 up主 素材与状态）
#    注意：GitHub API 大 body 上传会被掐断（>~5MB 时 401），因此只打包最近数据：
#    raw 保留 3 天、summary 保留 7 天（周报需要一周摘要）
mkdir -p output
TAR_TMP="$(mktemp -d)"
trap 'rm -rf "$TAR_TMP"' EXIT
mkdir -p "$TAR_TMP/data"
# -p 保留原始 mtime，才能按日期裁剪旧文件
cp -Rp data/raw data/summary data/upmasters data/state data/trading_calendar.json "$TAR_TMP/data/" 2>/dev/null || true
find "$TAR_TMP/data/raw" -name '*.json' -mtime +2 -delete 2>/dev/null || true
find "$TAR_TMP/data/summary" -name '*.json' -mtime +6 -delete 2>/dev/null || true
tar -czf output/data.tar.gz -C "$TAR_TMP" \
  --exclude='data/upmasters/*.xlsx' data 2>/dev/null || true
echo "data.tar.gz 大小: $(du -h output/data.tar.gz | cut -f1)"

# 3) 首选：Git Data API 直接同步（curl 稳定，绕开本机 git TLS 不稳定的问题）
if python3 deploy/gh_pages_api_push.py; then
  echo "已发布（API）: $ORIGIN (gh-pages)"
  if [ -n "$GITEE_URL" ]; then
    echo "检测到 Gitee 远程，开始镜像推送…"
    git $GIT_TIMEOUT_CFG push "$GITEE_URL" gh-pages:gh-pages 2>&1 | tail -2 \
      && echo "已镜像到 Gitee: $GITEE_URL (gh-pages)" \
      || echo "Gitee 镜像推送失败（可稍后手动重试）"
  fi
  exit 0
fi
echo "API 发布失败，回退 git 推送…"

# 4) 回退：同步到 gh-pages 分支（git，网络通畅时也可用）
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
CLONE_OK=0
for i in 1 2 3; do
  if git $GIT_TIMEOUT_CFG clone --depth 1 --branch gh-pages "$ORIGIN" "$WORK" >/dev/null 2>&1; then
    CLONE_OK=1
    break
  fi
  sleep $((i * 5))
done
if [ "$CLONE_OK" != "1" ]; then
  # 远端已存在 gh-pages 时不能空仓库回退（会造成非快进被拒）；只有首次发布才允许 init
  if git $GIT_TIMEOUT_CFG ls-remote --heads "$ORIGIN" gh-pages 2>/dev/null | grep -q 'refs/heads/gh-pages'; then
    echo "clone gh-pages 失败（网络问题），请稍后重试 bash deploy/gh_pages_push.sh"
    exit 1
  fi
  git init -b gh-pages "$WORK" >/dev/null 2>&1
fi
cd "$WORK"
find . -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
cp -R "$ROOT/output/." .
git add -A
git -c user.name="opagg-bot" -c user.email="opagg-bot@users.noreply.github.com" \
  commit -m "日报更新 $(date '+%Y-%m-%d %H:%M')" --allow-empty >/dev/null

# 5) 推送（本机到 GitHub 偶发 TLS 抖动，最多重试 3 次）
PUSH_OK=0
for i in 1 2 3; do
  echo "推送 gh-pages（第 $i 次）..."
  # 远端若被并发更新（如云端 Actions 同时推送），先 fetch 并对齐远端，避免非快进被拒
  if git $GIT_TIMEOUT_CFG fetch origin gh-pages >/dev/null 2>&1; then
    git reset --soft origin/gh-pages >/dev/null 2>&1 || true
    git -c user.name="opagg-bot" -c user.email="opagg-bot@users.noreply.github.com" \
      commit -m "日报更新 $(date '+%Y-%m-%d %H:%M')" --allow-empty >/dev/null 2>&1 || true
  fi
  if git $GIT_TIMEOUT_CFG push origin gh-pages 2>&1 | tail -3; then
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

# 6) 可选：镜像到 Gitee 仓库（Gitee Pages 已停服，仅作代码备份/国内拉取源）
if [ -n "$GITEE_URL" ]; then
  echo "检测到 Gitee 远程，开始镜像推送…"
  for i in 1 2 3; do
    if git $GIT_TIMEOUT_CFG push "$GITEE_URL" gh-pages:gh-pages 2>&1 | tail -3; then
      echo "已镜像到 Gitee: $GITEE_URL (gh-pages)"
      break
    fi
    sleep $((i * 5))
  done
fi
