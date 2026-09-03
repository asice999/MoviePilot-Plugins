"""自动订阅渠道契约。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from threading import Event
from typing import Any, Iterator, Optional


@dataclass
class SubscribeContext:
    owner: Any = None
    event: Optional[Event] = None
    logger: Any = None
    config: dict[str, Any] | None = None
    # 由宿主后端统一构造的搜索代理 URL（含可选认证信息）。
    proxy: Any = None

    def stopped(self) -> bool:
        return bool(self.event and self.event.is_set())

    def proxy_for(self, enabled: Any) -> Any:
        """按渠道开关返回共享搜索代理；未启用时保持直连。"""
        if not bool(enabled):
            return None
        if not self.proxy:
            raise RuntimeError("已启用榜单代理，但搜索渠道代理地址未配置或无效")
        return self.proxy


class SubscribeProvider(ABC):
    provider_id = ""
    provider_name = ""

    @abstractmethod
    def spec(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, options: dict[str, Any], context: SubscribeContext) -> Iterator[Any]:
        raise NotImplementedError

    def has_listening(self, options: dict[str, Any]) -> bool:
        return True
