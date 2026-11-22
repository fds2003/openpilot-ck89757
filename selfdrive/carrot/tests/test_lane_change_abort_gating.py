#!/usr/bin/env python3
"""
TDD Unit Test for P0-2: laneChangeStarting 阶段 TTC 复检 + is_driver_initiated 判定

Verifies selfdrive/controls/lib/rear_gate.py:
1. is_driver_initiated_change:
   - 远程车机指令 (trigger_name="cmd") 不属于驾驶员手动变道 → False（P0-2 核心）
   - 驾驶员手动 (driver / torque bsd / torque ok) → True
   - 自动发起 (torque auto / timeout) → False
2. evaluate_lane_change_abort:
   - 驾驶员手动：仅传感器在线且确认后车逼近 (0 < TTC < 阈值) 才中止；
     传感器失效/离线/净空 不阻断手动变道（回退原生 BSD 监控）
   - 车机指令/自动（含远程 cmd）：fail-safe —— 消息缺失 / TTC<=0（未确认清空）/
     TTC 不足 一律中止
3. 三档 OVERTAKE 阈值（1.8/2.5/3.5），非法档位回退标准档。
"""
import unittest

from openpilot.selfdrive.controls.lib.rear_gate import (
  evaluate_lane_change_abort,
  is_driver_initiated_change,
)


class TestIsDriverInitiated(unittest.TestCase):

  # P0-2 核心：远程 cmd 不是驾驶员手动变道
  def test_remote_cmd_is_not_driver_initiated(self):
    self.assertFalse(is_driver_initiated_change(3, "cmd"))

  def test_driver_paths_are_driver_initiated(self):
    self.assertTrue(is_driver_initiated_change(3, "driver"))
    self.assertTrue(is_driver_initiated_change(1, "torque bsd"))
    self.assertTrue(is_driver_initiated_change(2, "torque ok"))

  def test_auto_paths_are_not_driver_initiated(self):
    self.assertFalse(is_driver_initiated_change(4, "torque auto"))
    self.assertFalse(is_driver_initiated_change(7, "timeout"))


class TestLaneChangeAbort(unittest.TestCase):

  # ---- 驾驶员手动变道：宽松（传感器失效不阻断） ----
  def test_driver_not_aborted_on_sensor_failure(self):
    self.assertFalse(evaluate_lane_change_abort(True, False, 0.0, 1))
    self.assertFalse(evaluate_lane_change_abort(True, True, 0.0, 1))

  def test_driver_not_aborted_on_clear_lane(self):
    self.assertFalse(evaluate_lane_change_abort(True, True, 99.0, 1))

  def test_driver_aborted_on_confirmed_fast_rear_car(self):
    self.assertTrue(evaluate_lane_change_abort(True, True, 1.0, 1))

  # ---- 车机指令/自动变道（含远程 cmd）：fail-safe 严格 ----
  def test_cmd_aborted_on_missing_message(self):
    # P0-2 修复前：cmd 被误判为驾驶员路径，amapNavi 死亡反而不中止
    self.assertTrue(evaluate_lane_change_abort(False, False, 99.0, 1))

  def test_cmd_aborted_on_invalid_ttc(self):
    # ttc=0.0 视为未确认清空 → 中止
    self.assertTrue(evaluate_lane_change_abort(False, True, 0.0, 1))
    self.assertTrue(evaluate_lane_change_abort(False, True, -1.0, 1))

  def test_cmd_aborted_on_fast_rear_car(self):
    self.assertTrue(evaluate_lane_change_abort(False, True, 1.0, 1))

  def test_auto_permitted_on_clear_lane(self):
    self.assertFalse(evaluate_lane_change_abort(False, True, 99.0, 1))

  # ---- 三档阈值与边界 ----
  def test_threshold_boundary_is_permit(self):
    # TTC 恰好等于阈值：不算冲突
    self.assertFalse(evaluate_lane_change_abort(False, True, 2.5, 1))

  def test_three_level_thresholds(self):
    # 驾驶员路径：TTC=2.0，Aggressive(1.8) 放行 / Normal(2.5) 中止
    self.assertFalse(evaluate_lane_change_abort(True, True, 2.0, 0))
    self.assertTrue(evaluate_lane_change_abort(True, True, 2.0, 1))
    # 自动路径：TTC=3.0，Normal(2.5) 放行 / Safe(3.5) 中止
    self.assertFalse(evaluate_lane_change_abort(False, True, 3.0, 1))
    self.assertTrue(evaluate_lane_change_abort(False, True, 3.0, 2))

  def test_invalid_overtake_mode_falls_back_to_normal(self):
    self.assertTrue(evaluate_lane_change_abort(False, True, 2.0, 7))


if __name__ == "__main__":
  unittest.main()
