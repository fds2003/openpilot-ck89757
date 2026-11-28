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


def calculate_rear_ttc(main_lb_drel, lb_vrel, main_rb_drel, rb_vrel, lidar_online):
  """后方 TTC 计算（生产单一实现，自 amap_navi.make_navi_message 抽取，P1-5/P2-1）。

  Args:
    main_lb_drel / main_rb_drel: 左/右后向目标纵向距离（mm）；None = 无目标。
    lb_vrel / rb_vrel: 对应目标相对速度（m/s）。
    lidar_online: 左右两侧后向雷达是否同时在线。

  Returns:
    有逼近目标（v < -0.1 m/s）: min(d/|v|) —— 最保守（两侧取小）。
    无逼近目标且确为净空（两侧无目标 + 雷达在线）: 99.0。
    其余（有并排目标 / 雷达离线）: 0.0 失效哨兵（fail-safe）。
  """
  ttc_list = []
  for d, v in ((main_lb_drel, lb_vrel), (main_rb_drel, rb_vrel)):
    if d is not None and abs(d) > 0 and v is not None and v < -0.1:
      ttc_list.append((abs(d) / 1000.0) / abs(v))
  no_rear_target = main_lb_drel is None and main_rb_drel is None
  clear_lane = (not ttc_list) and no_rear_target and lidar_online
  return min(ttc_list) if ttc_list else (99.0 if clear_lane else 0.0)


def evaluate_rear_gate(rear_radar: bool, behind_ttc: float, overtake_mode: int,
                       amap_alive: bool, rear_sensor_seen: bool = True) -> tuple[bool, bool]:
  """判定后方 TTC 门禁与自动变道阻断。

  Args:
    rear_radar: RearRadarEnable 参数（是否安装后向雷达）。
    behind_ttc: amapNavi.lidarBehindVdistTime；0.0 = 无效/缺失哨兵，99.0 = 净空。
    overtake_mode: OVERTAKE 档位，非法值回退标准档（2.5s）。
    amap_alive: amapNavi 消息是否在线。
    rear_sensor_seen: 后向雷达（左右两侧）是否曾上线。P0-4：
      从未上线 → 回退原车 BSD 门控（放行 + 不播报，方向防护由
      evaluate_bsm_gate 承担）；曾上线后失效 → fail-safe 阻断 + 播报。

  Returns:
    (block_auto, play_audio):
      block_auto: 是否阻断自动变道触发路径（auto_lane_change_trigger 置 False）。
      play_audio: 是否播报"后方来车/盲区有车"（event 6）。
  """
  if not rear_radar:
    # 未装后向雷达：默认不允许自动变道；数据无意义，不播报以免每 2 秒误报
    return (True, False)

  threshold = REAR_TTC_THRESHOLDS.get(overtake_mode, REAR_TTC_THRESHOLDS[1])
  # 正 TTC 且不足阈值：确有后车逼近，无论传感器历史状态都阻断并播报
  if 0.0 < behind_ttc < threshold:
    return (True, True)
  # P0-4: TTC 失效(<=0.0)或消息缺失时按传感器历史分流——
  # 从未上线：数据源本就不存在，回退 BSD 门控而非永久阻断
  if (not amap_alive) or (behind_ttc <= 0.0):
    if not rear_sensor_seen:
      return (False, False)
    # 曾上线后失效：真实传感器故障，fail-safe 阻断并播报
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
                               behind_ttc: float, overtake_mode: int,
                               rear_sensor_seen: bool = True) -> bool:
  """laneChangeStarting 阶段的后方 TTC 复检（M-15 / P0-2 / P0-4）。

  Args:
    is_driver_initiated: is_driver_initiated_change() 的判定结果。
    amap_alive: amapNavi 消息是否在线。
    behind_ttc: amapNavi.lidarBehindVdistTime；0.0 = 无效/缺失哨兵，99.0 = 净空。
    overtake_mode: OVERTAKE 档位，非法值回退标准档（2.5s）。
    rear_sensor_seen: 后向雷达是否曾上线（P0-4 回退语义，与 evaluate_rear_gate 一致）。

  Returns:
    True = 中止变道；False = 继续执行。
  """
  threshold = REAR_TTC_THRESHOLDS.get(overtake_mode, REAR_TTC_THRESHOLDS[1])
  # 确认后车急追：无论发起方与传感器历史状态都中止并告警
  if amap_alive and (0.0 < behind_ttc < threshold):
    return True
  # P0-4: 传感器从未上线 → 与触发段一致回退 BSD 门控，不因失效哨兵/消息缺失中止
  if not rear_sensor_seen:
    return False
  if is_driver_initiated:
    # 驾驶员手动打灯变道：传感器失效/离线决不阻断自主变道，回退原生 BSD 监控
    return False
  # 车机指令/自动变道（OVERTAKE/ATC/远程 cmd）+ 传感器曾上线：fail-safe ——
  # 消息缺失 / TTC 失效(<=0.0，未确认清空) 一律严密中止
  return (not amap_alive) or (behind_ttc <= 0.0)
