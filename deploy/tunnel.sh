#!/bin/bash
# 临时公网隧道：把本地「立即刷新」服务暴露到 trycloudflare 公网地址，
# 手机（任何网络，无需同 WiFi）打开该地址即可同源刷新。无需注册账号、不依赖云端部署。
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

# 2) cloudflared（安装路径：~/bin 或 brew）
CLOUDFLARED="$(command -v cloudflared || true)"
for c in "$HOME/bin/cloudflared" /opt/homebrew/bin/cloudflared /usr/local/bin/cloudflared; do
  if [ -z "$CLOUDFLARED" ] && [ -x "$c" ]; then
    CLOUDFLARED="$c"
  fi
done
if [ -z "$CLOUDFLARED" ]; then
  echo "未安装 cloudflared，安装方法："
  echo "  curl -sL -o ~/bin/cloudflared.tgz https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz"
  echo "  mkdir -p ~/bin && tar -xzf ~/bin/cloudflared.tgz -C ~/bin && chmod +x ~/bin/cloudflared"
  exit 1
fi

# 3) 起隧道（写日志，便于抓取公网地址；URL 每次启动会变）
LOG="$ROOT/data/logs/tunnel.log"
echo "隧道启动中，等待公网地址（保持此终端运行）…"
"$CLOUDFLARED" tunnel --url http://127.0.0.1:8651 --no-autoupdate --logfile "$LOG" &
TUNNEL_PID=$!

# 4) 从日志里抓取 trycloudflare 地址并写入 data/tunnel_url.txt
URL=""
for i in $(seq 1 30); do
  sleep 2
  URL="$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | tail -1 || true)"
  if [ -n "$URL" ]; then
    break
  fi
  if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    echo "cloudflared 意外退出，请查看 $LOG"
    exit 1
  fi
done
if [ -n "$URL" ]; then
  mkdir -p "$ROOT/data"
  echo "$URL" > "$ROOT/data/tunnel_url.txt"
  echo ""
  echo "✅ 手机公网地址（任何网络可用）："
  echo "   $URL/report_$(date +%F).html"
  echo "   打开后点【立即刷新】即可实时更新（服务仍在本机 Mac 上执行）"
  echo "   本机可随时查看当前地址: $ROOT/data/tunnel_url.txt  或  局域网 http://<电脑IP>:8651/tunnel-url"
else
  echo "未能获取隧道地址，请查看 $LOG"
  exit 1
fi
wait "$TUNNEL_PID"
