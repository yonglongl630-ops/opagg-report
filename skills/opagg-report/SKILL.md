---
name: opagg-report
description: 舆论蒸馏日报系统（B站up主/雪球/同花顺/金十/财联社/东方财富）的采集、刷新、发布与排障。激活关键词：「日报刷新」「舆论日报」「opagg」「花生壳刷新」「充电动态」「发布日报」「立即刷新」。Use when the user asks to refresh/generate/publish the daily sentiment report, fix collection failures (B站/雪球/同花顺/财联社/东方财富), update cookies, or maintain 花生壳 ↔ GitHub Pages sync.
---

# 舆论蒸馏日报（opagg-report）

## 项目位置
`/Users/liangyonglong/Documents/ChatGPT/蒸馏up主分析舆论`

## 核心流程

### 1. 刷新日报（本地实时采集 + 生成）
```bash
cd /Users/liangyonglong/Documents/ChatGPT/蒸馏up主分析舆论
python3 scheduler.py --once --force --no-cache        # 全量实时采集并生成 report_YYYY-MM-DD.html
python3 scheduler.py --is-trading-day                 # 交易日判断（0=是）
python3 scheduler.py --once --force --no-cache --sources bilibili   # 只重取 B站
```
- 结果写入 `output/report_<date>.html`，首页 `output/index.html` 自动指向最新。
- 空数据保护：全源 0 条视为失败（保留旧日报），不会发布空报告。

### 2. 发布到 GitHub Pages
```bash
bash deploy/gh_pages_push.sh
```
- 首选 **Git Data API 直传**（`deploy/gh_pages_api_push.py`，curl 稳定，绕开本机 git TLS 大上传被掐断）；git 仅兜底。
- gh-pages 分支 = `output/` 内容（report_*.html + index.html + data.tar.gz + .nojekyll；自动剔除 preview_*.png）。
- `data.tar.gz` 已裁剪为 raw 3 天 + summary 7 天（<3MB），超过 ~5MB 会被 GitHub 拒绝（401）。
- 并发安全：API 推送直接重建整棵树，不存在非快进冲突。

### 3. 花生壳手机刷新（http://sf12894020jr.vicp.fun）
手机/电脑打开域名 → 点【🔄 立即刷新】→ 页面 POST 本地 serve（8651）→ 采集 → 新日报 → 自动发布同步。
前提：本地 serve（LaunchAgent `com.opagg.serve`，端口 8651）+ 花生壳客户端（贝锐花生壳）都在线。
- 免口令：浏览器页面请求（Origin 含 vicp.fun / github.io / 192.168./10.）自动放行；脚本/curl 直连仍需 `opagg_token`（`data/secrets.json`）。
- 检查链路：`curl http://sf12894020jr.vicp.fun/api/status` 应返回 JSON；`curl -X POST .../api/refresh?source=jin10` 不带 Origin 应返回 `token 无效`。

### 4. 定时任务
- 本机 launchd：`com.opagg.daily`（工作日 8:00/18:00，Terminal 方式绕开 macOS TCC）；`com.opagg.serve`（开机自启）。
- 云端兜底：`.github/workflows/daily.yml`（工作日 8:00/18:00 北京 = 0:00/10:00 UTC +15 分钟备份）；周日周报 `publish.yml`。
- 重新安装：`bash deploy/install_launchd.sh --daily`、`bash deploy/install_serve.sh`。

## 排障速查（详见 references/ops.md）
- **HTTPS 全断 `EOF / SSL_ERROR_SYSCALL`**：本地代理 127.0.0.1:1082 不稳定 → 等待网络恢复后重跑；云端 Actions 是兜底。
- **git push 失败/挂起**：改用 `bash deploy/gh_pages_push.sh`（API 直传），不要直接 git push 大文件。
- **充电动态变占位文案**：B站 cookie（SESSDATA）过期 → 更新 `config.json` + `data/secrets.json` 后重跑 `--no-cache --sources bilibili`；历史内容会自动回填（`_backfill_charge_dynamics`）。
- **同花顺热股为空**：`src/ths.py` 已处理 `topic` 为 dict/null 的情况；仍空则接口被风控，稍后重试。
- **手机刷新弹配置框**：确认 serve + 花生壳在线；新版已对浏览器 Origin 免口令，无需再输 token。
- **B站/雪球 cookie 更新**：改配置后无需重启 serve（每次请求重新读 config），但充电内容需重新采集。

## 资源
- `references/ops.md` — 命令/文件/接口/排障完整参考
- `scripts/refresh_report.sh` — 一键刷新 + 发布（服务接口 + token 方式）
