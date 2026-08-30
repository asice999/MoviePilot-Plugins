import re
from typing import Tuple

from app.core.config import settings
from app.log import logger
from app.plugins.autosignin_mod.sites import _ISiteSigninHandler
from app.utils.http import RequestUtils
from lxml import etree


class Pt52(_ISiteSigninHandler):
    """
    52pt
    滑块验证码签到（滑块值由页面JS动态生成，随session绑定）
    """
    # 匹配的站点Url，每一个实现类都需要设置为自己的站点Url
    site_url = "52pt.site"

    @classmethod
    def match(cls, url: str) -> bool:
        return "52pt" in url

    def signin(self, site_info: object) -> Tuple[bool, str]:
        site = site_info.get("name")
        site_cookie = site_info.get("cookie")
        ua = site_info.get("ua")
        proxy = site_info.get("proxy")

        # 同一session先GET获取token和动态滑块值，再POST提交
        req = RequestUtils(cookies=site_cookie, ua=ua, proxies=settings.PROXY if proxy else None)
        html_res = req.get_res(url="https://52pt.site/bakatest.php")
        if not html_res or html_res.status_code != 200:
            logger.error(f"{site} 签到失败，请检查站点连通性")
            return False, "签到失败，请检查站点连通性"

        html_text = html_res.text
        if "今天已经签过到了" in html_text:
            logger.info(f"{site} 今日已签到")
            return True, "今日已签到"

        # 提取动态滑块值 captchaInput.value = 'XXXX'
        captcha_match = re.search(r"captchaInput\.value\s*=\s*'(\d+)'", html_text)
        if not captcha_match:
            logger.error(f"{site} 签到失败，未获取到滑块验证码")
            return False, "签到失败，未获取到滑块验证码"
        captcha = captcha_match.group(1)

        # 提取 sign_token
        html = etree.HTML(html_text)
        token_list = html.xpath("//input[@name='sign_token']/@value")
        if not token_list:
            logger.error(f"{site} 签到失败，未获取到sign_token")
            return False, "签到失败，未获取到sign_token"
        sign_token = token_list[0]

        # POST 提交签到
        data = {
            "sign_captcha": captcha,
            "sign_token": sign_token,
            "sign_submit": "1",
        }
        sign_res = req.post_res(url="https://52pt.site/bakatest.php", data=data)
        if not sign_res or sign_res.status_code != 200:
            logger.error(f"{site} 签到失败，签到接口请求失败")
            return False, "签到失败，签到接口请求失败"

        sign_text = sign_res.text
        if "签到成功" in sign_text:
            logger.info(f"{site} 签到成功")
            return True, "签到成功"
        elif "今天已经签过到了" in sign_text:
            logger.info(f"{site} 今日已签到")
            return True, "今日已签到"
        elif "签到失败" in sign_text:
            logger.error(f"{site} 签到失败，{sign_text[sign_text.find('签到失败'):sign_text.find('签到失败')+100]}")
            return False, "签到失败"
        else:
            logger.error(f"{site} 签到失败，签到接口返回异常")
            return False, "签到失败，签到接口返回异常"
