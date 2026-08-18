#!/bin/bash
# 供 LaunchAgent 通过 Terminal 启动本地刷新服务：
# Terminal 属于有「文稿」访问权限的 GUI 应用，可绕开 launchd 后台进程的 TCC 限制。
cd "$(dirname "$0")/.."
IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo 127.0.0.1)"
echo "本地刷新服务已启动（手机同 WiFi 可访问）："
echo "  本机:   http://127.0.0.1:8651"
echo "  手机:   http://${IP}:8651/report_$(date +%F).html   （关闭本窗口即停止）"
exec /usr/bin/python3 src/serve.py --lan --port 8651
