#!/usr/bin/env python3
"""
selfdrive/carrot/tests/test_bug2_atc_state.py
=====================================================================
TDD 单元测试：BUG-2 atcType 字符串 → atc_state 整数映射
=====================================================================

BUG-2 把 atc_state 从「仅 modelV2.alive 时发 meta.laneChangeState.raw」改为
「carrotMan.alive 时从 atcType 字符串派生（稳定源），modelV2 路径后写覆盖」。
本测试镜像映射规则，并 grep 源码断言派生分支存在（防回退）。

映射（与 carrot_man.py atcType 枚举一致）：
  "laneChangeFinishing" → 3（变道完成）
  "laneChangeStarting"  → 2
  "preLaneChange"       → 1
  其它（none/prepare…） → 0
"""
import os
import re
import unittest

HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, "..", "amap_navi.py")


def atc_type_to_state(atc_type):
  """镜像 amap_navi.py carrotMan 块的 atc_state 派生规则。"""
  if "laneChangeFinishing" in atc_type:
    return 3
  elif "laneChangeStarting" in atc_type:
    return 2
  elif "preLaneChange" in atc_type:
    return 1
  else:
    return 0


class TestBug2AtcState(unittest.TestCase):

  def test_finishing_maps_to_3(self):
    self.assertEqual(atc_type_to_state("laneChangeFinishing"), 3)

  def test_starting_maps_to_2(self):
    self.assertEqual(atc_type_to_state("laneChangeStarting"), 2)

  def test_pre_lane_change_maps_to_1(self):
    self.assertEqual(atc_type_to_state("preLaneChange"), 1)

  def test_none_or_prepare_maps_to_0(self):
    self.assertEqual(atc_type_to_state("none"), 0)
    self.assertEqual(atc_type_to_state("prepare"), 0)
    self.assertEqual(atc_type_to_state(""), 0)

  def test_ordering_finishing_wins_over_starting(self):
    # 组合串时 finishing 优先（与源码 if/elif 顺序一致）
    self.assertEqual(atc_type_to_state("laneChangeFinishing+laneChangeStarting"), 3)

  def test_source_has_derivation_in_carrotman_block(self):
    """源码 carrotMan 块确实从 atcType 派生 atc_state（防回退到仅 modelV2）"""
    with open(SRC, encoding="utf-8", errors="replace") as f:
      src = f.read()
    self.assertIn('"laneChangeFinishing" in atc_type', src,
        "amap_navi.py 缺少 atcType→atc_state 派生（BUG-2 回退）")
    self.assertIn('msg["atc_state"] = 3', src,
        "amap_navi.py 缺少 finishing→3 派生分支")


if __name__ == "__main__":
  unittest.main()
