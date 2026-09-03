# MoviePilot 自用插件库（V2/V3 双版本）

## 安装

MoviePilot 设置 → 插件市场 → 添加仓库：

```
https://github.com/as****99/MoviePilot-Plugins
```

V2 自动读取 `package.v2.json` + `plugins.v2/`，V3 自动读取 `package.v3.json` + `plugins.v3/`，无需额外配置。

## 插件列表

| 插件 | 说明 |
|------|------|
| **`AutoSignInMod`** | 自动签到魔改版：模拟登录+签到，显示总时魔/等级/分享率/当日奖励 |
| **`CloudSubscribe`** | 网盘订阅助手：搜索、订阅、洗版、转存、卡死种子清理 |
| **`GetMissingEpisodesMod`** | 剧集管家·下载补齐自用版：检测剧集缺失并自动搜索下载补全 |
| **`MetaFiller`** | 缺失剧集元数据补全：TMDB 中文优先，电视猫/央视网回退 |
| **`nodeseeksign`** | NodeSeek 论坛签到：自动签到，随机奖励+自动重试 |
| **`SiteStatistic`** | 站点数据统计（自用）：统计数据图表 |

## 目录结构

```
plugins.v2/    # V2 适配版（import 路径已兼容 V2 API）
plugins.v3/    # V3 原生版
package.v2.json
package.v3.json
icons/
```

## V2 适配说明（2026-09-03）

从 V3 版移植到 `plugins.v2/` 的代码改动：

- `from app.domain.context import MediaInfo` → `from app.core.context import MediaInfo`（GetMissingEpisodesMod）
- `from app.domain.meta.metabase import MetaBase` → `from app.core.meta import MetaBase`（GetMissingEpisodesMod）
- `from app.sdk.logging import logger` → `from app.log import logger`（MetaFiller）
- `from app.application.storage import StorageHelper` → `from app.helper.storage import StorageHelper`（CloudSubscribe）
- `from app.db.oper.downloadhistory import DownloadHistoryOper` → `from app.db.downloadhistory_oper import DownloadHistoryOper`（GetMissingEpisodesMod）
- `MediaServerItem.media_source/media_id` → `tmdbid`（GetMissingEpisodesMod，V2 模型字段差异）
- `MediaInfo.media_source = MediaSource.TMDB` → `MediaInfo.source = MediaSource.TMDB`（GetMissingEpisodesMod，V2 字段名差异）

验证：全部 import 与 V2 主程序（v2 分支）逐项核对通过，`py_compile` 无语法错误。
