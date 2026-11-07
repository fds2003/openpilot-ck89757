#!/usr/bin/env python3
"""
selfdrive/carrot/tests/test_s1_red_light_lock_zero.py
=====================================================================
TDD 单元测试：S1 红灯停稳锁零（carrot_functions.py e2eStopped 分支）
=====================================================================

设计意图（archive/21 §4.3）：红灯停稳后 actual_stop_distance 必须归零，
杜绝停稳态残留 5.0m 假巡航距离导致的蠕动/溜车。

历史 bug：actual_stop_distance 只在 e2ePrepare(5.0)/e2eStop(>10m) 赋值，
停稳态(e2eStopped)未清零，导致锁零失效（archive/21 审计标注「条件相反，未实现」）。

本测试镜像 e2eStopped 分支的锁零条件（stopping_count>0 且非绿灯 → 归零），
并直接 grep 源码断言修复行存在，防止回退。
"""
import os
import re
import unittest

HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, "..", "carrot_functions.py")


def simulate_e2e_stopped_lock_zero(stopping_count, traffic_state, actual_stop_distance):
  """镜像 carrot_functions.py e2eStopped 分支的 S1 锁零逻辑。

  traffic_state: 1=red 2=green 3=left 0=off（与 carrot_serv.traffic_state 一致）
  返回停稳态下处理后的 actual_stop_distance。
  """
  if stopping_count > 0 and traffic_state != 2:  # 非绿灯且已停稳持续若干帧
    actual_stop_distance = 0.0
  return actual_stop_distance


class TestS1RedLightLockZero(unittest.TestCase):

  def test_stopped_red_light_zeroes_stop_distance(self):
    """停稳 + 红灯：残留 5.0m 假巡航距离必须被清零"""
    d = simulate_e2e_stopped_lock_zero(
        stopping_count=1, traffic_state=1, actual_stop_distance=5.0)
    self.assertEqual(d, 0.0,
        "红灯停稳态 actual_stop_distance 未归零，蠕动锁零失效！")

  def test_stopped_no_light_zeroes_stop_distance(self):
    """停稳 + 无信号（off）：同样应锁零防蠕动"""
    d = simulate_e2e_stopped_lock_zero(
        stopping_count=3, traffic_state=0, actual_stop_distance=5.0)
    self.assertEqual(d, 0.0)

  def test_green_light_does_not_force_zero(self):
    """绿灯起步（stop 态尚未切到 cruise）：不强制清零，保留起步缓冲"""
    d = simulate_e2e_stopped_lock_zero(
        stopping_count=1, traffic_state=2, actual_stop_distance=5.0)
    self.assertEqual(d, 5.0, "绿灯起步不应被 S1 锁零干扰")

  def test_stopping_count_zero_no_debounce_trigger(self):
    """stopping_count==0（刚进入停稳，未持续）：防抖门控，不触发锁零"""
    d = simulate_e2e_stopped_lock_zero(
        stopping_count=0, traffic_state=1, actual_stop_distance=5.0)
    self.assertEqual(d, 5.0, "stopping_count==0 时防抖未就绪，不应锁零")

  def test_source_contains_s1_lock_zero_line(self):
    """源码 e2eStopped 分支确实含 S1 锁零行（防回退）"""
    with open(SRC, encoding="utf-8", errors="replace") as f:
      src = f.read()
    self.assertTrue(
        re.search(r"if self\.stopping_count > 0 and self\.trafficState != TrafficState\.green:\s*\n\s*self\.actual_stop_distance = 0\.0",
                  src),
        "carrot_functions.py e2eStopped 分支缺少 S1 红灯停稳锁零修复行")


if __name__ == "__main__":
  unittest.main()
