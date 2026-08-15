---
name: upmaster-selflearn
description: Learn a Bilibili UP主's style and viewpoints from their archived past materials (videos, dynamics, comments), then write/update a machine-readable style profile. Use when analyzing an UP主's historical corpus, distilling their stance, catchphrases, keywords, quotes, or title patterns, updating data/upmasters/<mid>/learn/style_profile.json, or onboarding a new UP主 into the 舆论蒸馏 project.
---

# UP主素材自学

在 `蒸馏up主分析舆论` 项目内使用。目标：从 up主 的过往素材里提炼可复用的风格画像，并保持档案可更新。

## 快速开始

```bash
# 1) 归档 up主素材（视频+评论+动态，自动下载头像，写入注册表）
python3 -m src.upmaster_lib refresh --mid 320382958 --videos 15 --dynamics 30

# 2) 生成/刷新风格画像
python3 -m src.upmaster_lib profile --mid 320382958

# 3) 查看注册表与本地档案
python3 -m src.upmaster_lib list
open data/upmasters/320382958/learn/style_profile.json
```

也可以直接调用 `scripts/learn.py --mid <mid>` 一次性完成归档+画像。

## 自学工作流

1. **归档**：`src/upmaster_lib.py refresh` 拉取 up主 空间信息、近期视频（含热评）、动态，合并进 `data/upmasters/<mid>/archive/`，并生成 `corpus.json`（按时间排序的全文本语料）。B站评论/动态需要 cookie 时，先在注册表或 config.json 填 `cookie`（SESSDATA 等）。
2. **粗画像**：`profile` 命令用规则引擎生成 `learn/style_profile.json`：立场指数、关键词、口头禅（3-5字高频短语）、高赞金句、标题前缀模式。
3. **细读素材**：读取 `archive/corpus.json`，抽样不同时期内容，人工/模型补写 `style_profile.json` 中缺失的定性字段（如论证风格、常用立场框架、观点演变），保持 JSON 结构不变。
4. **更新档案**：修改 `data/upmasters/registry.json` 的 tags/notes；日常运行时 `aggregate.py` 会自动合并档案字段进日报。
5. **日报使用**：日报 up主 区块直接展示风格关键词与最近动态；周报聚合一周观点趋势。

## 目录与字段约定

见 [references/archive-schema.md](references/archive-schema.md)。修改结构前先读它，保持向后兼容。

## 注意事项

- 素材接口是公开接口，受风控：动态接口需要先访问 bilibili.com 建立 buvid 会话（库内已处理）；连续刷新请间隔数分钟。
- 评论只保留高赞样本，语料是抽样而非全量，画像结论需注明时间窗口。
- 结果用于研究参考，不构成投资建议。
