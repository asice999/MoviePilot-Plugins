import copy
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from app.adapters.network.http import RequestUtils
from app.chain.download import DownloadChain
from app.chain.search import SearchChain
from app.chain.subscribe import SubscribeChain
from app.core.config import settings
from app.domain.context import MediaInfo
from app.domain.meta.metabase import MetaBase
from app.log import logger
from app.plugins import _PluginBase
from app.runtime.events import Event, eventmanager
from app.schemas.types import EventType, MediaSource, MediaType
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta
import pytz


def _num(value: Any) -> float:
    """容错取数值，下载器字段缺失/非数字时返回 0。"""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class MpMissingEpisodes(_PluginBase):
    """
    扫描媒体库剧集缺失，自动搜索下载补齐
    """
    # 插件名称
    plugin_name = "缺失剧集补齐（自用）"
    # 插件描述
    plugin_desc = "定时扫描媒体库剧集缺失情况，自动搜索资源下载补齐。支持全库扫描或指定剧集（TMDB ID）"
    # 插件图标
    plugin_icon = "MdiTelevisionPlay"
    # 插件版本
    plugin_version = "1.0.0"
    # 插件作者
    plugin_author = "asice999"
    author_url = "https://github.com/asice999"
    # 插件配置项ID前缀
    plugin_config_prefix = "mp_missing_episodes."
    # 加载顺序
    plugin_order = 20
    # 可使用的用户级别
    auth_level = 1

    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        # 直接用内置 vuetify 渲染，避免 federated 前端文件依赖
        return "vuetify", None

    def __init__(self):
        super().__init__()
        self._enabled = False
        self._config: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._rule_groups_cache = None
        self._rule_groups_cache_at = 0.0
        self._search_cache = {}
        self._stuck_snap = {}
        self._stuck_candidates = {}

    def init_plugin(self, config: dict = None):
        self._config = dict(config or {})
        self._enabled = bool(self._config.get("enabled"))
        self._rule_groups_cache = None
        self._rule_groups_cache_at = 0.0
        self._search_cache = {}
        self._stuck_snap = {}
        self._stuck_candidates = {}
        if self._enabled:
            logger.info("缺失剧集补齐插件已启用")

        # 立即运行一次
        if self._config.get("onlyonce"):
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(
                func=self._scan_and_download,
                trigger=DateTrigger(
                    run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=5)
                ),
                name="缺失剧集扫描（仅一次）",
            )
            logger.info("缺失剧集补齐插件将立即运行一次")
            self._config["onlyonce"] = False
            self.update_config(self._config)
            if self._scheduler.get_jobs():
                self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [{
            "cmd": "/scan_missing",
            "event": EventType.PluginAction,
            "desc": "扫描媒体库缺失剧集",
            "category": "媒体管理",
            "data": {"action": "scan_missing"}
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        return [{
            "path": "/scan",
            "endpoint": self._scan_and_download,
            "methods": ["GET", "POST"],
            "summary": "扫描媒体库缺失剧集",
            "description": "扫描媒体库缺失剧集并自动搜索下载",
        }, {
            "path": "/libraries",
            "endpoint": self._api_libraries,
            "methods": ["GET"],
            "summary": "获取媒体库列表",
            "description": "从 Emby 获取媒体库列表并刷新缓存",
        }]

    def _api_libraries(self) -> Dict[str, Any]:
        """
        API: 获取媒体库列表并刷新缓存
        """
        try:
            libraries = self._fetch_library_names(self._config)
            if libraries:
                self.save_data("library_cache", libraries)
            return {"success": True, "libraries": libraries}
        except Exception as e:
            logger.error(f"获取媒体库列表失败: {e}")
            return {"success": False, "libraries": [], "message": str(e)}

    def _fetch_library_names(self, config: Dict[str, Any]) -> List[str]:
        """
        从 Emby 获取媒体库名称列表
        """
        emby_url = (config.get("emby_url") or "").strip().rstrip("/")
        api_key = (config.get("emby_api_key") or "").strip()
        if not emby_url or not api_key:
            return []
        try:
            if not emby_url.endswith("/emby"):
                base = f"{emby_url}/emby"
            else:
                base = emby_url
            users = RequestUtils().get_json(f"{base}/Users", params={"api_key": api_key}) or []
            uid = None
            for user in users:
                if user.get("Policy", {}).get("IsAdministrator"):
                    uid = user.get("Id")
                    break
            if not uid and users:
                uid = users[0].get("Id")
            if not uid:
                return []
            views = RequestUtils().get_json(
                f"{base}/Users/{uid}/Views", params={"api_key": api_key}
            ) or {}
            names = []
            for view in views.get("Items", []):
                name = view.get("Name", "未命名媒体库")
                if name not in names:
                    names.append(name)
            logger.info(f"从Emby获取媒体库列表: {names}")
            return names
        except Exception as e:
            logger.error(f"获取媒体库列表失败: {e}")
            return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面
        """
        # 读取缓存的媒体库列表（若已配置Emby则尝试自动刷新）
        libraries = self.get_data("library_cache") or []
        if not libraries and (self._config.get("emby_url") and self._config.get("emby_api_key")):
            libraries = self._fetch_library_names(self._config)
            if libraries:
                self.save_data("library_cache", libraries)
        library_items = [{'title': lib, 'value': lib} for lib in libraries]
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'auto_download',
                                            'label': '自动搜索下载',
                                            'hint': '关闭时仅通知缺失情况'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify',
                                            'label': '消息通知',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'emby_url',
                                            'label': 'Emby/Jellyfin 地址',
                                            'placeholder': 'http://192.168.1.2:8096',
                                            'hint': '用于枚举媒体库剧集列表'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'emby_api_key',
                                            'label': 'Emby/Jellyfin API Key',
                                            'placeholder': 'API Key',
                                            'hint': '媒体库API密钥；可留空用系统媒体服务器配置'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'scan_mode',
                                            'label': '扫描范围',
                                            'items': [
                                                {'title': '全库扫描', 'value': 'all'},
                                                {'title': '仅指定剧集', 'value': 'list'}
                                            ]
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'tmdb_ids',
                                            'label': '指定剧集 TMDB ID',
                                            'placeholder': '如 46260,60735',
                                            'hint': '扫描范围为「仅指定剧集」时生效，逗号分隔'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'max_downloads',
                                            'label': '每次最多下载部数',
                                            'hint': '防止一次扫描触发过多下载'
                                        }
                                    },
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'use_subscribe_rules',
                                            'label': '启用默认订阅规则',
                                            'hint': '补漏搜索沿用系统默认订阅过滤规则组'
                                        }
                                    },
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'pending_future',
                                            'label': '未更新先挂起',
                                            'hint': '未播出的集先进入挂起池，不直接搜种'
                                        }
                                    },
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'pending_days',
                                            'label': '挂起检查间隔（天）',
                                            'placeholder': '7',
                                            'hint': '多久复查一次挂起池，默认7天'
                                        }
                                    },
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'stuck_timeout',
                                            'label': '卡死超时（小时）',
                                            'placeholder': '12',
                                            'hint': '进度N小时无变化判定为卡死，默认12'
                                        }
                                    },
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'blacklist_ttl',
                                            'label': '黑名单过期（小时）',
                                            'placeholder': '24',
                                            'hint': '卡死种子拉黑多久后自动恢复，默认24'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '保存后立即运行一次',
                                            'hint': '勾选后保存，插件立即扫描一次'
                                        }
                                    },
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'library_filter',
                                            'label': '选择要扫描的媒体库',
                                            'multiple': True,
                                            'items': library_items,
                                            'hint': '留空扫描全部；配置 Emby 后自动获取，也可在详情页刷新'
                                        }
                                    },
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '定时表达式',
                                            'placeholder': '0 4 * * *',
                                            'hint': 'Cron表达式，默认每天4点'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "auto_download": False,
            "notify": True,
            "emby_url": "",
            "emby_api_key": "",
            "scan_mode": "all",
            "tmdb_ids": "",
            "library_filter": [],
            "max_downloads": 5,
            "use_subscribe_rules": True,
            "pending_future": True,
            "pending_days": 7,
            "blacklist_ttl": 24,
            "stuck_check": True,
            "stuck_timeout": 12,
            "cron": "0 4 * * *",
            "onlyonce": False
        }

    def get_page(self) -> List[dict]:
        """
        拼装插件详情页，展示最近一次扫描结果
        """
        result = self.get_data("last_result") or []
        pending = self.get_data("last_pending_notes") or []
        missing_items = [
            {'component': 'VListItem', 'props': {'title': f"{i.get('title', '')} (TMDB:{i.get('tmdbid', '')})", 'subtitle': i.get('detail', '')}}
            for i in result
        ]
        pending_items = [
            {'component': 'VListItem', 'props': {'title': f"{i.get('title', '')} S{int(i.get('season', 0)):02d}", 'subtitle': f"未播出集 {i.get('episodes', [])} -> 已转订阅"}}
            for i in pending
        ]
        return [{
            'component': 'VCard',
            'content': [
                {'component': 'VCardTitle', 'props': {'text': '最近扫描结果'}},
                {'component': 'VCardText', 'content': [
                    {'component': 'VCardTitle', 'props': {'text': '缺失项'}},
                    {'component': 'VList', 'props': {'dense': True}, 'content': missing_items or [{'component': 'VListItem', 'props': {'title': '暂无缺失记录'}}]},
                    {'component': 'VDivider'},
                    {'component': 'VCardTitle', 'props': {'text': '已转订阅'}},
                    {'component': 'VList', 'props': {'dense': True}, 'content': pending_items or [{'component': 'VListItem', 'props': {'title': '暂无订阅记录'}}]}
                ]}
            ]
        }]

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        """
        if not self._enabled:
            return []
        cron = (self._config.get("cron") or "0 4 * * *").strip()
        services = [{
            "id": "MpMissingEpisodesScan",
            "name": "缺失剧集扫描",
            "trigger": CronTrigger.from_crontab(cron),
            "func": self._scan_and_download,
            "kwargs": {}
        }]
        if self._config.get("stuck_check", True):
            services.append({
                "id": "MpMissingStuckCheck",
                "name": "卡死种子检测",
                "trigger": CronTrigger.from_crontab("*/30 * * * *"),
                "func": self._check_stuck_downloads,
                "kwargs": {}
            })
        return services

    def stop_service(self):
        """
        停止插件
        """
        pass

    @eventmanager.register(EventType.PluginAction)
    def remote_action(self, event: Event):
        if event.event_data and event.event_data.get("action") == "scan_missing":
            self._scan_and_download()

    # ===================== 核心逻辑 =====================

    def _scan_and_download(self):
        """
        扫描缺失剧集并自动下载
        """
        if not self._enabled:
            return
        if not self._lock.acquire(blocking=False):
            logger.warning("上一次扫描仍在进行，跳过本次")
            return
        try:
            config = self._config
            self._pending_notes = []
            # 1. 枚举媒体库剧集
            series = self._list_series(config)
            if not series:
                logger.warning("未获取到媒体库剧集列表（检查Emby配置）")
                return
            # 2. 逐部检查缺失（按媒体库分组）
            missing = []
            for tmdbid, title, library in series:
                try:
                    no_exists = self._check_missing(tmdbid, title)
                except Exception as e:
                    logger.error(f"检查缺失失败 tmdb:{tmdbid} {title}: {e}")
                    continue
                if no_exists:
                    missing.append({"tmdbid": tmdbid, "title": title,
                                    "library": library, "no_exists": no_exists})
            if not missing:
                logger.info("媒体库剧集无缺失")
                self._finish([], None)
                return
            logger.info(f"发现 {len(missing)} 部剧集存在缺失: "
                        + ", ".join(f"{m['title']}({m['tmdbid']})" for m in missing))
            # 2.5 过滤下载器中正在下载的任务（避免重复搜索触发）
            missing = self._filter_downloading(missing)
            if not missing:
                logger.info("缺失剧集均在下载中，无需操作")
                self._finish(missing, None)
                return
                    
            pending_notes = []
            # 2.6 未更新先转订阅：未来集不搜种，只建立订阅池，等播出后自动回流
            pending_notes = []
            if config.get("pending_future", True):
                new_missing = []
                for item in missing:
                    keep_no_exists = {}
                    for mid, seasons in item["no_exists"].items():
                        keep_seasons = {}
                        for season, ne in seasons.items():
                            dl_ne, pend_ne = self._split_missing_future(item, season, ne)
                            if pend_ne:
                                self._add_pending_subscribe(item, season)
                                pending_notes.append({"title": item["title"], "tmdbid": item["tmdbid"], "season": season, "episodes": list(getattr(pend_ne, "episodes", []) or []), "library": item.get("library", "")})
                            if dl_ne:
                                keep_seasons[season] = dl_ne
                        if keep_seasons:
                            keep_no_exists[mid] = keep_seasons
                    if keep_no_exists:
                        new_missing.append({**item, "no_exists": keep_no_exists})
                if pending_notes:
                    logger.info(f"未更新集已转入订阅池，共 {sum(len(x['episodes']) for x in pending_notes)} 集")
                if len(new_missing) != len(missing):
                    logger.info(f"未更新订阅后，待下载缺失剧集 {len(missing)} -> {len(new_missing)}")
                missing = new_missing
            if not missing and not pending_notes:
                logger.info("缺失项全部已处理")
                self._finish([], None, [])
                return
            # 3. 自动下载
            downloaded = None
            if config.get("auto_download") and missing:
                downloaded = self._download_missing(missing, config)
            self._finish(missing, downloaded, pending_notes)

        except Exception as e:
            logger.error(f"扫描处理异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self._lock.release()

    def _list_series(self, config: Dict[str, Any]) -> List[Tuple[str, str, str]]:
        """
        从媒体服务器按媒体库枚举剧集列表，返回 [(tmdbid, title, library)]
        """
        emby_url = (config.get("emby_url") or "").strip().rstrip("/")
        api_key = (config.get("emby_api_key") or "").strip()
        if not emby_url or not api_key:
            logger.error("未配置 Emby 地址/API Key，无法枚举媒体库（可在插件配置中填写）")
            return []
        try:
            if not emby_url.endswith("/emby"):
                base = f"{emby_url}/emby"
            else:
                base = emby_url
            users = RequestUtils().get_json(f"{base}/Users", params={"api_key": api_key}) or []
            uid = None
            for user in users:
                if user.get("Policy", {}).get("IsAdministrator"):
                    uid = user.get("Id")
                    break
            if not uid and users:
                uid = users[0].get("Id")
            if not uid:
                logger.error("Emby 未获取到用户ID")
                return []
            # 媒体库（Views）列表
            views = RequestUtils().get_json(
                f"{base}/Users/{uid}/Views", params={"api_key": api_key}
            ) or {}
            libs = []
            for view in views.get("Items", []):
                libs.append({
                    "id": view.get("Id"),
                    "name": view.get("Name", "未命名媒体库")
                })
            # 媒体库过滤（兼容列表或逗号分隔字符串）
            raw_filter = config.get("library_filter") or []
            if isinstance(raw_filter, str):
                library_filter = [x.strip() for x in raw_filter.split(",") if x.strip()]
            else:
                library_filter = [str(x).strip() for x in raw_filter if str(x).strip()]
            if library_filter:
                libs = [lib for lib in libs if lib["name"] in library_filter]
                logger.info(f"媒体库过滤: {library_filter}")
            if not libs:
                logger.warning("未找到媒体库（检查Emby配置或过滤条件）")
                return []
            # 逐库枚举剧集
            series = []
            for lib in libs:
                data = RequestUtils().get_json(
                    f"{base}/Users/{uid}/Items",
                    params={"ParentId": lib["id"], "Recursive": "true",
                            "IncludeItemTypes": "Series", "Fields": "ProviderIds",
                            "api_key": api_key}
                ) or {}
                lib_series = []
                for item in data.get("Items", []):
                    provider = item.get("ProviderIds") or {}
                    tmdbid = provider.get("Tmdb")
                    if not tmdbid:
                        continue
                    lib_series.append((str(tmdbid), item.get("Name", ""), lib["name"]))
                if lib_series:
                    logger.info(f"媒体库[{lib['name']}]发现 {len(lib_series)} 部剧集")
                    series.extend(lib_series)
            logger.info(f"共枚举 {len(series)} 部剧集")
            # 过滤扫描范围
            scan_mode = config.get("scan_mode") or "all"
            if scan_mode == "list":
                ids = set(x.strip() for x in (config.get("tmdb_ids") or "").split(",") if x.strip())
                series = [s for s in series if s[0] in ids]
                logger.info(f"指定扫描 {len(series)} 部剧集: {ids}")
            return series
        except Exception as e:
            logger.error(f"枚举媒体库剧集失败: {e}")
            return []

    # 视为"正在下载"的 qB/TR 状态，只有这些状态才参与卡死判定
    _ACTIVE_STATES = {
        "downloading", "stalleddl", "metadl", "forceddl", "queueddl",
        "checkingdl", "allocating", "error", "missingfiles",
        "download pending", "downloading metadata",
    }
    # 每轮最多清理几个卡死种子，防止一次误判导致批量删除
    _MAX_STUCK_PER_RUN = 3

    def _check_stuck_downloads(self):
        """
        检测卡死种子：处于下载态、进度长时间零增长的任务，删除并拉黑（按 hash）
        重搜交给下次定时扫描，避免拿过期缺失清单狂试种子
        """
        try:
            download_chain = DownloadChain()
            # 全量取，因为 downloading() 只返回有速度的任务，停滞种子会被漏掉
            torrents = download_chain.list_torrents() or []
        except Exception as e:
            logger.error(f"获取下载器任务失败: {e}")
            return
        if not torrents:
            return
        timeout_s = max(0.5, float(self._config.get("stuck_timeout") or 12)) * 3600
        snap = self.get_data("stuck_snap") or {}
        cand = self.get_data("stuck_candidates") or {}
        now = time.time()
        alive_hashes = set()
        new_candidates = {}
        removed = []
        for t in torrents:
            h = getattr(t, "hash", None)
            if not h:
                continue
            progress = _num(getattr(t, "progress", 0))
            dlspeed = _num(getattr(t, "dlspeed", 0))
            state = str(getattr(t, "state", "") or "").strip().lower()
            name = getattr(t, "title", None) or getattr(t, "name", None) or h
            if progress >= 1 or state not in self._ACTIVE_STATES:
                snap.pop(h, None)
                cand.pop(h, None)
                continue
            alive_hashes.add(h)
            prev = snap.get(h)
            if not prev:
                snap[h] = {"p": progress, "since": now}
                cand.pop(h, None)
                continue
            if progress > prev.get("p", 0) or dlspeed > 0:
                snap[h] = {"p": progress, "since": now}
                cand.pop(h, None)
                continue
            stalled_for = now - prev.get("since", now)
            if stalled_for >= timeout_s:
                hit = int(cand.get(h, 0)) + 1
                if hit < 2:
                    new_candidates[h] = hit
                    logger.info(f"疑似卡死种子（第1次命中，观察下轮）: {name} (进度{progress:.0%}, 停滞{stalled_for / 3600:.1f}h)")
                    continue
                logger.warning(f"清理卡死种子: {name} "
                               f"(进度{progress:.0%}, 停滞{stalled_for / 3600:.1f}h, 状态{state})")
                try:
                    try:
                        download_chain.remove_torrents(h, delete_file=True)
                    except TypeError:
                        download_chain.remove_torrents([h], delete_file=True)
                except Exception as e:
                    logger.error(f"删除卡死种子失败 {h}: {e}")
                    continue
                self._blacklist_add(h, name)
                removed.append(name)
                snap.pop(h, None)
                cand.pop(h, None)
        for h in list(snap.keys()):
            if h not in alive_hashes:
                snap.pop(h, None)
                cand.pop(h, None)
        self.save_data("stuck_snap", snap)
        self.save_data("stuck_candidates", new_candidates)
        if removed:
            names = ", ".join(dict.fromkeys(removed))
            logger.info(f"已清理 {len(removed)} 个卡死种子: {names}；重搜交由下次定时扫描")
            if self._config.get("notify"):
                self.post_message(title=f"清理卡死种子 {len(removed)} 个", text=f"{names}\n\n已加入黑名单，下次扫描自动重搜其他资源")
        return

    # ---------- 黑名单：按 hash 存，带过期时间 ----------

    def _blacklist_load(self) -> Dict[str, Dict[str, Any]]:
        """
        读取黑名单并剔除过期项，返回 {hash: {"name": str, "until": float}}
        """
        raw = self.get_data("stuck_blacklist") or {}
        # 兼容旧版：曾按种子名存成 list
        if isinstance(raw, list):
            raw = {}
        ttl_h = float(self._config.get("blacklist_ttl") or 24)
        now = time.time()
        alive = {k: v for k, v in raw.items()
                 if isinstance(v, dict) and v.get("until", 0) > now}
        if len(alive) != len(raw):
            self.save_data("stuck_blacklist", alive)
            logger.info(f"黑名单清理过期项: {len(raw)} -> {len(alive)}（TTL {ttl_h}h）")
        return alive

    def _blacklist_add(self, torrent_hash: str, name: str):
        """
        将卡死种子按 hash 拉黑，默认 24 小时后自动过期
        """
        bl = self._blacklist_load()
        ttl_h = float(self._config.get("blacklist_ttl") or 24)
        bl[torrent_hash] = {"name": name, "until": time.time() + ttl_h * 3600}
        self.save_data("stuck_blacklist", bl)

    @staticmethod
    def _torrent_identity(context: Any) -> Tuple[Optional[str], str]:
        """
        从搜索结果 Context 里取 (种子hash/唯一串, 展示名)
        注意 V3 的 TorrentInfo 没有 name 字段，只有 title/enclosure
        """
        tinfo = getattr(context, "torrent_info", None)
        if not tinfo:
            return None, ""
        title = getattr(tinfo, "title", "") or ""
        enclosure = getattr(tinfo, "enclosure", "") or ""
        # 种子链接里通常带 hash，取末段做标识；退化时用标题
        ident = None
        if enclosure:
            tail = enclosure.rstrip("/").split("/")[-1].split("?")[0]
            if len(tail) >= 32:
                ident = tail.lower()
        return ident, title

    def _filter_blacklisted(self, contexts: List[Any]) -> List[Any]:
        """
        过滤黑名单命中的资源（hash 优先，退化到标题匹配）
        """
        bl = self._blacklist_load()
        if not bl or not contexts:
            return contexts
        bad_hashes = set(bl.keys())
        bad_names = {v.get("name", "") for v in bl.values() if v.get("name")}
        kept = []
        for c in contexts:
            ident, title = self._torrent_identity(c)
            if ident and ident in bad_hashes:
                logger.info(f"跳过黑名单种子(hash): {title or ident}")
                continue
            if title and title in bad_names:
                logger.info(f"跳过黑名单种子(名称): {title}")
                continue
            kept.append(c)
        return kept

    def _redownload_stuck(self, torrent: Any, blacklist: List[str]):
        """
        对卡死删除的任务重新搜索下载，过滤黑名单种子
        """
        media = torrent.media
        if isinstance(media, dict):
            mid = media.get("media_id")
            title = media.get("title", "")
        else:
            mid = getattr(media, "media_id", None) if media else None
            title = getattr(media, "title", "") if media else ""
        if not mid:
            logger.warning("卡死任务无媒体信息，跳过重搜（等下次扫描兜底）")
            return
        tmdbid = str(mid)
        try:
            no_exists = self._check_missing(tmdbid, title)
        except Exception as e:
            logger.error(f"重搜前检查缺失失败 tmdb:{tmdbid}: {e}")
            return
        if not no_exists:
            logger.info(f"tmdb:{tmdbid} 重搜检查无缺失，跳过")
            return
        search_chain = SearchChain()
        download_chain = DownloadChain()
        for mid, seasons in no_exists.items():
            for season, ne in seasons.items():
                try:
                    contexts = search_chain.search_by_id(
                        media_source=MediaSource.TMDB,
                        media_id=tmdbid,
                        mtype=MediaType.TV,
                        season=season
                    )
                    if not contexts:
                        logger.warning(f"重搜 tmdb:{tmdbid} S{season:02d} 未搜索到资源")
                        continue
                    # 过滤黑名单种子
                    filtered = []
                    for c in contexts:
                        tinfo = getattr(c, "torrent_info", None)
                        if not tinfo:
                            filtered.append(c)
                            continue
                        tname = getattr(tinfo, "title", "") or getattr(tinfo, "enclosure", "") or ""
                        if tname in blacklist:
                            logger.info(f"跳过黑名单种子: {tname}")
                            continue
                        filtered.append(c)
                    if not filtered:
                        logger.warning(f"重搜 tmdb:{tmdbid} S{season:02d} 剩余资源已被黑名单过滤，跳过")
                        continue
                    downloaded, remain = download_chain.batch_download(
                        contexts=filtered,
                        no_exists={mid: {season: ne}},
                        username="缺失剧集补齐"
                    )
                    lack = remain.get(mid, {}).get(season)
                    if lack is None or not lack.episodes:
                        logger.info(f"卡死重下成功: {title} S{season:02d}")
                    else:
                        logger.info(f"卡死重下部分成功，剩余: {lack.episodes}")
                except Exception as e:
                    logger.error(f"卡死重搜失败 tmdb:{tmdbid} S{season}: {e}")

    def _filter_downloading(self, missing: List[Dict]) -> List[Dict]:
        """
        过滤掉下载器中已有任务（下载中+已完成待入库/已入库），按 tmdbid+season 粒度
        """
        try:
            torrents = DownloadChain().list_torrents() or []
        except Exception as e:
            logger.error(f"获取下载器任务失败: {e}")
            return missing
        if not torrents:
            return missing

        # 下载历史：用于把“已完成但 media 信息丢失”的任务还原成 tmdb/season
        try:
            from app.db.oper.downloadhistory import DownloadHistoryOper
        except Exception:
            DownloadHistoryOper = None
        history_map = {}
        if DownloadHistoryOper:
            hashes = [t.hash for t in torrents if getattr(t, 'hash', None)]
            try:
                history_map = DownloadHistoryOper().get_by_hashes(hashes) if hashes else {}
            except Exception as e:
                logger.error(f"获取下载历史失败: {e}")
                history_map = {}


        def _norm_mid(v: Any) -> Optional[str]:
            if v is None:
                return None
            s = str(v).strip()
            if not s:
                return None
            if ":" in s:
                s = s.split(":", 1)[1]
            return s if s.isdigit() else None

        def _norm_seasons(v: Any) -> List[int]:
            if isinstance(v, int):
                return [v]
            if isinstance(v, str):
                return [int(x) for x in v.split(',') if x.strip().isdigit()]
            if isinstance(v, (list, tuple, set)):
                return [int(x) for x in v if str(x).strip().isdigit()]
            return []

        keys = set()
        for t in torrents:
            mid = None
            seasons = []
            media = getattr(t, 'media', None)
            if isinstance(media, dict):
                mid = _norm_mid(media.get('media_id'))
                seasons = _norm_seasons(media.get('season'))
            else:
                mid = _norm_mid(getattr(media, 'media_id', None) if media else None)
                seasons = _norm_seasons(getattr(media, 'season', None) if media else None)
            hist = history_map.get(getattr(t, 'hash', None))
            if hist and not mid:
                mid = _norm_mid(getattr(hist, 'media_id', None))
                seasons = _norm_seasons(getattr(hist, 'seasons', None))
            if not mid or not seasons:
                continue
            for s in seasons:
                keys.add((mid, int(s)))

        if not keys:
            return missing

        before = len(missing)
        result = []
        for item in missing:
            kept = {}
            for mid_key, seasons in item["no_exists"].items():
                key_mid = mid_key.split(":", 1)[1] if ":" in mid_key else mid_key
                kept_seasons = {}
                for season, ne in seasons.items():
                    key = (key_mid, int(season))
                    if key in keys:
                        logger.info(f"跳过已在下载器中/历史中存在的: {item['title']} S{season:02d}")
                        continue
                    kept_seasons[season] = ne
                if kept_seasons:
                    kept[mid_key] = kept_seasons
            if kept:
                result.append({**item, "no_exists": kept})
        removed = before - len(result)
        if removed:
            logger.info(f"过滤下载器+历史后，缺失剧集 {before} -> {len(result)}（跳过 {removed} 部）")
        return result

    def _check_missing(self, tmdbid: str, title: str) -> Dict:
        """
        检查单部剧集缺失情况，返回 no_exists（空字典=无缺失）
        """
        mediainfo = MediaInfo()
        mediainfo.type = MediaType.TV
        mediainfo.media_source = MediaSource.TMDB
        mediainfo.media_id = str(tmdbid)
        mediainfo.tmdb_id = int(tmdbid)
        mediainfo.title = title
        meta = MetaBase(title=title)
        flag, no_exists = DownloadChain().get_no_exists_info(meta=meta, mediainfo=mediainfo)
        no_exists = no_exists or {}
        # 跳过 S00 特别篇/花絮季
        for mid_key in list(no_exists.keys()):
            seasons = no_exists[mid_key]
            s00 = seasons.pop(0, None)
            if s00 is not None:
                logger.info(f"跳过S00特别篇/花絮: {title} (tmdb:{tmdbid})")
            if not seasons:
                del no_exists[mid_key]
        return no_exists

    def _subscribe_rule_groups(self) -> Optional[List[str]]:
        """
        读取系统默认订阅过滤规则组（做短缓存，避免每次扫描都打配置表）
        """
        now = time.time()
        if self._rule_groups_cache is not None and now - self._rule_groups_cache_at < 300:
            return self._rule_groups_cache
        try:
            from app.chain.subscribe import _system_config
            from app.schemas.types import SystemConfigKey
            groups = _system_config().get(SystemConfigKey.SubscribeFilterRuleGroups)
            if not groups:
                self._rule_groups_cache = None
            elif isinstance(groups, str):
                self._rule_groups_cache = [x.strip() for x in groups.split(",") if x.strip()]
            else:
                self._rule_groups_cache = [str(x) for x in groups if str(x).strip()]
            self._rule_groups_cache_at = now
            logger.info(f"默认订阅规则组缓存: {self._rule_groups_cache}")
            return self._rule_groups_cache
        except Exception as e:
            logger.error(f"读取默认订阅规则组失败: {e}")
            return None

    def _search_with_rules(self, search_chain, tmdbid: str, title: str, mid: Any,
                           season: int, ne: Any,
                           rule_groups: Optional[List[str]]) -> List[Any]:
        """
        按默认订阅规则组搜索资源（走 SearchChain.process，支持 rule_groups）
        """
        mediainfo = MediaInfo()
        mediainfo.type = MediaType.TV
        mediainfo.media_source = MediaSource.TMDB
        mediainfo.media_id = str(tmdbid)
        mediainfo.tmdb_id = int(tmdbid)
        mediainfo.title = title
        return search_chain.process(
            mediainfo=mediainfo,
            no_exists={mid: {season: ne}},
            rule_groups=rule_groups
        ) or []

    def _search_cached(self, search_chain, tmdbid: str, title: str, mid: Any,
                       season: int, ne: Any, use_sub_rules: bool,
                       rule_groups: Optional[List[str]]) -> List[Any]:
        """
        季级搜索结果缓存，避免同一季重复搜站点
        """
        key = (str(tmdbid), int(season), bool(use_sub_rules), tuple(rule_groups or ()))
        if key in self._search_cache:
            return self._search_cache[key]
        if use_sub_rules:
            contexts = self._search_with_rules(search_chain, tmdbid, title, mid, season, ne, rule_groups)
        else:
            contexts = search_chain.search_by_id(
                media_source=MediaSource.TMDB,
                media_id=str(tmdbid),
                mtype=MediaType.TV,
                season=season
            )
        self._search_cache[key] = contexts or []
        # 控制缓存体积
        if len(self._search_cache) > 120:
            self._search_cache.clear()
        return self._search_cache[key]

    def _pending_load(self) -> Dict[str, Any]:
        """读取未更新挂起池。"""
        return self.get_data("pending_future_pool") or {"items": []}

    def _pending_save(self, pool: Dict[str, Any]):
        """保存未更新挂起池。"""
        self.save_data("pending_future_pool", pool)

    def _tmdb_episode_dates(self, tmdbid: str, season: int) -> Dict[int, Optional[str]]:
        """
        获取季级每集播出日期；拿不到就返回空字典。
        """
        try:
            info = DownloadChain().tmdb_info(int(tmdbid), MediaType.TV, season)
        except Exception as e:
            logger.error(f"获取TMDB播出日期失败 tmdb:{tmdbid} S{season}: {e}")
            return {}
        if not info:
            return {}
        eps = {}
        for ep in info.get("episodes", []) or []:
            n = ep.get("episode_number")
            d = ep.get("air_date")
            if n and str(n).isdigit():
                eps[int(n)] = d
        return eps

    def _split_missing_future(self, item: Dict, season: int, ne: Any) -> tuple[Optional[Dict], Optional[Dict]]:
        """
        把未播出集从缺失集中拆出来，返回 (可下载缺失, 未播出挂起)
        """
        dates = self._tmdb_episode_dates(item["tmdbid"], season)
        if not dates:
            return ne, None
        today = datetime.now().date()
        download_ne = copy.deepcopy(ne)
        future_eps = []
        # 只处理列表式 episodes 的情况；若结构异常就直接不拆
        try:
            if not hasattr(download_ne, "episodes"):
                return ne, None
            eps = list(download_ne.episodes or [])
            kept = []
            for ep in eps:
                ad = dates.get(int(ep))
                if ad:
                    try:
                        ad_date = datetime.strptime(ad, "%Y-%m-%d").date()
                    except Exception:
                        kept.append(ep)
                        continue
                    if ad_date > today:
                        future_eps.append(ep)
                        continue
                kept.append(ep)
            download_ne.episodes = kept
            if future_eps:
                pend = copy.deepcopy(ne)
                pend.episodes = future_eps
                return download_ne if kept else None, pend
        except Exception as e:
            logger.error(f"拆分未播出集失败 tmdb:{item['tmdbid']} S{season}: {e}")
        return ne, None

    def _pending_append(self, item: Dict, season: int, ne: Any):
        """追加到未更新挂起池。"""
        pool = self._pending_load()
        pool.setdefault("items", [])
        pool["items"].append({
            "tmdbid": item["tmdbid"],
            "title": item["title"],
            "library": item.get("library", ""),
            "season": season,
            "no_exists": ne.episodes if hasattr(ne, "episodes") else [],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        self._pending_save(pool)

    def _pending_exists(self, item: Dict, season: int) -> bool:
        """判断未播出集是否已在订阅池中。"""
        try:
            mediainfo = MediaInfo()
            mediainfo.type = MediaType.TV
            mediainfo.media_source = MediaSource.TMDB
            mediainfo.media_id = str(item["tmdbid"])
            mediainfo.tmdb_id = int(item["tmdbid"])
            mediainfo.title = item["title"]
            meta = MetaBase(title=item["title"])
            meta.begin_season = season
            return SubscribeChain.exists(mediainfo=mediainfo, meta=meta)
        except Exception as e:
            logger.error(f"检查订阅是否存在失败 tmdb:{item.get('tmdbid')} S{season}: {e}")
            return False

    def _add_pending_subscribe(self, item: Dict, season: int):
        """
        把未播出季直接放入订阅池；已存在则跳过。
        """
        if self._pending_exists(item, season):
            logger.info(f"未播出集已在订阅池，跳过: {item['title']} S{season:02d}")
            return
        try:
            title = item["title"]
            year = ""
            if "(" in title and ")" in title:
                year = title.rsplit("(", 1)[-1].split(")", 1)[0]
            sid, msg = SubscribeChain().add(title=title, year=year, mtype=MediaType.TV, season=season, media_source=MediaSource.TMDB, media_id=str(item["tmdbid"]), message=False, exist_ok=True, username="缺失剧集补齐")
            if sid:
                logger.info(f"未播出集已转订阅: {title} S{season:02d} -> 订阅#{sid}")
            else:
                logger.info(f"未播出集转订阅跳过: {title} S{season:02d}，原因：{msg}")
        except Exception as e:
            logger.error(f"未播出集转订阅失败 tmdb:{item.get('tmdbid')} S{season}: {e}")

    def _download_missing(self, missing: List[Dict], config: Dict[str, Any]) -> List[str]:
        """
        对缺失剧集逐季搜索并批量下载，返回已下载描述列表
        """
        max_downloads = int(config.get("max_downloads") or 5)
        search_chain = SearchChain()
        download_chain = DownloadChain()
        # 是否套用系统默认订阅过滤规则组（与订阅下载口味保持一致）
        use_sub_rules = bool(config.get("use_subscribe_rules", True))
        rule_groups = self._subscribe_rule_groups() if use_sub_rules else None
        if use_sub_rules:
            logger.info(f"使用默认订阅过滤规则组: {rule_groups or '（系统未配置，退化为默认搜索规则）'}")
        results = []
        for item in missing[:max_downloads]:
            tmdbid = item["tmdbid"]
            no_exists = item["no_exists"]
            logger.info(f"开始搜索下载缺失剧集: {item['title']} (tmdb:{tmdbid})")
            for mid, seasons in no_exists.items():
                for season, ne in seasons.items():
                    try:
                        contexts = self._search_cached(
                            search_chain=search_chain,
                            tmdbid=tmdbid,
                            title=item["title"],
                            mid=mid,
                            season=season,
                            ne=ne,
                            use_sub_rules=use_sub_rules,
                            rule_groups=rule_groups,
                        )
                        if not contexts:
                            logger.warning(f"tmdb:{tmdbid} S{season:02d} 未搜索到资源")
                            continue
                        contexts = self._filter_blacklisted(contexts)
                        if not contexts:
                            logger.warning(f"tmdb:{tmdbid} S{season:02d} 剩余资源已被黑名单过滤，跳过")
                            continue
                        downloaded, remain = download_chain.batch_download(
                            contexts=contexts,
                            no_exists={mid: {season: ne}},
                            username="缺失剧集补齐"
                        )
                        lack = remain.get(mid, {}).get(season)
                        if lack is None or not lack.episodes:
                            results.append(f"{item['title']} S{season:02d} 已补齐")
                        else:
                            results.append(f"{item['title']} S{season:02d} 缺{lack.episodes}")
                    except Exception as e:
                        logger.error(f"下载失败 tmdb:{tmdbid} S{season}: {e}")
        return results
    def _finish(self, missing: List[Dict], downloaded: Optional[List[str]]):
        """
        保存结果并通知
        """
        result = []
        for item in missing:
            detail = ""
            no_exists = item["no_exists"]
            for mid, seasons in no_exists.items():
                parts = []
                for season, ne in seasons.items():
                    eps = ne.episodes
                    parts.append(f"S{season:02d}" + (f" 缺{eps}" if eps else " 整季缺"))
                detail += "；".join(parts)
            result.append({"tmdbid": item["tmdbid"], "title": item["title"],
                           "library": item.get("library", ""), "detail": detail})
        self.save_data("last_result", result)
        if not self._config.get("notify"):
            return
        if not missing:
            self.post_message(title="缺失剧集补齐", text="媒体库剧集无缺失，全部已齐")
            return
        if not result:
            self.post_message(title="缺失剧集补齐", text="暂无需要处理的缺失项")
            return
        # 按媒体库分组
        by_lib = {}
        for r in result:
            lib = r.get("library") or "未分类"
            by_lib.setdefault(lib, []).append(r)
        lines = []
        for lib, items in by_lib.items():
            lines.append(f"【{lib}】")
            for r in items:
                lines.append(f"  {r['title']} (TMDB:{r['tmdbid']})：{r['detail']}")
        text = "\n".join(lines)
        if downloaded:
            text += f"\n\n已下载：\n" + "\n".join(downloaded)
        else:
            text += "\n\n未启用自动下载，手动触发请发送 /scan_missing 或到插件页点击扫描"
        self.post_message(title=f"缺失剧集补齐：更新 {len(result)} 部", text=text)