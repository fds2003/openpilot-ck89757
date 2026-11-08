#!/usr/bin/env python3
"""
TDD tests for 19号文档 C3 端「规划」档质量修复 Q-3（hasattr 防御调用收敛到统一 capnp 适配层）。

- Q-3: amap_navi.py 全文 ~39 处 hasattr 防御调用（capnp schema 字段运行时存在性
  跨版本不确定）。修复：在订阅入口封装轻量 dataclass 适配器（LeadState / CarStateData），
  hasattr 只在适配器内部出现一次，内部代码读确定类型字段。
  最密集的 capnp 字段组（radar leadOne/leadLeft/leadRight、carState 高频字段）收敛；
  零散/低频的 meta/modelV2 hasattr 保留（避免过度重构引入风险，稳定优先）。

测试分三类：
1. 适配器单元测试：parse_lead / parse_car_state 对 None、status=False、全字段、
   部分缺失字段的字段映射正确（None 哨兵保留"字段缺失"信息）。
2. 输出处不变黄金值回归（关键，防适配器改坏协议帧）：构造带 lead 的 fake radarState，
   调 make_navi_message / make_blinker_message，断言 lead 相关键的精确值与改造前一致
   （含"字段缺失 → 键缺席"行为）。
3. hasattr 数量下降静态检查：amap_navi.py 中 hasattr( 出现次数较改造前下降。

stub 模式复用 test_quality_fixes_q4_q5_q6.py（_install_stubs/_mk_serv/_SM）。
"""
import json
import os
import re
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

from test_quality_fixes_q4_q5_q6 import _install_stubs, _load_module, _mk_serv, _SM

AMAP_NAVI = os.path.join(ROOT, "selfdrive", "carrot", "amap_navi.py")


def _load_fresh():
  """每个测试类独立加载 amap_navi，避免互相污染模块级状态。"""
  _install_stubs()
  return _load_module("amap_navi_q3", AMAP_NAVI)


class _Lead:
  """capnp leadX 假对象：显式给属性（模拟 capnp 全字段/部分缺失两种情况）。"""
  def __init__(self, **kw):
    for k, v in kw.items():
      setattr(self, k, v)


def _mk_radar(leadOne=None, leadLeft=None, leadRight=None, has_attrs=True):
  """构造 fake radarState（SimpleNamespace）。has_attrs=False 模拟 lead 属性完全不存在。"""
  rs = types.SimpleNamespace()
  if has_attrs:
    rs.leadOne = leadOne
    rs.leadLeft = leadLeft
    rs.leadRight = leadRight
  return rs


# ---- 黄金值（改造前捕获，逐字节回归基准）----
# Case A: 全字段 lead
_NAVI_A = {"lead1": True, "drel": 40, "vlead": 28, "vrel": -10, "lead_accel": 0.5,
           "l_lead": True, "l_drel": 35, "l_vlead": 25, "l_vrel": -7,
           "r_lead": True, "r_drel": 30, "r_vlead": 21, "r_vrel": -3}
_BLINKER_A = {"lead1": True, "drel": 40.0, "vlead": 28.8, "vrel": -10.8, "lead_accel": 0.5}
# Case B: leadOne 缺 aRel、leadLeft 缺 vRel、leadRight status=False
_NAVI_B = {"lead1": True, "drel": 40, "vlead": 28, "vrel": -10,
           "l_lead": True, "l_drel": 40, "l_vlead": 28, "r_lead": False}
# Case C: radarState 无 lead 属性
_NAVI_C = {"lead1": False, "l_lead": False, "r_lead": False}
# Case D: lead 对象为 None
_NAVI_D = {"lead1": False, "l_lead": False, "r_lead": False}
# Case E: disableBlindSpot=True（l_lead/r_lead 恒 False）
_NAVI_E = {"lead1": True, "l_lead": False, "r_lead": False}
# Case F: leadOne 缺 dRel（status=True）→ drel 键缺席
_NAVI_F = {"lead1": True, "vlead": 28, "vrel": -10, "lead_accel": 0.5}
# Case G: leadLeft 缺 vLead → l_vlead 键缺席
_NAVI_G = {"l_lead": True, "l_drel": 40, "l_vrel": -10}


def _lead_subset(msg, keys):
  return {k: msg.get(k) for k in keys}


class TestQ3Adapters(unittest.TestCase):
  """Q-3: parse_lead / parse_car_state 适配器单元测试。"""

  @classmethod
  def setUpClass(cls):
    cls.amap_navi = _load_fresh()

  def test_parse_lead_none(self):
    amap = self.amap_navi
    lead = amap.parse_lead(None)
    self.assertFalse(lead.status)
    self.assertIsNone(lead.d_rel)
    self.assertIsNone(lead.v_lead)
    self.assertIsNone(lead.v_rel)
    self.assertIsNone(lead.a_rel)

  def test_parse_lead_status_false(self):
    """status=False 的 lead 应映射为 status=False（各字段仍按提供情况映射）。"""
    amap = self.amap_navi
    lead = amap.parse_lead(_Lead(status=False, dRel=40.0))
    self.assertFalse(lead.status)
    self.assertEqual(lead.d_rel, 40.0)

  def test_parse_lead_full_fields(self):
    """全字段 lead：capnp camelCase → dataclass snake_case 逐字段映射正确。"""
    amap = self.amap_navi
    lead = amap.parse_lead(_Lead(status=True, dRel=40.0, vLead=8.0, vRel=-3.0, aRel=0.5))
    self.assertTrue(lead.status)
    self.assertEqual(lead.d_rel, 40.0)
    self.assertEqual(lead.v_lead, 8.0)
    self.assertEqual(lead.v_rel, -3.0)
    self.assertEqual(lead.a_rel, 0.5)

  def test_parse_lead_missing_field_is_none_not_zero(self):
    """缺字段 → None（而非 0.0），保留"字段缺席"信息供调用点跳键。"""
    amap = self.amap_navi
    lead = amap.parse_lead(_Lead(status=True, dRel=40.0))
    self.assertEqual(lead.d_rel, 40.0)
    self.assertIsNone(lead.v_lead, "未提供的 vLead 应为 None")
    self.assertIsNone(lead.v_rel)
    self.assertIsNone(lead.a_rel)

  def test_parse_car_state_none(self):
    amap = self.amap_navi
    cs = amap.parse_car_state(None)
    self.assertFalse(cs.cruise_present)
    self.assertIsNone(cs.standstill)
    self.assertIsNone(cs.v_ego)
    self.assertIsNone(cs.cruise_enabled)

  def test_parse_car_state_full_fields(self):
    """全字段 carState（含嵌套 cruiseState）逐字段映射。"""
    amap = self.amap_navi
    class _Cruise:
      enabled = True
      available = False
    cs = amap.parse_car_state(_Lead(status=True, standstill=True, vEgoCluster=15.4,
                                    vCruise=60, vEgo=12.5, aEgo=1.1,
                                    steeringAngleDeg=3.3, steeringTorqueEps=-2.0,
                                    gasPressed=True, brakePressed=False,
                                    cruiseState=_Cruise(), leftBlindspot=1, rightBlindspot=0))
    self.assertIs(cs.standstill, True)
    self.assertEqual(cs.v_ego_cluster, 15.4)
    self.assertEqual(cs.v_cruise, 60)
    self.assertEqual(cs.v_ego, 12.5)
    self.assertEqual(cs.a_ego, 1.1)
    self.assertEqual(cs.steering_angle_deg, 3.3)
    self.assertEqual(cs.steering_torque_eps, -2.0)
    self.assertIs(cs.gas_pressed, True)
    self.assertIs(cs.brake_pressed, False)
    self.assertTrue(cs.cruise_present)
    self.assertIs(cs.cruise_enabled, True)
    self.assertIs(cs.cruise_available, False)
    self.assertEqual(cs.left_blindspot, 1)
    self.assertEqual(cs.right_blindspot, 0)

  def test_parse_car_state_missing_cruise_state(self):
    """无 cruiseState 属性 → cruise_present=False、cruise_* 为 None（等价原 hasattr 门控）。"""
    amap = self.amap_navi
    cs = amap.parse_car_state(_Lead(vEgo=12.5))
    self.assertFalse(cs.cruise_present)
    self.assertIsNone(cs.cruise_enabled)
    self.assertIsNone(cs.cruise_available)


class TestQ3LeadGoldenValues(unittest.TestCase):
  """Q-3: lead 适配器改造后 make_navi_message / make_blinker_message 输出处逐字节不变。"""

  @classmethod
  def setUpClass(cls):
    cls.amap_navi = _load_fresh()

  def _serv_with_radar(self, radar, disable_blindspot=False):
    sd = self.amap_navi.SharedData()
    sd.carState = True
    sd.v_cruise_kph = 60
    sd.v_ego_kph = 55
    serv = _mk_serv(sd)
    serv.disableBlindSpot = disable_blindspot
    serv.sm = _SM(['modelV2', 'selfdriveState', 'radarState', 'carrotMan'])
    serv.sm._data['radarState'] = radar
    return serv

  def test_navi_lead_full_fields(self):
    """Case A：全字段三向 lead，navi 帧 lead 相关键与改造前精确一致。"""
    serv = self._serv_with_radar(_mk_radar(
      _Lead(status=True, dRel=40.0, vLead=8.0, vRel=-3.0, aRel=0.5),
      _Lead(status=True, dRel=35.0, vLead=7.0, vRel=-2.0, aRel=0.3),
      _Lead(status=True, dRel=30.0, vLead=6.0, vRel=-1.0, aRel=0.2)))
    msg = json.loads(serv.make_navi_message())
    self.assertEqual(_lead_subset(msg, sorted(_NAVI_A.keys())), _NAVI_A)

  def test_blinker_lead_full_fields(self):
    """Case A：blinker 帧 leadOne 用 round1（非 int），输出与改造前一致。"""
    serv = self._serv_with_radar(_mk_radar(
      _Lead(status=True, dRel=40.0, vLead=8.0, vRel=-3.0, aRel=0.5)))
    msg = json.loads(serv.make_blinker_message())
    self.assertEqual(_lead_subset(msg, sorted(_BLINKER_A.keys())), _BLINKER_A)

  def test_navi_lead_partial_missing_fields(self):
    """Case B：leadOne 缺 aRel、leadLeft 缺 vRel、leadRight status=False → 键缺席行为不变。"""
    serv = self._serv_with_radar(_mk_radar(
      _Lead(status=True, dRel=40.0, vLead=8.0, vRel=-3.0),
      _Lead(status=True, dRel=40.0, vLead=8.0),
      _Lead(status=False, dRel=99)))
    msg = json.loads(serv.make_navi_message())
    self.assertEqual(_lead_subset(msg, sorted(_NAVI_B.keys())), _NAVI_B)
    # 缺失字段对应的键必须缺席
    self.assertNotIn("lead_accel", msg, "leadOne 缺 aRel → lead_accel 键应缺席")
    self.assertNotIn("l_vrel", msg, "leadLeft 缺 vRel → l_vrel 键应缺席")

  def test_navi_lead_no_radar_attrs(self):
    """Case C：radarState 无 lead 属性 → 各 lead 标志 False。"""
    serv = self._serv_with_radar(_mk_radar(has_attrs=False))
    msg = json.loads(serv.make_navi_message())
    self.assertEqual(_lead_subset(msg, sorted(_NAVI_C.keys())), _NAVI_C)

  def test_navi_lead_none_objects(self):
    """Case D：lead 对象为 None → 各 lead 标志 False。"""
    serv = self._serv_with_radar(_mk_radar(None, None, None))
    msg = json.loads(serv.make_navi_message())
    self.assertEqual(_lead_subset(msg, sorted(_NAVI_D.keys())), _NAVI_D)

  def test_navi_disable_blindspot(self):
    """Case E：disableBlindSpot=True 时 l_lead/r_lead 恒 False（即使有 lead）。"""
    serv = self._serv_with_radar(_mk_radar(
      _Lead(status=True, dRel=40.0, vLead=8.0, vRel=-3.0, aRel=0.5),
      _Lead(status=True, dRel=35.0, vLead=7.0, vRel=-2.0),
      _Lead(status=True, dRel=30.0, vLead=6.0, vRel=-1.0)),
      disable_blindspot=True)
    msg = json.loads(serv.make_navi_message())
    self.assertEqual(_lead_subset(msg, sorted(_NAVI_E.keys())), _NAVI_E)
    self.assertNotIn("l_drel", msg, "disableBlindSpot → l_drel 键应缺席")

  def test_navi_lead_one_missing_drel_key_absent(self):
    """Case F：leadOne 缺 dRel（status=True）→ drel 键缺席（逐字节回归）。"""
    serv = self._serv_with_radar(_mk_radar(
      _Lead(status=True, vLead=8.0, vRel=-3.0, aRel=0.5)))
    msg = json.loads(serv.make_navi_message())
    self.assertEqual(_lead_subset(msg, sorted(_NAVI_F.keys())), _NAVI_F)
    self.assertNotIn("drel", msg, "leadOne 缺 dRel → drel 键应缺席")

  def test_navi_lead_left_missing_vlead_key_absent(self):
    """Case G：leadLeft 缺 vLead → l_vlead 键缺席。"""
    serv = self._serv_with_radar(_mk_radar(
      _Lead(status=True, dRel=40.0, vLead=8.0, vRel=-3.0),
      _Lead(status=True, dRel=40.0, vRel=-3.0)))
    msg = json.loads(serv.make_navi_message())
    self.assertEqual(_lead_subset(msg, sorted(_NAVI_G.keys())), _NAVI_G)
    self.assertNotIn("l_vlead", msg, "leadLeft 缺 vLead → l_vlead 键应缺席")


class TestQ3CarStateGoldenValues(unittest.TestCase):
  """Q-3: carState 适配器改造后 update_navi_carstate 共享数据行为不变。"""

  @classmethod
  def setUpClass(cls):
    cls.amap_navi = _load_fresh()

  def _run_cs(self, cs, v_ego_m=0.0):
    amap = self.amap_navi
    sd = amap.SharedData()
    sd.carState = True
    sd.v_ego_m = v_ego_m
    serv = _mk_serv(sd)
    class _SM:
      def __init__(self, cs):
        self.alive = {"carState": True}
        self._cs = cs
      def __getitem__(self, t):
        return self._cs
    serv.sm = _SM(cs)
    serv.update_navi_carstate(serv.sm)
    return serv.shared_data

  def _cruise(self, enabled, available):
    c = types.SimpleNamespace()
    c.enabled = enabled
    c.available = available
    return c

  def test_full_fields(self):
    sd = self._run_cs(_Lead(standstill=True, vEgoCluster=15.4, vCruise=60, vEgo=12.5,
                            aEgo=1.1, steeringAngleDeg=3.3, steeringTorqueEps=-2.0,
                            gasPressed=True, brakePressed=False,
                            cruiseState=self._cruise(True, True),
                            leftBlindspot=1, rightBlindspot=0),
                      v_ego_m=5.0)
    self.assertIs(sd.standstill, True)
    self.assertEqual(sd.v_ego_kph, 55, "int(15.4*3.6+0.5)=55")
    self.assertEqual(sd.v_cruise_kph, 60)
    self.assertEqual(sd.v_ego_m, 12.5)
    self.assertEqual(sd.vEgo, 45.0, "round1(12.5*3.6)=45.0")
    self.assertEqual(sd.aEgo, 1.1)
    self.assertEqual(sd.steer_angle, 3.3)
    self.assertIs(sd.driver_steering, True, "torque=-2, angle=3.3 方向相反且 |torque|>0.5")
    self.assertIs(sd.gas_press, True)
    self.assertIs(sd.break_press, False)
    self.assertIs(sd.engaged, True)
    self.assertIs(sd.cruise_valid, True)
    self.assertEqual(sd.left_blindspot, 1)
    self.assertEqual(sd.right_blindspot, 0)

  def test_standstill_absent_fallback_low_speed(self):
    """standstill 缺失 + v_ego_m<0.1 → standstill=True（else 分支行为不变）。"""
    sd = self._run_cs(_Lead(vEgo=12.5), v_ego_m=0.05)
    self.assertIs(sd.standstill, True)

  def test_standstill_absent_fallback_high_speed(self):
    """standstill 缺失 + v_ego_m>=0.1 → standstill=False。"""
    sd = self._run_cs(_Lead(vEgo=12.5), v_ego_m=5.0)
    self.assertIs(sd.standstill, False)

  def test_torque_absent_driver_steering_false(self):
    """steeringTorqueEps 缺失 → driver_steering=False（原 hasattr 双字段门控）。"""
    sd = self._run_cs(_Lead(vEgo=12.5))
    self.assertIs(sd.driver_steering, False)

  def test_cruise_absent_fields_stay_none(self):
    """cruiseState 缺失 → engaged/cruise_valid/cruise_enable 保持 None（等价原 hasattr 门控）。"""
    sd = self._run_cs(_Lead(vEgo=12.5))
    self.assertIsNone(sd.engaged)
    self.assertIsNone(sd.cruise_valid)
    self.assertIsNone(sd.cruise_enable)

  def test_missing_fields_stay_none(self):
    """缺字段的共享数据保持默认 None（等价原 hasattr 缺失分支跳过）。"""
    sd = self._run_cs(_Lead(vEgo=12.5))
    self.assertIsNone(sd.aEgo)
    self.assertIsNone(sd.steer_angle)
    self.assertIsNone(sd.gas_press)
    self.assertIsNone(sd.break_press)
    self.assertIsNone(sd.left_blindspot)
    self.assertIsNone(sd.right_blindspot)


class TestQ3HasattrConvergence(unittest.TestCase):
  """Q-3: hasattr 防御调用较改造前收敛（静态检查）。"""

  def test_hasattr_call_sites_decreased(self):
    """改造前 hasattr( 调用点 39 处；收敛后 ≤ 9 处（lead + carState 集群消除）。"""
    with open(AMAP_NAVI, "r", encoding="utf-8") as f:
      src = f.read()
    # 只统计真实调用（行首或表达式内），排除注释/docstring 里的 hasattr 字样
    call_sites = len(re.findall(r"(?m)^[^#]*hasattr\(", src))
    self.assertLessEqual(call_sites, 9,
                        f"Q-3: hasattr( 调用点应收敛至 ≤9（实际 {call_sites}）")
    self.assertGreater(9, call_sites,
                       "Q-3: hasattr( 调用点应实际下降（改造前 39 处）")

  def test_adapters_defined(self):
    """适配层 dataclass + parse 函数存在（hasattr 收敛目标）。"""
    amap = _load_fresh()
    self.assertTrue(hasattr(amap, "LeadState"))
    self.assertTrue(hasattr(amap, "parse_lead"))
    self.assertTrue(hasattr(amap, "CarStateData"))
    self.assertTrue(hasattr(amap, "parse_car_state"))


if __name__ == "__main__":
  unittest.main()
