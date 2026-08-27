"""
版本一致性测试：插件主类 plugin_version 与 package.v3.json 索引版本一致。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_version_consistency():
    pkg = json.loads((ROOT / "package.v3.json").read_text(encoding="utf-8"))
    entry = pkg["MpMissingEpisodes"]
    init_py = ROOT / "plugins.v3" / "mpmissingepisodes" / "__init__.py"
    assert init_py.exists(), "插件 __init__.py 不存在"
    src = init_py.read_text(encoding="utf-8")
    lines = {l.strip() for l in src.splitlines()}
    v = None
    for l in lines:
        if l.startswith("plugin_version"):
            v = l.split("=", 1)[1].strip().strip('"').strip("'")
            break
    assert v == entry["version"], f"版本不一致: 代码={v} 索引={entry['version']}"
    assert f"v{v}" in entry.get("history", {}), "history 缺少当前版本"


if __name__ == "__main__":
    test_version_consistency()
    print("OK")
