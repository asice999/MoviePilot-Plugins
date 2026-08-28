from dataclasses import dataclass, field
from typing import Any, Dict, List

@dataclass
class SiteManagerCommon:
    enabled: bool = False
    onlyonce: bool = False
    cron: str = "0 8 * * *"
    show_signin: bool = True
    show_statistic: bool = True
    show_refresh: bool = True
    show_assessment: bool = True
    data_map: Dict[str, Any] = field(default_factory=dict)

    def load_config(self, cfg: Dict[str, Any]):
        self.enabled = bool(cfg.get('enabled', self.enabled))
        self.onlyonce = bool(cfg.get('onlyonce', self.onlyonce))
        self.cron = cfg.get('cron', self.cron)

    def form(self):
        return [
            {"component":"VSwitch","props":{"model":"enabled","label":"启用"}},
            {"component":"VSwitch","props":{"model":"onlyonce","label":"立即执行一次"}},
            {"component":"VTextField","props":{"model":"cron","label":"定时"}},
        ]

    def data(self):
        return {"enabled": self.enabled, "onlyonce": self.onlyonce, "cron": self.cron}

    def page(self):
        return []
