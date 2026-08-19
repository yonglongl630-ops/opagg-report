#!/bin/bash
# 供 LaunchAgent 通过 Terminal 运行每日日报自动生成 + 发布：
# Terminal 属于有「文稿」访问权限的 GUI 应用，可绕开 launchd 后台进程的 TCC 限制。
# 交易日 08:00 / 18:00 由 launchd 触发本脚本；非交易日自动跳过。
cd "$(dirname "$0")/.."
echo "==== 日报自动生成开始 $(date '+%Y-%m-%d %H:%M:%S') ===="

python3 scheduler.py --once --force --require-trading-day
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "采集失败(exit $rc)，保留旧日报。日志：data/logs/opagg_$(date +%Y-%m-%d).log"
  exit 1
fi

bash deploy/gh_pages_push.sh
echo "==== 完成 $(date '+%H:%M:%S')，已发布到 GitHub Pages（如配置 Gitee 远程会自动镜像） ===="
