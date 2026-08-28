"""NodeSeek签到自用版（合并测试）
版本: 1.0.0
作者: asice999
说明:
- 以 CloudSubscribe 合并架构为蓝本：业务逻辑全部在 core/signer.py，
  壳只负责 配置表单/定时服务/数据展示/通知回调
- 验证通过后，把 core/signer.py 拷入 CloudSubscribe/core/ 即完成合并
"""
from typing import Any, List, Dict, Tuple
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.plugins import _PluginBase
from app.log import logger
from app.schemas import NotificationType

from core.signer import NodeSeekSigner, HAS_CURL_CFFI, HAS_CLOUDSCRAPER


class nodeseekcheckin(_PluginBase):

    # 插件名称
    plugin_name = "NodeSeek签到自用版"
    # 插件描述
    plugin_desc = "自用：NodeSeek每日签到（合并架构测试版，业务在 core/signer.py）"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/asice999/MoviePilot-Plugins/main/icons/nodeseeksign.png"
    # 插件版本
    plugin_version = "1.0.0"
    # 插件作者
    plugin_author = "asice999"
    # 作者主页
    author_url = "https://github.com/asice999"
    # 插件配置项ID前缀
    plugin_config_prefix = "nodeseekcheckin_"
    # 加载顺序
    plugin_order = 1
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _enabled = False
    _cookie = None
    _notify = False
    _onlyonce = False
    _clear_history = False  # 新增：是否清除历史记录
    _cron = None
    _random_choice = True  # 是否选择随机奖励，否则选择固定奖励
    _history_days = 30  # 历史保留天数
    _use_proxy = True     # 是否使用代理，默认启用
    _max_retries = 3      # 最大重试次数
    _retry_count = 0      # 当天重试计数
    _scheduled_retry = None  # 计划的重试任务
    _verify_ssl = False    # 是否验证SSL证书，默认禁用
    _min_delay = 5         # 请求前最小随机等待（秒）
    _max_delay = 12        # 请求前最大随机等待（秒）
    _member_id = ""       # NodeSeek 成员ID（可选，用于获取用户信息）
    _stats_days = 30

    _scraper = None        # cloudscraper 实例

    # 定时器
    _scheduler: Optional[BackgroundScheduler] = None
    _manual_trigger = False

    def init_plugin(self, config: dict = None):
        try:
            if config:
                self._enabled = config.get("enabled")
                self._notify = config.get("notify")
                self._cron = config.get("cron")
                self._onlyonce = config.get("onlyonce")
                self._stats_days = int(config.get("stats_days", 30) or 30)

            # 构建/刷新签名器（业务逻辑全在 core/signer.py）
            if not getattr(self, '_signer', None):
                self._signer = NodeSeekSigner(
                    config=config,
                    save_data=lambda k, v: self.save_data(k, v),
                    get_data=lambda k: self.get_data(k),
                    notify=lambda **kw: self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title=kw.get('title', ''),
                        text=kw.get('text', '')),
                    update_config=lambda c: self.update_config(c),
                )
            else:
                self._signer.update_config(config)

            # 立即运行一次
            if self._onlyonce:
                self._onlyonce = False
                self.update_config({"onlyonce": False})
                try:
                    if not self._scheduler:
                        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
                    self._scheduler.add_job(
                        func=self.sign, trigger='date',
                        run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                        name="NodeSeek签到-立即运行")
                    if not self._scheduler.running:
                        self._scheduler.start()
                    logger.info("已安排 3 秒后执行一次性签到")
                except Exception as e:
                    logger.error(f"一次性签到调度失败: {str(e)}")
            else:
                self.stop_service()
        except Exception as e:
            logger.error(f"nodeseekcheckin 初始化错误: {str(e)}", exc_info=True)

    def sign(self):
        """委托给 signer 业务类"""
        if not getattr(self, '_signer', None):
            logger.error("signer 未初始化")
            return None
        return self._signer.sign()

    def get_state(self) -> bool:
        return self._enabled

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enabled and self._cron:
            logger.info(f"注册定时服务: {self._cron}")
            return [{
                "id": "nodeseeksign",
                "name": "NodeSeek论坛签到",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.sign,
                "kwargs": {}
            }]
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        # 状态提示移除CloudFlare相关文案
        curl_cffi_status = "✅ 已安装" if HAS_CURL_CFFI else "❌ 未安装"
        cloudscraper_status = "✅ 已启用" if HAS_CLOUDSCRAPER else "❌ 未启用"
        
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify',
                                            'label': '开启通知',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'random_choice',
                                            'label': '随机奖励',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'use_proxy',
                                            'label': '使用代理',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'verify_ssl',
                                            'label': '验证SSL证书',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'clear_history',
                                            'label': '清除历史记录',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'member_id',
                                            'label': '成员ID（可选）',
                                            'placeholder': '用于获取用户信息'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'min_delay',
                                            'label': '最小随机延迟(秒)',
                                            'type': 'number',
                                            'placeholder': '5'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'max_delay',
                                            'label': '最大随机延迟(秒)',
                                            'type': 'number',
                                            'placeholder': '12'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cookie',
                                            'label': '站点Cookie',
                                            'placeholder': '请输入站点Cookie值'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VCronField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '签到周期'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'history_days',
                                            'label': '历史保留天数',
                                            'type': 'number',
                                            'placeholder': '30'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'max_retries',
                                            'label': '失败重试次数',
                                            'type': 'number',
                                            'placeholder': '3'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'stats_days',
                                            'label': '收益统计天数',
                                            'type': 'number',
                                            'placeholder': '30'
                                        }
                                    }
                                ]
                            },

                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': f'【使用教程】\n1. 登录NodeSeek论坛网站，按F12打开开发者工具\n2. 在"网络"或"应用"选项卡中复制Cookie\n3. 粘贴Cookie到上方输入框\n4. 设置签到时间，建议早上8点(0 8 * * *)\n5. 启用插件并保存\n\n【功能说明】\n• 随机奖励：开启则使用随机奖励，关闭则使用固定奖励\n• 使用代理：开启则使用系统配置的代理服务器访问NodeSeek\n• 验证SSL证书：关闭可能解决SSL连接问题，但会降低安全性\n• 失败重试：设置签到失败后的最大重试次数，将在5-15分钟后随机重试\n• 随机延迟：请求前随机等待，降低被风控概率\n• 用户信息：配置成员ID后，通知中展示用户名/等级/鸡腿\n• 立即运行一次：手动触发一次签到\n• 清除历史记录：勾选后保存配置，插件将清空所有签到历史、用户信息等数据，使用后会自动关闭\n\n【环境状态】\n• curl_cffi: {curl_cffi_status}；cloudscraper: {cloudscraper_status}'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "notify": True,
            "onlyonce": False,
            "cookie": "",
            "cron": "0 8 * * *",
            "random_choice": True,
            "history_days": 30,
            "use_proxy": True,
            "max_retries": 3,
            "verify_ssl": False,
            "min_delay": 5,
            "max_delay": 12,
            "member_id": "",
            "clear_history": False,
            "stats_days": 30
        }

    def get_page(self) -> List[dict]:
        """
        构建插件详情页面，展示签到历史
        """
        # 读取缓存的用户信息
        user_info = self.get_data('last_user_info') or {}
        # 获取签到历史
        historys = self.get_data('sign_history') or []
        
        # 如果没有历史记录
        if not historys:
            return [
                {
                    'component': 'VAlert',
                    'props': {
                        'type': 'info',
                        'variant': 'tonal',
                        'text': '暂无签到记录，请先配置Cookie并启用插件',
                        'class': 'mb-2'
                    }
                }
            ]
        
        # 按时间倒序排列历史
        historys = sorted(historys, key=lambda x: x.get("date", ""), reverse=True)
        
        # 构建历史记录表格行
        history_rows = []
        for history in historys:
            status_text = history.get("status", "未知")
            
            # 判断状态颜色：所有成功状态都是绿色，失败状态是红色
            success_statuses = ["签到成功", "已签到", "签到成功（时间验证）", "已签到（从记录确认）"]
            status_color = "success" if status_text in success_statuses else "error"
            
            # 获取奖励信息
            reward_info = "-"
            try:
                # 检查是否为成功状态（包括新增的时间验证状态）
                if any(success_status in status_text for success_status in success_statuses):
                    # 尝试从历史记录中获取奖励信息
                    if "gain" in history:
                        reward_info = f"{history.get('gain', 0)}个鸡腿"
                        # 如果有排名信息，也显示
                        if "rank" in history and "total_signers" in history:
                            reward_info += f" (第{history.get('rank')}名，共{history.get('total_signers')}人)"
                    else:
                        # 如果没有直接的奖励信息，尝试从签到记录中获取
                        attendance_record = self.get_data('last_attendance_record') or {}
                        if attendance_record and attendance_record.get('gain'):
                            reward_info = f"{attendance_record.get('gain')}个鸡腿"
                            # 如果有排名信息，也显示
                            if attendance_record.get('rank') and attendance_record.get('total_signers'):
                                reward_info += f" (第{attendance_record.get('rank')}名，共{attendance_record.get('total_signers')}人)"
            except Exception as e:
                logger.warning(f"获取奖励信息失败: {str(e)}")
                reward_info = "-"
            
            history_rows.append({
                'component': 'tr',
                'content': [
                    # 日期列
                    {
                        'component': 'td',
                        'props': {
                            'class': 'text-caption'
                        },
                        'text': history.get("date", "")
                    },
                    # 状态列
                    {
                        'component': 'td',
                        'content': [
                            {
                                'component': 'VChip',
                                'props': {
                                    'color': status_color,
                                    'size': 'small',
                                    'variant': 'outlined'
                                },
                                'text': status_text
                            }
                        ]
                    },
                    # 奖励列
                    {
                        'component': 'td',
                        'content': [
                            {
                                'component': 'VChip',
                                'props': {
                                    'color': 'amber-darken-2' if reward_info != "-" else 'grey',
                                    'size': 'small',
                                    'variant': 'outlined'
                                },
                                'text': reward_info
                            }
                        ]
                    },
                    # 消息列
                    {
                        'component': 'td',
                        'text': history.get('message', '-')
                    }
                ]
            })
        
        # 用户信息卡片（可选）
        user_info_card = []
        
        # 初始化用户信息相关变量，避免未定义错误
        member_id = ""
        avatar_url = None
        user_name = "-"
        rank = "-"
        coin = "-"
        npost = "-"
        ncomment = "-"
        sign_rank = None
        total_signers = None
        
        if user_info:
            member_id = str(user_info.get('member_id') or getattr(self, '_member_id', '') or '').strip()
            avatar_url = f"https://www.nodeseek.com/avatar/{member_id}.png" if member_id else None
            user_name = user_info.get('member_name', '-')
            rank = str(user_info.get('rank', '-'))
            coin = str(user_info.get('coin', '-'))
            npost = str(user_info.get('nPost', '-'))
            ncomment = str(user_info.get('nComment', '-'))
            
            # 获取签到排名信息
            attendance_record = self.get_data('last_attendance_record') or {}
            sign_rank = attendance_record.get('rank')
            total_signers = attendance_record.get('total_signers')
            
            user_info_card = [
                {
                    'component': 'VCard',
                    'props': {'variant': 'outlined', 'class': 'mb-4'},
                    'content': [
                        {'component': 'VCardTitle', 'props': {'class': 'text-h6'}, 'text': '👤 NodeSeek 用户信息'},
                        {
                            'component': 'VCardText',
                            'content': [
                                {
                                    'component': 'VRow',
                                    'props': {'align': 'center'},
                                    'content': [
                                        {
                                            'component': 'VCol',
                                            'props': {'cols': 12, 'md': 2},
                                            'content': [
                                                (
                                                    {
                                                        'component': 'VAvatar',
                                                        'props': {'size': 72, 'class': 'mx-auto'},
                                                        'content': [
                                                            {
                                                                'component': 'VImg',
                                                                'props': {'src': avatar_url} if avatar_url else {}
                                                            }
                                                        ]
                                                    } if avatar_url else {
                                                        'component': 'VAvatar',
                                                        'props': {'size': 72, 'color': 'grey-lighten-2', 'class': 'mx-auto'},
                                                        'text': user_name[:1]
                                                    }
                                                )
                                            ]
                                        },
                                        {
                                            'component': 'VCol',
                                            'props': {'cols': 12, 'md': 10},
                                            'content': [
                                                {
                                                    'component': 'VRow',
                                                    'props': {'class': 'mb-2'},
                                                    'content': [
                                                        {'component': 'span', 'props': {'class': 'text-subtitle-1 mr-4'}, 'text': user_name},
                                                        {'component': 'VChip', 'props': {'size': 'small', 'variant': 'outlined', 'color': 'primary', 'class': 'mr-2'}, 'text': f'等级 {rank}'},
                                                        {'component': 'VChip', 'props': {'size': 'small', 'variant': 'outlined', 'color': 'amber-darken-2', 'class': 'mr-2'}, 'text': f'鸡腿 {coin}'},
                                                        {'component': 'VChip', 'props': {'size': 'small', 'variant': 'outlined', 'class': 'mr-2'}, 'text': f'主题 {npost}'},
                                                        {'component': 'VChip', 'props': {'size': 'small', 'variant': 'outlined'}, 'text': f'评论 {ncomment}'}
                                                    ] + ([
                                                        # 添加签到排名信息
                                                        {'component': 'VChip', 'props': {'size': 'small', 'variant': 'outlined', 'color': 'success', 'class': 'mr-2'}, 'text': f'签到排名 {sign_rank}'},
                                                        {'component': 'VChip', 'props': {'size': 'small', 'variant': 'outlined', 'color': 'info', 'class': 'mr-2'}, 'text': f'总人数 {total_signers}'}
                                                    ] if sign_rank and total_signers else [])
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]

        stats = self.get_data('last_signin_stats') or {}

        stats_card = []
        if stats:
            period = stats.get('period') or f"近{self._stats_days}天"
            days_count = stats.get('days_count', 0)
            total_amount = stats.get('total_amount', 0)
            average = stats.get('average', 0)
            stats_card = [
                {
                    'component': 'VCard',
                    'props': {'variant': 'outlined', 'class': 'mb-4'},
                    'content': [
                        {'component': 'VCardTitle', 'props': {'class': 'text-h6'}, 'text': '📈 NodeSeek收益统计'},
                        {
                            'component': 'VCardText',
                            'content': [
                                {'component': 'div', 'props': {'class': 'mb-2'}, 'text': f'{period} 已签到 {days_count} 天'},
                                {
                                    'component': 'VRow',
                                    'content': [
                                        {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [{'component': 'VChip', 'props': {'variant': 'outlined', 'color': 'amber-darken-2'}, 'text': f'总鸡腿 {total_amount}'}]},
                                        {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [{'component': 'VChip', 'props': {'variant': 'outlined', 'color': 'primary'}, 'text': f'平均/日 {average}'}]},
                                        {'component': 'VCol', 'props': {'cols': 12, 'md': 4}, 'content': [{'component': 'VChip', 'props': {'variant': 'outlined'}, 'text': f'统计天数 {days_count}'}]},
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]

        return user_info_card + stats_card + [
            # 标题
            {
                'component': 'VCard',
                'props': {'variant': 'outlined', 'class': 'mb-4'},
                'content': [
                    {
                        'component': 'VCardTitle',
                        'props': {'class': 'text-h6'},
                        'text': '📊 NodeSeek论坛签到历史'
                    },
                    {
                        'component': 'VCardText',
                        'content': [
                            {
                                'component': 'VTable',
                                'props': {
                                    'hover': True,
                                    'density': 'compact'
                                },
                                'content': [
                                    # 表头
                                    {
                                        'component': 'thead',
                                        'content': [
                                            {
                                                'component': 'tr',
                                                'content': [
                                                    {'component': 'th', 'text': '时间'},
                                                    {'component': 'th', 'text': '状态'},
                                                    {'component': 'th', 'text': '奖励'},
                                                    {'component': 'th', 'text': '消息'}
                                                ]
                                            }
                                        ]
                                    },
                                    # 表内容
                                    {
                                        'component': 'tbody',
                                        'content': history_rows
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

    def get_command(self) -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [] 

    def stop_service(self):
        """
        退出插件，停止定时任务
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error(f"退出插件失败: {str(e)}")

    def stop_service(self):
        """退出插件，停止定时任务"""
        try:
            if getattr(self, '_scheduler', None):
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error(f"退出插件失败: {str(e)}")
