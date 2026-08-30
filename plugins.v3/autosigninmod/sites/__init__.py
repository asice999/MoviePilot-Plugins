# -*- coding: utf-8 -*-
import re
from abc import ABCMeta, abstractmethod
from typing import Tuple

import chardet
from ruamel.yaml import CommentedMap

from app.core.config import settings
from app.helper.browser import PlaywrightHelper
from app.log import logger
from app.utils.http import RequestUtils
from app.utils.string import StringUtils


class _ISiteSigninHandler(metaclass=ABCMeta):
    """
    实现站点签到的基类，所有站点签到类都需要继承此类，并实现match和signin方法
    实现类放置到sitesignin目录下将会自动加载
    """
    # 匹配的站点Url，每一个实现类都需要设置为自己的站点Url
    site_url = ""

    @abstractmethod
    def match(self, url: str) -> bool:
        """
        根据站点Url判断是否匹配当前站点签到类，大部分情况使用默认实现即可
        :param url: 站点Url
        :return: 是否匹配，如匹配则会调用该类的signin方法
        """
        if StringUtils.url_equal(url, self.site_url):
            return True
        return False

    @abstractmethod
    def signin(self, site_info: CommentedMap) -> Tuple[bool, str]:
        """
        执行签到操作
        :param site_info: 站点信息，含有站点Url、站点Cookie、UA等信息
        :return: True|False,签到结果信息
        """
        pass

    @staticmethod
    def get_page_source(url: str, cookie: str, ua: str, proxy: bool, render: bool,
                        token: str = None, timeout: int = None) -> str:
        """
        获取页面源码
        :param url: Url地址
        :param cookie: Cookie
        :param ua: UA
        :param proxy: 是否使用代理
        :param render: 是否渲染
        :param token: JWT Token
        :param timeout: 请求超时时间，单位秒
        :return: 页面源码，错误信息
        """
        if render:
            return PlaywrightHelper().get_page_source(url=url,
                                                      cookies=cookie,
                                                      ua=ua,
                                                      proxies=settings.PROXY_SERVER if proxy else None,
                                                      timeout=timeout or 60)
        else:
            if token:
                headers = {
                    "Authorization": token,
                    "User-Agent": ua
                }
            else:
                headers = {
                    "User-Agent": ua,
                    "Cookie": cookie
                }
            res = RequestUtils(headers=headers,
                               proxies=settings.PROXY if proxy else None,
                               timeout=timeout or 20).get_res(url=url)
            if res is not None:
                # 使用chardet检测字符编码
                raw_data = res.content
                if raw_data:
                    try:
                        result = chardet.detect(raw_data)
                        encoding = result['encoding']
                        # 解码为字符串
                        return raw_data.decode(encoding)
                    except Exception as e:
                        logger.error(f"chardet解码失败：{str(e)}")
                        return res.text
                else:
                    return res.text
            return ""

    @staticmethod
    def sign_in_result(html_res: str, regexs: list) -> bool:
        """
        判断是否签到成功
        """
        html_text = re.sub(r"#\d+", "", re.sub(r"\d+px", "", html_res))
        for regex in regexs:
            if re.search(str(regex), html_text):
                return True
        return False


    @staticmethod
    def _extract_reward(text: str) -> str:
        """
        从签到返回文本中提取奖励信息（魔力值/积分/点数等）
        :param text: 签到返回的HTML源码或JSON字符串
        :return: 奖励描述字符串，如"获得100魔力值"，未提取到返回空字符串
        """
        if not text:
            return ""
        plain = re.sub(r"<[^>]+>", "", text)
        plain = re.sub(r"\s+", " ", plain)
        patterns = [
            r"(?:本次|此次)?签到(?:成功)?[，,。]?(?:您)?(?:已)?获得(\d+(?:\.\d+)?)(?:个|点|克)?(魔力值|积分|猫粮|金币|能量|豆|魔力)",
            r"获得(\d+(?:\.\d+)?)(?:个|点|克)?(魔力值|积分|猫粮|金币|能量|豆)",
            r"[\"']integral[\"']\s*[:=]\s*[\"']?(\d+(?:\.\d+)?)\s*(积分)?",
            r"(\d+(?:\.\d+)?)\s*(?:个|点|克)?\s*(魔力值|积分|猫粮|金币|能量|豆)",
            r"(魔力值|积分|猫粮|金币|能量|豆)\s*[+：:]\s*(\d+(?:\.\d+)?)",
        ]
        for p in patterns:
            m = re.search(p, plain)
            if m:
                if p == patterns[-1]:
                    unit, val = m.group(1), m.group(2)
                else:
                    val, unit = m.group(1), m.group(2) or "积分"
                if unit == "魔力":
                    unit = "魔力值"
                return f"获得{val}{unit}"
        return ""


    @staticmethod
    def _reward_msg(text: str, default: str = "签到成功") -> str:
        """
        签到成功消息 + 奖励信息
        :param text: 签到返回文本
        :param default: 默认成功消息
        :return: 如"签到成功，获得100魔力值"，无奖励则返回默认消息
        """
        reward = _ISiteSigninHandler._extract_reward(text)
        if reward:
            return f"{default}，{reward}"
        return default
