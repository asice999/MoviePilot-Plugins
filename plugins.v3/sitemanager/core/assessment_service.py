from .service_adapter import ServiceAdapter
"""
站点考核状态插件
自动获取站点考核情况并在仪表板显示
"""
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from lxml import etree

from app.core.config import settings
from app.core.event import eventmanager, Event
from app.db.site_oper import SiteOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.utils.http import RequestUtils
from html import unescape


class SiteAssessment(ServiceAdapter):
    """站点考核状态插件"""

    # 插件名称
        # 插件描述
    plugin_desc = "自用：自动获取站点考核情况并在仪表板显示，支持考核临近时发送通知。"
    # 插件图标
        # 插件版本
        # 插件作者
    plugin_author = "asice999"
    # 作者主页
    author_url = "https://github.com/asice999"
    # 插件配置项ID前缀
        # 加载顺序
    plugin_order = 10
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _enabled: bool = False
    _onlyonce: bool = False
    _cron: str = ""
    _notify: bool = False
    _notify_days: int = 3
    _selected_sites: List[int] = []
    _scheduler: Optional[BackgroundScheduler] = None
    _cached_statuses: List[Dict[str, Any]] = []  # 缓存的考核状态数据

    # 文件大小单位转换（转为字节）
    _SIZE_UNITS: Dict[str, float] = {
        # 十进制单位
        'B': 1,
        'KB': 1024,
        'MB': 1024 ** 2,
        'GB': 1024 ** 3,
        'TB': 1024 ** 4,
        'PB': 1024 ** 5,
        # 二进制单位
        'KIB': 1024,
        'MIB': 1024 ** 2,
        'GIB': 1024 ** 3,
        'TIB': 1024 ** 4,
        'PIB': 1024 ** 5,
    }

    # 时间单位转换（转为小时）
    _TIME_UNITS: Dict[str, float] = {
        '秒': 1 / 3600, 'S': 1 / 3600, 'SEC': 1 / 3600, 'SECOND': 1 / 3600, 'SECONDS': 1 / 3600,
        '分': 1 / 60, 'M': 1 / 60, 'MIN': 1 / 60, 'MINUTE': 1 / 60, 'MINUTES': 1 / 60, '分钟': 1 / 60, '分鐘': 1 / 60,
        '时': 1, 'H': 1, 'HR': 1, 'HRS': 1, 'HOUR': 1, 'HOURS': 1, '小时': 1, '小時': 1,
        '天': 24, 'D': 24, 'DAY': 24, 'DAYS': 24, '日': 24,
        '周': 24 * 7, 'W': 24 * 7, 'WEEK': 24 * 7, 'WEEKS': 24 * 7, '週': 24 * 7,
        '月': 24 * 30, 'MONTH': 24 * 30, 'MONTHS': 24 * 30, '個月': 24 * 30,
        '年': 24 * 365, 'Y': 24 * 365, 'YEAR': 24 * 365, 'YEARS': 24 * 365,
    }

    # 考核相关关键词（用于识别考核区块）
    _ASSESSMENT_KEYWORDS: Tuple[str, ...] = (
        # 简体
        '考核', '新手任务', '养成期', '试用期', '观察期', '新人任务',
        '保号', '活跃度', '做种任务', '上传任务', '魔力任务',
        '试炼', '分支任务', '挑战任务', '成就任务',
        # 繁体
        '養成期', '試用期', '觀察期', '新人任務', '做種任務', '上傳任務', '魔力任務',
        '試煉', '分支任務', '挑戰任務', '成就任務',
        # 英文
        'assessment', 'probation', 'trial', 'newbie', 'requirement', 'quest', 'mission',
    )

    # 考核指标名称关键词（用于识别指标类型）
    _METRIC_KEYWORDS: Dict[str, Tuple[str, ...]] = {
        'upload': ('上传', '上傳', 'upload', '上传量', '上傳量', '上传增量', '上傳增量'),
        'download': ('下载', '下載', 'download', '下载量', '下載量', '下载增量', '下載增量'),
        'ratio': ('分享率', '分享比', '比率', 'ratio', 'share ratio'),
        'bonus': ('魔力', '积分', '魔力值', '積分', 'bonus', 'points', 'karma', 'credits', '魔力增量', '做种积分', '做種積分'),
        'seeding': ('做种', '做種', '保种', '保種', 'seeding', 'seed', '做种量', '做種量'),
        'seedtime': ('做种时间', '做種時間', '保种时间', '保種時間', 'seed time', 'seeding time', '做种时长', '做種時長'),
        'seedsize': ('做种体积', '做種體積', '保种体积', '保種體積', 'seeding size'),
        'torrents': ('发布数', '發布數', '发种数', '發種數'),
        'invites': ('邀请', '邀請', 'invite', '邀请数', '邀請數'),
    }

    # 有效的考核指标名称（精确匹配，用于严格模式）
    # 注意：这些名称必须是考核特有的，避免与站点统计混淆
    _VALID_METRIC_NAMES: Tuple[str, ...] = (
        # 上传相关（考核常用）
        '上传量', '上傳量', '上传增量', '上傳增量',
        # 下载相关（考核常用）
        '下载量', '下載量', '下载增量', '下載增量',
        # 分享率
        '分享率', '分享比',
        # 魔力/积分（考核常用）
        '魔力', '魔力值', '魔力增量',
        '积分', '積分', '积分增量',
        '做种积分', '做種積分', '做种积分增量',
        # 做种时间（考核常用）
        '做种时间', '做種時間', '做种时长', '做種時長',
        '保种时间', '保種時間',
        # 做种体积
        '做种体积', '做種體積', '保种体积', '保種體積',
    )

    # 无效指标名称（黑名单，用于排除）
    _INVALID_METRIC_PATTERNS: Tuple[str, ...] = (
        # 站点统计信息
        '注册用户', '註冊用戶', '访问用户', '訪問用戶', '当前访问', '當前訪問',
        '种子总', '種子總', '总上传', '總上傳', '总下载', '總下載', '总数据', '總數據',
        '贵宾', '貴賓', '被警告', '被禁', '男生', '女生', '断种', '斷種',
        '同伴', 'tracker', 'Tracker',
        # 用户等级
        'Peasant', 'User', 'Power User', 'Elite', 'Crazy', 'Insane', 'Veteran', 'Extreme', 'Ultimate', 'Master',
        # 版块/帖子
        '版块', '版塊', 'Feedback', 'Appeal', 'Record',
        # 种子标题特征
        '1080p', '2160p', '4K', 'BluRay', 'Blu-ray', 'WEB-DL', 'REMUX', 'HDR', 'DoVi',
        'H.264', 'H.265', 'HEVC', 'AVC', 'DTS', 'AAC', 'FLAC', 'Atmos',
        '导演', '主演', '类别', '國語', '国语', '中字', '字幕',
        # 投票选项
        '弃权', '棄權', '是，', '否，',
        # 时间标签（非指标）
        '开注时间', '開注時間', '发邀时间', '發邀時間',
        # 公告信息
        '招聘', '解封', '申诉', '申訴', 'QQ群', 'TG群', 'PM管理',
    )

    # 考核区块结束标记
    _ASSESSMENT_END_MARKERS: Tuple[str, ...] = (
        '最新种子', '最新發布', '最新帖子', '论坛', '論壇', '公告', '公告栏',
        '热门', '熱門', '推荐', '推薦', '排行', '榜单', '榜單',
        '友情链接', '友情連結', '站点统计', '站點統計',
        '版权', '版權', 'Copyright', '©',
    )

    # 支持的日期时间格式
    _DATETIME_FORMATS: Tuple[str, ...] = (
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y/%m/%d %H:%M:%S',
        '%Y/%m/%d %H:%M',
        '%Y.%m.%d %H:%M:%S',
        '%Y.%m.%d %H:%M',
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%Y.%m.%d',
    )

    # 状态关键词映射（简繁体）- 注意：否定词必须在肯定词之前检查
    _STATUS_KEYWORDS: Dict[str, bool] = {
        # 否定词（必须先检查）
        '未通过': False, '未通過': False, '不合格': False,
        '失敗': False, '失败': False, '未達標': False, '未达标': False,
        '未完成': False, '未達成': False, '未达成': False,
        'fail': False, 'failed': False, 'incomplete': False,
        # 肯定词
        '已通过': True, '已通過': True, '已完成': True,
        '已達標': True, '已达标': True, '已達成': True, '已达成': True,
        '通过': True, '通過': True, '合格': True,
        '達標': True, '达标': True, '達成': True, '达成': True,
        '完成': True, 'pass': True, 'passed': True, 'complete': True,
    }

    # 通过/未通过图标映射
    _STATUS_ICONS: Dict[str, bool] = {
        # 通过图标
        '✓': True, '✔': True, '√': True, '☑': True, '✅': True,
        '⭕': True, '🟢': True, '🟩': True,
        # 未通过图标
        '✗': False, '✘': False, '×': False, '☒': False, '❌': False,
        '⭙': False, '🔴': False, '🟥': False,
    }

    def init_plugin(self, config: dict = None):
        """初始化插件"""
        self.stop_service()

        if config:
            self._enabled = config.get("enabled", False)
            self._onlyonce = config.get("onlyonce", False)
            self._cron = config.get("cron", "")
            self._notify = config.get("notify", False)
            self._notify_days = config.get("notify_days", 3)
            self._selected_sites = config.get("selected_sites", [])

        # 从数据库加载缓存数据
        self._cached_statuses = self.get_data('cached_statuses') or []

        if self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(
                func=self.__refresh_assessment,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name="站点考核状态刷新"
            )
            self._scheduler.start()
            # 关闭一次性开关
            self._onlyonce = False
            self.__update_config()

    def get_state(self) -> bool:
        """获取插件状态"""
        return self._enabled

    def __update_config(self):
        """更新配置"""
        self.update_config({
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "cron": self._cron,
            "notify": self._notify,
            "notify_days": self._notify_days,
            "selected_sites": self._selected_sites,
        })

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """定义远程控制命令"""
        return [{
            "cmd": "/site_assessment",
            "event": EventType.PluginAction,
            "desc": "刷新站点考核状态",
            "category": "站点",
            "data": {"action": "site_assessment"}
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        """获取插件API"""
        return [{
            "path": "/assessment_status",
            "endpoint": self.get_assessment_status,
            "methods": ["GET"],
            "summary": "获取站点考核状态",
            "description": "获取所有配置站点的考核状态",
        }]

    def get_service(self) -> List[Dict[str, Any]]:
        """注册插件公共服务"""
        if self._enabled and self._cron:
            try:
                return [{
                    "id": "SiteAssessment",
                    "name": "站点考核状态刷新",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.__refresh_assessment,
                    "kwargs": {}
                }]
            except Exception as e:
                logger.error(f"站点考核状态服务配置错误: {e}")
        return []

    def stop_service(self):
        """停止服务"""
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error(f"停止站点考核状态服务失败: {e}")

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """拼装插件配置页面"""
        # 获取站点列表
        site_options = [
            {"title": site.name, "value": site.id}
            for site in SiteOper().list_order_by_pri()
        ]
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'enabled', 'label': '启用插件'}
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'notify', 'label': '发送通知'}
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'onlyonce', 'label': '立即运行一次'}
                                }]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [{
                                    'component': 'VCronField',
                                    'props': {
                                        'model': 'cron',
                                        'label': '执行周期',
                                        'placeholder': '5位cron表达式'
                                    }
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [{
                                    'component': 'VTextField',
                                    'props': {
                                        'model': 'notify_days',
                                        'label': '提前通知天数',
                                        'type': 'number'
                                    }
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [{
                                    'component': 'VSelect',
                                    'props': {
                                        'model': 'selected_sites',
                                        'label': '选择考核站点',
                                        'items': site_options,
                                        'multiple': True,
                                        'chips': True,
                                        'clearable': True
                                    }
                                }]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [{
                            'component': 'VCol',
                            'props': {'cols': 12},
                            'content': [{
                                'component': 'VAlert',
                                'props': {
                                    'type': 'info',
                                    'variant': 'tonal',
                                    'text': '使用说明：选择需要监控的站点（留空则检查全部站点），插件会自动抓取站点首页的考核信息'
                                }
                            }]
                        }]
                    }
                ]
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "cron": "0 8 * * *",
            "notify": True,
            "notify_days": 3,
            "selected_sites": [],
        }

    def get_page(self) -> List[dict]:
        """插件详情页面 - 显示考核状态（读取缓存数据）"""
        statuses = self._cached_statuses
        if not statuses:
            return [{
                'component': 'div',
                'text': '暂无数据，请先启用插件并运行一次刷新',
                'props': {'class': 'text-center pa-4'}
            }]

        # 构建表格行
        table_rows = []
        for status in statuses:
            color = self.__get_status_color(status['status'])
            status_text = {'completed': '已通过', 'in_progress': '考核中',
                          'failed': '未通过', 'unknown': '未知'}.get(status['status'], '未知')

            table_rows.append({
                'component': 'tr',
                'props': {'class': 'text-sm'},
                'content': [
                    {'component': 'td', 'props': {'class': 'whitespace-nowrap'},
                     'text': status['site_name']},
                    {'component': 'td', 'props': {'class': f'text-{color}'},
                     'text': status_text},
                    {'component': 'td', 'text': f"{status['progress']*100:.0f}%"},
                    {'component': 'td',
                     'text': f"{status['remaining_days']}天" if status.get('remaining_days') is not None else '-'},
                    {'component': 'td', 'props': {'class': 'text-caption'},
                     'text': status.get('message', '')}
                ]
            })

        return [{
            'component': 'VTable',
            'props': {'hover': True},
            'content': [
                {
                    'component': 'thead',
                    'content': [
                        {'component': 'th', 'text': '站点'},
                        {'component': 'th', 'text': '状态'},
                        {'component': 'th', 'text': '进度'},
                        {'component': 'th', 'text': '剩余'},
                        {'component': 'th', 'text': '详情'}
                    ]
                },
                {
                    'component': 'tbody',
                    'content': table_rows
                }
            ]
        }]

    def get_dashboard(self, key: str = None, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], List[dict]]]:
        """获取仪表板组件（读取缓存数据）"""
        statuses = self._cached_statuses
        if not statuses:
            return None

        elements = []
        for status in statuses:
            color = self.__get_status_color(status['status'])
            elements.append(self.__build_status_card(status, color))

        return (
            {"cols": 12, "md": 12},
            {"refresh": 3600},
            [{'component': 'VRow', 'content': elements}]
        )

    def __build_status_card(self, status: Dict, color: str) -> Dict:
        """构建单个状态卡片"""
        return {
            'component': 'VCol',
            'props': {'cols': 12, 'md': 6, 'lg': 4},
            'content': [{
                'component': 'VCard',
                'props': {'variant': 'outlined', 'class': 'mb-2'},
                'content': [
                    {
                        'component': 'VCardTitle',
                        'props': {'class': f'text-{color}'},
                        'text': status['site_name']
                    },
                    {
                        'component': 'VCardText',
                        'content': [
                            {
                                'component': 'VProgressLinear',
                                'props': {
                                    'model-value': status['progress'] * 100,
                                    'color': color,
                                    'height': 20,
                                    'rounded': True
                                }
                            },
                            {
                                'component': 'div',
                                'props': {'class': 'mt-2'},
                                'text': f"进度: {status['progress']*100:.1f}%"
                            },
                            {
                                'component': 'div',
                                'text': f"剩余: {status['remaining_days']}天" if status.get('remaining_days') else "无期限"
                            },
                            {
                                'component': 'div',
                                'props': {'class': 'text-caption'},
                                'text': status.get('message', '')
                            }
                        ]
                    }
                ]
            }]
        }

    @staticmethod
    def __get_status_color(status: str) -> str:
        """根据状态返回颜色"""
        color_map = {
            'completed': 'success',
            'in_progress': 'warning',
            'failed': 'error',
            'info': 'primary',
            'unknown': 'grey'
        }
        return color_map.get(status, 'grey')

    def get_assessment_status(self) -> List[Dict[str, Any]]:
        """API: 获取考核状态（读取缓存数据）"""
        return self._cached_statuses

    def __refresh_assessment(self):
        """刷新考核状态并发送通知"""
        logger.info("开始刷新站点考核状态...")
        statuses = self.__calculate_all_status()

        # 更新内存缓存
        self._cached_statuses = statuses

        # 持久化到数据库
        self.save_data('cached_statuses', statuses)

        if self._notify and statuses:
            for status in statuses:
                self.__check_and_notify(status)

        logger.info(f"站点考核状态刷新完成，共{len(statuses)}个站点")

    def __check_and_notify(self, status: Dict[str, Any]):
        """检查并发送通知"""
        remaining = status.get('remaining_days')
        if remaining is None:
            return

        if status['status'] == 'in_progress' and remaining <= self._notify_days:
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title=f"【站点考核提醒】{status['site_name']}",
                text=f"考核剩余 {remaining} 天\n"
                     f"当前进度: {status['progress']*100:.1f}%\n"
                     f"{status.get('message', '')}"
            )
        elif status['status'] == 'failed':
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title=f"【站点考核失败】{status['site_name']}",
                text=f"考核已超期！\n{status.get('message', '')}"
            )

    def __calculate_all_status(self) -> List[Dict[str, Any]]:
        """计算所有站点的考核状态，只返回检测到考核的站点"""
        statuses = []

        # 获取所有站点信息
        all_sites = {site.id: site for site in SiteOper().list_order_by_pri()}

        # 确定目标站点（留空则检查全部站点）
        if self._selected_sites:
            # 确保类型一致（转为整数）
            target_sites = [int(sid) for sid in self._selected_sites if sid]
            logger.info(f"已选择 {len(target_sites)} 个站点进行考核检查")
        else:
            target_sites = list(all_sites.keys())
            logger.info(f"未选择站点，检查全部 {len(target_sites)} 个站点")

        for site_id in target_sites:
            site = all_sites.get(site_id)
            if not site:
                continue
            try:
                status = self.__calculate_site_status(site)
                # 只添加检测到考核的站点
                if status:
                    statuses.append(status)
            except Exception as e:
                logger.error(f"计算站点 {site.name} 考核状态失败: {e}")

        return statuses

    def __calculate_site_status(self, site) -> Optional[Dict[str, Any]]:
        """计算站点考核状态（通过抓取站点首页获取考核信息）"""
        site_id = site.id
        site_name = site.name

        # 抓取站点首页考核信息
        return self.__build_info_status(site_id, site_name)

    def __build_info_status(self, site_id: int, site_name: str) -> Optional[Dict[str, Any]]:
        """通过访问站点首页抓取考核信息，未检测到考核返回None"""
        # 获取站点信息
        site = SiteOper().get(site_id)
        if not site:
            return None

        # 抓取站点首页考核信息
        assessment = self.__fetch_site_assessment(site)

        if assessment:
            return self.__build_assessment_result(site_id, site_name, assessment)
        else:
            return None

    def __fetch_site_assessment(self, site) -> Optional[Dict[str, Any]]:
        """访问站点首页抓取考核信息"""
        try:
            # 第一次尝试：按站点配置访问
            res = RequestUtils(
                cookies=site.cookie,
                ua=site.ua or settings.USER_AGENT,
                proxies=settings.PROXY if site.proxy else None,
                timeout=site.timeout or 15
            ).get_res(url=site.url)

            # 访问失败且未使用代理，尝试使用代理重试
            if (not res or res.status_code != 200) and not site.proxy:
                logger.info(f"站点 {site.name} 直连失败，尝试使用代理访问...")
                res = RequestUtils(
                    cookies=site.cookie,
                    ua=site.ua or settings.USER_AGENT,
                    proxies=settings.PROXY,
                    timeout=site.timeout or 15
                ).get_res(url=site.url)

            if not res or res.status_code != 200:
                logger.warning(f"访问站点 {site.name} 失败")
                return None

            return self.__parse_assessment_html(res.text)
        except Exception as e:
            logger.error(f"抓取站点 {site.name} 考核信息失败: {e}")
            return None

    def __normalize_html(self, html: str) -> Tuple[str, List[str]]:
        """
        将HTML标准化为换行分隔的纯文本
        返回: (标准化文本, 行列表)
        """
        text = unescape(html)
        # 移除script、style、noscript等标签及其内容
        text = re.sub(r'(?is)<script[^>]*>.*?</script>', '', text)
        text = re.sub(r'(?is)<style[^>]*>.*?</style>', '', text)
        text = re.sub(r'(?is)<noscript[^>]*>.*?</noscript>', '', text)
        # 将各种换行标签转为换行符
        text = re.sub(r'(?i)<br\s*/?>', '\n', text)
        text = re.sub(r'(?i)</?(?:p|div|li|tr|td|h\d)[^>]*>', '\n', text)
        # 移除所有HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        # 标准化空白字符
        text = text.replace('\xa0', ' ')
        # 按行分割并清理
        lines = []
        for line in text.splitlines():
            cleaned = re.sub(r'[ \t\u3000]+', ' ', line).strip()
            if cleaned:
                lines.append(cleaned)
        return '\n'.join(lines), lines

    def __extract_tables_from_html(self, html: str) -> List[List[List[str]]]:
        """
        从HTML中提取表格数据
        返回: 表格列表，每个表格是行列表，每行是单元格列表
        """
        tables = []
        try:
            # 使用 lxml 解析 HTML
            tree = etree.HTML(html)
            if tree is None:
                return tables

            # 查找所有表格
            for table in tree.xpath('//table'):
                table_data = []
                # 优先查找 tbody，如果没有则直接查找 tr
                rows = table.xpath('.//tbody/tr') or table.xpath('.//tr')
                for row in rows:
                    row_data = []
                    # 获取所有单元格（th 和 td）
                    cells = row.xpath('.//th | .//td')
                    for cell in cells:
                        # 获取单元格文本，包括嵌套元素
                        text = ''.join(cell.itertext()).strip()
                        # 标准化空白
                        text = re.sub(r'\s+', ' ', text)
                        row_data.append(text)
                    if row_data:
                        table_data.append(row_data)
                if table_data:
                    tables.append(table_data)
        except Exception as e:
            logger.debug(f"表格解析失败: {e}")

        return tables

    def __extract_metrics_from_tables(self, tables: List[List[List[str]]]) -> List[Dict[str, Any]]:
        """
        从表格数据中提取考核指标
        支持多种表格布局：
        - 横向布局：指标名 | 要求 | 当前 | 结果
        - 纵向布局：指标名 | 值
        - 混合布局：指标名 | 当前值/要求值
        """
        metrics = []

        for table in tables:
            if len(table) < 2:
                continue

            # 检查是否是考核相关表格
            table_text = ' '.join(' '.join(row) for row in table)
            if not self.__is_assessment_table(table_text):
                continue

            # 尝试解析表格结构
            header = table[0] if table else []
            header_lower = [h.lower() for h in header]

            # 检测表格类型
            if self.__is_horizontal_layout(header_lower):
                # 横向布局：每行一个指标
                metrics.extend(self.__parse_horizontal_table(table))
            elif self.__is_vertical_layout(header_lower, table):
                # 纵向布局：每列一个指标
                metrics.extend(self.__parse_vertical_table(table))
            else:
                # 尝试通用解析
                metrics.extend(self.__parse_generic_table(table))

        return metrics

    def __is_assessment_table(self, table_text: str) -> bool:
        """检查表格是否包含考核相关内容"""
        text_lower = table_text.lower()
        # 检查是否包含考核关键词
        for keyword in self._ASSESSMENT_KEYWORDS:
            if keyword.lower() in text_lower:
                return True
        # 检查是否包含指标关键词
        for keywords in self._METRIC_KEYWORDS.values():
            for kw in keywords:
                if kw.lower() in text_lower:
                    return True
        return False

    def __is_horizontal_layout(self, header: List[str]) -> bool:
        """检查是否是横向布局表格（指标名 | 要求 | 当前 | 结果）"""
        keywords = {
            'name': ('指标', '項目', '项目', 'name', '名称', '名稱'),
            'required': ('要求', '目标', '目標', 'required', 'target', '标准', '標準'),
            'current': ('当前', '當前', '目前', 'current', '已完成', '已達成'),
            'result': ('结果', '結果', '状态', '狀態', 'result', 'status', '是否通过', '是否通過'),
        }
        found = set()
        for h in header:
            h_lower = h.lower()
            for key, kws in keywords.items():
                if any(kw.lower() in h_lower for kw in kws):
                    found.add(key)
        return len(found) >= 2

    def __is_vertical_layout(self, header: List[str], table: List[List[str]]) -> bool:
        """检查是否是纵向布局表格"""
        # 纵向布局通常只有2列，第一列是指标名
        if not table:
            return False
        # 大部分行是2列
        two_col_count = sum(1 for row in table if len(row) == 2)
        return two_col_count >= len(table) * 0.7

    def __parse_horizontal_table(self, table: List[List[str]]) -> List[Dict[str, Any]]:
        """解析横向布局表格"""
        metrics = []
        if len(table) < 2:
            return metrics

        header = table[0]
        # 确定列索引
        col_map = self.__detect_column_mapping(header)

        for row in table[1:]:
            if len(row) < 2:
                continue

            metric = self.__create_metric_from_row(row, col_map, header)
            if metric and metric.get('name'):
                metrics.append(metric)

        return metrics

    def __detect_column_mapping(self, header: List[str]) -> Dict[str, int]:
        """检测表格列映射"""
        col_map = {}
        keywords = {
            'name': ('指标', '項目', '项目', 'name', '名称', '名稱', '考核项', '考核項'),
            'required': ('要求', '目标', '目標', 'required', 'target', '标准', '標準', '需要', '需達'),
            'current': ('当前', '當前', '目前', 'current', '已完成', '已達成', '完成', '达成', '達成'),
            'result': ('结果', '結果', '状态', '狀態', 'result', 'status', '通过', '通過'),
        }

        for idx, h in enumerate(header):
            h_lower = h.lower()
            for key, kws in keywords.items():
                if key not in col_map and any(kw.lower() in h_lower for kw in kws):
                    col_map[key] = idx
                    break

        # 如果没找到 name 列，默认第一列
        if 'name' not in col_map:
            col_map['name'] = 0

        return col_map

    def __create_metric_from_row(self, row: List[str], col_map: Dict[str, int],
                                  header: List[str]) -> Optional[Dict[str, Any]]:
        """从表格行创建指标"""
        metric = {
            'name': None,
            'index': None,
            'required': None,
            'current': None,
            'passed': None,
        }

        # 提取各字段
        for key, idx in col_map.items():
            if idx < len(row):
                value = row[idx].strip()
                if key == 'name':
                    metric['name'] = value
                elif key == 'required':
                    metric['required'] = value
                elif key == 'current':
                    metric['current'] = value
                elif key == 'result':
                    metric['passed'] = self.__interpret_status(value)

        # 如果 required/current 未从指定列获取，尝试从剩余列解析
        if not metric['required'] or not metric['current']:
            for idx, cell in enumerate(row):
                if idx in col_map.values():
                    continue
                # 尝试解析为 "当前/要求" 格式
                ratio = self.__parse_ratio_value(cell)
                if ratio:
                    metric['current'] = ratio['current']
                    metric['required'] = ratio['required']
                    if metric['passed'] is None:
                        metric['passed'] = ratio.get('passed')
                    break

        # 尝试从 current 推断 passed
        if metric['passed'] is None and metric['current']:
            metric['passed'] = self.__interpret_status(metric['current'])

        # 如果有 current 和 required，计算 passed
        if metric['passed'] is None and metric['current'] and metric['required']:
            cur_val = self.__parse_metric_value(metric['current'])
            req_val = self.__parse_metric_value(metric['required'])
            if cur_val is not None and req_val is not None and req_val > 0:
                metric['passed'] = cur_val >= req_val

        return metric if metric.get('name') else None

    def __parse_vertical_table(self, table: List[List[str]]) -> List[Dict[str, Any]]:
        """解析纵向布局表格"""
        metrics = []

        for row in table:
            if len(row) < 2:
                continue

            name = row[0].strip()
            value = row[1].strip()

            # 检查是否是指标名称
            if not self.__is_metric_name(name):
                continue

            metric = {
                'name': name,
                'index': None,
                'required': None,
                'current': None,
                'passed': None,
            }

            # 尝试解析值
            ratio = self.__parse_ratio_value(value)
            if ratio:
                metric.update(ratio)
            else:
                metric['current'] = value
                metric['passed'] = self.__interpret_status(value)

            metrics.append(metric)

        return metrics

    def __parse_generic_table(self, table: List[List[str]]) -> List[Dict[str, Any]]:
        """通用表格解析"""
        metrics = []

        for row in table:
            # 尝试从行中提取指标
            row_text = ' '.join(row)

            # 跳过非指标行
            if not self.__contains_metric_keywords(row_text):
                continue

            metric = self.__parse_simple_metric_from_text(row_text)
            if metric:
                metrics.append(metric)

        return metrics

    def __is_metric_name(self, name: str, strict: bool = True) -> bool:
        """
        检查是否是有效的指标名称
        strict=True 时使用白名单精确匹配，strict=False 时使用关键词匹配
        """
        if not name:
            return False

        # 名称长度限制（考核指标名称通常很短）
        if len(name) > 10:
            return False

        # 黑名单检查：包含无效模式则排除
        for pattern in self._INVALID_METRIC_PATTERNS:
            if pattern.lower() in name.lower():
                return False

        # 严格模式：使用白名单精确匹配
        if strict:
            # 检查是否精确匹配有效指标名称
            for valid_name in self._VALID_METRIC_NAMES:
                if name == valid_name or name.replace(' ', '') == valid_name:
                    return True
            # 也检查是否以有效名称开头或结尾
            for valid_name in self._VALID_METRIC_NAMES:
                if name.startswith(valid_name) or name.endswith(valid_name):
                    return True
            return False

        # 宽松模式：关键词匹配
        name_lower = name.lower()
        for keywords in self._METRIC_KEYWORDS.values():
            for kw in keywords:
                if kw.lower() in name_lower:
                    return True
        return False

    def __is_valid_metric_value(self, value: str) -> bool:
        """
        检查是否是有效的指标值（用于过滤无关内容）
        有效的指标值通常是：
        - "当前值 / 目标值" 格式
        - "已通过"、"未通过" 等状态文本
        - "还需要 X GB" 等描述
        """
        if not value:
            return False

        # 值太长通常不是有效的指标值
        if len(value) > 100:
            return False

        # 包含种子标题特征则排除
        title_patterns = [
            r'\d{4}p', r'BluRay', r'Blu-ray', r'WEB-DL', r'REMUX', r'HDR',
            r'H\.26[45]', r'HEVC', r'AVC', r'DTS', r'AAC', r'FLAC', r'Atmos',
            r'导演', r'主演', r'类别', r'字幕', r'国语', r'國語', r'中字',
            r'第\d+季', r'全\d+集', r'S\d{2}', r'E\d{2}',
            r'\d{4}[-/]\d{2}[-/]\d{2}',  # 日期格式的种子
        ]
        for pattern in title_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                return False

        # 包含版块/帖子特征则排除
        if re.search(r'版[块塊]|Feedback|Appeal|Record|问题反馈|备案', value, re.IGNORECASE):
            return False

        # 包含站点统计特征则排除
        stat_patterns = [
            r'访问用户', r'訪問用戶', r'注册用户', r'註冊用戶',
            r'今日', r'本周', r'当前', r'總',
            r'Peasant|User|Elite|Crazy|Insane|Veteran|Extreme|Ultimate|Master',
        ]
        for pattern in stat_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                return False

        # 如果值只是一个大数字（>1000且没有单位），通常是站点统计
        pure_number = re.match(r'^[\d,]+$', value.replace(' ', ''))
        if pure_number:
            try:
                num = float(value.replace(',', '').replace(' ', ''))
                if num > 1000:  # 超过1000的纯数字不太可能是考核指标
                    return False
            except ValueError:
                pass

        # 有效的格式：包含 "/" 或状态关键词或 "需" 等
        valid_patterns = [
            r'/',  # 当前/目标 格式
            r'已通过|通過|合格|達標|达标',  # 通过状态
            r'未通过|未通過|不合格|未達標|未达标',  # 未通过状态
            r'还需|還需|仍需|需要',  # 需要描述
            r'^\s*[\d,.]+\s*[A-Za-z]+\s*$',  # 带单位的数值 (如 "100 GB")
        ]

        for pattern in valid_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                return True

        # 如果是简单的数值+单位格式，也认为有效
        if re.match(r'^[\d,.]+\s*[A-Za-z%]+$', value.strip()):
            return True

        return False

    def __contains_metric_keywords(self, text: str) -> bool:
        """检查文本是否包含指标关键词"""
        text_lower = text.lower()
        for keywords in self._METRIC_KEYWORDS.values():
            for kw in keywords:
                if kw.lower() in text_lower:
                    return True
        return False

    def __parse_ratio_value(self, value: str) -> Optional[Dict[str, Any]]:
        """
        解析比例值格式
        支持: "100 GB / 500 GB", "100/500", "50%", "已通过" 等
        """
        if not value:
            return None

        value = value.strip()

        # 格式1: "当前值 / 要求值"
        ratio_match = re.search(
            r'([\d,.]+)\s*([A-Za-z]*)\s*/\s*([\d,.]+)\s*([A-Za-z]*)',
            value
        )
        if ratio_match:
            cur_val = ratio_match.group(1).replace(',', '')
            cur_unit = ratio_match.group(2) or ''
            req_val = ratio_match.group(3).replace(',', '')
            req_unit = ratio_match.group(4) or ''

            current = f"{cur_val} {cur_unit}".strip()
            required = f"{req_val} {req_unit}".strip()

            try:
                passed = float(cur_val) >= float(req_val)
            except ValueError:
                passed = None

            return {'current': current, 'required': required, 'passed': passed}

        # 格式2: 百分比
        percent_match = re.search(r'([\d.]+)\s*%', value)
        if percent_match:
            percent = float(percent_match.group(1))
            return {
                'current': f"{percent}%",
                'required': '100%',
                'passed': percent >= 100
            }

        # 格式3: 状态文本
        passed = self.__interpret_status(value)
        if passed is not None:
            return {'current': value, 'required': None, 'passed': passed}

        return None

    def __parse_simple_metric_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """从文本行解析简单指标"""
        # 尝试匹配 "指标名：值" 或 "指标名 值" 格式
        patterns = [
            re.compile(r'(?P<name>[\u4e00-\u9fa5]+(?:量|率|值|数|數|间|間)?)[：:]\s*(?P<value>.+)', re.IGNORECASE),
            re.compile(r'(?P<name>[\u4e00-\u9fa5]{2,6})\s+(?P<value>[\d,.]+\s*[A-Za-z]*(?:\s*/\s*[\d,.]+\s*[A-Za-z]*)?)', re.IGNORECASE),
        ]

        for pattern in patterns:
            match = pattern.search(text)
            if match and self.__is_metric_name(match.group('name')):
                name = match.group('name').strip()
                value = match.group('value').strip()

                metric = {
                    'name': name,
                    'index': None,
                    'required': None,
                    'current': None,
                    'passed': None,
                }

                ratio = self.__parse_ratio_value(value)
                if ratio:
                    metric.update(ratio)
                else:
                    metric['current'] = value
                    metric['passed'] = self.__interpret_status(value)

                return metric

        return None

    def __extract_time_from_title(self, html: str) -> Optional[str]:
        """从HTML的title属性中提取结束时间（只在考核相关区块中搜索）"""
        # 只在包含考核相关关键词附近搜索title属性
        # 模式1：关键词在title之前
        match = re.search(
            r'(?:考核|结束|還有|还有).{0,100}title=["\'](\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})["\']',
            html, re.DOTALL
        )
        if match:
            return match.group(1)
        # 模式2：title在关键词之前
        match = re.search(
            r'title=["\'](\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})["\'].{0,100}(?:考核|结束|還有|还有)',
            html, re.DOTALL
        )
        if match:
            return match.group(1)
        return None

    def __parse_assessment_html(self, html: str) -> Optional[Dict[str, Any]]:
        """
        解析考核HTML信息（支持简繁体中文）
        使用文本解析策略
        """
        if not html:
            return None

        # 在标准化前提取title属性中的时间（用于倒计时格式）
        title_time = self.__extract_time_from_title(html)

        # 提取相对时间（还有X天X小时）
        relative_time = self.__extract_relative_time(html)

        # 标准化HTML
        normalized_text, lines = self.__normalize_html(html)

        # 提取考核名称和位置（支持简繁体）
        name, name_index = self.__extract_assessment_name(lines)

        if not name:
            logger.debug("未找到考核名称")
            return None

        assessment = {'name': name, 'metrics': []}
        logger.info(f"检测到考核: {name}")

        # 确定考核区块范围（从名称到结束标记）
        end_index = self.__find_assessment_end(lines, name_index)
        lines_in_assessment = lines[name_index:end_index]

        logger.debug(f"考核区块范围: 行 {name_index} ~ {end_index}（共 {len(lines_in_assessment)} 行）")

        # 提取时间范围（优先级：title属性 > 文本时间范围 > 相对时间）
        # title属性通常与倒计时直接关联，更准确
        if title_time:
            assessment['end_time'] = title_time
            logger.debug(f"从title属性解析结束时间: {title_time}")
        else:
            start_time, end_time = self.__extract_time_range(lines_in_assessment)
            if start_time and end_time:
                assessment['start_time'] = start_time
                assessment['end_time'] = end_time
                logger.debug(f"解析时间: {start_time} ~ {end_time}")
            elif relative_time:
                # 使用相对时间计算结束时间
                assessment['end_time'] = relative_time
                logger.debug(f"从相对时间解析结束时间: {relative_time}")

        # 只使用文本解析提取指标
        text_metrics = self.__extract_metrics(lines_in_assessment)
        assessment['metrics'] = text_metrics

        if text_metrics:
            logger.info(f"共解析 {len(text_metrics)} 个考核指标")
            return assessment

        logger.debug("未找到考核指标")
        return None

    def __find_assessment_end(self, lines: List[str], start_index: int) -> int:
        """
        查找考核区块的结束位置
        通过检测结束标记来确定范围
        """
        # 最大搜索范围（从起始位置向后最多50行）
        max_range = min(start_index + 50, len(lines))

        for i in range(start_index + 1, max_range):
            line = lines[i]

            # 检查是否遇到结束标记
            for marker in self._ASSESSMENT_END_MARKERS:
                if marker in line:
                    logger.debug(f"在行 {i} 找到考核区块结束标记: {marker}")
                    return i

            # 检查是否遇到新的考核区块（说明前一个结束了）
            if '考核' in line and i > start_index + 3:
                # 检查是否是新的考核标题
                if re.search(r'[【\[「『].*考核.*[】\]」』]', line):
                    return i
                if re.match(r'^(?:新手|养成|試用|试用)', line):
                    return i

        return max_range

    def __extract_relative_time(self, html: str) -> Optional[str]:
        """
        从HTML中提取相对时间并转换为绝对时间
        支持: "还有3天5小时", "剩余10天", "距离结束还有2周"
        """
        # 匹配相对时间模式
        patterns = [
            # "还有X天X小时X分钟"
            re.compile(
                r'(?:还有|還有|剩余|剩餘|距[离離]?\S*?(?:结束|結束|到期)?\S*?(?:还有|還有)?)\s*'
                r'(?:(\d+)\s*(?:年|years?))?\s*'
                r'(?:(\d+)\s*(?:月|个月|個月|months?))?\s*'
                r'(?:(\d+)\s*(?:周|週|weeks?))?\s*'
                r'(?:(\d+)\s*(?:天|日|days?))?\s*'
                r'(?:(\d+)\s*(?:小?时|小?時|hours?|hrs?))?\s*'
                r'(?:(\d+)\s*(?:分钟?|分鐘?|minutes?|mins?))?',
                re.IGNORECASE
            ),
        ]

        for pattern in patterns:
            match = pattern.search(html)
            if match:
                years = int(match.group(1) or 0)
                months = int(match.group(2) or 0)
                weeks = int(match.group(3) or 0)
                days = int(match.group(4) or 0)
                hours = int(match.group(5) or 0)
                minutes = int(match.group(6) or 0)

                # 至少要有一个时间单位
                if years + months + weeks + days + hours + minutes == 0:
                    continue

                # 计算结束时间
                try:
                    tz = pytz.timezone(settings.TZ)
                    now = datetime.now(tz)
                    end_time = now + timedelta(
                        days=years * 365 + months * 30 + weeks * 7 + days,
                        hours=hours,
                        minutes=minutes
                    )
                    return end_time.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass

        return None

    def __merge_metrics(self, table_metrics: List[Dict[str, Any]],
                        text_metrics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并表格指标和文本指标，去除重复
        表格指标优先（通常更准确）
        """
        if not table_metrics:
            return text_metrics
        if not text_metrics:
            return table_metrics

        # 使用指标名称作为key进行去重
        merged = {self.__normalize_metric_name(m['name']): m for m in table_metrics}

        for metric in text_metrics:
            key = self.__normalize_metric_name(metric['name'])
            if key not in merged:
                merged[key] = metric
            else:
                # 补充缺失字段
                existing = merged[key]
                if not existing.get('required') and metric.get('required'):
                    existing['required'] = metric['required']
                if not existing.get('current') and metric.get('current'):
                    existing['current'] = metric['current']
                if existing.get('passed') is None and metric.get('passed') is not None:
                    existing['passed'] = metric['passed']

        return list(merged.values())

    def __normalize_metric_name(self, name: str) -> str:
        """标准化指标名称用于去重比较"""
        if not name:
            return ''
        # 移除空白和标点
        normalized = re.sub(r'[\s：:：\-_]+', '', name.lower())
        # 简繁体转换（简单替换）
        replacements = {
            '傳': '传', '種': '种', '時': '时', '間': '间',
            '積': '积', '數': '数', '標': '标', '達': '达',
        }
        for trad, simp in replacements.items():
            normalized = normalized.replace(trad, simp)
        return normalized

    def __extract_assessment_name(self, lines: List[str]) -> Tuple[Optional[str], int]:
        """
        提取考核名称（支持简繁体），返回(名称, 行索引)
        使用多级匹配策略，优先级从高到低
        """
        # 排除模式：这些是提示用户开启考核的文本，不是真正的考核
        exclude_patterns = [
            re.compile(r'(?:用户|用戶)?(?:开启|開啟|启动|啟動|进入|進入|申请|申請|参加|參加).*?考核', re.IGNORECASE),
            re.compile(r'考核.*?(?:开启|開啟|启动|啟動|申请|申請|入口|链接|鏈接)', re.IGNORECASE),
            re.compile(r'(?:点击|點擊|click).*?考核', re.IGNORECASE),
        ]

        # 模式1：标准格式 "名称：xxx" / "考核项目：xxx" / "任务名称：xxx"
        name_patterns = [
            re.compile(r'^名[称稱][：:]\s*(?P<value>.+)', re.IGNORECASE),
            re.compile(r'(?:考核|任[务務])?(?:名[称稱字]|项目|項目)[：:]\s*(?P<value>.+)', re.IGNORECASE),
            re.compile(r'(?:当前|當前)?考核[：:]\s*(?P<value>.+)', re.IGNORECASE),
        ]

        # 模式2：倒计时格式 "离xxx考核结束还有" / "距xxx结束"
        countdown_patterns = [
            re.compile(r'[离離距](?P<name>.+?)考核(?:结束|結束)', re.IGNORECASE),
            re.compile(r'[离離距](?P<name>.+?)(?:结束|結束|到期)', re.IGNORECASE),
        ]

        # 模式3：标题格式 "【xxx考核】" / "[新手任务]" / "★考核信息★"
        title_patterns = [
            re.compile(r'[【\[「『](?P<name>[^】\]」』]*?考核[^】\]」』]*)[】\]」』]', re.IGNORECASE),
            re.compile(r'[【\[「『](?P<name>(?:新手|新人|养成|試用|试用|观察|養成|觀察)[^】\]」』]*)[】\]」』]', re.IGNORECASE),
            re.compile(r'[★☆▶►◆◇](?P<name>[^★☆▶►◆◇]*?考核[^★☆▶►◆◇]*)[★☆▶►◆◇]', re.IGNORECASE),
        ]

        # 模式4：独立考核类型 "新手考核" / "养成期" 等
        standalone_patterns = [
            re.compile(r'^(?P<name>(?:新手|新人|保[号號]|活[跃躍]度?|做[种種]|上[传傳]|魔力|养成|養成|试用|試用|观察|觀察)考核)(?:[：:\s]|$)', re.IGNORECASE),
            re.compile(r'^(?P<name>(?:养成|養成|试用|試用|观察|觀察|新手|probation|trial)期?)(?:[：:\s]|$)', re.IGNORECASE),
        ]

        # 模式5：包含"考核"且有指标特征的行
        assessment_indicator = re.compile(
            r'考核.{0,20}(?:指[标標]|要求|目[标標]|任[务務])',
            re.IGNORECASE
        )

        for i, line in enumerate(lines):
            # 先检查是否匹配排除模式（如"用户开启新手考核"）
            if any(pattern.search(line) for pattern in exclude_patterns):
                continue

            # 1. 先尝试标准名称格式
            for pattern in name_patterns:
                match = pattern.search(line)
                if match:
                    value = match.group('value').strip()
                    # 再次检查提取的值是否包含排除关键词
                    if any(pattern.search(value) for pattern in exclude_patterns):
                        continue
                    return value, i

            # 2. 再尝试倒计时格式
            for pattern in countdown_patterns:
                match = pattern.search(line)
                if match:
                    name = match.group('name').strip()
                    # 如果名称末尾没有"考核"则补充
                    if not name.endswith(('考核', '任务', '任務', '期')):
                        name = f"{name}考核"
                    return name, i

            # 3. 尝试标题格式
            for pattern in title_patterns:
                match = pattern.search(line)
                if match:
                    name = match.group('name').strip()
                    # 检查是否包含排除关键词
                    if any(pattern.search(name) for pattern in exclude_patterns):
                        continue
                    return name, i

            # 4. 尝试独立考核类型
            for pattern in standalone_patterns:
                match = pattern.search(line)
                if match:
                    return match.group('name').strip(), i

        # 5. 最后尝试通过指标特征定位考核区块
        for i, line in enumerate(lines):
            # 跳过排除模式
            if any(pattern.search(line) for pattern in exclude_patterns):
                continue
            if assessment_indicator.search(line):
                # 提取考核类型
                type_match = re.search(r'([\u4e00-\u9fa5]+考核)', line)
                if type_match:
                    name = type_match.group(1)
                    # 检查是否包含排除关键词
                    if any(pattern.search(name) for pattern in exclude_patterns):
                        continue
                    return name, i
                return "站点考核", i

        # 6. 如果仍未找到，检查是否存在考核关键词
        for i, line in enumerate(lines):
            # 跳过排除模式
            if any(pattern.search(line) for pattern in exclude_patterns):
                continue
            line_lower = line.lower()
            for keyword in self._ASSESSMENT_KEYWORDS:
                if keyword.lower() in line_lower:
                    # 尝试提取更具体的名称
                    type_match = re.search(r'([\u4e00-\u9fa5]{2,6}(?:考核|任务|任務|期))', line)
                    if type_match:
                        return type_match.group(1), i
                    return keyword, i

        return None, 0

    def __extract_time_range(self, lines: List[str]) -> Tuple[Optional[str], Optional[str]]:
        """提取时间范围（支持简繁体）"""
        # 日期范围模式
        date_pattern = r'\d{4}[./-]\d{1,2}[./-]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?'
        date_range = re.compile(rf'({date_pattern})\s*(?:~|～|至|到|—|-)\s*({date_pattern})')

        # 时间触发关键词（支持简繁体）
        time_triggers = [
            re.compile(r'^[时時][间間][：:]', re.IGNORECASE),  # "时间：" 开头
            re.compile(r'(?:考核)?(?:[时時][间間]|期[間间]|周期|期限)', re.IGNORECASE),  # 原有模式
        ]

        for line in lines:
            # 检查是否包含时间触发词
            has_trigger = any(trigger.search(line) for trigger in time_triggers)
            if not has_trigger:
                continue

            match = date_range.search(line)
            if match:
                return match.group(1).strip(), match.group(2).strip()

        # 如果没有找到带触发词的，尝试直接匹配日期范围
        for line in lines:
            match = date_range.search(line)
            if match:
                return match.group(1).strip(), match.group(2).strip()

        return None, None

    def __extract_metrics(self, lines: List[str]) -> List[Dict[str, Any]]:
        """
        提取考核指标（支持简繁体和多种格式）
        使用多重匹配策略
        """
        metrics = []

        # 模式1：标准格式 "指标1：上传量"
        metric_header = re.compile(
            r'(?:(?:考核)?(?:指[标標]|项目|項目|条件|條件))\s*(?P<index>\d+)?[：:]\s*(?P<name>[^,，。；;]+)',
            re.IGNORECASE
        )

        # 模式2：简单格式 "上传量： 已通过" 或 "做种积分： 已通过"
        # 支持更多名称后缀：量|率|值|数|數|分|积分|時間|时间|时长|時長
        simple_metric = re.compile(
            r'^(?P<name>[\u4e00-\u9fa5]{2,8})[：:]\s*(?P<value>.+)$'
        )

        # 模式3：列表格式 "• 上传量 100GB" 或 "1. 做种时间 ≥ 100小时"
        list_metric = re.compile(
            r'^(?:[•·●○◆◇★☆\-\*]|\d+[\.、\)])\s*(?P<name>[\u4e00-\u9fa5]{2,8})\s*[:：]?\s*(?P<value>.+)$'
        )

        # 模式4：进度格式 "上传量: 50.5GB / 100GB (50.5%)"
        progress_metric = re.compile(
            r'(?P<name>[\u4e00-\u9fa5]{2,8})\s*[:：]\s*'
            r'(?P<current>[\d,.]+\s*[A-Za-z]*)\s*/\s*(?P<required>[\d,.]+\s*[A-Za-z]*)'
            r'(?:\s*\((?P<percent>[\d.]+)\s*%\))?',
            re.IGNORECASE
        )

        # 模式5：状态格式 "✓ 上传量已达标" 或 "✗ 做种时间未完成"
        status_metric = re.compile(
            r'^(?P<icon>[✓✔√☑✅✗✘×☒❌])\s*(?P<name>[\u4e00-\u9fa5]{2,8})\s*(?P<status>.*)$'
        )

        # 跳过的行（非指标内容）
        skip_patterns = [
            r'[离離距].+(?:考核|结束|結束)',  # 倒计时行
            r'(?:通过|透過)捐[赠贈]',          # 捐赠提示
            r'温馨提示|溫馨提示',              # 提示信息
            r'(?:如有|若有)(?:疑问|疑問)',    # 疑问提示
            r'考核(?:时间|時間|期间|期間)',   # 时间说明行
            r'注意[：:]',                      # 注意提示行
            r'请保持|請保持',                  # 保持状态提示
            r'也可以通过|也可以透過',          # 可选提示
            # 站点统计
            r'访问用户|訪問用戶|注册用户|註冊用戶',
            r'今日访问|本周访问|当前访问',
            r'种子总|總上传|總下载|总数据',
            r'Peasant|Power User|Elite User|Crazy User|Insane User|Veteran User|Extreme User|Ultimate User|Nexus Master',
            r'贵宾|捐赠者|被警告|被禁用户',
            r'男生|女生',
            r'断种|斷種|同伴|Tracker',
            # 版块/帖子
            r'版[块塊]|Feedback|Appeal|Record',
            r'问题反馈|备案',
            # 种子标题
            r'\d{4}p|BluRay|WEB-DL|REMUX|H\.26[45]',
            r'导演|主演|类别|字幕',
            # 投票
            r'弃权|棄權|是，|否，',
            # 公告
            r'招聘|解封|申诉|QQ群|TG群',
            r'开注时间|发邀时间',
        ]
        skip_re = re.compile('|'.join(skip_patterns), re.IGNORECASE)

        current_metric = None
        for line in lines:
            # 跳过URL
            if '://' in line or line.startswith('http'):
                continue
            # 跳过特定模式的行
            if skip_re.search(line):
                continue

            # 1. 先尝试进度格式（最精确）
            progress_match = progress_metric.search(line)
            if progress_match and self.__is_metric_name(progress_match.group('name')):
                if current_metric:
                    metrics.append(current_metric)
                    current_metric = None

                name = progress_match.group('name').strip()
                current = progress_match.group('current').strip()
                required = progress_match.group('required').strip()

                # 计算是否通过
                cur_val = self.__parse_metric_value(current)
                req_val = self.__parse_metric_value(required)
                passed = cur_val >= req_val if cur_val is not None and req_val is not None and req_val > 0 else None

                metrics.append({
                    'name': name,
                    'index': None,
                    'required': required,
                    'current': current,
                    'passed': passed,
                })
                continue

            # 2. 尝试状态格式
            status_match = status_metric.match(line)
            if status_match and self.__is_metric_name(status_match.group('name')):
                if current_metric:
                    metrics.append(current_metric)
                    current_metric = None

                icon = status_match.group('icon')
                name = status_match.group('name').strip()
                status_text = status_match.group('status').strip()

                passed = icon in '✓✔√☑✅'
                metrics.append({
                    'name': name,
                    'index': None,
                    'required': None,
                    'current': status_text if status_text else ('已通过' if passed else '未通过'),
                    'passed': passed,
                })
                continue

            # 3. 尝试标准格式
            header_match = metric_header.search(line)
            if header_match:
                if current_metric:
                    metrics.append(current_metric)
                current_metric = {
                    'name': header_match.group('name').strip(),
                    'index': int(header_match.group('index')) if header_match.group('index') else None,
                    'required': None,
                    'current': None,
                    'passed': None,
                }
                remainder = line[header_match.end():]
                self.__parse_metric_details(current_metric, remainder)
                continue

            # 4. 尝试列表格式
            list_match = list_metric.match(line)
            if list_match and self.__is_metric_name(list_match.group('name')):
                if current_metric:
                    metrics.append(current_metric)
                    current_metric = None

                metric = self.__parse_simple_metric(
                    list_match.group('name'),
                    list_match.group('value')
                )
                if metric:
                    metrics.append(metric)
                continue

            # 5. 尝试简单格式
            simple_match = simple_metric.match(line)
            if simple_match and self.__is_metric_name(simple_match.group('name')):
                if current_metric:
                    metrics.append(current_metric)
                    current_metric = None

                metric = self.__parse_simple_metric(
                    simple_match.group('name'),
                    simple_match.group('value')
                )
                if metric:
                    metrics.append(metric)
                continue

            # 6. 继续解析当前指标详情
            if current_metric:
                self.__parse_metric_details(current_metric, line)

        if current_metric:
            metrics.append(current_metric)

        # 过滤无效指标
        valid_metrics = [m for m in metrics if m.get('name') and (m.get('current') or m.get('required') or m.get('passed') is not None)]

        return valid_metrics

    def __parse_simple_metric(self, name: str, value: str) -> Optional[Dict[str, Any]]:
        """解析简单格式指标（如"上传量： 已通过"或"上传量： 还需要 97.60 GB"）"""
        # 验证指标名称
        if not self.__is_metric_name(name):
            return None

        # 验证指标值
        if not self.__is_valid_metric_value(value):
            return None

        metric = {
            'name': name.strip(),
            'index': None,
            'required': None,
            'current': None,
            'passed': None,
        }

        value = value.strip()

        # 检查是否已通过
        if re.search(r'已通过|通過|合格|達標|达标', value):
            metric['passed'] = True
            metric['current'] = '已通过'
            return metric

        # 检查是否还需要
        need_match = re.search(r'(?:还需要|還需要|仍需|需再?)\s*([\d.]+)\s*([A-Za-z]+)?', value)
        if need_match:
            metric['passed'] = False
            metric['current'] = f"还需 {need_match.group(1)} {need_match.group(2) or ''}".strip()
            return metric

        # 检查是否未通过
        if re.search(r'未通过|未通過|不合格|未達標|未达标', value):
            metric['passed'] = False
            metric['current'] = '未通过'
            return metric

        # 检查"当前值 / 要求值"格式（如"0.00 KB / 100.00 GB"或"548 / 10000"）
        ratio_match = re.search(
            r'([\d,.]+)\s*([A-Za-z]*)\s*/\s*([\d,.]+)\s*([A-Za-z]*)',
            value
        )
        if ratio_match:
            current_val = ratio_match.group(1)
            current_unit = ratio_match.group(2) or ''
            required_val = ratio_match.group(3)
            required_unit = ratio_match.group(4) or ''

            metric['current'] = f"{current_val} {current_unit}".strip()
            metric['required'] = f"{required_val} {required_unit}".strip()

            # 使用单位转换进行正确比较
            cur_parsed = self.__parse_metric_value(metric['current'])
            req_parsed = self.__parse_metric_value(metric['required'])

            if cur_parsed is not None and req_parsed is not None and req_parsed > 0:
                metric['passed'] = cur_parsed >= req_parsed
            else:
                # 如果无法解析带单位值，尝试直接比较数字
                try:
                    cur_num = float(current_val.replace(',', ''))
                    req_num = float(required_val.replace(',', ''))
                    metric['passed'] = cur_num >= req_num
                except ValueError:
                    metric['passed'] = None
            return metric

        return None

    def __should_preserve_comma(self, metric_name: str) -> bool:
        """
        判断指标是否需要保留英文逗号（千分位）
        主要针对可能包含大数值的时间类指标
        """
        if not metric_name:
            return False

        # 需要保留千分位逗号的指标关键词
        preserve_keywords = (
            '做种时间', '做種時間', '保种时间', '保種時間',
            '做种时长', '做種時長', '平均做种', '平均做種',
            'seed time', 'seeding time', 'average seed'
        )

        name_lower = metric_name.lower()
        for keyword in preserve_keywords:
            if keyword.lower() in name_lower or keyword in metric_name:
                return True

        return False

    def __parse_metric_details(self, metric: Dict[str, Any], text: str) -> None:
        """解析指标详情（要求、当前值、结果）"""
        # 判断当前指标是否需要保留英文逗号
        preserve_comma = self.__should_preserve_comma(metric.get('name', ''))

        if preserve_comma:
            # 对于时间类指标：只在中文逗号"，"处分隔，英文逗号","保留（用于千分位数字如 "3,202.78"）
            # 解析要求值
            if not metric.get('required'):
                req_match = re.search(
                    r'(?:要求|需要|目標|目标|標準|标准)[：:]\s*(?P<value>[^，]+?)(?=\s*(?:，\s*)?(?:当前|當前|目前|結果|结果)|$)',
                    text
                )
                if req_match:
                    metric['required'] = req_match.group('value').strip()

            # 解析当前值
            if not metric.get('current'):
                cur_match = re.search(
                    r'(?:当前|當前|目前)[：:]\s*(?P<value>[^，]+?)(?=\s*(?:，\s*)?(?:結果|结果|要求)|$)',
                    text
                )
                if cur_match:
                    metric['current'] = cur_match.group('value').strip()

            # 解析结果
            if metric.get('passed') is None:
                result_match = re.search(r'(?:結果|结果)[：:]\s*(?P<value>[^，]+)', text)
                if result_match:
                    result_text = result_match.group('value').strip()
                    metric['passed'] = self.__interpret_status(result_text)
                else:
                    passed = self.__interpret_status(text)
                    if passed is not None:
                        metric['passed'] = passed
        else:
            # 对于其他指标：按中英文逗号、分号分割（传统逻辑）
            chunks = re.split(r'[，,；;]+', text)

            for chunk in chunks:
                chunk = chunk.strip()
                if not chunk:
                    continue

                # 解析要求值
                if not metric.get('required'):
                    req_match = re.search(r'(?:要求|需要|目標|目标|標準|标准)[：:]\s*(?P<value>.+)', chunk)
                    if req_match:
                        metric['required'] = req_match.group('value').strip()
                        continue

                # 解析当前值
                if not metric.get('current'):
                    cur_match = re.search(r'(?:当前|當前|目前)[：:]\s*(?P<value>.+)', chunk)
                    if cur_match:
                        metric['current'] = cur_match.group('value').strip()
                        continue

                # 解析结果
                if metric.get('passed') is None:
                    result_match = re.search(r'(?:結果|结果)[：:]\s*(?P<value>.+)', chunk)
                    if result_match:
                        result_text = result_match.group('value').strip()
                        metric['passed'] = self.__interpret_status(result_text)
                        continue

            # 如果没有显式结果，尝试从整个文本解析状态
            if metric.get('passed') is None:
                passed = self.__interpret_status(text)
                if passed is not None:
                    metric['passed'] = passed

    def __interpret_status(self, text: str) -> Optional[bool]:
        """
        解析状态文本，返回是否通过
        支持：状态关键词、图标、百分比
        """
        if not text:
            return None

        # 清理文本
        cleaned = re.sub(r'[！!。．\.]+$', '', text.strip())

        # 1. 首先检查图标（最可靠）
        for icon, passed in self._STATUS_ICONS.items():
            if icon in cleaned:
                return passed

        # 2. 检查百分比（100%及以上表示通过）
        percent_match = re.search(r'(\d+(?:\.\d+)?)\s*%', cleaned)
        if percent_match:
            percent = float(percent_match.group(1))
            if percent >= 100:
                return True
            # 如果只有百分比，0%表示未通过
            if percent == 0 and len(cleaned.strip()) < 10:
                return False

        # 3. 检查状态关键词（按优先级：否定词先检查）
        # 使用更宽松的匹配，允许前后有其他字符
        for keyword, passed in self._STATUS_KEYWORDS.items():
            if keyword in cleaned.lower() if keyword.isascii() else keyword in cleaned:
                return passed

        return None

    def __build_assessment_result(self, site_id: int, site_name: str,
                                   assessment: Dict) -> Optional[Dict[str, Any]]:
        """根据抓取的考核信息构建结果，如果考核无效则返回None"""
        metrics = assessment.get('metrics', [])

        # 检查是否有有效的指标数据
        # 如果所有指标的当前值都是无效的（如 "-", 空, 或无数据），则认为没有真正的考核
        valid_metric_count = 0
        for m in metrics:
            current = m.get('current', '')
            # 检查当前值是否有效（非空、非"-"、非纯符号）
            if current and current.strip() not in ['-', '--', '—', '']:
                # 检查是否包含数字或状态关键词
                if re.search(r'\d|已通过|通過|合格|未通过|未通過|不合格', current):
                    valid_metric_count += 1

        # 如果没有任何有效指标数据，则认为这不是真正的考核
        if valid_metric_count == 0 and metrics:
            logger.debug(f"站点 {site_name} 考核指标无有效数据，跳过")
            return None

        # 重新计算未确定的passed状态
        for m in metrics:
            if m.get('passed') is None:
                # 尝试从current值解析状态
                if m.get('current'):
                    status = self.__interpret_status(m['current'])
                    if status is not None:
                        m['passed'] = status
                        continue

                # 尝试通过数值比较判断
                if m.get('current') and m.get('required'):
                    cur_val = self.__parse_metric_value(m['current'])
                    req_val = self.__parse_metric_value(m['required'])
                    if cur_val is not None and req_val is not None and req_val > 0:
                        m['passed'] = cur_val >= req_val

        # 统计通过的指标数量
        passed_count = sum(1 for m in metrics if m.get('passed') is True)
        failed_count = sum(1 for m in metrics if m.get('passed') is False)
        total_count = len(metrics)

        # 计算进度（基于实际值的比例）
        if total_count > 0:
            progress_values = []
            for m in metrics:
                metric_progress = self.__calculate_metric_progress_value(
                    m.get('current', '0'),
                    m.get('required', '0'),
                    m.get('passed')  # 传递 passed 状态用于辅助计算
                )
                progress_values.append(metric_progress)
            progress = sum(progress_values) / len(progress_values)
        else:
            progress = 0

        # 计算剩余天数
        remaining_days = None
        end_time = assessment.get('end_time')
        if end_time:
            remaining_days = self.__parse_remaining_days(end_time, site_name)

        # 判断状态
        # 优先级：已完成 > 已过期 > 考核中
        # 注意：考核期间指标未达标不算失败，只有过期后才算失败
        if passed_count == total_count and total_count > 0:
            status = 'completed'
        elif remaining_days is not None and remaining_days < 0:
            # 已过期：有未通过指标则失败，全部通过则完成
            status = 'failed' if failed_count > 0 else 'completed'
        else:
            # 考核中（还有时间，继续努力）
            status = 'in_progress'

        # 构建消息（只显示考核内容）
        msg_parts = [f"[{assessment.get('name', '考核')}]"]
        for m in metrics:
            passed = m.get('passed')
            if passed is True:
                icon = "✓"
            elif passed is False:
                icon = "✗"
            else:
                icon = "?"

            current = m.get('current') or '-'
            required = m.get('required') or '-'
            msg_parts.append(f"{m['name']}: {current}/{required} {icon}")

        return {
            'site_id': site_id,
            'site_name': site_name,
            'status': status,
            'progress': progress,
            'remaining_days': remaining_days,
            'message': ' | '.join(msg_parts)
        }

    @staticmethod
    def __calculate_registered_days(join_at: str) -> Optional[int]:
        """根据加入时间计算注册天数"""
        if not join_at:
            return None
        try:
            # 尝试多种日期格式
            for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d']:
                try:
                    join_date = datetime.strptime(join_at.split()[0], fmt.split()[0])
                    return (datetime.now() - join_date).days
                except ValueError:
                    continue
            return None
        except Exception:
            return None

    @staticmethod
    def __is_newbie_level(user_level: str) -> bool:
        """判断是否为新用户/考核期等级"""
        if not user_level:
            return False
        # 常见的新用户等级关键词
        newbie_keywords = [
            '新', 'new', 'trial', '试用', '考核',
            'peasant', 'user', '学员', '见习'
        ]
        level_lower = user_level.lower()
        return any(kw in level_lower for kw in newbie_keywords)

    def __parse_metric_value(self, value_str: str) -> Optional[float]:
        """
        解析指标数值，支持多种单位
        统一转换为标准单位进行比较：
        - 文件大小: 转为字节 (bytes)
        - 时间: 转为小时 (hours)
        - 比率: 保持原值
        - 魔力/积分: 保持原值

        例如:
        - "3.00 GB" -> 3221225472.0 (字节)
        - "100 小时" -> 100.0 (小时)
        - "7 天" -> 168.0 (小时)
        - "1.5" (比率) -> 1.5
        - "10,000" (积分) -> 10000.0
        """
        if not value_str:
            return None

        value_str = value_str.strip()

        # 检查是否是状态文本
        if self.__interpret_status(value_str) is not None:
            return None

        # 移除常见前缀符号
        prefixes = [
            '≥', '>=', '>', '≤', '<=', '<',
            '不少于', '至少', '最少', '不低于', '不少於', '至少', '最少', '不低於',
            '需要', '需達', '需达', '要求',
            '还需', '還需', '仍需',
        ]
        for prefix in prefixes:
            if value_str.startswith(prefix):
                value_str = value_str[len(prefix):].strip()
                break

        # 尝试解析复合时间格式 "X天Y小时Z分钟"
        compound_time = self.__parse_compound_time(value_str)
        if compound_time is not None:
            return compound_time

        # 匹配数值和单位
        # 支持格式: "100", "100.5", "1,000", "100 GB", "100GB", "100 小时"
        match = re.search(r'([\d,.]+)\s*([A-Za-z\u4e00-\u9fa5]*)', value_str)
        if not match:
            return None

        try:
            # 解析数值部分
            num_str = match.group(1).replace(',', '')
            num_value = float(num_str)

            # 解析单位部分
            unit_str = match.group(2).strip() if match.group(2) else ''

            if not unit_str:
                return num_value

            unit_upper = unit_str.upper()

            # 检查是否是文件大小单位
            if unit_upper in self._SIZE_UNITS:
                return num_value * self._SIZE_UNITS[unit_upper]

            # 检查是否是时间单位
            if unit_str in self._TIME_UNITS:
                return num_value * self._TIME_UNITS[unit_str]
            if unit_upper in self._TIME_UNITS:
                return num_value * self._TIME_UNITS[unit_upper]

            # 检查中文单位
            for time_unit, multiplier in self._TIME_UNITS.items():
                if time_unit in unit_str:
                    return num_value * multiplier

            # 未知单位，返回原值
            return num_value

        except (ValueError, TypeError):
            return None

    def __parse_compound_time(self, value_str: str) -> Optional[float]:
        """
        解析复合时间格式
        支持: "3天5小时", "1周2天", "100小时30分钟"
        返回: 小时数
        """
        # 复合时间模式
        pattern = re.compile(
            r'(?:(\d+)\s*(?:年|years?))?\s*'
            r'(?:(\d+)\s*(?:月|个月|個月|months?))?\s*'
            r'(?:(\d+)\s*(?:周|週|weeks?))?\s*'
            r'(?:(\d+)\s*(?:天|日|days?))?\s*'
            r'(?:(\d+)\s*(?:小?时|小?時|hours?|hrs?))?\s*'
            r'(?:(\d+)\s*(?:分钟?|分鐘?|minutes?|mins?))?',
            re.IGNORECASE
        )

        match = pattern.match(value_str)
        if not match:
            return None

        years = int(match.group(1) or 0)
        months = int(match.group(2) or 0)
        weeks = int(match.group(3) or 0)
        days = int(match.group(4) or 0)
        hours = int(match.group(5) or 0)
        minutes = int(match.group(6) or 0)

        # 至少要有两个时间单位才认为是复合时间
        units_count = sum(1 for v in [years, months, weeks, days, hours, minutes] if v > 0)
        if units_count < 2:
            return None

        # 转换为小时
        total_hours = (
            years * 365 * 24 +
            months * 30 * 24 +
            weeks * 7 * 24 +
            days * 24 +
            hours +
            minutes / 60
        )

        return total_hours if total_hours > 0 else None

    def __detect_metric_type(self, name: str) -> str:
        """
        检测指标类型，用于确定数值比较方式
        返回: 'size' (文件大小), 'time' (时间), 'ratio' (比率), 'count' (数量)
        """
        name_lower = name.lower()

        # 检查各类型关键词
        for metric_type, keywords in self._METRIC_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in name_lower:
                    if metric_type in ('upload', 'download', 'seedsize'):
                        return 'size'
                    elif metric_type in ('seedtime', 'time'):
                        return 'time'
                    elif metric_type == 'ratio':
                        return 'ratio'
                    else:
                        return 'count'

        return 'count'  # 默认为数量类型

    def __calculate_metric_progress_value(self, current_str: str, required_str: str,
                                          passed: Optional[bool] = None) -> float:
        """
        计算单个指标的进度值
        返回 0.0 ~ 1.0 之间的进度值

        参数:
        - current_str: 当前值字符串
        - required_str: 要求值字符串
        - passed: 是否通过的状态（可选）
        """
        # 1. 如果已知通过状态，优先使用
        if passed is True:
            return 1.0  # 已通过 = 100%

        # 2. 尝试解析数值计算进度
        current = self.__parse_metric_value(current_str)
        required = self.__parse_metric_value(required_str)

        if current is not None and required is not None and required > 0:
            # 正常计算进度
            progress = current / required
            return min(progress, 1.0)

        # 3. 如果无法计算但已知未通过，给一个估算值
        if passed is False:
            # 尝试从"还需 X"提取剩余量来估算进度
            if current is not None and current > 0:
                # 有剩余量数据，说明有一定进度但未完成
                # 粗略估算：假设剩余量占总量的一部分
                return 0.3  # 未通过时给 30% 作为估算
            return 0.1  # 完全无进度时给 10%

        # 4. 状态未知且无法计算，返回0
        return 0.0

    def __parse_remaining_days(self, end_time: str, site_name: str) -> Optional[int]:
        """
        解析结束时间并计算剩余天数
        支持多种日期格式，使用时区感知的计算
        """
        if not end_time:
            return None

        # 标准化日期分隔符
        normalized_time = end_time.strip().replace('/', '-')

        # 尝试多种日期格式
        end_dt = None
        for fmt in self._DATETIME_FORMATS:
            try:
                end_dt = datetime.strptime(normalized_time, fmt)
                break
            except ValueError:
                continue

        if not end_dt:
            logger.warning(f"站点 {site_name} 时间解析失败: {end_time}")
            return None

        # 使用时区感知的计算
        try:
            tz = pytz.timezone(settings.TZ)
            end_dt_aware = tz.localize(end_dt)
            now_aware = datetime.now(tz)
            # 直接计算时区感知的时间差
            delta = end_dt_aware - now_aware
        except Exception:
            # 时区处理失败，使用本地时间
            delta = end_dt - datetime.now()

        remaining = delta.days

        # 如果还有剩余时间，算作多一天
        if delta.seconds > 0 and remaining >= 0:
            remaining += 1

        logger.debug(f"站点 {site_name} 结束时间: {end_time}, 剩余: {remaining}天")
        return remaining

    @eventmanager.register(EventType.PluginAction)
    def handle_plugin_action(self, event: Event):
        """处理插件动作事件"""
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "site_assessment":
            return
        self.__refresh_assessment()
