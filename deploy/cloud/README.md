# 云端部署「立即刷新 + 日报」

让手机在任何地方都能打开日报并点击「立即刷新」——无需本地电脑开机。

## 方式一：Render（推荐，免费）

1. 把项目推到 GitHub（`config.json` 已被 .gitignore 排除，云端会自动用脱敏的 `config.workflow.json`）。
2. Render 控制台 → New → Web Service → 选仓库，类型选 **Docker**。
3. 环境变量（Dashboard → Environment）：
   - `OPAGG_TOKEN`：刷新口令（随机字符串），保护 `/api/refresh`、`/api/publish`
   - `BILI_COOKIE`：你的 B站 cookie（同 config.json 里的那串）
   - `XUEQIU_COOKIE`：可选，雪球 cookie
4. 挂载磁盘（Disks）→ 挂到 `/app/data`（保留 data/raw、data/summary 缓存）。
5. 部署完成后会得到 `https://xxx.onrender.com`。

手机使用：打开 `https://xxx.onrender.com/report_YYYY-MM-DD.html` → 点「立即刷新」→ 首次会提示配置地址，填 `https://xxx.onrender.com` 即可（同源自动连接，也可用 `?api=` 参数）。若设置了 `OPAGG_TOKEN`，刷新地址填 `https://xxx.onrender.com?token=你的口令`（保存后会记住）。

## 方式二：Railway / Fly.io / 任意 VPS

- Railway：New Project → Deploy from GitHub → 服务命令 `python3 -m src.serve --cloud --port 8000`，加环境变量与 Volume。
- Fly.io：`fly launch` 后把 `deploy/cloud/Dockerfile` 作为 Dockerfile，`fly secrets set OPAGG_TOKEN=... BILI_COOKIE=...`，`fly volumes create opagg_data --size 1`，挂载 `/app/data`。
- VPS：`docker build -f deploy/cloud/Dockerfile -t opagg . && docker run -d -p 8000:8000 -v /var/lib/opagg/data:/app/data -e OPAGG_TOKEN=xxx -e BILI_COOKIE=... opagg`，再用 Nginx/Caddy 反代 HTTPS。

## 无人值守日报（不用本地、不用手动点）

GitHub Actions 每日自动生成并发布到 Pages（见仓库 `.github/workflows/daily.yml`）：
- 每天 08:00 / 18:00（北京时间）自动执行 `scheduler.py --once`（需在仓库 Secrets 里配置 `BILI_COOKIE`、`XUEQIU_COOKIE`）
- 手动触发：Actions → 舆论蒸馏日报自动生成 → Run workflow
- 日报发布到 `https://<用户名>.github.io/<仓库>/report_YYYY-MM-DD.html`

## 本地 + 手机（不部署云端时）

```bash
python3 -m src.serve --lan --open
# 终端会打印“手机端(同WiFi/云端): http://192.168.x.x:8651/report_YYYY-MM-DD.html”
# 手机连同一 WiFi，打开该地址即可同源刷新（电脑需保持开机）
```
