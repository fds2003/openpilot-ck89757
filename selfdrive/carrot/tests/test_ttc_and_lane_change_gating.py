#!/usr/bin/env python3
"""
TDD tests for P1-5 + P2-1: TTC 计算/门禁统一为生产单一实现。

- P1-5: 旧测试 helper 在 ttc_list 为空时一律返回 99.0，与生产语义分叉
  （生产仅"确为净空"才 99.0，有并排目标时为 0.0 失效哨兵）。迁移后
  测试直接调用 rear_gate.calculate_rear_ttc 生产函数，并补
  no_rear_target=False 用例。
- P2-1: TTC 阈值映射 {0:1.8, 1:2.5, 2:3.5} 三处重复 → rear_gate.py
  单一常量 REAR_TTC_THRESHOLDS。
"""
from openpilot.selfdrive.controls.lib.rear_gate import (
  REAR_TTC_THRESHOLDS,
  calculate_rear_ttc,
  evaluate_rear_gate,
)


class TestRearTtcProduction:

  def test_clear_lane_returns_99(self):
    # 两侧均无目标 + 雷达在线 + 无逼近 → 99.0 净空放行
    ttc = calculate_rear_ttc(None, None, None, None, lidar_online=True)
    assert ttc == 99.0

  def test_approaching_vehicle_returns_min_ttc(self):
    # 左后 -18m 以 -15m/s 逼近 → TTC = 1.2s
    ttc = calculate_rear_ttc(-18000, -15.0, None, None, lidar_online=True)
    assert abs(ttc - 1.2) < 0.01

  def test_parallel_target_is_not_clear_lane(self):
    # P1-5 新增：有并排目标（drel 非 None 但 vrel 不逼近）→ 0.0 失效哨兵，
    # 不得误判 99.0 净空（16aff86 fail-open 裁决的回归覆盖）
    ttc = calculate_rear_ttc(5000, 0.0, None, None, lidar_online=True)
    assert ttc == 0.0

  def test_lidar_offline_is_sentinel_even_without_targets(self):
    ttc = calculate_rear_ttc(None, None, None, None, lidar_online=False)
    assert ttc == 0.0

  def test_fastest_of_both_sides_wins(self):
    # 左后 TTC 3.0s / 右后 TTC 1.5s → 取最小 1.5s（最保守）
    ttc = calculate_rear_ttc(-30000, -10.0, -15000, -10.0, lidar_online=True)
    assert abs(ttc - 1.5) < 0.01


class TestRearGateThresholds:

  def test_threshold_constants_single_source(self):
    # P2-1: 阈值常量唯一来源为 rear_gate.REAR_TTC_THRESHOLDS
    assert REAR_TTC_THRESHOLDS == {0: 1.8, 1: 2.5, 2: 3.5}

  def test_clear_lane_permits(self):
    block, audio = evaluate_rear_gate(True, 99.0, 1, True)
    assert not block and not audio

  def test_fast_rear_car_blocks_and_alerts(self):
    block, audio = evaluate_rear_gate(True, 1.0, 1, True)
    assert block and audio

  def test_invalid_ttc_failsafe_blocks_and_alerts(self):
    block, audio = evaluate_rear_gate(True, 0.0, 1, True)
    assert block and audio

  def test_threshold_boundary_is_permit(self):
    block, audio = evaluate_rear_gate(True, 2.5, 1, True)
    assert not block and not audio

  def test_three_level_thresholds(self):
    assert not evaluate_rear_gate(True, 2.0, 0, True)[0]  # Aggressive 1.8s: 2.0 放行
    assert evaluate_rear_gate(True, 2.0, 1, True)[0]      # Normal 2.5s: 2.0 阻断
    assert not evaluate_rear_gate(True, 3.0, 1, True)[0]  # Normal 2.5s: 3.0 放行
    assert evaluate_rear_gate(True, 3.0, 2, True)[0]      # Safe 3.5s: 3.0 阻断
