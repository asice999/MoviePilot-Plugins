# MoviePilot V3 插件仓库

这里放两套插件：

- **MpMissingEpisodes**：缺失剧集补齐
- **MetaFiller**：缺失剧集元数据补全

## 安装

在 MoviePilot 设置 → 插件市场 中添加本仓库：

```text
https://github.com/asice999/MoviePilot-Plugins
```

## 插件说明

### MpMissingEpisodes
扫描媒体库剧集缺失情况，自动搜索资源下载补齐。

### MetaFiller
扫描 Emby 剧集库，自动补全缺失的分集标题、简介与缩略图。支持：

- TMDB 中文优先
- 电视猫 / 央视网回退
- 预览模式
- 断点续跑
- 指定剧处理
- 历史报告
- 丢弃分类可视化

## 目录

```text
plugins.v3/mpmissingepisodes/__init__.py
plugins.v3/metafiller/__init__.py
package.v3.json
icons/
```
