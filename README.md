# 缺失剧集补齐 (MoviePilot V3 插件)

定时扫描媒体库（Emby/Jellyfin）剧集缺失情况，自动搜索资源下载补齐。

## 功能

- **全库扫描 / 指定剧集**：默认全库扫描，也可按 TMDB ID 指定
- **自动搜索下载**：按自定义筛选规则自动搜索下载缺失剧集
- **未播出集自动转订阅**：未来集不搜种，自动建立订阅池，等播出后自动回流
- **卡死种子清理**：下载进度长时间零增长的任务自动删除并拉黑
- **结果通知**：推送缺失 / 已下载 / 已转订阅汇总
- **结果页**：插件详情页分栏展示「缺失项」与「已转订阅」

## 安装

在 MoviePilot 设置 → 插件市场 中添加本仓库：

```
https://github.com/asice999/MoviePilot-Plugins
```

## 配置

| 配置项 | 说明 |
| --- | --- |
| 启用插件 | 开关 |
| 自动搜索下载 | 关闭时仅通知缺失情况 |
| 消息通知 | 推送扫描结果 |
| Emby/Jellyfin 地址 | 用于枚举媒体库剧集（可留空用系统媒体服务器配置） |
| Emby/Jellyfin API Key | 媒体库 API 密钥 |
| 扫描范围 | 全库 / 仅指定剧集 |
| 指定剧集 TMDB ID | 逗号分隔，如 `46260,60735` |
| 每次最多下载部数 | 防止一次扫描触发过多下载 |

## 开发

```text
plugins.v3/mpmissingepisodes/__init__.py   # 插件主实现
tests/v3/mpmissingepisodes/test_plugin.py  # 版本一致性测试
package.v3.json                            # 市场索引
icons/mpmissingepisodes.png                # 图标
```
