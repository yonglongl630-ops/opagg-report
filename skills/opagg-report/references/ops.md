# opagg-report 运维参考

## 文件地图
| 路径 | 作用 |
| --- | --- |
| `scheduler.py` | 调度入口（--once/--weekly/--is-trading-day/--no-cache/--force） |
| `src/serve.py` | 本地刷新服务（端口 8651，/api/refresh、/api/publish、/api/status） |
| `src/aggregate.py` | 采集+蒸馏主流程；`_backfill_charge_dynamics` 充电回填 |
| `src/report.py` | 日报 HTML 渲染；页面 JS（花生壳默认地址、刷新后自动发布） |
| `src/ths.py` | 同花顺热股/板块/圈子 |
| `config.json` | 本地敏感配置（gitignore）：B站/雪球 cookie、upmaster 列表 |
| `config.workflow.json` | 仓库内脱敏配置，GitHub Actions 回退使用（scheduler.daily_enabled=true） |
| `data/secrets.json` | 敏感密钥（gitignore）：opagg_token / bilibili_cookie / xueqiu_cookie |
| `data/raw/` `data/summary/` | 原始采集 / 蒸馏结果（JSON） |
| `data/upmasters/` | up主档案库（registry.json + 头像 + 素材归档，gitignore） |
| `deploy/gh_pages_push.sh` | 发布主脚本：site.py → tar 裁剪 → API 推送（git 兜底）→ Gitee 镜像 |
| `deploy/gh_pages_api_push.py` | Git Data API 推送（blob/tree/commit/ref），curl 实现 |
| `.github/workflows/daily.yml` | 云端工作日 8:00/18:00 日报（含 15 分钟兜底 cron） |
| `.github/workflows/publish.yml` | 周日周报 |
| `deploy/launchd/` | launchd plist（daily / serve） |

## 关键接口
- `GET /api/status` — 刷新任务状态（无需 token）
- `POST /api/refresh?source=all|jin10,...&date=YYYY-MM-DD` — 触发采集（token 或浏览器 Origin）
- `POST /api/publish` — 触发发布 gh-pages（token 或浏览器 Origin）
- `GET /api/publish-status` — 发布状态
- `GET /tunnel-url` — 当前 trycloudflare 公网地址（如有）

## 浏览器免口令规则（src/serve.py `_check_token`）
请求带 `?token=<opagg_token>` 直接放行；否则若 Origin/Referer 含 `vicp.fun`、`github.io`、`127.0.0.1`、`localhost`、`192.168.`、`10.` 也放行；其余（裸 curl）返回 403。

## GitHub 发布细节
- 大 body 上传（>~5MB）会被 GitHub 掐断（HTTP 000/401），因此 `data.tar.gz` 必须裁剪：
  raw 保留 3 天、summary 保留 7 天（cp -Rp 保留 mtime 后 find -mtime 裁剪），成品约 2.3MB。
- API 推送每次重建整棵 gh-pages 树（base_tree 缺省=空根），旧 preview png 自动消失；并发安全。
- 本地 git 走代理（127.0.0.1:1082）时 TLS 不稳定：ls-remote 偶发可通，clone/push 大文件必断。
  可用直连真实 IP 测试：`curl -s 'https://223.5.5.5/resolve?name=github.com&type=A'`。

## Cookie 管理
- B站：`config.json → bilibili.cookie` 与 `data/secrets.json → bilibili_cookie` 同步更新；
  关键字段 `SESSDATA=`（HttpOnly，浏览器 DevTools → Application → Cookies 复制）与 `bili_jct=`。
  验证：请求 `https://api.bilibili.com/x/web-interface/nav`，code=0 且有 uname 即有效。
- 雪球：`xueqiu.cookie`（含 `xq_a_token`、可选 `acw_sc__v2`）；验证 `python3 -m src.xueqiu --test`。
- cookie 过期症状：充电动态变「充电专属动态（仅充电用户可见）」（B站）、雪球 WAF「需 acw_sc__v2」（云端）。

## 定时/服务管理
```bash
launchctl print gui/$(id -u)/com.opagg.serve       # 查看 serve 任务
launchctl kickstart gui/$(id -u)/com.opagg.serve   # 拉起 serve（Terminal 方式）
bash deploy/install_serve.sh                       # 安装/重装 serve 自启
bash deploy/install_launchd.sh --daily             # 安装工作日日报任务
```
注意：花生壳客户端（贝锐花生壳）需单独保持登录/运行，否则 vicp.fun 域名不通。

## 常见问题排查表
| 现象 | 根因 | 处理 |
| --- | --- | --- |
| 所有 HTTPS 源 EOF/SSL 错误 | 本地代理 1082 不稳定（DNS 走 198.18.x.x） | 等网络恢复重跑；云端 Actions 兜底；检查代理客户端 |
| vicp.fun 打不开 | 花生壳客户端没运行 或 serve 没监听 8651 | 启动贝锐花生壳；`launchctl kickstart` serve |
| 手机点刷新弹配置框 | 旧版需 token；serve/花生壳掉线 | 确认两者在线；新版浏览器 Origin 已免口令 |
| 日报缺充电内容 | B站 cookie 过期 | 更新 SESSDATA 后 `--no-cache --sources bilibili` |
| 同花顺热股「暂无热股数据」 | 接口 topic 字段 dict/null 崩溃（已修复）或风控 | 重跑 ths；检查 `src/ths.py` |
| gh-pages 不更新 | git push 被代理掐断 / 大 tar 超限 | `bash deploy/gh_pages_push.sh`（API 直传+裁剪 tar） |
| 云端日报缺 up主 | 云端无 B站 cookie/历史 | 本地跑一次并发布，数据随 data.tar.gz 同步给云端 |
| 日报页无「立即刷新」服务 | serve 未运行 | 本地 `python3 -m src.serve --lan` 或 kickstart |

## 一键刷新脚本
```bash
bash skills/opagg-report/scripts/refresh_report.sh [YYYY-MM-DD]
```
流程：校验 serve 在线 → `/api/refresh?source=all`（带 token）→ 轮询完成 → `/api/publish` → 轮询发布 → 打印两端地址。
