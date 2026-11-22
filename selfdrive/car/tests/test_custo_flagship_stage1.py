import sys
import types
import unittest
import tomllib
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

# 构建 cereal / panda 基础桩对象
car_mock = MagicMock()
cereal_mod = types.ModuleType("cereal")
cereal_mod.car = car_mock
sys.modules["cereal"] = cereal_mod
sys.modules["cereal.car"] = car_mock

for mod in ["capnp", "panda", "panda.python", "panda.python.uds"]:
  if mod not in sys.modules:
    sys.modules[mod] = MagicMock()

try:
  import openpilot
  import common
  import selfdrive
  import system
  sys.modules["openpilot.common"] = common
  sys.modules["openpilot.selfdrive"] = selfdrive
  sys.modules["openpilot.system"] = system
except Exception:
  pass

from selfdrive.car.hyundai.values import CAR, HyundaiFlags


class TestCustoFlagshipStage1(unittest.TestCase):
  def test_custin_specs(self):
    cfg = CAR.HYUNDAI_CUSTIN_1ST_GEN.config
    self.assertIsNotNone(cfg, "HYUNDAI_CUSTIN_1ST_GEN must have a valid PlatformConfig")
    self.assertEqual(cfg.specs.mass, 1754, "2.0T Flagship mass must be exactly 1754 kg")
    self.assertEqual(cfg.specs.wheelbase, 3.055, "Wheelbase must be exactly 3.055 m")
    self.assertEqual(cfg.specs.steerRatio, 17.0, "Steer ratio must be 17.0")
    self.assertTrue(bool(cfg.flags & HyundaiFlags.SEND_LFA), "SEND_LFA flag must be enabled for cluster 0x485")
    self.assertTrue(bool(cfg.flags & HyundaiFlags.CHECKSUM_CRC8), "CHECKSUM_CRC8 flag must be enabled")

  def test_torque_substitute_palisade_mapping(self):
    sub_path = ROOT / "selfdrive" / "car" / "torque_data" / "substitute.toml"
    self.assertTrue(sub_path.is_file(), f"substitute.toml not found at {sub_path}")
    with open(sub_path, "rb") as f:
      mapping = tomllib.load(f)
    self.assertEqual(mapping.get("HYUNDAI_CUSTIN_1ST_GEN"), "HYUNDAI_PALISADE",
                     "HYUNDAI_CUSTIN_1ST_GEN must map to HYUNDAI_PALISADE in substitute.toml")

  def test_interface_source_no_lkas_toggle_hack(self):
    interface_path = ROOT / "selfdrive" / "car" / "hyundai" / "interface.py"
    with open(interface_path, "r", encoding="utf-8") as f:
      content = f.read()
    self.assertNotIn("Params().get_bool(\"LkasToggle\")", content,
                     "LkasToggle borrowing hack must be completely removed from hyundai/interface.py")
    self.assertIn("candidate == CAR.HYUNDAI_CUSTIN_1ST_GEN", content,
                  "Dedicated CUSTIN candidate branch must exist in hyundai/interface.py")
    self.assertIn("ret.steerActuatorDelay = 0.15", content,
                  "Custo must set steerActuatorDelay to 0.15s in interface.py")
    self.assertIn("ret.startAccel = 1.0", content,
                  "Custo must set startAccel to 1.0 in interface.py")


if __name__ == "__main__":
  unittest.main()
