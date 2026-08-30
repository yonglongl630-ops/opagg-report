#!/bin/bash
# 一键刷新日报并发布到 GitHub Pages（走本地 serve 接口，与手机「立即刷新」同路径）
# 用法: bash refresh_report.sh [YYYY-MM-DD]
set -euo pipefail

ROOT="/Users/liangyonglong/Documents/ChatGPT/蒸馏up主分析舆论"
cd "$ROOT"

BASE="http://127.0.0.1:8651"
DATE="${1:-$(date +%F)}"
TOKEN="$(python3 -c "import json; print(json.load(open('data/secrets.json')).get('opagg_token',''))" 2>/dev/null || true)"

echo "== 1/4 检查本地服务 =="
if ! curl -s --max-time 5 "$BASE/api/status" >/dev/null 2>&1; then
  echo "serve 未运行，尝试拉起…"
  launchctl kickstart "gui/$(id -u)/com.opagg.serve" 2>/dev/null || true
  sleep 8
  curl -s --max-time 5 "$BASE/api/status" >/dev/null 2>&1 || { echo "serve 仍不可用，请先启动花生壳/本地服务"; exit 1; }
fi
echo "serve 在线"

echo "== 2/4 触发全量刷新 ($DATE) =="
Q="$BASE/api/refresh?source=all&date=$DATE"
[ -n "$TOKEN" ] && Q="$Q&token=$TOKEN"
curl -s --max-time 10 -X POST "$Q" | head -c 200; echo

echo "== 3/4 等待采集完成 =="
for i in $(seq 1 60); do
  sleep 10
  S="$(curl -s --max-time 8 "$BASE/api/status" 2>/dev/null || true)"
  RUNNING="$(echo "$S" | python3 -c "import sys,json; print(json.load(sys.stdin).get('running'))" 2>/dev/null || echo true)"
  echo "  ... 采集状态 running=$RUNNING"
  [ "$RUNNING" = "False" ] && break
done

echo "== 4/4 触发发布并等待 =="
Q="$BASE/api/publish"
[ -n "$TOKEN" ] && Q="$Q?token=$TOKEN"
curl -s --max-time 10 -X POST "$Q" | head -c 200; echo
for i in $(seq 1 60); do
  sleep 10
  S="$(curl -s --max-time 8 "$BASE/api/publish-status" 2>/dev/null || true)"
  RUNNING="$(echo "$S" | python3 -c "import sys,json; print(json.load(sys.stdin).get('running'))" 2>/dev/null || echo true)"
  ERR="$(echo "$S" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error',''))" 2>/dev/null || true)"
  echo "  ... 发布状态 running=$RUNNING${ERR:+ err=$ERR}"
  [ "$RUNNING" = "False" ] && break
done

echo "完成。花生壳: http://sf12894020jr.vicp.fun/report_$DATE.html"
echo "GitHub Pages: https://yonglongl630-ops.github.io/opagg-report/report_$DATE.html"
