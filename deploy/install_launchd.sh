#!/bin/bash
# 安装 launchd 定时任务：
#   - 周日 15:00 生成周报（默认）
#   - 交易日 08:00 / 18:00 生成日报（需显式 --daily，默认已停用，改用日报页「立即刷新」）
# 用法: bash deploy/install_launchd.sh [--daily]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENT_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$AGENT_DIR" "$ROOT/data/logs"

INSTALL_DAILY=0
if [[ "${1:-}" == "--daily" ]]; then
  INSTALL_DAILY=1
fi

names=(com.opagg.weekly)
if [[ "$INSTALL_DAILY" == "1" ]]; then
  names+=(com.opagg.daily)
fi

for name in "${names[@]}"; do
  src="$ROOT/deploy/launchd/$name.plist"
  # 把 plist 里的项目路径替换为当前路径
  sed "s|/Users/liangyonglong/Documents/ChatGPT/蒸馏up主分析舆论|$ROOT|g" "$src" > "$AGENT_DIR/$name.plist"
  launchctl unload "$AGENT_DIR/$name.plist" 2>/dev/null || true
  launchctl load "$AGENT_DIR/$name.plist"
  echo "已安装: $name"
done

if [[ "$INSTALL_DAILY" == "0" ]]; then
  launchctl unload "$AGENT_DIR/com.opagg.daily.plist" 2>/dev/null || true
  echo "提示: 日报定时任务已停用（config.scheduler.daily_enabled=false），可在日报页点击「立即刷新」手动更新。"
fi
echo "完成。查看任务: launchctl list | grep opagg"
