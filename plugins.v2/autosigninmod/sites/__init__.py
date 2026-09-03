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
        从签到返回文本中提取奖励信息（魔力值/时魔/积分/点数等）。
        优先匹配当日签到奖励（签到已得X / 签到成功获得X魔力值），
        避免把「做种积分」等非签到字段当成奖励。
        :param text: 签到返回的HTML源码或JSON字符串
        :return: 奖励描述字符串，如"获得130魔力值"，未提取到返回空字符串
        """
        if not text:
            return ""
        plain = re.sub(r"<[^>]+>", "", text)
        plain = re.sub(r"\s+", " ", plain)
        # 排除做种积分等非签到字段干扰（去掉「积分」字，防止被单位正则误匹配）
        plain_clean = plain.replace("做种总积分", "做种合计").replace("做种积分", "做种值").replace("标种积分", "标种值")
        units = "魔力值|时魔|积分|猫粮|金币|能量|豆|魔力|经验|点数"
        patterns = [
            # 1. 家园hdhome风格：签到已得X（默认魔力值/时魔）
            r"签到已得(\d+(?:\.\d+)?)",
            # 2. 动词+数字+单位：签到成功，获得/奖励27个魔力值
            r"(?:本次|此次|今日|每日)?(?:签到|打卡)?(?:成功)?[，,。！!、]?(?:您)?(?:已)?(?:获得|奖励|增加|加|收到)(?:了)?\s*(\d+(?:\.\d+)?)(?:个|点|克)?\s*(%s)" % units,
            # 3. 动词+单位+数字：获得魔力值27 / 奖励 27 个魔力值
            r"(?:获得|奖励|增加|加|收到)(?:了)?(%s)(?:个|点|克)?\s*(\d+(?:\.\d+)?)" % units,
            # 4. 单位+分隔符+数字：魔力值：27 / 魔力值 +27
            r"(%s)\s*[+：:]\s*(\d+(?:\.\d+)?)" % units,
            # 5. 数字+单位（兜底）
            r"(\d+(?:\.\d+)?)\s*(?:个|点|克)?\s*(%s)" % units,
        ]
        # 先跑文本正则（索引：0=签到已得, 1=动词+数字+单位, 2=动词+单位+数字, 3=单位+分隔符+数字, 4=数字+单位兜底）
        for i, p in enumerate(patterns):
            m = re.search(p, plain_clean)
            if m:
                if i == 0:
                    val = m.group(1)
                    unit = "魔力值"
                elif i in (2, 3):
                    # 单位在前：group(1)=单位, group(2)=数字
                    unit, val = m.group(1), m.group(2)
                else:
                    # 数字在前：group(1)=数字, group(2)=单位
                    val, unit = m.group(1), m.group(2) or "魔力值"
                if unit == "魔力":
                    unit = "魔力值"
                return f"获得{val}{unit}"
        # JSON 数值字段兜底（纯数值响应，如 {"bonus": 27}）
        try:
            import json
            obj = json.loads(plain)
            unit_map = {
                "bonus": "积分", "integral": "积分", "points": "积分", "score": "积分",
                "magic": "魔力值", "魔力": "魔力值", "时魔": "魔力值",
                "gold": "金币", "coin": "金币", "energy": "能量", "bean": "豆",
            }

            def _find(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        kl = str(k).lower()
                        hit = next((u for key, u in unit_map.items() if key in kl), None)
                        if hit and isinstance(v, (int, float)) or (hit and isinstance(v, str) and str(v).replace(".", "", 1).isdigit()):
                            return f"获得{str(v).replace('.0', '')}{hit}"
                        r = _find(v)
                        if r is not None:
                            return r
                elif isinstance(obj, list):
                    for v in obj:
                        r = _find(v)
                        if r is not None:
                            return r
                return None
            return _find(obj) or ""
        except Exception:
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
