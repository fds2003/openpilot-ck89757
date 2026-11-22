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


# 驾驶员手动发起的变道触发类型/名称（desire_helper.py trigger 赋值处保持一致）：
# trigger_type 1="torque bsd" 2="torque ok" 3="driver"；trigger_type 3 还可能为
# trigger_name="cmd"（远程车机指令），P0-2 要求其排除在驾驶员路径之外。
DRIVER_TRIGGER_TYPES = (1, 2, 3)
DRIVER_TRIGGER_NAMES = ("driver", "torque bsd", "torque ok")


def is_driver_initiated_change(trigger_type: int, trigger_name: str) -> bool:
  """判定变道发起方是否为驾驶员手动操作。

  P0-2：trigger_type 3 同时覆盖 "driver"（打灯）与 "cmd"（远程车机指令），
  远程指令必须排除，否则走宽松 abort 条件，amapNavi 离线或 TTC=0.0 时
  反而不中止，违背 fail-safe 语义。

  Returns:
    True = 驾驶员手动变道（复检用宽松条件）；False = 车机指令/自动（fail-safe）。
  """
  if trigger_name == "cmd":
    return False
  return trigger_type in DRIVER_TRIGGER_TYPES or trigger_name in DRIVER_TRIGGER_NAMES


def evaluate_lane_change_abort(is_driver_initiated: bool, amap_alive: bool,
                               behind_ttc: float, overtake_mode: int) -> bool:
  """laneChangeStarting 阶段的后方 TTC 复检（M-15 / P0-2）。

  Args:
    is_driver_initiated: is_driver_initiated_change() 的判定结果。
    amap_alive: amapNavi 消息是否在线。
    behind_ttc: amapNavi.lidarBehindVdistTime；0.0 = 无效/缺失哨兵，99.0 = 净空。
    overtake_mode: OVERTAKE 档位，非法值回退标准档（2.5s）。

  Returns:
    True = 中止变道；False = 继续执行。
  """
  threshold = REAR_TTC_THRESHOLDS.get(overtake_mode, REAR_TTC_THRESHOLDS[1])
  if is_driver_initiated:
    # 驾驶员手动打灯变道：仅传感器在线且确认后车急追（0 < TTC < 门限）才中止；
    # 传感器失效/离线/未装雷达 决不阻断驾驶员自主变道，回退原生 BSD 监控
    return amap_alive and (0.0 < behind_ttc < threshold)
  # 车机指令/自动变道（OVERTAKE/ATC/远程 cmd）：fail-safe ——
  # 消息缺失 / TTC 失效(<=0.0，未确认清空) / TTC 不足 一律严密中止
  return (not amap_alive) or (behind_ttc <= 0.0) or (behind_ttc < threshold)
