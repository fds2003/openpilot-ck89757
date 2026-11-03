#!/usr/bin/env python3
"""A1 契约测试：车机 blinker 整数码 -> C3 内部转向灯状态。

车机 LaneAction.kt 发送 1=左 / 2=右 / 0=关（Int），
旧客户端仍可能发送 left/stockleft/right/stockright（String）。
C3 必须两种都接受，且未知值 fail-closed 归零。

注意：本仓库依赖 capnp，CI/本地裸机无法导入 cereal.messaging，
因此按接口给 openpilot/cereal 打桩，再直接加载被测文件，测试真实实现而非复制逻辑。
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AMAP_NAVI_PATH = REPO_ROOT / "selfdrive" / "carrot" / "amap_navi.py"


def _install_stub(name, **attrs):
  if name in sys.modules:
    return sys.modules[name]
  mod = types.ModuleType(name)
  mod.__dict__.update(attrs)
  sys.modules[name] = mod
  return mod


def _load_amap_navi():
  # fcntl 是 Linux 专有模块，Windows 上无法导入，但被测方法不触达文件锁
  _install_stub("fcntl", flock=lambda *a, **k: None, LOCK_EX=2, LOCK_NB=4, LOCK_UN=8)

  class _SubMaster:
    def __init__(self, *args, **kwargs):
      pass

  class _PubMaster:
    def __init__(self, *args, **kwargs):
      pass

  class _UnifiedParams:
    def __init__(self, *args, **kwargs):
      pass

  _install_stub("cereal")
  _install_stub("cereal.messaging", SubMaster=_SubMaster, PubMaster=_PubMaster,
                new_message=lambda *a, **k: None)
  _install_stub("openpilot")
  _install_stub("openpilot.common")
  _install_stub("openpilot.common.realtime", Ratekeeper=lambda *a, **k: None)
  _install_stub("openpilot.system")
  _install_stub("openpilot.system.hardware", PC=None)
  _install_stub("openpilot.selfdrive")
  _install_stub("openpilot.selfdrive.carrot")
  _install_stub("openpilot.selfdrive.carrot.config", UnifiedParams=_UnifiedParams)

  spec = importlib.util.spec_from_file_location("amap_navi_under_test", AMAP_NAVI_PATH)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


amap_navi = _load_amap_navi()


def _make_serv():
  # 只测纯方法，跳过会起线程/建 socket 的 __init__
  serv = amap_navi.AmapNaviServ.__new__(amap_navi.AmapNaviServ)
  serv.shared_data = amap_navi.SharedData()
  serv.blinker_alive = False
  serv.blinker_time = 0.0
  return serv


class TestBlinkerContract(unittest.TestCase):

  def _update(self, serv, payload, now=100.0):
    serv._update_blinker(payload, "192.168.3.165", {}, now)

  def test_int_codes_map_to_blinker_state(self):
    """车机整数码必须生效，不能被当成未知值清零"""
    cases = ((1, amap_navi.BLINKER_LEFT), (2, amap_navi.BLINKER_RIGHT), (0, amap_navi.BLINKER_NONE))
    for code, expected in cases:
      serv = _make_serv()
      self._update(serv, {"blinker": code})
      self.assertEqual(expected, serv.shared_data.ext_blinker, f"blinker={code}")
      self.assertTrue(serv.blinker_alive)
      self.assertEqual(100.0, serv.blinker_time)

  def test_numeric_string_codes_supported(self):
    for raw, expected in (("1", amap_navi.BLINKER_LEFT), ("2", amap_navi.BLINKER_RIGHT)):
      serv = _make_serv()
      self._update(serv, {"blinker": raw})
      self.assertEqual(expected, serv.shared_data.ext_blinker, f"blinker={raw!r}")

  def test_legacy_string_protocol_supported(self):
    cases = (
      ("left", amap_navi.BLINKER_LEFT),
      ("stockleft", amap_navi.BLINKER_LEFT),
      ("right", amap_navi.BLINKER_RIGHT),
      ("stockright", amap_navi.BLINKER_RIGHT),
    )
    for raw, expected in cases:
      serv = _make_serv()
      self._update(serv, {"blinker": raw})
      self.assertEqual(expected, serv.shared_data.ext_blinker, f"blinker={raw!r}")

  def test_unknown_value_fails_closed(self):
    """未知值必须归零，避免误以为打了转向灯"""
    for raw in (3, "both", "bogus", None, ""):
      serv = _make_serv()
      serv.shared_data.ext_blinker = amap_navi.BLINKER_LEFT
      self._update(serv, {"blinker": raw})
      self.assertEqual(amap_navi.BLINKER_NONE, serv.shared_data.ext_blinker, f"blinker={raw!r}")

  def test_missing_key_keeps_previous_state(self):
    """未携带 blinker 的包不得改动转向灯，也不得刷新存活时间"""
    serv = _make_serv()
    serv.shared_data.ext_blinker = amap_navi.BLINKER_RIGHT
    serv.blinker_alive = True
    serv.blinker_time = 50.0
    self._update(serv, {"cmd": "LANE_CHANGE"}, now=100.0)
    self.assertEqual(amap_navi.BLINKER_RIGHT, serv.shared_data.ext_blinker)
    self.assertTrue(serv.blinker_alive)
    self.assertEqual(50.0, serv.blinker_time)


if __name__ == "__main__":
  unittest.main()
