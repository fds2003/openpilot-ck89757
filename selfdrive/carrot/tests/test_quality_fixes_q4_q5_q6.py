#!/usr/bin/env python3
"""
TDD tests for 19号文档 C3 端「立即」档质量修复（Q-4 / Q-5 / Q-6）。

RED 阶段语义：对未修复代码，下列测试各自因对应缺陷而失败；
GREEN 阶段：Q-5（deque 化）、Q-6（fields 裁剪）、Q-4（TURN_TYPE_MAP 单一字典）
实施后全部通过。

仅依赖标准库 + cereal/opencv stub（carrot_serv 离线导入需要），
不启动服务、不联网、不读 Params。
"""
import collections
import importlib.util
import os
import socket
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
AMAP_NAVI = os.path.join(ROOT, "selfdrive", "carrot", "amap_navi.py")
CARROT_SERV = os.path.join(ROOT, "selfdrive", "carrot", "carrot_serv.py")

# ---- 离线导入 amap_navi / carrot_serv 所需的 stub（Windows 无 fcntl，cereal 无 capnp）----

class _LC:
  raw = 0


class _Meta:
  """modelV2.meta 替身：带 make_navi_message 读取的固定属性。"""
  laneWidthLeft = 3.5
  laneWidthRight = 3.5
  distanceToRoadEdgeLeft = 1.0
  distanceToRoadEdgeRight = 1.0
  laneChangeState = _LC()


class _SDS:
  """selfdriveState 最小替身。"""
  active = False


class _CarrotMan:
  """carrotMan 最小替身。"""
  desiredSpeed = 30
  atcType = "none"
  szPosRoadName = ""
  xSpdType = -1
  xSpdDist = 0


class _ModelV2:
  """modelV2 最小替身：meta 无属性（hasattr 检查全部 False），lane 概率数组齐全。"""
  def __init__(self):
    self.meta = _Meta()
    self.roadEdgeStds = [0.5, 0.5]
    self.laneLineProbs = [0.9, 0.1, 0.8, 0.2]


class _SM:
  """SubMaster 最小替身：alive/valid 全 True；modelV2/selfdriveState 返回替身，其余返回 None。"""
  def __init__(self, topics):
    self.alive = {t: True for t in topics}
    self.valid = {t: True for t in topics}
    self.updated = {t: True for t in topics}
    self._data = {"modelV2": _ModelV2(), "selfdriveState": _SDS(), "carrotMan": _CarrotMan()}
  def __getitem__(self, t):
    return self._data.get(t)
  def update(self, *a, **k):
    pass
  def __getattr__(self, name):
    return None


def _install_stubs():
  # fcntl（Windows 无）
  fcntl_stub = types.ModuleType("fcntl")
  fcntl_stub.flock = lambda *a, **k: None
  fcntl_stub.LOCK_EX = 2
  fcntl_stub.LOCK_NB = 4
  fcntl_stub.flock_unlock = lambda *a, **k: None
  sys.modules.setdefault("fcntl", fcntl_stub)

  # openpilot.common.params
  params_mod = types.ModuleType("openpilot.common.params")
  class Params:
    def __init__(self, *a, **k):
      pass
    def get_bool(self, key, default=False):
      if key == "IsOnroad":
        return True   # 让 make_navi_message 进入雷达数据段（与车机实际运行态一致）
      return default
    def get_int(self, k, default=0):
      return default
    def get_param(self, *a, **k):
      return None
    def put(self, *a, **k):
      pass
  params_mod.Params = Params
  sys.modules.setdefault("openpilot.common.params", params_mod)

  # openpilot.common.realtime（Ratekeeper 最小替身）
  rt_mod = types.ModuleType("openpilot.common.realtime")
  class Ratekeeper:
    def __init__(self, dt, clip: bool = True):
      self.dt = dt
    def keep_time(self):
      pass
  rt_mod.Ratekeeper = Ratekeeper
  rt_mod.DT_MDL = 0.02
  sys.modules.setdefault("openpilot.common.realtime", rt_mod)

  # openpilot.system.hardware
  hw_mod = types.ModuleType("openpilot.system.hardware")
  hw_mod.PC = True
  hw_mod.TICI = False
  hw_mod.get_thermal_state = lambda: None
  sys.modules.setdefault("openpilot.system.hardware", hw_mod)

  # cereal 包命名空间（阻止导入真实 cereal -> capnp 缺失）
  cereal_pkg = types.ModuleType("cereal")
  cereal_pkg.__path__ = []
  log_mod = types.ModuleType("cereal.log")
  messaging_mod = types.ModuleType("cereal.messaging")
  messaging_mod.SubMaster = _SM
  messaging_mod.pub_sock = lambda *a, **k: None
  sys.modules.setdefault("cereal", cereal_pkg)
  sys.modules.setdefault("cereal.log", log_mod)
  sys.modules.setdefault("cereal.messaging", messaging_mod)

  # openpilot.selfdrive.carrot.config / udp_trust / traffic_light（真实模块依赖 fcntl/capnp）
  config_mod = types.ModuleType("openpilot.selfdrive.carrot.config")
  class UnifiedParams:
    def __init__(self):
      pass
    def get_bool(self, key, default=False):
      if key == "IsOnroad":
        return True   # 让 make_navi_message 进入雷达数据段（与车机实际运行态一致）
      return default
    def get_int(self, k, default=0):
      return default
  config_mod.UnifiedParams = UnifiedParams
  sys.modules.setdefault("openpilot.selfdrive.carrot.config", config_mod)

  udp_mod = types.ModuleType("openpilot.selfdrive.carrot.udp_trust")
  udp_mod.evaluate = lambda *a, **k: None
  udp_mod.parse_allowed = lambda *a, **k: set()
  sys.modules.setdefault("openpilot.selfdrive.carrot.udp_trust", udp_mod)

  tl_mod = types.ModuleType("openpilot.selfdrive.carrot.traffic_light")
  tl_mod.BRIDGE_TL_PORT = 4215
  tl_mod.state_from_wire = lambda *a, **k: 0
  tl_mod.bridge_state_allowed = lambda *a, **k: True
  tl_mod.is_fresh = lambda *a, **k: False
  sys.modules.setdefault("openpilot.selfdrive.carrot.traffic_light", tl_mod)

  # carrot_serv 依赖
  sys.modules.setdefault("numpy", types.ModuleType("numpy"))
  zmq_stub = types.ModuleType("zmq")
  zmq_stub.Context = lambda *a, **k: None
  sys.modules.setdefault("zmq", zmq_stub)

  coop_mod = types.ModuleType("openpilot.selfdrive.carrot.cooperative_mode")
  coop_mod.auto_turn_allowed = lambda *a, **k: True
  coop_mod.hu_alive = lambda *a, **k: True
  sys.modules.setdefault("openpilot.selfdrive.carrot.cooperative_mode", coop_mod)

  fs_mod = types.ModuleType("openpilot.common.filter_simple")
  class MyMovingAverage:
    def __init__(self, *a, **k):
      pass
  fs_mod.MyMovingAverage = MyMovingAverage
  sys.modules.setdefault("openpilot.common.filter_simple", fs_mod)

  helpers_mod = types.ModuleType("openpilot.selfdrive.navd.helpers")
  helpers_mod.Coordinate = type("Coordinate", (), {})
  sys.modules.setdefault("openpilot.selfdrive.navd.helpers", helpers_mod)

  conv_mod = types.ModuleType("opendbc.car.common.conversions")
  class Conversions:
    MS_TO_KPH = 3.6
    KPH_TO_MPH = 0.621371
  conv_mod.Conversions = Conversions
  sys.modules.setdefault("opendbc.car.common.conversions", conv_mod)

  sl_mod = types.ModuleType("openpilot.common.swaglog")
  class _CloudLog:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def exception(self, *a, **k): pass
  sl_mod.cloudlog = _CloudLog()
  sys.modules.setdefault("openpilot.common.swaglog", sl_mod)


def _load_module(name, path):
  spec = importlib.util.spec_from_file_location(name, path)
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  return mod


def _mk_serv(shared_data):
  """构造最小 AmapNaviServ 实例（不跑 __init__），只挂 make_navi_message 依赖属性。"""
  amap_navi = _load_module("amap_navi_q6", AMAP_NAVI)
  serv = amap_navi.AmapNaviServ.__new__(amap_navi.AmapNaviServ)
  serv.shared_data = shared_data
  serv.params = amap_navi.UnifiedParams()
  serv.sm = _SM(['modelV2', 'selfdriveState', 'radarState', 'carrotMan'])
  serv.local_ip_address = "127.0.0.1"
  serv.listen_port = 4211
  serv.disableBlindSpot = False
  serv.lead_left_right = False
  serv.model_event_type = 0
  serv.sec_count_down = -1
  serv.left_blindspot = lambda: False
  serv.right_blindspot = lambda: False
  return serv


class TestQ5SpeedHistDeque(unittest.TestCase):
  """Q-5: speed_hist 改 deque(maxlen)，消灭 20~50Hz 路径 O(n) pop(0)。"""

  @classmethod
  def setUpClass(cls):
    _install_stubs()
    cls.amap_navi = _load_module("amap_navi_q5", AMAP_NAVI)

  def test_speed_hist_is_bounded_deque(self):
    est = self.amap_navi.RadarSpeedEstimator(smooth_n=5)
    for i in range(100):
      est.update(1000.0 * (i + 1), i * 50)  # 匀速 10 m/s
    hist = est.speed_hist
    self.assertIsInstance(hist, collections.deque, msg="Q-5 RED: speed_hist 应为 collections.deque")
    self.assertEqual(len(hist), 5, msg="Q-5 RED: deque(maxlen=5) 应恒保持 5 元素")
    self.assertEqual(hist.maxlen, 5)

  def test_sliding_average_matches(self):
    est = self.amap_navi.RadarSpeedEstimator(smooth_n=5)
    for i in range(50):
      est.update(1000.0 * (i + 1), i * 50)
    avg = sum(est.speed_hist) / len(est.speed_hist)
    self.assertAlmostEqual(avg, 10.0, delta=1.0, msg="匀速 10 m/s 时滑动平均应趋近 10")

  def test_lost_timeout_reset_clears_history(self):
    est = self.amap_navi.RadarSpeedEstimator(smooth_n=3, lost_timeout_ms=500)
    est.update(1000.0, 0)
    est.update(2000.0, 100)
    self.assertIsNotNone(est.update(5000.0, 200))
    r = est.update(None, 20000)  # 超 500ms 丢帧
    self.assertIsNone(r, "丢帧超时后应返回 None")
    self.assertEqual(len(est.speed_hist), 0, "丢帧超时后 history 应被清空")


class TestQ6LbRbDrelOwnership(unittest.TestCase):
  """Q-6: lb_drel/rb_drel 广播 key 只由 main_*_drel 决定，fields 循环不再参与。"""

  @classmethod
  def setUpClass(cls):
    _install_stubs()
    cls.amap_navi = _load_module("amap_navi_q6", AMAP_NAVI)

  def _sd(self, main_lb=None, main_rb=None, lb0=None, rb0=None):
    sd = self.amap_navi.SharedData()
    sd.main_lb_drel = main_lb
    sd.main_rb_drel = main_rb
    sd.lf_drel = {}
    sd.lb_drel = {}
    sd.rf_drel = {}
    sd.rb_drel = {}
    sd.lf_xrel = {}
    sd.lb_xrel = {}
    sd.rf_xrel = {}
    sd.rb_xrel = {}
    sd.lf_drel[0] = 5000
    if lb0 is not None:
      sd.lb_drel[0] = lb0
    if rb0 is not None:
      sd.rb_drel[0] = rb0
    return sd

  def test_raw_per_lidar_value_not_broadcast(self):
    """原始多雷达值 idx==0 的 lb_drel/rb_drel 不得进入广播帧（Q-6 修复后）。"""
    import json
    serv = _mk_serv(self._sd(main_lb=None, main_rb=None, lb0=-1234, rb0=4321))
    msg = json.loads(serv.make_navi_message())
    self.assertNotIn("lb_drel", msg, "Q-6 RED: 无主雷达数据时 lb_drel 不应由 fields 循环写入")
    self.assertNotIn("rb_drel", msg, "Q-6 RED: 无主雷达数据时 rb_drel 不应由 fields 循环写入")

  def test_main_value_overrides_and_unit_is_meters(self):
    import json
    serv = _mk_serv(self._sd(main_lb=-5000, main_rb=5000, lb0=-1234, rb0=4321))
    msg = json.loads(serv.make_navi_message())
    self.assertEqual(msg.get("lb_drel"), 5.0, "main_lb_drel(mm) 应取绝对值转米")
    self.assertEqual(msg.get("rb_drel"), 5.0, "main_rb_drel(mm) 应取绝对值转米")

  def test_lf_rb_keys_still_broadcast(self):
    import json
    serv = _mk_serv(self._sd())
    msg = json.loads(serv.make_navi_message())
    self.assertEqual(msg.get("lf_drel"), 5000, "lf_drel idx0 仍应由 fields 循环广播")


class TestQ4TurnTypeMapSingleSource(unittest.TestCase):
  """Q-4: 两份 nav_type_mapping 合并为单一 TURN_TYPE_MAP。"""

  @classmethod
  def setUpClass(cls):
    _install_stubs()
    cls.carrot_serv = _load_module("carrot_serv_q4", CARROT_SERV)

  def test_single_module_level_mapping(self):
    self.assertTrue(hasattr(self.carrot_serv, "TURN_TYPE_MAP"), "Q-4 RED: 应存在模块级 TURN_TYPE_MAP")
    self.assertEqual(len(self.carrot_serv.TURN_TYPE_MAP), 53, "键集合不变（并集 53 个）")

  def test_conflicting_keys_resolved(self):
    m = self.carrot_serv.TURN_TYPE_MAP
    # 14/201 取 _update_tbt 原值（顶层旧值 5/None 为死值）
    self.assertEqual(m[14][2], 7, "uturn xTurnInfo 应为 7")
    self.assertEqual(m[201][2], 8, "arrive xTurnInfo 应为 8")
    # 51-55 取顶层 None（0 在 >0 判断下等效，None 保持 update_nav_instruction 原行为）
    for k in (51, 52, 53, 54, 55):
      self.assertIsNone(m[k][2], f"notification {k} xTurnInfo 应保持 None")

  def test_no_local_mapping_in_update_tbt(self):
    src = open(CARROT_SERV, encoding="utf-8").read()
    self.assertNotIn("turn_type_mapping = {", src, "Q-4 RED: _update_tbt 内局部字典应已删除")
    self.assertIn("TURN_TYPE_MAP", src)

  def test_no_stale_top_level_name(self):
    src = open(CARROT_SERV, encoding="utf-8").read()
    self.assertNotIn("nav_type_mapping", src.replace("原顶层 nav_type_mapping 与", ""),
                     "Q-4 RED: 顶层 nav_type_mapping 应重命名为 TURN_TYPE_MAP")

  def test_update_tbt_uses_shared_map(self):
    serv = object.__new__(self.carrot_serv.CarrotServ)
    serv.nTBTTurnType = 14
    serv.nTBTTurnTypeNext = 201
    serv.nTBTDist = 100
    serv.nTBTDistNext = 200
    serv.xDistToTurnNavLast = 0
    serv.xDistToTurnMaxCnt = 0
    self.carrot_serv.CarrotServ._update_tbt(serv)
    self.assertEqual(serv.xTurnInfo, 7, "14 -> uturn xTurnInfo 7")
    self.assertEqual(serv.xTurnInfoNext, 8, "201 -> arrive xTurnInfo 8")


if __name__ == "__main__":
  unittest.main()
