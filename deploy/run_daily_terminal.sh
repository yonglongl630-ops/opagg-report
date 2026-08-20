#!/bin/bash
# 供 LaunchAgent 通过 Terminal 运行每日日报自动生成 + 发布：
# Terminal 属于有「文稿」访问权限的 GUI 应用，可绕开 launchd 后台进程的 TCC 限制。
# 交易日 08:00 / 18:00 由 launchd 触发本脚本；非交易日自动跳过。
# 每次运行输出写入 data/logs/daily_terminal_YYYYmmdd_HHMM.log，方便排查失败原因。
cd "$(dirname "$0")/.."
mkdir -p data/logs
LOG="data/logs/daily_terminal_$(date '+%Y%m%d_%H%M').log"
echo "==== 日报自动生成开始 $(date '+%Y-%m-%d %H:%M:%S') ====" | tee -a "$LOG"

# 非交易日直接跳过（launchd 每天都触发，仅工作日生成）
python3 scheduler.py --is-trading-day >> "$LOG" 2>&1 || {
  echo "今天非交易日，跳过生成" | tee -a "$LOG"
  exit 0
}

# 实时采集：8:00/18:00 都拉最新数据（--no-cache）；失败时回退缓存重跑
if ! python3 scheduler.py --once --force --no-cache >> "$LOG" 2>&1; then
  echo "实时采集失败，回退缓存重跑" | tee -a "$LOG"
  rm -f "data/raw/$(date +%F).json"
  if ! python3 scheduler.py --once --force >> "$LOG" 2>&1; then
    echo "采集失败，保留旧日报。日志：$LOG" | tee -a "$LOG"
    exit 1
  fi
fi

if ! bash deploy/gh_pages_push.sh >> "$LOG" 2>&1; then
  echo "发布失败，请查看日志：$LOG（可手动运行 bash deploy/gh_pages_push.sh 重试）" | tee -a "$LOG"
  exit 1
fi

echo "==== 完成 $(date '+%H:%M:%S')，已发布到 GitHub Pages（如配置 Gitee 远程会自动镜像） ====" | tee -a "$LOG"
