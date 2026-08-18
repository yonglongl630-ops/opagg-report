#!/bin/bash
# 安装/卸载「立即刷新」常驻本地服务（开机自启，端口 8651）：
#   bash deploy/install_serve.sh           # 安装并立即启动
#   bash deploy/install_serve.sh --uninstall
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST="$AGENT_DIR/com.opagg.serve.plist"
mkdir -p "$AGENT_DIR" "$ROOT/data/logs"

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "已卸载本地刷新服务。"
  exit 0
fi

# 把 plist 里的项目路径替换为当前路径
sed "s|/Users/liangyonglong/Documents/ChatGPT/蒸馏up主分析舆论|$ROOT|g" \
  "$ROOT/deploy/com.opagg.serve.plist" > "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
sleep 1
if curl -s --max-time 3 "http://127.0.0.1:8651/api/status" >/dev/null 2>&1; then
  IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1)"
  echo "本地刷新服务已启动（开机自启，--lan 手机可访问）：http://127.0.0.1:8651"
  echo "手机端（同 WiFi）：打开 http://${IP}:8651/report_$(date +%F).html 后点【立即刷新】即可实时更新"
else
  echo "服务已注册但暂未响应，请查看 $ROOT/data/logs/serve.err.log"
fi
