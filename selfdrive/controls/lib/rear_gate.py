"""后向雷达 TTC 门禁 + 原车 BSM 自动变道门禁（纯逻辑，无重依赖，可独立单测）。

RearRadarEnable 参数语义：
- 1 = 已安装后向雷达：启用后方 TTC 门禁（fail-safe），TTC 失效/不足时阻断自动变道并播报。
- 0 = 未安装（默认）：TTC 恒为 0.0 失效哨兵，若按 fail-safe 判冲突会每 2 秒误报
  "盲区有车"；正确行为是静默禁用自动变道（默认不允许自动变道），不播报。
  驾驶员手动打灯变道不受影响。
"""

# 变向灯状态，取值与 desire_helper.py 保持一致
BLINKER_NONE = 0
BLINKER_LEFT = 1
BLINKER_RIGHT = 2
BLINKER_BOTH = 3

# OVERTAKE 档位对应的后方 TTC 门限（秒）：0=激进 1.8 / 1=标准 2.5 / 2=保守 3.5
REAR_TTC_THRESHOLDS = {0: 1.8, 1: 2.5, 2: 3.5}


def evaluate_rear_gate(rear_radar: bool, behind_ttc: float, overtake_mode: int, amap_alive: bool) -> tuple[bool, bool]:
  """判定后方 TTC 门禁与自动变道阻断。

  Args:
    rear_radar: RearRadarEnable 参数（是否安装后向雷达）。
    behind_ttc: amapNavi.lidarBehindVdistTime；0.0 = 无效/缺失哨兵，99.0 = 净空。
    overtake_mode: OVERTAKE 档位，非法值回退标准档（2.5s）。
    amap_alive: amapNavi 消息是否在线。

  Returns:
    (block_auto, play_audio):
      block_auto: 是否阻断自动变道触发路径（auto_lane_change_trigger 置 False）。
      play_audio: 是否播报"后方来车/盲区有车"（event 6）。
  """
  if not rear_radar:
    # 未装后向雷达：默认不允许自动变道；数据无意义，不播报以免每 2 秒误报
    return (True, False)

  threshold = REAR_TTC_THRESHOLDS.get(overtake_mode, REAR_TTC_THRESHOLDS[1])
  # fail-safe：消息缺失 / TTC 失效(<=0.0) / 逼近车辆 TTC 不足 一律阻断并播报
  conflict = (not amap_alive) or (behind_ttc <= 0.0) or (behind_ttc < threshold)
  if conflict:
    return (True, True)
  return (False, False)


def evaluate_bsm_gate(bsm_left: bool, bsm_right: bool, blinker_state: int, bsm_enabled: bool = True) -> bool:
  """原车 BSM（后视镜盲区指示灯）自动变道门禁。

  利用原车角落雷达的 0/1 盲区信号，在变道方向侧有车时放弃自动变道。
  仅约束自动变道触发路径；驾驶员打灯+扭矩的手动变道由 desire_helper 既有逻辑处理。

  Args:
    bsm_left: carState.leftBlindspot（后视镜左侧盲区指示灯）。
    bsm_right: carState.rightBlindspot（后视镜右侧盲区指示灯）。
    blinker_state: 当前变道方向（BLINKER_* 常量）。
    bsm_enabled: DisableBlindSpot=1（用户禁用原车盲区信号）时传 False，永不阻断。

  Returns:
    True = 阻断自动变道；False = 放行。
  """
  if not bsm_enabled:
    return False
  if blinker_state == BLINKER_LEFT:
    return bool(bsm_left)
  if blinker_state == BLINKER_RIGHT:
    return bool(bsm_right)
  # 方向未知（NONE）或双闪（BOTH）时不阻断，避免误伤
  return False
