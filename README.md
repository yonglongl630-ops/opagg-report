# 当日舆论聚合与蒸馏日报

用 Codex 实现的多平台舆论聚合系统：采集 **B站（热搜/排行/搜索/up主视频/动态/评论）、股吧、雪球、同花顺、金十快讯、财联社、东方财富**，自动提炼**热词、情绪、热点主题**，对配置的 **up主** 做观点蒸馏（立场、金句、关键词、动态），并生成**HTML 日报**。

## 快速开始

```bash
python3 run.py                        # 采集今日全部数据源并生成 HTML 日报
python3 run.py --date 2026-08-13      # 从缓存重新蒸馏某天
python3 run.py --sources jin10 --no-cache   # 只重取金十（其他源保留缓存）
python3 run.py --open                 # 生成后打开浏览器
```

生成结果：

- 日报：`output/report_YYYY-MM-DD.html`
- 原始数据：`data/raw/YYYY-MM-DD.json`
- 蒸馏结果：`data/summary/YYYY-MM-DD.json`

## 界面头部卡片

日报头部展示 5 个信息卡（雪球/同花顺/金十/财联社/东方财富；Wind 板块已剔除），每张卡统一包含 **热股 TOP10** 与 **热门话题 TOP10** 两个区块（同一自选股/话题按热度排序），下方另设「今日热门板块 / 热榜」（官方板块榜：同花顺/财联社/东方财富 + 雪球热榜）：

| 卡片 | 内容 | 数据源 |
| --- | --- | --- |
| 雪球热榜 | 热股=热股榜；话题=官网右侧「热门话题」 | stock.xueqiu.com 热股榜；xueqiu.com/hot_event/list.json（话题含讨论数） |
| 同花顺热榜 | 热股=官方实时热股榜；话题=官方板块热榜（概念+行业按热度合并） | dq.10jqka.com.cn `hot_list/v1/stock`（`type=hour&list_type=normal`）与 `hot_list/v1/plate`（`type=concept|industry`） |
| 金十快讯 | 热股=快讯中识别到的自选股；话题=热点头条 TOP10 | www.jin10.com/flash_newest.js + cdn.jin10.com/json/index/hits_rank.json（xnews.jin10.com/53 同源） |
| 财联社热榜 | 热股=暂无（App 热股榜为签名私有接口，公开渠道无个股热股榜，显示「暂无热股数据」）；话题=热门文章 TOP10 | x-quote.cls.cn `web_quote/plate/hot_plate`（仅用于官方板块条）+ www.cls.cn 首页 `hotArticleData`（按阅读数排序） |
| 东方财富热榜 | 热股=个股人气榜 TOP10；话题=领涨概念 TOP10 | emappdata.eastmoney.com `stockrank/getAllCurrentList`（人气榜）+ push2delay/push2 `clist/get fs=m:90+t:3&fid=f3`（so.eastmoney.com 领涨概念同源） |

> **板块口径**：已剔除 Wind 终端近似板块（无法准确取数）。日报头部下方「今日热门板块」只使用
> 平台官方板块榜：同花顺官方板块热榜（概念+行业）+ 财联社官方热门板块（含主力资金/领涨股）+ 东方财富领涨概念榜。
>
> **聚合口径**：综合热榜（热股/热门话题跨平台合并）、各平台聚合 TOP10 话题
> 均以 雪球 / 同花顺 / 金十 / 财联社 / 东方财富 五平台数据输出，并带平台彩色标签。
>
> **版面**：「蒸馏摘要」「今日梗 / 高频短语」区块已剔除；up主 头像以 base64 内嵌，
> 兼容 file:// 与本地服务打开方式。
>
> **版面**：原「蒸馏热点主题 → 代表热帖」区块已删除；「各平台原始帖流（逐平台列表）」已替换为
> 「各平台聚合 TOP10 话题」总结，不再单独展示每个平台信息。
>
> 说明：财联社 App 内「热股榜」走的是签名私有接口（`api3.cls.cn` 需要 sign，网页端无公开等价接口），
> 因此取数路径采用财联社官方行情页同源的「热门板块」领涨股 + 电报资讯关联个股；若需要精确对齐 App 榜单，
> 可抓包提供该接口地址与参数，我们再接入。

## up主档案库与自学 skill

`data/upmasters/` 是 up主 档案库（注册表 + 素材归档 + 头像图片 + 风格画像），方便随时更新 up主 信息：

```text
data/upmasters/
  registry.json               # 注册表：uid/cookie/头像/标签/备注/粉丝/最近刷新（含敏感信息，已 gitignore）
  <mid>/
    avatar.jpg                # 本地头像（日报优先展示本地图）
    archive/                  # 素材归档：videos.json / dynamics.json / comments.json / corpus.json
    learn/style_profile.json  # 自学风格画像：立场/关键词/口头禅/金句/标题模式
```

常用命令：

```bash
python3 -m src.upmaster_lib list
python3 -m src.upmaster_lib add --name "小Lin说" --mid <uid> --tags 财经
python3 -m src.upmaster_lib sync-xlsx                          # 从博主信息表(xlsx)同步博主
python3 -m src.upmaster_lib sync-xlsx --merge                  # 追加合并而不是整体替换
python3 -m src.upmaster_lib refresh --mid 472747194 --videos 15 --dynamics 30   # 归档素材+下载头像
python3 -m src.upmaster_lib profile --mid 472747194                            # 生成/刷新风格画像
python3 -m src.upmaster_lib sync-config                                         # config.json → 注册表
```

### 博主信息表（推荐维护方式）

`data/upmasters/B站博主信息管理系统.xlsx` 是博主主档案表，表头为：博主UID / 博主名称 / 博主主页 / 所属赛道 / 当前粉丝数 / 合作报价 / 最新视频动态 / 备注 / 录入人。
以后新增或修改博主，直接编辑这份表格，然后执行：

```bash
python3 -m src.upmaster_lib sync-xlsx     # 同步到 config.json 与注册表（同 uid 的 cookie 会保留）
python3 -m src.upmaster_lib refresh --mid <uid> --videos 5 --dynamics 10   # 归档素材
```

已内置博主：笨笨的韭菜(11473291)、史诗级韭菜(322005137)、海螺复盘(471949556)、星话大白(2233213)。

### 热门话题排除作者

`config.json → distill.exclude_authors_from_topics` 配置要从"今日热门话题"剔除的博主名（如 `["巫师财经"]`），这些作者的内容不再进入话题聚类，但 up主 分析照常保留。

**自学 skill**：`skills/upmaster-selflearn/` 是给 Codex 使用的 skill，说明如何从 up主 历史视频/动态/评论中学习其风格并更新画像。日报 up主 区块会展示头像、标签、风格关键词、近期视频、最近动态与高赞金句。

### B站 uid 与 cookie

- `config.json → bilibili.upmasters[].mid` 填 up主 的 B站 uid（空间地址里的数字）。已内置 巫师财经（472747194）、饭统戴老板（253553776）。
- 匿名采集多数接口可用，但空间视频列表受风控（-799/412）时自动降级为搜索发现视频。
- 需要**动态/评论稳定采集**时，把登录后的 cookie（含 `SESSDATA=...`）填入 `config.json → bilibili.cookie`，或写入档案库注册表（`python3 -m src.upmaster_lib update --mid <uid> --cookie "SESSDATA=..."`）。注册表已 gitignore，不会误提交敏感信息。
- 雪球被阿里云 WAF（acw_sc__v2 挑战）拦截时，把浏览器登录态的完整 Cookie 填入配置即可解封：

  ```bash
  python3 -m src.xueqiu --set-cookie "acw_sc__v2=...; xq_a_token=...; u=..."
  python3 -m src.xueqiu --test        # 验证 cookie 是否已通过 WAF
  ```

  说明：登录 cookie（`xq_a_token` 等）即可解锁**热股榜**与**热帖流**（热帖走 `api.xueqiu.com`，可绕过阿里云 WAF 挑战；若该通道失效会自动回退 `xueqiu.com`）。`acw_sc__v2` 非必需，有则一并提交更稳。cookie 同时写入 `config.json` 与 gitignore 的 `data/secrets.json`，不会提交到仓库。

## 日报内容结构

按使用反馈简化为：**头部 5 卡片**（雪球/同花顺/金十/财联社/东方财富，每卡热股 TOP10 + 热门话题 TOP10；财联社热股无公开个股榜故显示「暂无热股数据」，与金十一致）→ **今日热门板块 / 热榜**（官方板块榜 + 雪球热榜）→ **综合热榜面板**（五平台汇总合并：热股 TOP10 + 热门话题 TOP10 跨平台去重、带平台标签；已剔除「蒸馏热点主题 → 代表热帖」区块）→ **今日综合热词**（全文蒸馏热词 + 五大平台热词聚合；已剔除「蒸馏摘要」「今日梗/高频短语」区块）→ **各平台聚合 TOP10 话题**（替代逐平台原始帖流，不单独展示每个平台）→ **up主动态与观点蒸馏汇总**（置于最底部，逐 up主 一行汇总 + 可展开的视频/评论热点/最近动态/充电分析详情）。

up主 卡片细节（默认展开）：**视频分析**（窗口内近期视频 + 立场/关键词）、**最近动态固定取窗口内近 3 条**（含充电专属内容与正文全文，没有则显示“无”）、**评论汇总分析**（评论情绪分布、评论热点词、活跃评论用户及其态度/高赞评论）、**高赞金句**；充电信息只展示**本月充电人次**（不展示榜单排名），并补充**充电专属动态分析**（窗口内充电专属动态条数与赞/评）。

说明：

- 热词/梗按**当日采集时间范围**统计（早于日报日期的历史帖/视频不进入统计），梗按 3~8 字短语出现次数统计并做碎片去重。
- B站热搜、B站全站排行不再在日报中展示（仍参与热词统计），up主 分析使用其视频/动态/评论数据。
- 某 up主 未配置 B站 cookie 时，日报会给出配置命令提示（见下方「B站 uid 与 cookie」）。

## 定时运行与「立即刷新」

> 默认已停止每日自动采集（`config.json → scheduler.daily_enabled=false`），
> 改为查看日报时点击页面上的 **🔄 立即刷新** 按钮实时重采集。

调度器内置 A股交易日历（`data/trading_calendar.json`，含 2026 官方休市安排，跨年后请更新）：

```bash
python3 scheduler.py --once                            # 采集一次并生成日报
python3 scheduler.py --is-trading-day                  # 判断今天是否交易日（0=是，1=否）
python3 scheduler.py --next-run                        # 预览下次日报运行时间
python3 scheduler.py --once --force                    # 手动强制跑一次日报
python3 scheduler.py --once --refresh-upmasters        # 采集前先归档 up主素材
```

日报页「立即刷新」依赖一个本地常驻服务（默认已开机自启，无需手动启动）：

```bash
python3 -m src.serve            # 手动启动 http://127.0.0.1:8651（提供日报 + /api/refresh 刷新接口）
python3 -m src.serve --open     # 启动并打开日报
bash deploy/install_serve.sh    # 安装开机自启（登录后自动用 Terminal 启动服务）
bash deploy/install_serve.sh --uninstall   # 卸载自启
```

> 说明：页面用 `file://` 打开时，点【立即刷新】会自动跳转到
> `http://127.0.0.1:8651/report_YYYY-MM-DD.html?refresh=1`（服务版页面）并自动执行刷新；
> 刷新完成后回到当前日期日报。服务通过 Terminal 启动，登录后会出现一个常驻终端窗口
> （关闭窗口即停止服务；若不想看到窗口，可在系统设置给 python3 授予「完全磁盘访问权限」后改用后台方式）。

如需重新开启 macOS launchd 定时任务（会写入 `~/Library/LaunchAgents`）：

```bash
bash deploy/install_launchd.sh            # 默认不安装任何定时任务
bash deploy/install_launchd.sh --daily    # 同时安装每日 8:00/18:00 日报
launchctl list | grep opagg
```

> 周报已移除。`deploy/install_launchd.sh` 默认不安装任何任务（周报/日报均已剔除），
> 如需开启每日 8:00 / 18:00 日报定时，执行 `bash deploy/install_launchd.sh --daily`。
> 也可用 Codex 自动化、cron 或 `--interval-minutes` 循环模式替代。

## 公网网址（GitHub Pages，与「破线监控」同款）

利用 GitHub 免费提供的 Pages：**日报在本地生成后一键发布**，任何设备浏览器直接访问网址即可。

部署步骤：

1. 注册 GitHub 账号（免费）：<https://github.com>；未安装 `gh` 可用网页操作
2. 新建仓库：右上角 **+ → New repository**，仓库名随意（如 `opagg-report`），**Visibility 选 Public**，不要勾选初始化 README
3. 在终端执行（把用户名和仓库名换成自己的）：

```bash
cd "/Users/liangyonglong/Documents/ChatGPT/蒸馏up主分析舆论"
git init -b main
git add .
git commit -m "舆论蒸馏日报系统"
git remote add origin https://github.com/你的用户名/opagg-report.git
git push -u origin main
```

> 含敏感 cookie 的 `config.json`、`data/secrets.json`、`data/upmasters/registry.json` 已被 `.gitignore` 排除，不会上传。
> 生成类数据（`output/`、`data/raw|summary`）不入库，由本地发布脚本打包到 gh-pages 存档。

4. 开启 Pages：仓库页面 **Settings → Pages**，Source 选 **Deploy from a branch**，分支选 `gh-pages`、目录 `/ (root)`，点 Save
5. 等 1~2 分钟，访问（替换成自己的用户名和仓库名）：

```text
https://yonglongl630-ops.github.io/opagg-report/
```

### 发布在线版（GitHub Pages）

**日报不设定时、也不由云端生成**（GitHub 服务器 IP 会被雪球 WAF 拦截）：
本地打开日报页点击「🔄 立即刷新」实时采集（`python3 -m src.serve`），
再点「☁️ 发布在线版」一键推到网址（执行 `deploy/gh_pages_push.sh`），手机即可查看。

## 配置（config.json）

| 配置项 | 说明 |
| --- | --- |
| `watchlist` | 自选股，驱动股吧个股页/热帖采集与关键词保护 |
| `bilibili.cookie` | 可选：B站登录 cookie（SESSDATA 等） |
| `bilibili.upmasters` | 关注 up主：`mid`/`uid`、`url`、`avatar`、`cookie`、`tags`、`notes`、`enabled` |
| `bilibili.time_window` | **蒸馏模式统计窗口**：`{"mode":"today"}`（当天 00:00 起，默认）或 `{"mode":"hours","hours":24}`（滚动最近 N 小时），up主 视频/动态只统计窗口内内容，杜绝历史混入 |
| `bilibili.incremental_updates` | 增量去重：同一天多次运行时只上报新增动态/视频（盘中循环模式自动开启） |
| `bilibili.charging_limit` | up主 本月充电榜展示条数（日报 up主 卡片展示“本月充电 X 人次 + 榜单”） |
| `bilibili.search_keywords` | 关键词搜索（WBI 签名） |
| `sector.*` | 板块汇总（已停用：`enabled=false`，Wind/东财近似无法准确取数，板块改用各平台官方板块榜） |
| `jin10.*` / `cls.*` | 金十快讯 / 财联社电报条数；热门话题分别取热点头条/热门文章 |
| `em.*` | 东方财富：人气榜/领涨概念/热门搜索条数 |
| `xueqiu.cookie` | 可选：雪球登录 cookie |
| `scheduler.daily_enabled` | 是否启用每日定时日报（默认 false，改用「立即刷新」） |
| `distill.*` | 蒸馏参数：热词数、梗数、最低频次等 |

### B站充电动态/评论稳定采集（cookie 配置）

充电专属动态与评论需要**登录态**才能取到全文：

1. 浏览器登录 bilibili.com（建议勾选“记住登录状态”），打开开发者工具（F12）→ Network → 任选一个 `api.bilibili.com` 请求 → 复制 `Cookie` 请求头。
2. 全局配置：把 `SESSDATA=...; bili_jct=...`（连同 `buvid3` 等一并）填入 `config.json → bilibili.cookie`。
3. 或只给单个 up主 配置：`python3 -m src.upmaster_lib update --mid 11473291 --cookie "SESSDATA=...; bili_jct=..."`。
4. 重采：`python3 run.py --no-cache --sources bilibili`。

说明：不需要长期保持浏览器/账号在线，cookie 有效期通常较长；失效后重新复制一次即可。若某 up主 的充电内容仍不可见，请确认该 B站账号已对该 up主 充电（有查看权限）。未配置 cookie 时，日报会如实标注“充电专属动态存在但内容锁定”或“动态接口被风控拦截（-352）”，不会把缺失伪装成“无”。

## 数据源可用性

各平台均为**匿名公开接口**，无登录态也能抓取，但受出口 IP 风控影响：

| 平台 | 状态 | 备注 |
| --- | --- | --- |
| B站 | ✅ 可用 | 热搜/排行/WBI 搜索/up主视频(搜索降级)/动态(WBI 签名)；空间接口风控时需 cookie |
| 股吧 | ✅ 可用 | 自选股最新帖 + 个股热帖 JSONP |
| 同花顺 | ✅ 可用 | 官方热股榜/板块热榜（dq.10jqka.com.cn JSON）；圈子帖流 http 版保留 |
| 板块 | ⛔ 已停用 | Wind/东财近似无法准确取数；改用同花顺官方板块热榜 + 财联社官方热门板块 |
| 金十 | ✅ 可用 | flash_newest.js + hits_rank.json（热点头条） |
| 财联社 | ✅ 可用 | 官方热门板块（x-quote.cls.cn）+ www.cls.cn 首页热门文章 + m.cls.cn 电报 |
| 雪球 | ⚠️ 视网络 | 被阿里云 WAF 拦截时报告标注失败，可配置 cookie；热门话题走 hot_event/list.json |
| 东方财富 | ✅ 可用 | 人气榜（emappdata）+ 领涨概念（push2delay/push2）+ 热门搜索（searchadapter） |

采集失败不会中断整体流程：失败数据源会在日报"数据源异常"区块标注，其他平台照常出日报。

## 蒸馏模式：定时窗口内的 up主 实时动态

日报头部会显示**统计窗口**（默认“当天 00:00 起”）。该窗口贯穿采集与蒸馏：

- **up主 视频**：只保留窗口内发布的视频（含其热评），更早的视频不会进入日报（`run.py --since-hours 24` 可临时改为滚动窗口）。
- **up主 动态**：只保留窗口内的文字/图文/转发/投稿动态，并标记 **🔒充电专属**；窗口外动态一律丢弃。
- **充电信息**：展示 up主 **本月充电榜**（充电人次 + TOP 榜单），充电榜本身是实时月榜，不存在历史混入。
- **评论热点**：up主 详情里的“高赞金句/评论热点”只来自窗口内视频的热评。
- **盘中循环**：`scheduler.py --interval-minutes 60` 自动开启增量模式（窗口=上一轮采集至今），并记录 `data/state/seen_<date>.json`，同一动态/视频不会重复上报。

示例：up主 星话大白 在当天 11:30 发了《特朗普传媒进军核聚变》视频、12:21 发了靖国神社相关动态，则当天日报只出现这两条（及其它当天内容），08-14 及更早的内容全部不出现。

## 项目结构

```text
src/
  common.py       HTTP 会话 / 重试 / 编码 / 文本清洗 / 原子写
  bilibili.py     B站采集（WBI 签名、cookie、up主视频+动态+评论）
  guba.py         股吧采集
  xueqiu.py       雪球采集（会话 + 可选 Cookie）
  ths.py          同花顺采集（官方热股榜/板块热榜 + 圈子帖流）
  sector.py       板块行情（东财口径，已停用：config.sector.enabled=false）
  jin10.py        金十快讯 + 热点头条
  cls.py          财联社热门板块 + 热门文章 + 电报
  em.py           东方财富人气榜 + 领涨概念 + 热门搜索
  distill.py      蒸馏引擎（热词/梗/情感/聚类/up主观点/摘要）
  aggregate.py    聚合流水线
  report.py       HTML 日报渲染（头部 5 卡片 + 官方板块条 + up主档案展示）
  site.py         站点首页 index.html（最新日报 + 历史归档）
  upmaster_lib.py up主档案库（注册表/归档/头像/风格画像）
  serve.py        本地预览 + 「立即刷新」服务（http://127.0.0.1:8651）
run.py            命令行入口
scheduler.py      定时/循环调度入口（日报默认停用）
config.json       配置
config.workflow.json  云端脱敏配置（GitHub Actions 使用）
skills/upmaster-selflearn/    up主素材自学 skill
deploy/launchd/               macOS 定时任务
```

## 说明

- 仅依赖 Python 标准库（urllib / re / json），无需 `pip install`。
- 数据仅供研究参考，不构成投资建议；接口字段以原平台为准。
