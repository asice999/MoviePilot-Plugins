"""站点多面板管理器（合并测试版）"""
from typing import Any, Dict, List, Tuple
from app.plugins import _PluginBase
from app.core.config import settings
from app.log import logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import pytz

from .core.refresh_service import SiteRefresh
from .core.signin_service import AutoSignIn
from .core.statistic_service import SiteStatistic
from .core.assessment_service import SiteAssessment

class SiteManager(_PluginBase):
    plugin_name = "站点多面板管理器"
    plugin_desc = "自用：合并签到、统计、刷新、考核的多面板管理器"
    plugin_version = "0.1.0"
    plugin_icon = "statistic.png"
    plugin_author = "asice999"
    author_url = "https://github.com/asice999"
    plugin_config_prefix = "sitemanager_"
    _enabled = False
    _scheduler = None

    def __init__(self):
        super().__init__()
        self._refresh = SiteRefresh()
        self._signin = AutoSignIn()
        self._statistic = SiteStatistic()
        self._assessment = SiteAssessment()
        self._bind_owner()


    def _bind_owner(self):
        for s in [self._refresh, self._signin, self._statistic, self._assessment]:
            try:
                s._init_callbacks(self)
            except Exception as e:
                logger.error(f"bind owner {s.__class__.__name__}: {e}")
    def init_plugin(self, config: dict = None):
        self._enabled = bool((config or {}).get('enabled', False))
        for s in [self._refresh, self._signin, self._statistic, self._assessment]:
            try:
                s.init_plugin(config or {})
            except Exception as e:
                logger.error(f'init {s.__class__.__name__} failed: {e}')
        if not self._scheduler:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        if not self._scheduler.running:
            self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    def get_service(self) -> List[Dict[str, Any]]:
        rv=[]
        for s in [self._refresh, self._signin, self._statistic, self._assessment]:
            try: rv.extend(s.get_service() or [])
            except Exception as e: logger.error(f'get_service {s.__class__.__name__}: {e}')
        return rv

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        forms=[]
        data={'enabled':self._enabled}
        for s in [self._refresh, self._signin, self._statistic, self._assessment]:
            try:
                f,d=s.get_form()
                forms.extend(f or [])
                data.update(d or {})
            except Exception as e:
                logger.error(f'get_form {s.__class__.__name__}: {e}')
        return forms, data

    def get_api(self) -> List[Dict[str, Any]]:
        rv=[]
        for s in [self._refresh, self._signin, self._statistic, self._assessment]:
            try: rv.extend(s.get_api() or [])
            except Exception: pass
        return rv

    def get_command(self) -> List[Dict[str, Any]]:
        rv=[]
        for s in [self._refresh, self._signin, self._statistic, self._assessment]:
            try: rv.extend(s.get_command() or [])
            except Exception: pass
        return rv

    def get_page(self) -> List[dict]:
        pages=[]
        for s in [self._refresh, self._signin, self._statistic, self._assessment]:
            try: pages.extend(s.get_page() or [])
            except Exception as e: logger.error(f'get_page {s.__class__.__name__}: {e}')
        return pages

    def stop_service(self):
        for s in [self._refresh, self._signin, self._statistic, self._assessment]:
            try: s.stop_service()
            except Exception: pass
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown()
            self._scheduler=None
