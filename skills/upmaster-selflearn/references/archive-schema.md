# 档案目录与字段约定

所有路径相对于项目根目录 `蒸馏up主分析舆论/`。

## 目录结构

```
data/upmasters/
  registry.json                    # 全局注册表
  <mid>/
    avatar.<jpg|png>               # 本地头像
    archive/
      videos.json                  # 历史视频：bvid/title/desc/pubdate/views/top_comments
      dynamics.json                # 历史动态：title/content/time/likes/comments/url
      comments.json                # 评论汇总：content/likes/author
      corpus.json                  # 全文本语料（按时间排序）
    learn/
      style_profile.json           # 风格画像
```

## registry.json 条目字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `mid` / `uid` | int | B站 uid（两者等价） |
| `name` | str | 昵称 |
| `url` | str | 空间地址 |
| `avatar_remote` / `avatar_local` | str | 远程/本地头像，日报优先本地 |
| `cookie` | str | 登录 cookie（SESSDATA 等），用于评论/动态采集，请勿提交到 git |
| `sign` / `fans` | str/int | 签名、粉丝数（刷新时自动更新） |
| `tags` | list[str] | 标签 |
| `notes` | str | 备注 |
| `enabled` | bool | 是否参与采集 |
| `last_refresh` | str | 最近归档时间 |
| `stats` | dict | videos/dynamics/comments/corpus_entries 数量 |

## style_profile.json 字段

| 字段 | 说明 |
| --- | --- |
| `upmaster` | mid |
| `built_at` / `corpus_size` | 生成时间与语料规模 |
| `stance` / `stance_score` | 整体立场（看多/看空/中性）与指数 |
| `keywords` | 高频关键词 |
| `catchphrases` | 口头禅（3-5字高频短语） |
| `top_quotes` | 高赞金句 [{text,likes,type}] |
| `title_patterns` | 视频标题前缀模式 [{prefix,count}] |

可追加定性字段（如 `argument_style`、`stance_shifts`），但不要删除上述字段，日报/周报依赖它们。

## 更新规则

- 用 `src/upmaster_lib.py` 的命令更新，避免手改 JSON 破坏结构。
- cookie 属于敏感信息：`config.json`/`registry.json` 已加入 `.gitignore` 之外的本地文件时应谨慎；建议 registry.json 保留在本地不同步到远端。
