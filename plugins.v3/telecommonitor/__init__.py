"""
电信套餐监控插件 — 监控中国电信手机套餐流量、语音、余额使用情况
"""
import json
import datetime
import re
import calendar
import threading
from typing import Optional, Any, List, Dict, Tuple, Callable

import pytz
from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .core.services.telecom_api import Telecom


class TelecomMonitor(_PluginBase):
    """电信套餐监控插件。"""

    plugin_name = "电信套餐监控"
    plugin_desc = "监控中国电信手机套餐流量、语音、余额使用情况，每日自动查询并推送。"
    plugin_icon = "https://raw.githubusercontent.com/Cp0204/ChinaTelecomMonitor/main/icon.png"
    plugin_version = "0.0.1"
    plugin_author = "asice999"
    author_url = "https://github.com/asice999"
    plugin_config_prefix = "telecommonitor_"
    plugin_order = 22
    auth_level = 1

    # 调度器
    _scheduler: Optional[BackgroundScheduler] = None

    # 配置属性
    _enabled: bool = False
    _show_sidebar_nav: bool = True
    _notify: bool = False
    _notification_type: NotificationType = NotificationType.Plugin
    _cron: str = "0 20 * * *"
    _phonenum: str = ""
    _password: str = ""
    _only_warn: bool = False  # 流量正常时跳过通知

    # 缓存（不存配置，只存运行时）
    _login_info: Dict[str, Any] = {}
    _last_summary: Dict[str, Any] = {}

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "show_sidebar_nav",
                                            "label": "启用左侧导航",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "phonenum",
                                            "label": "手机号",
                                            "placeholder": "11位手机号",
                                            "type": "text",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "password",
                                            "label": "密码",
                                            "placeholder": "电信服务密码",
                                            "type": "password",
                                            "autocomplete": "new-password",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "cron",
                                            "label": "定时 cron",
                                            "placeholder": "0 20 * * *",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "notify",
                                            "label": "启用通知",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "only_warn",
                                            "label": "流量正常时跳过通知",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "notification_type",
                                            "label": "通知类型",
                                            "items": [
                                                {"title": "插件消息", "value": "Plugin"},
                                                {"title": "系统消息", "value": "System"},
                                                {"title": "重要消息", "value": "Important"},
                                            ],
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "show_sidebar_nav": True,
            "notify": False,
            "notification_type": "Plugin",
            "cron": "0 20 * * *",
            "phonenum": "",
            "password": "",
            "only_warn": False,
        }

    def get_page(self) -> Optional[List[dict]]:
        return [
            {
                "component": "VMenuCard",
                "content": [
                    {
                        "component": "VMenuItem",
                        "props": {
                            "to": "/plugins/telecom_monitor/dashboard",
                            "icon": "mdi-monitor-dashboard",
                            "title": "套餐概览",
                        },
                    },
                    {
                        "component": "VMenuItem",
                        "props": {
                            "to": "/plugins/telecom_monitor/history",
                            "icon": "mdi-history",
                            "title": "查询历史",
                        },
                    },
                ],
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/query",
                "endpoint": self.api_query,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "查询当前套餐用量",
            },
            {
                "path": "/login",
                "endpoint": self.api_login,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "测试登录并获取 token",
            },
            {
                "path": "/history",
                "endpoint": self.api_history,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取查询历史记录",
            },
            {
                "path": "/overview",
                "endpoint": self.api_overview,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取仪表盘概览数据",
            },
        ]

    def get_sidebar_nav(self) -> List[Dict[str, Any]]:
        if not self._enabled or not self._show_sidebar_nav:
            return []
        return [{
            "nav_key": "main",
            "title": "电信套餐",
            "icon": "mdi-cellphone-check",
            "section": "subscribe",
            "permission": "subscribe",
            "order": 31,
        }]

    def get_dashboard_meta(self) -> List[Dict[str, str]]:
        if not self._enabled:
            return []
        return [
            {"key": "overview", "name": "电信套餐"},
        ]

    def get_dashboard(self, key: str = "overview", **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], None]]:
        if not self._enabled:
            return None
        return (
            {"cols": 12, "sm": 6, "md": 4},
            {"title": "电信套餐", "subtitle": "流量/语音/余额概览", "dashboard": "overview", "refresh": 3600, "border": True},
            None,
        )

    @staticmethod
    def _cron_is_valid(cron_expr: str) -> bool:
        cron_expr = (cron_expr or "").strip()
        if not cron_expr:
            return False
        try:
            tz = pytz.timezone(settings.TZ)
            CronTrigger.from_crontab(cron_expr, timezone=tz)
            return True
        except Exception:
            return False

    def init_plugin(self, config: dict = None):
        """加载配置并启动调度。"""
        config = dict(config or {})
        self._enabled = config.get("enabled", False)
        self._show_sidebar_nav = config.get("show_sidebar_nav", True)
        self._notify = config.get("notify", False)
        self._notification_type = config.get("notification_type", "Plugin")
        self._cron = config.get("cron", "0 20 * * *")
        self._phonenum = config.get("phonenum", "")
        self._password = config.get("password", "")
        self._only_warn = config.get("only_warn", False)

        # 停止旧调度
        self.stop()

        if not self._enabled:
            logger.info("电信套餐监控插件未启用")
            return

        # 启动定时任务
        if self._cron_is_valid(self._cron):
            try:
                self._scheduler = BackgroundScheduler(timezone=settings.TZ)
                self._scheduler.add_job(
                    self.check_and_notify,
                    CronTrigger.from_crontab(self._cron, timezone=settings.TZ),
                    name="telecom_monitor_check",
                )
                self._scheduler.start()
                logger.info(f"电信套餐监控定时任务已启动: {self._cron}")
            except Exception as e:
                logger.error(f"启动定时任务失败: {e}")
        else:
            logger.warning(f"无效 cron 表达式: {self._cron}")

        # 恢复缓存登录信息（从数据存储）
        self._load_login_info()

        logger.info("电信套餐监控插件初始化完成")

    def stop(self):
        """停止调度器。"""
        if self._scheduler:
            try:
                self._scheduler.remove_all_jobs()
                self._scheduler.shutdown(wait=False)
            except Exception as e:
                logger.error(f"停止调度器失败: {e}")
            self._scheduler = None

    def _load_login_info(self):
        """从数据存储加载缓存的登录信息。"""
        try:
            data = self.get_data("login_info")
            if data:
                self._login_info = data
                logger.info("已加载缓存的登录信息")
        except Exception as e:
            logger.debug(f"加载登录信息缓存失败: {e}")

    def _save_login_info(self, login_info: dict):
        """保存登录信息到数据存储。"""
        self._login_info = login_info
        try:
            self.save_data("login_info", login_info)
            logger.info("登录信息已缓存")
        except Exception as e:
            logger.error(f"保存登录信息缓存失败: {e}")

    def _get_telecom_client(self) -> Telecom:
        """创建并配置 Telecom 客户端。"""
        client = Telecom()
        if self._login_info.get("phonenum"):
            client.set_login_info(self._login_info)
        return client

    def _do_login(self) -> dict:
        """使用配置的手机号+密码登录，返回登录信息。"""
        phonenum = self._phonenum.strip()
        password = self._password.strip()
        if not phonenum or not password:
            raise ValueError("手机号和密码未配置")

        client = Telecom()
        result = client.do_login(phonenum, password)
        response_data = result.get("responseData", {})
        if response_data.get("resultCode") == "0000":
            login_info = response_data["data"]["loginSuccessResult"]
            login_info["phonenum"] = phonenum
            login_info["createTime"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_login_info(login_info)
            return login_info
        else:
            err_msg = response_data.get("data", {}).get("loginFailResult", {}).get("loginFailDesc", "登录失败")
            raise RuntimeError(f"登录失败: {err_msg}")

    def _do_query(self, force_login: bool = False) -> dict:
        """查询套餐用量。自动处理 token 过期。"""
        client = self._get_telecom_client()

        # 尝试用缓存 token 查询
        if not force_login and self._login_info.get("token"):
            try:
                data = client.qry_important_data()
                if data.get("responseData"):
                    return client.to_summary(data["responseData"]["data"])
                elif data.get("headerInfos", {}).get("code") == "X201":
                    logger.info("Token 已过期，重新登录")
                    return self._do_query(force_login=True)
                else:
                    raise RuntimeError(f"查询失败: {data.get('headerInfos', {}).get('reason', '未知错误')}")
            except Exception as e:
                if "X201" in str(e) or "token" in str(e).lower():
                    return self._do_query(force_login=True)
                raise

        # 需要重新登录
        if self._phonenum and self._password:
            self._do_login()
            return self._do_query(force_login=False)
        else:
            raise ValueError("无有效 token 且未配置手机号密码，无法查询")

    # === API 端点 ===

    def api_query(self) -> Dict[str, Any]:
        """查询当前套餐用量（API 端点）。"""
        try:
            summary = self._do_query()
            self._last_summary = summary
            self.save_data("last_summary", summary)
            # 记录历史
            self._save_history(summary)
            return {"success": True, "data": summary}
        except Exception as e:
            logger.error(f"查询套餐用量失败: {e}")
            return {"success": False, "error": str(e)}

    def api_login(self, **kwargs) -> Dict[str, Any]:
        """测试登录（API 端点）。"""
        try:
            phonenum = kwargs.get("phonenum") or self._phonenum
            password = kwargs.get("password") or self._password
            if not phonenum or not password:
                return {"success": False, "error": "手机号和密码不能为空"}
            login_info = self._do_login()
            return {"success": True, "data": {"phonenum": phonenum, "token": login_info.get("token", "")[:20] + "..."}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_history(self, **kwargs) -> Dict[str, Any]:
        """获取查询历史。"""
        try:
            limit = int(kwargs.get("limit", 30))
            data = self.get_data("history") or []
            return {"success": True, "data": data[:limit]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_overview(self) -> Dict[str, Any]:
        """获取仪表盘概览数据。"""
        try:
            summary = self._last_summary or self.get_data("last_summary") or {}
            login_info = self._login_info or {}
            history = self.get_data("history") or []
            return {
                "success": True,
                "data": {
                    "summary": summary,
                    "phonenum": login_info.get("phonenum", self._phonenum),
                    "last_query_time": summary.get("createTime", ""),
                    "history_count": len(history),
                    "cron": self._cron,
                    "enabled": self._enabled,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # === 数据存储 ===

    def _save_history(self, summary: dict):
        """保存查询历史。"""
        try:
            history = self.get_data("history") or []
            record = {
                "time": summary.get("createTime", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                "flow_use_gb": round(summary.get("flowUse", 0) / (1024**3), 2),
                "flow_total_gb": round(summary.get("flowTotal", 0) / (1024**3), 2),
                "voice_use": summary.get("voiceUsage", 0),
                "balance": summary.get("balance", 0),
                "common_use_gb": round(summary.get("commonUse", 0) / (1024**3), 2),
                "common_total_gb": round(summary.get("commonTotal", 0) / (1024**3), 2),
            }
            history.insert(0, record)
            # 保留最近 100 条
            if len(history) > 100:
                history = history[:100]
            self.save_data("history", history)
        except Exception as e:
            logger.error(f"保存历史记录失败: {e}")

    # === 定时任务 ===

    def check_and_notify(self):
        """定时执行：查询套餐用量并推送通知。"""
        logger.info("开始执行电信套餐查询...")
        try:
            summary = self._do_query()
            self._last_summary = summary
            self.save_data("last_summary", summary)
            self._save_history(summary)
            logger.info(f"查询成功: {json.dumps(summary, ensure_ascii=False)}")

            if not self._notify:
                return

            # 判断是否跳过通知
            if self._only_warn:
                common_use = summary.get("commonUse", 0)
                common_total = summary.get("commonTotal", 0)
                if common_total > 0:
                    today = datetime.date.today()
                    _, days_in_month = calendar.monthrange(today.year, today.month)
                    time_progress = today.day / days_in_month
                    usage_progress = common_use / common_total
                    if usage_progress <= time_progress * 1.5:
                        logger.info("流量使用正常，跳过通知")
                        return

            # 构建通知消息
            phonenum = summary.get("phonenum", self._phonenum)
            balance = round(summary.get("balance", 0) / 100, 2)
            voice_use = summary.get("voiceUsage", 0)
            voice_total = summary.get("voiceTotal", 0)
            common_use_gb = round(summary.get("commonUse", 0) / (1024**3), 2)
            common_total_gb = round(summary.get("commonTotal", 0) / (1024**3), 2)

            title = "📱 电信套餐用量"
            body = (
                f"📱 手机：{phonenum}\n"
                f"💰 余额：{balance} 元\n"
                f"📞 通话：{voice_use}/{voice_total} min\n"
                f"🌐 流量：{common_use_gb}/{common_total_gb} GB\n"
                f"⏰ {summary.get('createTime', '')}"
            )
            self.post_message(
                mtype=NotificationType[self._notification_type] if self._notification_type in NotificationType.__members__ else NotificationType.Plugin,
                title=title,
                body=body,
            )
            logger.info("通知已发送")
        except Exception as e:
            logger.error(f"定时查询失败: {e}")
            if self._notify:
                self.post_message(
                    mtype=NotificationType[self._notification_type] if self._notification_type in NotificationType.__members__ else NotificationType.Plugin,
                    title="❌ 电信套餐查询失败",
                    body=str(e),
                )