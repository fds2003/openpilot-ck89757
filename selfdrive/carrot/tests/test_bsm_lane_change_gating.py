#!/usr/bin/env python3
"""
TDD Unit Test for 原车 BSM(后视镜盲区指示灯)自动变道门禁

Verifies evaluate_bsm_gate (selfdrive/controls/lib/rear_gate.py):
1. 方向相关：变道方向侧的盲区指示灯亮 → 阻断自动变道；对侧有车不影响。
2. 无方向(NONE/BOTH)不阻断（无明确变道方向时不误伤）。
3. DisableBlindSpot=1（原车盲区信号已禁用）时永不阻断。
4. 该门禁仅约束自动变道触发路径；驾驶员打灯+扭矩的手动变道由既有逻辑处理，不在本函数职责内。
"""
import unittest

from openpilot.selfdrive.controls.lib.rear_gate import (
  BLINKER_NONE, BLINKER_LEFT, BLINKER_RIGHT, BLINKER_BOTH,
  evaluate_bsm_gate,
)


class TestBsmLaneChangeGating(unittest.TestCase):

  def test_left_bsm_blocks_left_auto_lane_change(self):
    self.assertTrue(evaluate_bsm_gate(True, False, BLINKER_LEFT))

  def test_right_bsm_blocks_right_auto_lane_change(self):
    self.assertTrue(evaluate_bsm_gate(False, True, BLINKER_RIGHT))

  def test_opposite_side_bsm_does_not_block(self):
    self.assertFalse(evaluate_bsm_gate(True, False, BLINKER_RIGHT))   # 左有车，向右变道
    self.assertFalse(evaluate_bsm_gate(False, True, BLINKER_LEFT))    # 右有车，向左变道

  def test_no_bsm_never_blocks(self):
    for direction in (BLINKER_NONE, BLINKER_LEFT, BLINKER_RIGHT, BLINKER_BOTH):
      with self.subTest(direction=direction):
        self.assertFalse(evaluate_bsm_gate(False, False, direction))

  def test_disable_blind_spot_never_blocks(self):
    # DisableBlindSpot=1: 原车盲区信号被用户禁用，即使指示灯亮也不阻断
    for direction in (BLINKER_NONE, BLINKER_LEFT, BLINKER_RIGHT, BLINKER_BOTH):
      with self.subTest(direction=direction):
        self.assertFalse(evaluate_bsm_gate(True, True, direction, bsm_enabled=False))

  def test_unknown_direction_does_not_block(self):
    # 方向未知（NONE）或双闪（BOTH）时不阻断，避免误伤
    self.assertFalse(evaluate_bsm_gate(True, True, BLINKER_NONE))
    self.assertFalse(evaluate_bsm_gate(True, True, BLINKER_BOTH))


if __name__ == "__main__":
  unittest.main()
