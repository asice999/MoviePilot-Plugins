"""ServiceAdapter: 让各签到/统计/考核服务脱离 _PluginBase，通过回调注入依赖"""
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.config import settings
from app.log import logger


class ServiceAdapter:
    """服务基类：所有原 _PluginBase 依赖改为回调注入"""

    def __init__(self, owner=None):
        self._owner = owner
        self._enabled = False
        self._onlyonce = False
        self._cron = ""
        self._notify = False
        self._scheduler: Optional[BackgroundScheduler] = None
        self._config: Dict[str, Any] = {}
        self._siteconf = {}

    # ---- 回调注入 ----
    def _init_callbacks(self, owner):
        self._owner = owner

    def save_data(self, key: str, value: Any):
        if self._owner and hasattr(self._owner, 'save_data'):
            self._owner.save_data(key, value)

    def get_data(self, key: str):
        if self._owner and hasattr(self._owner, 'get_data'):
            return self._owner.get_data(key)
        return None

    def post_message(self, mtype=None, title="", text=""):
        if self._owner and hasattr(self._owner, 'post_message'):
            self._owner.post_message(mtype=mtype, title=title, text=text)

    def update_config(self, config: Dict[str, Any]):
        if self._owner and hasattr(self._owner, 'update_config'):
            self._owner.update_config(config)

    def get_state(self) -> bool:
        return bool(self._enabled)

    def get_service(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self):
        return [], {}

    def get_page(self):
        return []

    def stop_service(self):
        try:
            if self._scheduler and self._scheduler.running:
                self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error(f"stop_service error: {e}")

    def _ensure_scheduler(self):
        if not self._scheduler:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            if not self._scheduler.running:
                self._scheduler.start()
        return self._scheduler

    def get_api(self):
        return []

    def get_command(self):
        return []

    def get_config(self, key=None, default=None):
        if key is None:
            return self._config
        return self._config.get(key, default)

    def get_config_prefix(self):
        return ""
