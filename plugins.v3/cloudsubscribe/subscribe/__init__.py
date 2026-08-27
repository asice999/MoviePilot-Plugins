"""自动订阅渠道集合。"""

from .douban import create_douban_provider
from .maoyan import create_maoyan_provider
from .mikan import create_mikan_provider
from .netflix import create_netflix_provider

__all__ = [
    "create_douban_provider",
    "create_maoyan_provider",
    "create_mikan_provider",
    "create_netflix_provider",
]
