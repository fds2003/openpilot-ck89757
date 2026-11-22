#!/usr/bin/env python3
"""
TDD Unit Test for RearRadarEnable gating (无后向雷达: 默认禁用自动变道 + 消除"盲区有车"误报)

Verifies evaluate_rear_gate (selfdrive/controls/lib/rear_gate.py):
1. 未装后向雷达(rear_radar=False): 默认不允许自动变道(block=True)，且不播报后方来车(audio=False)。
   - 这是 RearRadarEnable=0 的核心语义: TTC 恒为 0.0 失效哨兵，若按 fail-safe 判冲突
     会每 2 秒误报"盲区有车"，且永久阻断自动变道；正确行为是静默禁用自动变道。
2. 已装雷达 + 净空(99.0): 允许自动变道，不播报。
3. 已装雷达 + TTC 不足或失效(0.0/负值/消息缺失): fail-safe 阻断并播报。
4. 3-level overtake thresholds (Aggressive 1.8s / Normal 2.5s / Safe 3.5s)，边界值 TTC==thr 放行。
5. 非法 overtakeMode 回退 Normal(2.5)。
"""
import unittest

from openpilot.selfdrive.controls.lib.rear_gate import evaluate_rear_gate


class TestRearRadarGating(unittest.TestCase):

  # ---- RearRadarEnable=0: 未装后向雷达 ----
  def test_no_radar_blocks_auto_and_mutes_audio(self):
    for ttc in (0.0, 99.0, 1.0):
      with self.subTest(ttc=ttc):
        block, audio = evaluate_rear_gate(False, ttc, 1, True)
        self.assertTrue(block)   # 默认不允许自动变道
        self.assertFalse(audio)  # 不误报"盲区有车"

  # ---- RearRadarEnable=1: 已装后向雷达 ----
  def test_clear_lane_permits(self):
    block, audio = evaluate_rear_gate(True, 99.0, 1, True)
    self.assertFalse(block)
    self.assertFalse(audio)

  def test_invalid_ttc_failsafe_blocks_and_alerts(self):
    for ttc in (0.0, -1.0):
      with self.subTest(ttc=ttc):
        block, audio = evaluate_rear_gate(True, ttc, 1, True)
        self.assertTrue(block)
        self.assertTrue(audio)

  def test_missing_message_failsafe_blocks_and_alerts(self):
    block, audio = evaluate_rear_gate(True, 99.0, 1, amap_alive=False)
    self.assertTrue(block)
    self.assertTrue(audio)

  def test_fast_rear_car_blocks_and_alerts(self):
    block, audio = evaluate_rear_gate(True, 1.0, 1, True)
    self.assertTrue(block)
    self.assertTrue(audio)

  def test_three_level_thresholds(self):
    self.assertFalse(evaluate_rear_gate(True, 2.0, 0, True)[0])  # Aggressive 1.8s: 2.0 放行
    self.assertTrue(evaluate_rear_gate(True, 2.0, 1, True)[0])   # Normal 2.5s: 2.0 阻断
    self.assertFalse(evaluate_rear_gate(True, 3.0, 1, True)[0])  # Normal 2.5s: 3.0 放行
    self.assertTrue(evaluate_rear_gate(True, 3.0, 2, True)[0])   # Safe 3.5s: 3.0 阻断

  def test_threshold_boundary_is_permit(self):
    # behind_ttc < thr 才算冲突，恰好等于阈值为放行
    block, audio = evaluate_rear_gate(True, 2.5, 1, True)
    self.assertFalse(block)
    self.assertFalse(audio)

  def test_invalid_overtake_mode_falls_back_to_normal(self):
    block, _ = evaluate_rear_gate(True, 2.0, 7, True)  # 非法档位 -> Normal 2.5s
    self.assertTrue(block)


if __name__ == "__main__":
  unittest.main()
