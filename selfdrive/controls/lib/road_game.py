import time
import numpy as np

class RoadGame:
  def __init__(self):
    self.last_oncoming_time = 0.0
    self.active = False
    self.slow_target = 0.0

  def update(self, sm):
    now = time.time()

    # ===== 基本信息 =====
    v_ego = max(sm['carState'].vEgo, 0.0)
    lead = sm['modelV2'].lead
    lead_prob = sm['modelV2'].leadProb

    lane_width = sm['lateralPlan'].laneWidth
    narrow_road = sm['amapNavi'].isNarrowRoad if sm.seen['amapNavi'] else False

    # ===== 对向车判断 =====
    # 对向车：距离 < 50m，相对速度 > 0（靠近中）
    oncoming = False
    if lead_prob > 0.35 and lead is not None:
      dist = getattr(lead, 'dist', 999.0)
      rel_speed = getattr(lead, 'relSpeed', 0.0)
      if 0 < dist < 50.0 and rel_speed > 0:
        oncoming = True
        self.last_oncoming_time = now

    # ===== 会车激活条件 =====
    active = oncoming or (now - self.last_oncoming_time < 1.5)

    # ===== 目标速度计算 =====
    target_speed = v_ego
    if active:
      if narrow_road or lane_width < 3.0:
        target_speed = min(v_ego, 15.0)   # 窄路：≤15km/h
      else:
        target_speed = min(v_ego, 25.0)   # 正常路：≤25km/h

    self.active = active
    self.slow_target = target_speed

    return {
      "active": active,
      "slow_target": target_speed,
    }