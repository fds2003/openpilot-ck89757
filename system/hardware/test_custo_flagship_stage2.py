import sys
import types
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

for mod in ["capnp", "cereal", "cereal.log", "zmq"]:
  if mod not in sys.modules:
    sys.modules[mod] = MagicMock()

try:
  import openpilot
  import common
  import system
  import selfdrive
  sys.modules["openpilot.common"] = common
  sys.modules["openpilot.system"] = system
  sys.modules["openpilot.selfdrive"] = selfdrive

  hw_mock = types.ModuleType("openpilot.system.hardware")
  hw_mock.__path__ = []
  hw_mock.PC = False
  hw_mock.TICI = True
  sys.modules["openpilot.system.hardware"] = hw_mock

  hw_sub = types.ModuleType("openpilot.system.hardware.hw")
  hw_sub.Paths = MagicMock()
  sys.modules["openpilot.system.hardware.hw"] = hw_sub
  hw_mock.hw = hw_sub
except Exception:
  pass

# 加载目标模块
fan_spec = importlib.util.spec_from_file_location("fan_controller", ROOT / "system" / "hardware" / "fan_controller.py")
fan_mod = importlib.util.module_from_spec(fan_spec)
sys.modules["system.hardware.fan_controller"] = fan_mod
fan_spec.loader.exec_module(fan_mod)
TiciFanController = fan_mod.TiciFanController


class TestCustoFlagshipStage2(unittest.TestCase):
  def setUp(self):
    self.fan = TiciFanController()

  def test_fan_quiet_zone(self):
    # 常温舒适段 (< 72℃) 点火输出在 15~30 之间
    pwr_on = self.fan.update(cur_temp=68.0, ignition=True)
    self.assertGreaterEqual(pwr_on, 15)
    self.assertLessEqual(pwr_on, 30)

    # 熄火驻车限速 <= 15
    pwr_off = self.fan.update(cur_temp=68.0, ignition=False)
    self.assertLessEqual(pwr_off, 15)

  def test_fan_linear_balance_zone(self):
    # 温升过渡段 (72℃ ~ 82℃) 平稳爬升
    pwr_on = self.fan.update(cur_temp=77.0, ignition=True)
    self.assertGreaterEqual(pwr_on, 45)
    self.assertLessEqual(pwr_on, 65)

    # 熄火状态小电瓶保护 <= 20
    pwr_off = self.fan.update(cur_temp=77.0, ignition=False)
    self.assertLessEqual(pwr_off, 20)

  def test_fan_emergency_cooling(self):
    # 极端暴晒段 (>= 82℃) 点火必须全力拉满 100% 极温救险
    pwr_on = self.fan.update(cur_temp=85.0, ignition=True)
    self.assertEqual(pwr_on, 100, "Emergency cooling must provide 100% fan power on ignition")

    # 熄火状态极温限额 30%
    pwr_off = self.fan.update(cur_temp=85.0, ignition=False)
    self.assertEqual(pwr_off, 30, "Offroad fan power must cap at 30%")

  def test_source_cleanup(self):
    fan_path = ROOT / "system" / "hardware" / "fan_controller.py"
    with open(fan_path, "r", encoding="utf-8") as f:
      fan_content = f.read()
    self.assertNotIn("StockLongToyota", fan_content, "StockLongToyota hack must be removed from fan_controller.py")

    hw_path = ROOT / "system" / "hardware" / "hardwared.py"
    with open(hw_path, "r", encoding="utf-8") as f:
      hw_content = f.read()
    self.assertNotIn("if False: #TICI", hw_content, "if False: #TICI hack must be removed from hardwared.py")
    self.assertIn("if TICI:", hw_content, "if TICI: check must be restored in hardwared.py")
    self.assertIn("Offroad_StorageMissing", hw_content, "Offroad_StorageMissing check must be retained")
    self.assertNotIn("set_offroad_alert_if_changed(\"Offroad_BadNvme\", True)", hw_content,
                     "Offroad_BadNvme alert popup must be disabled for non-Samsung SSD")


if __name__ == "__main__":
  unittest.main()
