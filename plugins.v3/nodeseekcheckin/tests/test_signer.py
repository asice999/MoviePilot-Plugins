"""NodeSeekSigner 独立冒烟测试（离线，不联网）
运行: python3 plugins.v3/nodeseekcheckin/tests/test_signer.py
"""
import sys, types, os

# 桩掉 app 模块，验证 signer 脱离插件框架可独立运行
app = types.ModuleType('app'); app.core = types.ModuleType('app.core')
app.core.config = types.ModuleType('app.core.config')
app.core.config.settings = types.SimpleNamespace(TZ='Asia/Shanghai', PROXY=None)
app.log = types.ModuleType('app.log')
class _L:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def debug(self, *a, **k): pass
app.log.logger = _L()
sys.modules['app'] = app
sys.modules['app.core'] = app.core
sys.modules['app.core.config'] = app.core.config
sys.modules['app.log'] = app.log

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.signer import NodeSeekSigner

saved = {}
notes = []

def save(k, v): saved[k] = v
def get(k): return saved.get(k)
def notify(**kw): notes.append(kw)

# 1) 无 cookie → 返回"未配置Cookie"，不联网
s = NodeSeekSigner(config={'cookie': ''}, save_data=save, get_data=get, notify=notify)
r = s.sign()
assert r and '未配置Cookie' in r['status'], r
print('PASS no-cookie:', r['status'])

# 2) 代理归一化
assert NodeSeekSigner(config={})._normalize_proxies('http://x:1') == {'http': 'http://x:1', 'https': 'http://x:1'}
assert NodeSeekSigner(config={})._normalize_proxies({'https': 'http://x:1'}) == {'http': 'http://x:1', 'https': 'http://x:1'}
print('PASS normalize_proxies')

# 3) 配置数值兜底
s2 = NodeSeekSigner(config={'history_days': 'abc', 'max_delay': 5, 'min_delay': 9, 'notify': False})
assert s2._history_days == 30 and s2._max_delay == 5 and s2._min_delay == 9 and s2._notify is False
print('PASS config defaults')

# 4) 已签到检测（空历史）
assert s2._is_already_signed_today() is False
print('PASS already-signed check')

# 5) 统计空数据
assert s2._get_signin_stats(days=30) == {}
print('PASS stats empty')

print('ALL PASS')
