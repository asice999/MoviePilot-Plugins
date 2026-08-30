from typing import Any, List, Dict, Tuple

from app.chain.site import SiteChain
from app.core.event import eventmanager
from app.db.site_oper import SiteOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.utils.string import StringUtils


class SiteRefresh(_PluginBase):
    # 插件名称
    plugin_name = "站点自动更新"
    # 插件描述
    plugin_desc = "自用：使用浏览器模拟登录站点获取Cookie和UA。"
    # 插件图标
    plugin_icon = "Chrome_A.png"
    # 插件版本
    plugin_version = "1.3"
    # 插件作者
    plugin_author = "asice999"
    # 作者主页
    author_url = "https://github.com/asice999"
    # 插件配置项ID前缀
    plugin_config_prefix = "siterefresh_"
    # 加载顺序
    plugin_order = 2
    # 可使用的用户级别
    auth_level = 2

    # 配置属性
    _enabled: bool = False
    _notify: bool = False
    """
    格式
    站点domain|用户名|用户密码
    """
    _siteconf: list = []

    def init_plugin(self, config: dict = None):

        # 配置
        if config:
            self._enabled = config.get("enabled")
            self._notify = config.get("notify")
            # 兼容旧版文本域
            self._siteconf = []
            if config.get("siteconf"):
                self._siteconf = [x.strip() for x in str(config.get("siteconf")).split('\n') if x.strip()]
            # 新版结构化配置：5 组槽位
            for i in range(1, 13):
                domain = str(config.get(f"domain_{i}") or "").strip()
                username = str(config.get(f"username_{i}") or "").strip()
                password = str(config.get(f"password_{i}") or "").strip()
                code = str(config.get(f"code_{i}") or "").strip()
                if domain and username and password:
                    item = f"{domain}|{username}|{password}"
                    if code:
                        item += f"|{code}"
                    self._siteconf.append(item)

    def get_state(self) -> bool:
        return self._enabled

    @eventmanager.register(EventType.PluginAction)
    def site_refresh(self, event):
        """
        开始站点登录，刷新Cookie&UA
        """
        if not self.get_state():
            return
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "site_refresh":
            return
        # 站点id
        site_id = event_data.get("site_id")
        if not site_id:
            logger.error(f"未获取到site_id")
            return

        site = SiteOper().get(site_id)
        if not site:
            logger.error(f"未获取到site_id {site_id} 对应的站点数据")
            return

        site_name = site.name
        logger.info(f"开始尝试登录站点 {site_name}")
        siteurl, siteuser, sitepwd, sitecode = None, None, None, None
        # 判断site是否已配置用户名密码
        for site_conf in self._siteconf:
            if not site_conf:
                continue
            site_confs = str(site_conf).split("|")
            try:
                siteurl, siteuser, sitepwd, *sitecode = site_confs
                sitecode = str(sitecode[0]) if sitecode else ""
            except Exception as e:
                logger.error(f"{site_conf}配置有误:{e}，已跳过")
                continue

            # 判断是否是目标域名
            if str(siteurl) in StringUtils.get_url_domain(site.url):
                # 找到目标域名配置，跳出循环
                break

        # 开始登录更新cookie和ua
        if siteurl and siteuser and sitepwd:
            state, messages = SiteChain().update_cookie(site_info=site,
                                                        username=siteuser,
                                                        password=sitepwd,
                                                        two_step_code=sitecode)
            if state:
                logger.info(f"站点{site_name}自动更新Cookie和Ua成功")
            else:
                logger.error(f"站点{site_name}自动更新Cookie和Ua失败")

            if self._notify:
                self.post_message(mtype=NotificationType.SiteMessage,
                                  title=f"站点 {site_name} Cookie已失效。",
                                  text=f"自动更新Cookie和Ua{'成功' if state else '失败'}")
        else:
            logger.error(f"未获取到站点{site_name}配置，已跳过")

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        # 全部已配置站点
        site_options = [{"title": site.name, "value": StringUtils.get_url_domain(site.url)}
                        for site in SiteOper().list_order_by_pri()]
        if not site_options:
            site_options = [{"title": "无可用站点", "value": ""}]

        # 开关区
        content = [
            {
                'component': 'VRow',
                'content': [
                    {
                        'component': 'VCol',
                        'props': {'cols': 12, 'md': 6},
                        'content': [
                            {
                                'component': 'VSwitch',
                                'props': {'model': 'enabled', 'label': '启用插件'}
                            }
                        ]
                    },
                    {
                        'component': 'VCol',
                        'props': {'cols': 12, 'md': 6},
                        'content': [
                            {
                                'component': 'VSwitch',
                                'props': {'model': 'notify', 'label': '开启通知'}
                            }
                        ]
                    }
                ]
            }
        ]
        # 5 组站点凭据槽位
        for i in range(1, 13):
            rows = [
                {
                    'component': 'VCol',
                    'props': {'cols': 12, 'md': 3},
                    'content': [
                        {
                            'component': 'VSelect',
                            'props': {
                                'model': f'domain_{i}',
                                'label': f'站点 {i}',
                                'items': site_options,
                                'clearable': True
                            }
                        }
                    ]
                },
                {
                    'component': 'VCol',
                    'props': {'cols': 12, 'md': 3},
                    'content': [
                        {
                            'component': 'VTextField',
                            'props': {
                                'model': f'username_{i}',
                                'label': f'用户名 {i}',
                                'placeholder': '登录账号'
                            }
                        }
                    ]
                },
                {
                    'component': 'VCol',
                    'props': {'cols': 12, 'md': 3},
                    'content': [
                        {
                            'component': 'VTextField',
                            'props': {
                                'model': f'password_{i}',
                                'label': f'密码 {i}',
                                'type': 'password',
                                'autocomplete': 'new-password',
                                'placeholder': '登录密码'
                            }
                        }
                    ]
                },
                {
                    'component': 'VCol',
                    'props': {'cols': 12, 'md': 3},
                    'content': [
                        {
                            'component': 'VTextField',
                            'props': {
                                'model': f'code_{i}',
                                'label': f'二步验证密钥 {i}',
                                'placeholder': 'TOTP密钥，选填'
                            }
                        }
                    ]
                }
            ]
            content.append({'component': 'VRow', 'content': rows})
        # 批量文本域（可选，支持任意数量站点）
        content.append(
            {
                'component': 'VRow',
                'content': [
                    {
                        'component': 'VCol',
                        'props': {'cols': 12},
                        'content': [
                            {
                                'component': 'VTextarea',
                                'props': {
                                    'model': 'siteconf',
                                    'label': '批量配置（可选，与上方槽位合并生效）',
                                    'rows': 4,
                                    'placeholder': '每行一个站点：域名|用户名|密码(|TOTP密钥)\n'
                                                   '例：piggo.me|asice999|密码|JBSWY3DPEHPK3PXP'
                                }
                            }
                        ]
                    }
                ]
            }
        )
        # 提示区
        content.append(
            {
                'component': 'VRow',
                'content': [
                    {
                        'component': 'VCol',
                        'props': {'cols': 12},
                        'content': [
                            {
                                'component': 'VAlert',
                                'props': {
                                    'type': 'info',
                                    'variant': 'tonal',
                                    'text': '站点签到提示Cookie过期时自动触发。'
                                            '支持二步验证站点（填TOTP密钥自动算动态码）。'
                                            '不是所有站点都支持，失败请手动更新。'
                                }
                            }
                        ]
                    }
                ]
            }
        )
        data = {"enabled": False, "notify": False, "siteconf": ""}
        for i in range(1, 13):
            data[f"domain_{i}"] = ""
            data[f"username_{i}"] = ""
            data[f"password_{i}"] = ""
            data[f"code_{i}"] = ""
        return [{
            'component': 'VForm',
            'content': content
        }], data

    def get_page(self) -> List[dict]:
        pass

    def stop_service(self):
        """
        退出插件
        """
        pass
