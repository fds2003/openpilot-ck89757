#!/usr/bin/env python3
"""
TDD Contract Test for P0-3: echo_cmd UI 开关 (CarrotEchoCmdEnable) 必须可被用户打开

问题：carrot_man.py:944 用 UnifiedParams.get_bool("CarrotEchoCmdEnable") 做开关，
但该 key 从未注册——params_keys.h 无此键、nav_params.html 无开关、config.py
无默认值 → UnifiedParams 恒返回 default=False，echo_cmd 网关是永久死路，
test_security_switches.py 用 MockParams 测不出这一断路。

契约（三源 + 清单一致）：
1. common/params_keys.h 注册 {"CarrotEchoCmdEnable", PERSISTENT}（strict Params 可写）
2. selfdrive/carrot/config.py 默认值 0（UnifiedParams 回退基线，安全默认关闭）
3. selfdrive/carrot/nav_params.html 提供 UI 开关（用户可打开）
4. carrot_settings.json / apilot.json 设置清单含该条目（车机设置页可见）
"""
import json
import re
from pathlib import Path

KEY = "CarrotEchoCmdEnable"


class TestEchoCmdSwitchRegistered:

  def test_params_keys_h_registers_key(self):
    h = Path("common/params_keys.h").read_text()
    assert re.search(rf'\{{"{KEY}",\s*PERSISTENT\}}', h)

  def test_config_py_default_is_zero(self):
    src = Path("selfdrive/carrot/config.py").read_text()
    m = re.search(rf'"{KEY}"\s*:\s*(\d+)', src)
    assert m is not None
    assert m.group(1) == "0", "安全开关默认必须为 0（关闭）"

  def test_nav_params_html_has_switch(self):
    html = Path("selfdrive/carrot/nav_params.html").read_text()
    assert f'"{KEY}"' in html, "P0-3: nav_params.html 缺少 UI 开关定义"

  def test_settings_manifests_contain_entry(self):
    for f in ("selfdrive/carrot_settings.json", "selfdrive/apilot.json"):
      d = json.load(open(f))
      entry = next((x for x in d["params"] if x["name"] == KEY), None)
      assert entry is not None
      assert entry.get("default") == 0, "设置清单默认必须为 0（关闭）"


if __name__ == "__main__":
  unittest.main()
