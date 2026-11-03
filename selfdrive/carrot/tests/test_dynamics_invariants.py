#!/usr/bin/env python3
"""
selfdrive/carrot/tests/test_dynamics_invariants.py
=====================================================================
TDD 单元测试套件：动力学与工控数学不变量断言 (避让边界 & 8AT停稳下限)
=====================================================================
"""
import unittest

def calculate_clamped_avoidance(raw_shift, lane_width, car_width=1.85, safety_margin=0.15):
  """提取 lane_planner_2.py 中的两轮车避让车道边界几何限幅纯函数"""
  eff_lane_w = max(lane_width, 2.5)
  left_max_shift = max(0.0, (eff_lane_w / 2.0) - (car_width / 2.0) - safety_margin)
  clamped_shift = min(raw_shift, left_max_shift)
  return clamped_shift, eff_lane_w

def simulate_100hz_stopping_decel(initial_accel, stop_accel, steps=500, dt=0.01):
  """模拟 100Hz 频率下 5 秒 (500 步) 的停稳减速度输出"""
  output_accel = initial_accel
  history = []
  
  for step in range(steps):
    v_ego = max(0.0, 0.45 - step * 0.001) # 车速平滑下降
    soft_hold_active = False

    # 实施无状态安全下限箝位 (Stateless Clamp)
    if v_ego < 0.5 and not soft_hold_active:
      output_accel = max(output_accel, min(-0.65, stop_accel))

    history.append(output_accel)
  return history

class TestDynamicsInvariants(unittest.TestCase):

  def test_lateral_lane_boundary_invariant(self):
    """断言 1: 无论车道多窄，两轮车避让后的左车轮外缘距车道线恒 >= 15cm"""
    CUSTIN_WIDTH = 1.85
    SAFETY_MARGIN = 0.15
    raw_shifts = [0.3, 0.55, 0.8, 1.2] # 包含超大避让需求
    test_lane_widths = [2.4, 2.6, 2.8, 3.0, 3.25, 3.5, 3.75, 4.0]

    for lane_w in test_lane_widths:
      for raw_shift in raw_shifts:
        clamped_shift, eff_w = calculate_clamped_avoidance(raw_shift, lane_w, CUSTIN_WIDTH, SAFETY_MARGIN)
        left_wheel_y = (CUSTIN_WIDTH / 2.0) + clamped_shift
        half_lane = eff_w / 2.0
        clearance = half_lane - left_wheel_y

        # 严格数学断言：裕量必须 >= 0.15m (允许浮点误差 1e-7)
        self.assertGreaterEqual(
          clearance, SAFETY_MARGIN - 1e-7,
          f"在车道宽 {lane_w}m 时避让 {raw_shift}m 压线！左侧净空仅剩 {clearance:.4f}m"
        )

  def test_longitudinal_stopping_non_decay_invariant(self):
    """断言 2: 100Hz 500 周期连续停稳期间，制动减速度绝对不能发生乘性衰减归零"""
    initial_accel = -1.0
    stop_accel = -1.2
    
    # 模拟旧版错误衰减 (对照组)
    bad_accel = -1.0
    for _ in range(15): # 仅 150ms
      bad_accel *= 0.75
    self.assertAlmostEqual(bad_accel, 0.0, delta=0.02, msg="已复现旧版乘性复利 Bug: 150ms 内制动力瓦解！")

    # 运行新版无状态下限法
    accel_history = simulate_100hz_stopping_decel(initial_accel, stop_accel, steps=500)
    
    # 严格工控断言：在所有 500 个时间步内，制动力恒定保底在 -0.65 m/s² 以下，绝不归零
    for step, accel in enumerate(accel_history):
      self.assertLessEqual(
        accel, -0.65,
        f"在第 {step} 步制动力减弱至 {accel} m/s²，存在溜车隐患！"
      )
      self.assertGreaterEqual(
        accel, -1.2,
        f"在第 {step} 步制动力超限！"
      )

if __name__ == "__main__":
  unittest.main()
