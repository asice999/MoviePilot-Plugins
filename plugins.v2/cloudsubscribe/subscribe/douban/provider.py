"""豆瓣自动订阅能力组装。"""
from typing import Iterator
from urllib.parse import urlsplit, urlunsplit

from app.log import logger

from .client import DoubanClient
from .service import DoubanService
from ...core.subscribe import MediaCandidate, SubscribeContext, SubscribeProvider
from ...core.subscribe.registry import register

DOUBAN_ROUTES = {
    "movie-ustop": "/douban/movie/ustop",
    "movie-weekly": "/douban/movie/weekly",
    "movie-real-time": "/douban/movie/weekly/movie_real_time_hotest",
    "show-domestic": "/douban/movie/weekly/show_domestic",
    "movie-hot-gaia": "/douban/movie/weekly/movie_hot_gaia",
    "tv-hot": "/douban/movie/weekly/tv_hot",
    "movie-top250": "/douban/list/movie_top250",
}


@register
class DoubanSubscribeProvider(SubscribeProvider):
    provider_id = "douban"
    provider_name = "豆瓣榜单"

    def __init__(self, client: DoubanClient | None = None, service: DoubanService | None = None):
        self.client = client or DoubanClient()
        self.service = service or DoubanService()

    def spec(self) -> dict:
        return {"id": self.provider_id, "name": self.provider_name, "default_cron": "0 8 * * *"}

    def has_listening(self, options: dict) -> bool:
        return bool(options.get("ranks") or str(options.get("rss_urls") or "").strip())

    def fetch(self, options: dict, context: SubscribeContext) -> Iterator[MediaCandidate]:
        configured_base = options.get("rsshub_base") or options.get("rsshub_base_url")
        configured_base = str(configured_base or "").strip().rstrip("/")
        base = configured_base or "https://rsshub.liumingye.cn"
        if not base.startswith(("http://", "https://")):
            base = f"https://{base}"
        configured_urls = options.get("rss_urls") or []
        if isinstance(configured_urls, str):
            configured_urls = configured_urls.splitlines()
        urls = [str(value or "").strip() for value in configured_urls if str(value or "").strip()]
        urls.extend(
            f"{base}{DOUBAN_ROUTES[rank]}"
            for rank in options.get("ranks") or []
            if rank in DOUBAN_ROUTES
        )
        logger.debug(
            f"豆瓣榜单请求配置：rsshub_base={base}, configured={bool(configured_base)}, "
            f"custom_urls={len(configured_urls)}, ranks={list(options.get('ranks') or [])}, "
            f"request_urls={len(dict.fromkeys(urls))}"
        )
        failures = []
        for url in dict.fromkeys(urls):
            if context.stopped():
                return
            try:
                text = self.client.get(url, context.proxy_for(options.get("proxy")))
                logger.debug(f"豆瓣榜单请求成功：url={self._display_url(url)}, bytes={len(text)}")
                yield from self.service.parse(text, url)
            except Exception as error:
                display_url = self._display_url(url)
                failures.append(f"{display_url}: {error}")
                logger.warning(f"豆瓣榜单 URL 跳过：url={display_url}, error={error}")
        if urls and failures and len(failures) == len(dict.fromkeys(urls)):
            raise RuntimeError("豆瓣榜单所有 RSS 地址均请求失败：" + "；".join(failures))

    @staticmethod
    def _display_url(url: str) -> str:
        parsed = urlsplit(str(url or ""))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def create_douban_provider() -> DoubanSubscribeProvider:
    return DoubanSubscribeProvider()
