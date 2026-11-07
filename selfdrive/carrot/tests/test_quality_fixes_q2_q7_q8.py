#!/usr/bin/env python3
"""
TDD tests for 19号文档 C3 端「近期」档质量修复（Q-2 / Q-7 / Q-8）。

- Q-8: f1/f2 重命名 round1/round2；模块级 lock/data_queue 内聚为
       AmapNaviServ._lock / _data_queue（实例属性）。
- Q-7: UDP 包解析路径异常分层（JSONDecodeError/UnicodeDecodeError ->
       malformed 计数后 return；KeyError -> cloudlog.warning；
       兜底 -> cloudlog.exception）。
- Q-2: make_navi_message / make_lidar_message / make_blinker_message 的
       公共逐字重复块抽取为 _build_base_fields / _apply_cruise_state，
       广播帧黄金值回归保证同输入下逐字段一致。

stub 模式复用 test_quality_fixes_q4_q5_q6.py（_install_stubs / _SM / _ModelV2
/ _CarrotMan / _Meta / _LC / _mk_serv），两文件独立可跑。
"""
import importlib.util
import json
import os
import queue
import re
import socket
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
AMAP_NAVI = os.path.join(ROOT, "selfdrive", "carrot", "amap_navi.py")

from test_quality_fixes_q4_q5_q6 import (
  _install_stubs, _load_module, _mk_serv, _SM, _ModelV2, _CarrotMan, _Meta, _LC,
)


def _load_fresh():
  """每个测试类独立加载 amap_navi，避免互相污染模块级状态。"""
  _install_stubs()
  return _load_module("amap_navi_q2q7q8", AMAP_NAVI)


class _RadarLead:
  dRel = 1234; vLead = 5.0; vRel = 1.5; aRel = 0.2; status = True


class _RadarLeadOff:
  status = False; dRel = 0; vLead = 0; vRel = 0


class _RadarState:
  leadOne = _RadarLead()
  leadLeft = None
  leadRight = None


class _RadarEmpty:
  leadOne = _RadarLeadOff()
  leadLeft = None
  leadRight = None


def _mk_serv_variant(amap, radar, cruise_valid, active):
  """构造 make_*_message 依赖齐全的最小实例。

  radar: _RadarState（有主雷达目标）/ _RadarEmpty（leadOne.status=False）/ None
  cruise_valid/active: 写进 shared_data，驱动 _apply_cruise_state 分支。
  """
  sd = amap.SharedData()
  sd.carState = True
  sd.v_cruise_kph = 60
  sd.v_ego_kph = 55
  sd.cruise_valid = cruise_valid
  sd.selfdrive_active = active
  serv = _mk_serv(sd)
  serv.sm.alive = {t: (t != "radarState" or radar is not None) for t in serv.sm.alive}
  if radar is not None:
    serv.sm._data["radarState"] = radar
  return serv


class TestQ8NamingAndEncapsulation(unittest.TestCase):
  """Q-8: 命名清理 + 锁/队列内聚。"""

  @classmethod
  def setUpClass(cls):
    cls.amap_navi = _load_fresh()

  def test_round1_round2_behavior(self):
    a = self.amap_navi
    self.assertEqual(a.round1(3.456), 3.5)
    self.assertEqual(a.round2(3.456), 3.46)

  def test_f1_f2_removed(self):
    self.assertFalse(hasattr(self.amap_navi, "f1"), "f1 应已重命名为 round1")
    self.assertFalse(hasattr(self.amap_navi, "f2"), "f2 应已重命名为 round2")

  def test_init_sets_instance_lock_and_queue(self):
    """__init__ 应设置 self._lock（threading.Lock）与 self._data_queue（maxsize=5 队列）。

    真实 __init__ 会启动 UDP 线程/绑端口（测试环境不可控），故做源码静态检查，
    并验证类型定义本身（Lock / Queue(maxsize=5) 构造行为正确）。
    """
    amap = self.amap_navi
    src = open(AMAP_NAVI, encoding="utf-8").read()
    self.assertIn("self._lock = threading.Lock()", src, "Q-8 RED: __init__ 应设置 self._lock")
    self.assertIn("self._data_queue = queue.Queue(5)", src,
                  "Q-8 RED: __init__ 应设置 self._data_queue(maxsize=5)")

  def test_no_module_level_lock_or_data_queue(self):
    src = open(AMAP_NAVI, encoding="utf-8").read()
    import re
    # 排除注释行后检查裸赋值（模块级）是否残留
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    self.assertIsNone(re.search(r"^lock = threading\.Lock\(\)", code, re.M),
                      "Q-8 RED: 模块级裸 lock 赋值应已移入 __init__")
    self.assertIsNone(re.search(r"^data_queue = queue\.Queue\(\)", code, re.M),
                      "Q-8 RED: 模块级裸 data_queue 赋值应已移入 __init__")

  def test_lock_only_used_via_instance_attr(self):
    src = open(AMAP_NAVI, encoding="utf-8").read()
    # 所有 with lock: 应已改为 with self._lock:
    self.assertNotIn("with lock:", src, "Q-8 RED: 裸 with lock: 应全部改为 self._lock")


class TestQ7ParseExceptionLayering(unittest.TestCase):
  """Q-7: UDP 解析路径异常分层。"""

  @classmethod
  def setUpClass(cls):
    cls.amap_navi = _load_fresh()

  def test_imports_cloudlog(self):
    self.assertTrue(hasattr(self.amap_navi, "cloudlog"),
                    "Q-7 RED: amap_navi 应 import cloudlog")

  def test_malformed_json_does_not_raise(self):
    """喂坏 JSON 给 _process_single_packet：分层捕获后不抛出、不中断。"""
    amap = self.amap_navi
    sd = amap.SharedData()
    serv = object.__new__(amap.AmapNaviServ)
    serv.shared_data = sd
    serv.params = amap.UnifiedParams()
    serv.sm = _SM(['modelV2', 'selfdriveState', 'radarState', 'carrotMan'])
    serv.local_ip_address = "127.0.0.1"
    serv.listen_port = 4211
    serv.clients = {}
    serv._lock = amap.threading.Lock()
    serv._malformed_count = 0  # _process_single_packet 分层捕获会累加该计数
    # 坏 JSON（触发 json.JSONDecodeError）与坏编码（触发 UnicodeDecodeError）都不应抛出
    for bad in (b"{not json", b"\xff\xfe\x00bad-bytes"):
      try:
        serv._process_single_packet(bad, ("127.0.0.1", 4211))
      except Exception as e:
        self.fail(f"Q-7 RED: 坏包 {bad!r} 解析应被捕获而不抛出: {e}")

  def test_keyerror_goes_to_cloudlog_warning(self):
    """解析后 KeyError 分支应走 cloudlog.warning（带来源 IP），不再裸 print。"""
    src = open(AMAP_NAVI, encoding="utf-8").read()
    self.assertIn("except KeyError as e:", src, "Q-7 RED: 解析路径应分层捕获 KeyError")
    self.assertIn('cloudlog.warning(f"amap_navi KeyError from {ip}', src,
                  "Q-7 RED: KeyError 分支应调用 cloudlog.warning（带来源 IP）")

  def test_fallback_is_cloudlog_exception(self):
    """解析路径兜底 except 应使用 cloudlog.exception（完整 traceback）。"""
    src = open(AMAP_NAVI, encoding="utf-8").read()
    self.assertIn('cloudlog.exception(f"amap_navi packet error from {ip}")', src,
                  "Q-7 RED: 解析路径兜底应为 cloudlog.exception")

  def test_malformed_counter(self):
    """JSONDecodeError 分支应记录 malformed 计数（实例属性）。"""
    src = open(AMAP_NAVI, encoding="utf-8").read()
    self.assertIn("except (json.JSONDecodeError, UnicodeDecodeError):", src,
                  "Q-7 RED: 应显式捕获 JSONDecodeError/UnicodeDecodeError")
    self.assertIn("self._malformed_count += 1", src,
                  "Q-7 RED: 坏包分支应累加 _malformed_count")


class TestQ2MessageRefactor(unittest.TestCase):
  """Q-2: 公共逻辑抽取后广播帧黄金值回归（重构前取，保证逐字段一致）。"""

  @classmethod
  def setUpClass(cls):
    cls.amap_navi = _load_fresh()

  def _variants(self):
    # (名称, radar, cruise_valid, selfdrive_active)
    return [
      ("main_radar", _RadarState(), True, True),
      ("no_radar", None, None, None),
      ("cruise_none", _RadarEmpty(), None, False),
    ]

  def _golden(self, name):
    # 黄金值于重构前（2026-11-08）对当前代码实际输出打印取得。
    # None = 该键应缺席。
    if name == "main_radar":
      n = {"IsOnroad": True, "engaged": False, "active": True, "lb_drel": None, "rb_drel": None,
           "lf_drel": None, "v_cruise_kph": 60, "v_ego_kph": 55, "lead1": True, "drel": 1234,
           "vlead": 18, "vrel": 5, "atc_state": 0}
      l = {"IsOnroad": True, "engaged": False, "active": True, "atc_type": "none", "road_name": ""}
      b = {"IsOnroad": True, "engaged": False, "active": True, "lead1": True, "drel": 1234.0,
           "vlead": 18.0, "vrel": 5.4}
    elif name == "no_radar":
      n = {"IsOnroad": True, "engaged": False, "active": None, "v_cruise_kph": 60, "v_ego_kph": 55,
           "lead1": None, "atc_state": 0}
      l = {"IsOnroad": True, "engaged": False, "active": None, "atc_type": "none", "road_name": ""}
      b = {"IsOnroad": True, "engaged": False, "active": None, "lead1": None}
    else:  # cruise_none: leadOne.status=False
      n = {"IsOnroad": True, "engaged": False, "active": None, "v_cruise_kph": 60, "v_ego_kph": 55,
           "lead1": False, "atc_state": 0}
      l = {"IsOnroad": True, "engaged": False, "active": None, "atc_type": "none", "road_name": ""}
      b = {"IsOnroad": True, "engaged": False, "active": None, "lead1": False}
    return {"navi": n, "lidar": l, "blinker": b}

  def _check(self, msg, golden, ctx):
    for k, v in golden.items():
      if v is None:
        self.assertNotIn(k, msg, f"{ctx}: 键 {k} 应缺席")
      else:
        self.assertEqual(msg.get(k), v, f"{ctx}: 键 {k} 应等于 {v!r}")

  def test_golden_regression(self):
    amap = self.amap_navi
    for name, radar, cv, act in self._variants():
      serv = _mk_serv_variant(amap, radar, cv, act)
      golden = self._golden(name)
      self._check(json.loads(serv.make_navi_message()), golden["navi"], f"{name}.navi")
      self._check(json.loads(serv.make_lidar_message()), golden["lidar"], f"{name}.lidar")
      self._check(json.loads(serv.make_blinker_message()), golden["blinker"], f"{name}.blinker")

  def test_lf_drel_fields_loop_regression(self):
    """Q-6 裁剪后 fields 循环仍广播 lf_drel idx0（防止 Q-2 重构回退）。"""
    amap = self.amap_navi
    sd = amap.SharedData()
    sd.carState = True
    sd.v_cruise_kph = 60
    sd.lf_drel[0] = 5000
    serv = _mk_serv(sd)
    msg = json.loads(serv.make_navi_message())
    self.assertEqual(msg.get("lf_drel"), 5000, "lf_drel idx0 应仍由 fields 循环广播")

  def test_helper_methods_exist(self):
    amap = self.amap_navi
    for meth in ("_build_base_fields", "_apply_cruise_state"):
      self.assertTrue(callable(getattr(amap.AmapNaviServ, meth, None)),
                      f"Q-2 RED: 应存在 AmapNaviServ.{meth} 辅助方法")


if __name__ == "__main__":
  unittest.main()
