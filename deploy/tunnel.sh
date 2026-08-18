#!/bin/bash
# 临时公网隧道：把本地「立即刷新」服务暴露到 trycloudflare 公网地址，
# 手机（任何网络）打开该地址即可同源刷新。无需注册账号。
# 用法: bash deploy/tunnel.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# 1) 确保本地刷新服务在跑（8651）
if ! curl -s --max-time 2 http://127.0.0.1:8651/api/status >/dev/null 2>&1; then
  echo "启动本地刷新服务…"
  nohup python3 -m src.serve --port 8651 > data/logs/serve_tunnel.log 2>&1 &
  sleep 2
fi

# 2) cloudflared
CLOUDFLARED="$(command -v cloudflared || true)"
if [ -z "$CLOUDFLARED" ] && [ -x /opt/homebrew/bin/cloudflared ]; then
  CLOUDFLARED=/opt/homebrew/bin/cloudflared
fi
if [ -z "$CLOUDFLARED" ]; then
  echo "未安装 cloudflared，请先安装："
  echo "  brew install cloudflared"
  echo "（或下载 https://github.com/cloudflare/cloudflared/releases 后放回 PATH）"
  exit 1
fi

# 3) 起隧道并打印公网地址
echo "隧道启动中，等待公网地址（保持此终端运行）…"
"$CLOUDFLARED" tunnel --url http://127.0.0.1:8651 --no-autoupdate
