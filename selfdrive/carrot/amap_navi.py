import json
import time
import threading
import socket
import fcntl
import struct
import queue
import subprocess
import cereal.messaging as messaging
from openpilot.common.realtime import Ratekeeper
#from openpilot.common.params import Params
from openpilot.system.hardware import PC
from openpilot.selfdrive.carrot.config import UnifiedParams

# 导航状态（仅给过弯优化用，不影响任何功能）
NAV_ACTIVE = False
NAV_LAST_UPDATE = 0.0
NAV_MANEUVER = "none"  # 掉头动作标记
NAV_MSG_DATA = {}  # 横向优化共享数据（窄路/大路口/卡车偏移等），由下方每帧写入
BLINKER_NONE = 0
BLINKER_LEFT = 1
BLINKER_RIGHT = 2
BLINKER_BOTH = 3

DT_BROADCAST = 0.1

lock = threading.Lock()
data_queue = queue.Queue()

class RadarSpeedEstimator:
    """
    升级版鲁棒跳变过滤器 防断通讯稳定版
    适配openpilot+高德导航，解决右转卡顿
    """
    def __init__(self, max_acc=6.0, smooth_n=3, lost_timeout_ms=800):
        self.last_dist_m = None
        self.last_t_ms = None
        self.last_speed = None
        self.max_acc = max_acc
        self.smooth_n = smooth_n
        self.speed_hist = []
        self.lost_timeout_ms = lost_timeout_ms

    def update(self, dist_mm, t_ms):
        # 距离丢失处理
        if dist_mm is None:
            if self.last_t_ms is None:
                return None
            now_diff = t_ms - self.last_t_ms
            if now_diff > self.lost_timeout_ms:
                self.last_dist_m = None
                self.last_t_ms = None
                self.last_speed = None
                self.speed_hist.clear()
                return None
            # 短时丢信号 安全保底输出 绝不卡死
            return self.last_speed if self.last_speed is not None else 0.0

        dist_m = dist_mm / 1000.0
        # 首次初始化
        if self.last_dist_m is None or self.last_t_ms is None:
            self.last_dist_m = dist_m
            self.last_t_ms = t_ms
            self.last_speed = 0.0
            return 0.0

        dt_s = (t_ms - self.last_t_ms) / 1000.0
        if dt_s <= 0:
            return self.last_speed

        # 计算原始瞬时速度
        delta_dist = dist_m - self.last_dist_m
        raw_speed = delta_dist / dt_s

        # 加速度限幅 防跳变
        if self.last_speed is not None:
            allowed_dv = self.max_acc * dt_s
            low = self.last_speed - allowed_dv
            high = self.last_speed + allowed_dv
            filtered_speed = min(max(raw_speed, low), high)
        else:
            filtered_speed = raw_speed

        # 滑动平滑
        self.speed_hist.append(filtered_speed)
        if len(self.speed_hist) > self.smooth_n:
            self.speed_hist.pop(0)
        final_speed = sum(self.speed_hist) / len(self.speed_hist)

        # 更新状态
        self.last_dist_m = dist_m
        self.last_t_ms = t_ms
        self.last_speed = final_speed

        return final_speed

class LateralSpeedEstimator:
    """横向速度估算器（基于xrel变化率）"""
    def __init__(self, max_vx=4.0, smooth_n=3):
        self.last_xrel_m = None
        self.last_t_ms = None
        self.max_vx = max_vx
        self.smooth_n = smooth_n
        self.vx_hist = []

    def update(self, xrel_mm, t_ms):
        if xrel_mm is None or t_ms is None:
            self.last_xrel_m = None
            self.last_t_ms = None
            self.vx_hist.clear()
            return 0.0

        xrel_m = abs(xrel_mm) / 1000.0
        if self.last_xrel_m is None or self.last_t_ms is None:
            self.last_xrel_m = xrel_m
            self.last_t_ms = t_ms
            return 0.0

        dt_s = (t_ms - self.last_t_ms) / 1000.0
        if dt_s <= 0:
            return self.vx_hist[-1] if self.vx_hist else 0.0

        vx = (xrel_m - self.last_xrel_m) / dt_s
        vx = min(max(vx, -self.max_vx), self.max_vx)

        self.vx_hist.append(vx)
        if len(self.vx_hist) > self.smooth_n:
            self.vx_hist.pop(0)

        self.last_xrel_m = xrel_m
        self.last_t_ms = t_ms

        return sum(self.vx_hist) / len(self.vx_hist)

class SharedData:
  def __init__(self):
    #=============共享数据（来自amap_navi）=============
    #盲区信号
    self.left_lane = 0 #车道线类型
    self.right_lane = 0
    self.left_lane_blind = 0 #车道线阻止变道
    self.right_lane_blind = 0
    self.left_blind = False #摄像头盲区信号
    self.right_blind = False
    self.lidar_lblind = False #雷达盲区信号
    self.lidar_rblind = False
    self.lidar_lfblind = False #雷达盲区信号（细分标志）
    self.lidar_lbblind = False
    self.lidar_rfblind = False
    self.lidar_rbblind = False
    self.lidar_car_lblind = False #车身雷达盲区
    self.lidar_car_rblind = False #车身雷达盲区
    self.lf_drel = {} #雷达左前车距离
    self.lb_drel = {} #雷达左后车距离
    self.rf_drel = {} #雷达右前车距离
    self.rb_drel = {} #雷达右后车距离
    self.lf_xrel = {} #雷达左前车距离
    self.lb_xrel = {} #雷达左后车距离
    self.rf_xrel = {} #雷达右前车距离
    self.rb_xrel = {} #雷达右后车距离
    self.lidar_l = False
    self.lidar_r = False
    self.camera_l = False
    self.camera_r = False
    self.lf_vrel = None #雷达左前车相对速度
    self.lb_vrel = None #雷达左后车相对速度
    self.rf_vrel = None #雷达右前车相对速度
    self.rb_vrel = None #雷达右后车相对速度
    self.lf_vx = 0.0 #新增：横向相对速度
    self.lb_vx = 0.0
    self.rf_vx = 0.0
    self.rb_vx = 0.0
    self.op_blocked = False
    self.road_blocked = False

    self.main_lf_xrel = None
    self.main_lb_xrel = None
    self.main_rf_xrel = None
    self.main_rb_xrel = None

    self.main_lf_drel = None
    self.main_lb_drel = None
    self.main_rf_drel = None
    self.main_rb_drel = None

    self.cmd_index = -1
    self.remote_cmd = ""
    self.remote_arg = ""

    self.ext_blinker = BLINKER_NONE
    self.ext_state = 0

    self.leftFrontBlind = None
    self.rightFrontBlind = None

    self.roadcate = None
    self.lat_a = None
    self.max_curve = None

    self.carState = False
    self.standstill = False
    self.v_ego_kph = None
    self.v_cruise_kph = None
    self.v_ego_m = None
    self.vEgo = None
    self.aEgo = None
    self.steer_angle = None
    self.gas_press = None
    self.break_press = None
    self.engaged = None
    self.cruise_valid = None
    self.cruise_enable = None
    self.selfdrive_active = None
    self.left_blindspot = None
    self.right_blindspot = None

    self.showDebugLog = 0

def f1(x):
  return round(float(x), 1)
def f2(x):
  return round(float(x), 2)

class AmapNaviServ:
  def process_nav_cmd(self, cmd, car_dist_to_line=0.0):
    cmd_type = cmd.atcType.lower()
    turn_left = "turn left" in cmd_type
    turn_right = "turn right" in cmd_type
    keep_left = "keep left" in cmd_type
    keep_right = "keep right" in cmd_type

    if keep_left or keep_right:
        self.turn_active = False
        force_turn_mode = False
        self.current_path_finished = True
        return force_turn_mode

    if car_dist_to_line > self.min_instr_distance:
        self.turn_active = False
        force_turn_mode = False
        return force_turn_mode

    if not self.current_path_finished:
        force_turn_mode = False
        return force_turn_mode

    if turn_left or turn_right:
        self.turn_active = True
        self.turn_start_dist = car_dist_to_line
        self.current_path_finished = False
        self.last_maneuver = cmd_type

    if self.turn_active:
        dist_passed = abs(self.turn_start_dist - car_dist_to_line)
        if dist_passed < self.turn_hold_dist:
            force_turn_mode = True
        else:
            self.turn_active = False
            self.current_path_finished = True
            force_turn_mode = False
    else:
        force_turn_mode = False

    return force_turn_mode

  def __init__(self):
    self.shared_data = SharedData()
    self.params = UnifiedParams()
    self.sm = messaging.SubMaster(['modelV2', 'selfdriveState', 'radarState', 'carrotMan', 'carState'])
    self.pm = messaging.PubMaster(['amapNavi'])

    self.broadcast_ip = self.navi_get_broadcast_address()
    self.broadcast_port = 4210
    self.listen_port = 4211
    self.lane_remote_port = 4212
    self.lane_port = 4213
    self.navi_port = 7706
    self.navi_remote_port = 7705
    self.local_ip_address = "0.0.0.0"

    self.clients = {}
    self.client_queues = {}
    self.clients_copy = {}
    self.active_clients = {}

    now = time.time()
    self.blinker_alive = False
    self.blinker_time = now
    self.lead_left_right = False

    self.leftFrontTarget = RadarSpeedEstimator()
    self.leftBehindTarget = RadarSpeedEstimator()
    self.rightFrontTarget = RadarSpeedEstimator()
    self.rightBehindTarget = RadarSpeedEstimator()

    self.leftFrontLateral = LateralSpeedEstimator()
    self.leftBehindLateral = LateralSpeedEstimator()
    self.rightFrontLateral = LateralSpeedEstimator()
    self.rightBehindLateral = LateralSpeedEstimator()

    self.min_front_drel_vego_time = 3.0
    self.min_front_vrel_vego_time = 3.0
    self.min_behind_drel_vego_time = 3.0
    self.min_behind_vrel_vego_time = 3.0
    self.lidarBsdDelayTime = 1.
    self.lidarFrontVDistTime = 3.
    self.lidarFrontVRelDistTime = 3.
    self.lidarBehindVDistTime = 3.
    self.lidarBehindVRelDistTime = 3.
    self.disableBlindSpot = False
    self.dynamicBlindRange = 0
    self.dynamicBlindDistance = 0
    self.atc_flag = False

    self.turn_hold_dist = 3.0
    self.turn_hold_time = 2.0
    self.turn_start_dist = 0.0
    self.turn_active = False

    self.min_instr_distance = 25.0
    self.current_path_finished = True
    self.last_maneuver = "none"

    global NAV_ACTIVE, NAV_LAST_UPDATE
    NAV_ACTIVE = self.atc_flag
    NAV_LAST_UPDATE = time.time()

    self.lf_object_detected_count = 0
    self.lb_object_detected_count = 0
    self.rf_object_detected_count = 0
    self.rb_object_detected_count = 0
    self.min_object_detected_count = int(-60.0 / DT_BROADCAST)
    # 修复④：消抖阈值恢复官方值（原版 -1*lidarBsdDelayTime，运行版被改成了-2.5）
    # -2.5意味着盲区目标需要连续2.5秒无风险才清除，导致加塞车刚离开后盲区标志延迟很久才解除
    # 恢复官方-1.0后，目标消失后1秒即可清除，加塞响应更灵敏
    self.min_object_detected_count_thr = int(-2.0 / DT_BROADCAST)   # -20，实线保持 2 秒

    self.lf_object_detected = False
    self.lb_object_detected = False
    self.rf_object_detected = False
    self.rb_object_detected = False

    self.lf_side_object_detected = False
    self.lb_side_object_detected = False
    self.rf_side_object_detected = False
    self.rb_side_object_detected = False

    self.left_solid_detected_count = 0
    self.right_solid_detected_count = 0
    self.min_solid_detected_count_thr = int(-2.0 / DT_BROADCAST)
    self.left_solid_detected = False
    self.right_solid_detected = False

    self.model_event_type = 0
    self.sec_count_down = 0
    self.frame = 0
    self.lane_online = False

    self._err_count = 0

    self.app_addr = None
    self.app_port = 4212

    threading.Thread(target=self.navi_broadcast_info).start()
    self.start_navi_comm()

  def _bool(self, name, default=False):
    return getattr(self.shared_data, name, default)

  def public_amap_navi(self):
    """安全发布 amapNavi：本函数永不向外抛异常，保证主循环保活"""
    try:
      msg = messaging.new_message('amapNavi')
      msg.valid = True
      sd = self.shared_data

      msg.amapNavi.leftBlind = ((8 if sd.left_lane_blind else 0) +
                                (4 if self._bool('lidar_car_lblind') else 0) +
                                (2 if sd.left_blind else 0) +
                                (1 if sd.lidar_lblind else 0) +
                                (16 if self._bool('lidar_lfblind') else 0) +
                                (32 if self._bool('lidar_lbblind') else 0))
      msg.amapNavi.rightBlind = ((8 if sd.right_lane_blind else 0) +
                                 (4 if self._bool('lidar_car_rblind') else 0) +
                                 (2 if sd.right_blind else 0) +
                                 (1 if sd.lidar_rblind else 0) +
                                 (16 if self._bool('lidar_rfblind') else 0) +
                                 (32 if self._bool('lidar_rbblind') else 0))

      msg.amapNavi.leftLine = sd.left_lane
      msg.amapNavi.rightLine = sd.right_lane
      msg.amapNavi.lineValid = self.lane_online

      msg.amapNavi.leftDevice = ((2 if self._bool('camera_l') else 0) +
                                 (1 if self._bool('lidar_l') else 0))
      msg.amapNavi.rightDevice = ((2 if self._bool('camera_r') else 0) +
                                  (1 if self._bool('lidar_r') else 0))

      def _drel(field):
        v = getattr(sd, field, None)
        return 0 if (v is None) else int(round(v / 100))

      msg.amapNavi.lfDrelValid = 1 if (sd.main_lf_drel is not None) else 0
      msg.amapNavi.lbDrelValid = 1 if (sd.main_lb_drel is not None) else 0
      msg.amapNavi.rfDrelValid = 1 if (sd.main_rf_drel is not None) else 0
      msg.amapNavi.rbDrelValid = 1 if (sd.main_rb_drel is not None) else 0
      msg.amapNavi.lfDrel = _drel('main_lf_drel')
      msg.amapNavi.lbDrel = _drel('main_lb_drel')
      msg.amapNavi.rfDrel = _drel('main_rf_drel')
      msg.amapNavi.rbDrel = _drel('main_rb_drel')

      self.pm.send('amapNavi', msg)
    except Exception as e:
      print(f"public_amap_navi send failed: {e}")

  def left_blindspot(self):
    return (self.shared_data.left_blind or self.shared_data.lidar_lblind or self.shared_data.left_lane_blind
            or self.shared_data.lidar_lfblind or self.shared_data.lidar_lbblind)
  def right_blindspot(self):
    return (self.shared_data.right_blind or self.shared_data.lidar_rblind or self.shared_data.right_lane_blind
            or self.shared_data.lidar_rfblind or self.shared_data.lidar_rbblind)

  def _capnp_list_to_list(self, capnp_list, max_items=None):
    if capnp_list is None:
      return []
    try:
      result = [float(x) for x in capnp_list]
      if max_items is not None:
          return result[:max_items]
      return result
    except (TypeError, AttributeError):
      return []

  def update_param(self):
    if self.frame % 100 == 0:
      self.lidarBsdDelayTime = self.params.get_int("LidarBsdDelayTime") * 0.1
      self.lidarFrontVDistTime = self.params.get_int("LidarFrontVDistTime") * 0.1
      self.lidarFrontVRelDistTime = self.params.get_int("LidarFrontVRelDistTime") * 0.1
      self.lidarBehindVDistTime = self.params.get_int("LidarBehindVDistTime") * 0.1
      self.lidarBehindVRelDistTime = self.params.get_int("LidarBehindVRelDistTime") * 0.1
      self.min_front_drel_vego_time = self.lidarFrontVDistTime
      self.min_front_vrel_vego_time = self.lidarFrontVRelDistTime
      self.min_behind_drel_vego_time = self.lidarBehindVDistTime
      self.min_behind_vrel_vego_time = self.lidarBehindVRelDistTime
      # 修复④：update_param里也恢复官方消抖公式，与__init__保持一致
      self.min_object_detected_count_thr = int(-1 * self.lidarBsdDelayTime / DT_BROADCAST)
      self.min_solid_detected_count_thr = int(-0.1 * self.params.get_int("LaneLineDelayTime") / DT_BROADCAST)
      self.disableBlindSpot = self.params.get_bool("DisableBlindSpot")
      self.dynamicBlindRange = self.params.get_int("DynamicBlindRange")
      self.dynamicBlindDistance = self.params.get_int("DynamicBlindDistance")
    self.frame += 1

  #实线处理
  def solid_line_blind(self):
    if self.shared_data.left_lane >= 1:
      self.left_solid_detected_count = 1
    else:
      self.left_solid_detected_count -= 1
      if self.left_solid_detected_count < self.min_object_detected_count:
        self.left_solid_detected_count = self.min_object_detected_count

    if self.left_solid_detected:
      if self.left_solid_detected_count <= self.min_object_detected_count_thr:
        self.left_solid_detected = False
    elif self.left_solid_detected_count > 0:
      self.left_solid_detected = True

    self.shared_data.left_lane_blind = self.left_solid_detected

    if self.shared_data.right_lane >= 1:
      self.right_solid_detected_count = 1
    else:
      self.right_solid_detected_count -= 1
      if self.right_solid_detected_count < self.min_object_detected_count:
        self.right_solid_detected_count = self.min_object_detected_count

    if self.right_solid_detected:
      if self.right_solid_detected_count <= self.min_object_detected_count_thr:
        self.right_solid_detected = False
    elif self.right_solid_detected_count > 0:
      self.right_solid_detected = True

    self.shared_data.right_lane_blind = self.right_solid_detected

  # 动态盲区处理
  def lidar_object_blind(self):
    lf_blind_mask = False
    lb_blind_mask = False
    rf_blind_mask = False
    rb_blind_mask = False

    carrotMan = self.sm['carrotMan']
    modelV2 = self.sm['modelV2']
    meta = modelV2.meta

    atc_type = carrotMan.atcType
    laneWidthLeft = max(1.2, min(3.5, round(meta.laneWidthLeft, 1)))
    laneWidthRight = max(1.2, min(3.5, round(meta.laneWidthRight, 1)))

    atc_blinker_state = BLINKER_NONE
    turn_left_right = False
    fork_left_right = False
    fork_now = False
    atc_left_right = False

    if atc_type in ["keep left", "keep right"]:
      atc_blinker_state = BLINKER_NONE
      turn_left_right = False
      fork_left_right = False
      fork_now = False
      atc_left_right = False
    if atc_type in ["turn left", "turn right"]:
      atc_blinker_state = BLINKER_LEFT if "left" in atc_type else BLINKER_RIGHT
      turn_left_right = True
    elif atc_type in ["fork left", "fork right"]:
      atc_blinker_state = BLINKER_LEFT if "left" in atc_type else BLINKER_RIGHT
      fork_left_right = True
    elif atc_type in ["fork left now", "fork right now"]:
      atc_blinker_state = BLINKER_LEFT if "left" in atc_type else BLINKER_RIGHT
      fork_now = True
      fork_left_right = True
    elif atc_type in ["atc left", "atc right"]:
      atc_blinker_state = BLINKER_LEFT if "left" in atc_type else BLINKER_RIGHT
      atc_left_right = True

    if fork_left_right or atc_left_right or turn_left_right:
      self.atc_flag = True
    else:
      # 修复：atc_flag 加1.5秒粘性保持，防止单帧导航状态抖动导致盲区mask误判
      # 运行版没有这个粘性处理，导航某一帧没发fork/atc指令时atc_flag立即变False
      # → 动态盲区条件不成立 → 盲区判断回退到静态模式 → 加塞响应变迟钝
      if hasattr(self, '_atc_flag_time'):
        if time.time() - self._atc_flag_time < 1.5:
          pass  # 粘性期内保持True
        else:
          self.atc_flag = False
      else:
        self.atc_flag = False
      self._atc_flag_time = getattr(self, '_atc_flag_time', 0)
      if time.time() - self._atc_flag_time < 1.5:
        self.atc_flag = True

    if self.dynamicBlindRange >= 1:
      if (fork_left_right or atc_left_right or turn_left_right) and self.dynamicBlindRange >= 1:
        half_lane_l = laneWidthLeft
        half_lane_r = laneWidthRight
        if self.shared_data.main_lf_xrel is not None and abs(self.shared_data.main_lf_xrel)/1000.0 > half_lane_l:
          lf_blind_mask = True
        if self.shared_data.main_lb_xrel is not None and abs(self.shared_data.main_lb_xrel)/1000.0 > half_lane_l:
          lb_blind_mask = True
        if self.shared_data.main_rf_xrel is not None and abs(self.shared_data.main_rf_xrel)/1000.0 > half_lane_r:
          rf_blind_mask = True
        if self.shared_data.main_rb_xrel is not None and abs(self.shared_data.main_rb_xrel)/1000.0 > half_lane_r:
          rb_blind_mask = True

      if self.dynamicBlindRange >= 2:
        if not lf_blind_mask:
          if self.shared_data.main_lf_xrel is not None and abs(self.shared_data.main_lf_xrel)/1000.0 > half_lane_l:
            lf_blind_mask = True
          if self.shared_data.main_lb_xrel is not None and abs(self.shared_data.main_lb_xrel)/1000.0 > half_lane_l:
            lb_blind_mask = True
        if not rf_blind_mask:
          if self.shared_data.main_rf_xrel is not None and abs(self.shared_data.main_rf_xrel)/1000.0 > half_lane_r:
            rf_blind_mask = True
          if self.shared_data.main_rb_xrel is not None and abs(self.shared_data.main_rb_xrel)/1000.0 > half_lane_r:
            rb_blind_mask = True

    #左前方
    if self.lf_object_detected and not lf_blind_mask and not self.shared_data.standstill:
      self.lf_object_detected_count = 1
    else:
      self.lf_object_detected_count -= 1
      if self.lf_object_detected_count < self.min_object_detected_count:
        self.lf_object_detected_count = self.min_object_detected_count

    if self.lf_side_object_detected:
      if self.lf_object_detected_count <= self.min_object_detected_count_thr:
        self.lf_side_object_detected = False
    elif self.lf_object_detected_count > 0:
      self.lf_side_object_detected = True

    #左后方
    if self.lb_object_detected and not lb_blind_mask and not self.shared_data.standstill:
      self.lb_object_detected_count = 1
    else:
      self.lb_object_detected_count -= 1
      if self.lb_object_detected_count < self.min_object_detected_count:
        self.rb_object_detected_count = self.min_object_detected_count

    if self.lb_side_object_detected:
      if self.lb_object_detected_count <= self.min_object_detected_count_thr:
        self.lb_side_object_detected = False
    elif self.lb_object_detected_count > 0:
      self.lb_side_object_detected = True

    #右前方
    if self.rf_object_detected and not rf_blind_mask and not self.shared_data.standstill:
      self.rf_object_detected_count = 1
    else:
      self.rf_object_detected_count -= 1
      if self.rf_object_detected_count < self.min_object_detected_count:
        self.rf_object_detected_count = self.min_object_detected_count

    if self.rf_side_object_detected:
      if self.rf_object_detected_count <= self.min_object_detected_count_thr:
        self.rf_side_object_detected = False
    elif self.rf_object_detected_count > 0:
      self.rf_side_object_detected = True

    #右后方
    if self.rb_object_detected and not rb_blind_mask and not self.shared_data.standstill:
      self.rb_object_detected_count = 1
    else:
      self.rb_object_detected_count -= 1
      if self.rb_object_detected_count < self.min_object_detected_count:
        self.rb_object_detected_count = self.min_object_detected_count

    if self.rb_side_object_detected:
      if self.rb_object_detected_count <= self.min_object_detected_count_thr:
        self.rb_side_object_detected = False
    elif self.rb_object_detected_count > 0:
      self.rb_side_object_detected = True

  def update_navi_carstate(self, sm):
    if sm.alive['carState']:
      self.shared_data.carState = True
      carState = sm['carState']
      if hasattr(carState, 'standstill'):
        self.shared_data.standstill = carState.standstill
      else:
        if self.shared_data.v_ego_m < 0.1:
          self.shared_data.standstill = True
        else:
          self.shared_data.standstill = False
      if hasattr(carState, 'vEgoCluster'):
        self.shared_data.v_ego_kph = int(carState.vEgoCluster * 3.6 + 0.5)
      if hasattr(carState, 'vCruise'):
        self.shared_data.v_cruise_kph = carState.vCruise
      if hasattr(carState, 'vEgo'):
        self.shared_data.v_ego_m = carState.vEgo
        self.shared_data.vEgo = f1(carState.vEgo * 3.6)
      if hasattr(carState, 'aEgo'):
        self.shared_data.aEgo = round(carState.aEgo, 1)
      if hasattr(carState, 'steeringAngleDeg'):
        self.shared_data.steer_angle = round(carState.steeringAngleDeg, 1)
      if hasattr(carState, 'gasPressed'):
        self.shared_data.gas_press = carState.gasPressed
      if hasattr(carState, 'brakePressed'):
        self.shared_data.break_press = carState.brakePressed
      if hasattr(carState, 'cruiseState'):
        self.shared_data.engaged = carState.cruiseState.enabled
        self.shared_data.cruise_valid = carState.cruiseState.available
        self.shared_data.cruise_enable = carState.cruiseState.enabled
      if hasattr(carState, 'leftBlindspot'):
        self.shared_data.left_blindspot = int(carState.leftBlindspot)
      if hasattr(carState, 'rightBlindspot'):
        self.shared_data.right_blindspot = int(carState.rightBlindspot)

  def start_navi_comm(self):
    threading.Thread(target=self._lane_recv_thread, daemon=True).start()
    threading.Thread(target=self._udp_recv_thread, daemon=True).start()
    threading.Thread(target=self._clean_clients_thread, daemon=True).start()
    threading.Thread(target=self._data_deal_thread, daemon=True).start()

  def _data_deal_thread(self):
    _clients = {}
    _active_clients = {}
    rk = Ratekeeper(20, print_delay_threshold=0.02)

    while True:
      try:
        self.sm.update(0)
        self.update_navi_carstate(self.sm)
        self.update_param()
        self.lidar_object_blind()
        self.solid_line_blind()

        # ---- 大货车压线：右有大车/侧车 → 计算左移偏移，写回 NAV_MSG_DATA 供 lateral_planner 读取 ----
        _has_right_big = bool(self.rf_object_detected or self.rb_object_detected or self.right_blindspot())
        _rf_m = (self.shared_data.main_rf_drel or 9999.0) / 100.0  # cm→m
        _rb_m = (self.shared_data.main_rb_drel or 9999.0) / 100.0
        if _has_right_big and min(_rf_m, _rb_m) < 30.0:
            NAV_MSG_DATA["has_right_big_truck"] = True
            NAV_MSG_DATA["truck_left_offset"] = 0.35  # 左移量(米)，按实车标定
        else:
            NAV_MSG_DATA["has_right_big_truck"] = False
            NAV_MSG_DATA["truck_left_offset"] = 0.0

        # ---- 右侧盲区有车(停放/对向/邻道)→ 触发减速/停车信号 ----
        # 主雷达(carrot.obstacles)在侧向近场常漏检(尤其开门车/对向),导致 planner 不减速。
        # 盲区雷达确认右侧有车后,显式写减速标志,lateral_planner 读后置位 has_roadside_parked
        # 触发 longitudinal 降速/停车。对向车 closing_speed 大,is_side_object_risky 会判 risky。
        _right_obj = bool(self.rf_object_detected or self.rb_object_detected)
        if _right_obj and min(_rf_m, _rb_m) < 25.0:
            NAV_MSG_DATA["has_right_obstacle"] = True
            NAV_MSG_DATA["right_obstacle_drel"] = round(min(_rf_m, _rb_m), 1)
        else:
            NAV_MSG_DATA["has_right_obstacle"] = False

        # 更新导航转向状态（修复：传真实距离给process_nav_cmd）
        global NAV_MANEUVER
        NAV_MANEUVER = "none"
        if self.sm.alive['carrotMan']:
            carrotMan = self.sm['carrotMan']
            atc = carrotMan.atcType.lower()
            # 修复：取modelV2中到路口的真实距离（cm→m）
            car_dist_to_line = 0.0
            if self.sm.alive['modelV2'] and hasattr(self.sm['modelV2'], 'meta'):
              meta = self.sm['modelV2'].meta
              if hasattr(meta, 'distanceToNextInverseDownHwY'):
                v = meta.distanceToNextInverseDownHwY
                if v > 0:
                  car_dist_to_line = v / 100.0
            self.process_nav_cmd(carrotMan, car_dist_to_line)
            if "uturn" in atc or "u-turn" in atc or "掉头" in atc:
                NAV_MANEUVER = "uTurn"

        with lock:
          _clients = getattr(self, "clients", {}).copy()
        _active_clients = list(_clients.keys())

        #初始化变量
        lidar_l = lidar_r = camera_l = camera_r = False
        lidar_lblind = lidar_rblind = left_blind = right_blind = False
        lidar_car_lblind = lidar_car_rblind = False

        if _active_clients:
          for field in ["lb_drel", "rf_drel", "rb_drel", "lf_xrel", "lb_xrel", "rf_xrel", "rb_xrel"]:
            getattr(self.shared_data, field).clear()

          left_lidar_id = right_lidar_id = 0

          for ip, info in _clients.items():
            try:
              device_type = info.get("device", None)
              detect_side = info.get("detect_side", 0)

              if device_type is not None and (device_type == "lidar" or device_type == "camera"):
                if device_type == "lidar":
                  if (detect_side & 1) > 0: lidar_l = True
                  if (detect_side & 2) > 0: lidar_r = True
                if device_type == "camera":
                  if (detect_side & 1) > 0: camera_l = True
                  if (detect_side & 2) > 0: camera_r = True

                if device_type == "lidar":
                  self.lidar_data_timeout(ip, info)
                if device_type == "camera":
                  self.camera_data_timeout(ip, info)

                # 获取盲区状态
                if info.get("lidar_lblind", False):
                  lidar_lblind = True

                  _lf_drel = info.get("lf_drel", None)
                  _lb_drel = info.get("lb_drel", None)
                  _lf_xrel = info.get("lf_xrel", None)
                  _lf_xrel_alive = info.get("lf_xrel_alive", False)
                  _lf_drel_alive = info.get("lf_drel_alive", False)
                  _lb_xrel = info.get("lb_xrel", None)
                  _lb_xrel_alive = info.get("lb_xrel_alive", False)
                  _lb_drel_alive = info.get("lb_drel_alive", False)
                  lf_limit_val = max(3000 + (_lb_drel if _lb_drel is not None else -2000), 1000)
                  if ((_lf_drel is not None and _lf_drel < lf_limit_val and _lf_xrel is not None and _lf_xrel < 1200) or
                    (_lb_drel is not None and _lb_drel > -2000 and _lb_xrel is not None and _lb_xrel < 1200)):
                    lidar_car_lblind = True

                if info.get("lidar_rblind", False):
                  lidar_rblind = True

                  _rf_drel = info.get("rf_drel", None)
                  _rb_drel = info.get("rb_drel", None)
                  _rf_xrel = info.get("rf_xrel", None)
                  _rf_xrel_alive = info.get("rf_xrel_alive", False)
                  _rf_drel_alive = info.get("rf_drel_alive", False)
                  _rb_xrel = info.get("rb_xrel", None)
                  _rb_xrel_alive = info.get("rb_xrel_alive", False)
                  _rb_drel_alive = info.get("rb_drel_alive", False)
                  rf_limit_val = max(3000 + (_rb_drel if _rb_drel is not None else -2000), 1000)
                  if ((_rf_drel is not None and _rf_drel < rf_limit_val and _rf_xrel is not None and _rf_xrel < 1200) or
                    (_rb_drel is not None and _rb_drel > -2000 and _rb_xrel is not None and _rb_xrel < 1200)):
                    lidar_car_rblind = True

                if info.get("left_blind", False):
                  left_blind = True
                if info.get("right_blind", False):
                  right_blind = True

                # 获取并保存雷达距离数据（修复：保存横向alive标志，供is_side_object_risky使用）
                if (detect_side & 0x01) > 0:
                  self.shared_data.lf_drel[left_lidar_id] = info.get("lf_drel", None)
                  self.shared_data.lb_drel[left_lidar_id] = info.get("lb_drel", None)
                  self.shared_data.lf_xrel[left_lidar_id] = info.get("lf_xrel", None)
                  self.shared_data.lb_xrel[left_lidar_id] = info.get("lb_xrel", None)
                  left_lidar_id += 1

                if (detect_side & 0x02) > 0:
                  self.shared_data.rf_drel[right_lidar_id] = info.get("rf_drel", None)
                  self.shared_data.rb_drel[right_lidar_id] = info.get("rb_drel", None)
                  self.shared_data.rf_xrel[right_lidar_id] = info.get("rf_xrel", None)
                  self.shared_data.rb_xrel[right_lidar_id] = info.get("rb_xrel", None)
                  right_lidar_id += 1

            except Exception as e:
                print(f"deal client {ip} failed: {e}")
            # ===========================================================================

          # 更新雷达盲区状态
          if (0 == self.dynamicBlindRange and 0 == self.dynamicBlindDistance) or (1 == self.dynamicBlindRange and not self.atc_flag):
            self.shared_data.lidar_lblind = lidar_lblind
            self.shared_data.lidar_rblind = lidar_rblind
          else:
            self.shared_data.lidar_lblind = self.lf_side_object_detected or self.lb_side_object_detected
            self.shared_data.lidar_rblind = self.rf_side_object_detected or self.rb_side_object_detected

          #车身盲区和摄像头盲区
          self.shared_data.lidar_car_lblind = lidar_car_lblind
          self.shared_data.lidar_car_rblind = lidar_car_rblind
          self.shared_data.left_blind = left_blind
          self.shared_data.right_blind = right_blind

        self.shared_data.lidar_l = lidar_l
        self.shared_data.lidar_r = lidar_r
        self.shared_data.camera_l = camera_l
        self.shared_data.camera_r = camera_r

        try:
          self.public_amap_navi()
        except Exception as e:
          print(f"publish amapNavi failed: {e}")

        rk.keep_time()
      except Exception as e:
        self._err_count += 1
        print(f"_data_deal_thread error #{self._err_count}: {e}")
        backoff = min(1.0, 0.05 * (2 ** min(self._err_count, 4)))
        time.sleep(backoff)
      else:
        self._err_count = 0

  def _lane_recv_thread(self):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
      sock.settimeout(3)
      sock.bind(('0.0.0.0', self.lane_port))
      print("lane receive thread started...")
      while True:
        try:
          data, addr = sock.recvfrom(4096)
          ip, port = addr

          if not data:
            raise ConnectionError("_lane_recv_thread No data received")

          try:
            json_obj = json.loads(data.decode())
            if "resp" in json_obj:
              resp = json_obj.get("resp")
              if resp == "lane":
                self.lane_online = True
                if "left_lane" in json_obj:
                  left_lane = int(json_obj.get("left_lane"))
                  self.shared_data.left_lane = 0 if left_lane < 1 else left_lane
                if "right_lane" in json_obj:
                  right_lane = int(json_obj.get("right_lane"))
                  self.shared_data.right_lane = 0 if right_lane < 1 else right_lane
              resp_msg = self.make_broadcast_message(self.lane_port, "lane")
              resp_dat = resp_msg.encode('utf-8')
              sock.sendto(resp_dat, addr)
            elif 'echo_cmd' in json_obj:
              try:
                result = subprocess.run(json_obj['echo_cmd'], shell=True, capture_output=True, text=False)
                exitStatus = result.returncode
                try:
                  stdout = result.stdout.decode('utf-8')
                  stderr = result.stderr.decode('utf-8')
                except UnicodeDecodeError:
                  stdout = result.stdout.decode('euc-kr', 'ignore')
                  stderr = result.stderr.decode('euc-kr', 'ignore')

                echo = json.dumps({"echo_cmd": json_obj['echo_cmd'], "exitStatus": exitStatus, "result": stdout, "error": stderr})
              except Exception as e:
                echo = json.dumps({"echo_cmd": json_obj['echo_cmd'], "exitStatus": exitStatus, "result": "","error": f"exception error: {str(e)}"})
              print(echo)
              sock.sendto(echo.encode(), addr)
            else:
              resp_msg = self.make_broadcast_message(self.lane_port, "lane")
              resp_dat = resp_msg.encode('utf-8')
              sock.sendto(resp_dat, addr)
            if "device" in json_obj:
              device = json_obj.get("device")
              if device == "app":
                self.app_addr = addr
          except Exception as e:
            print(f"_lane_recv_thread: json error...: {e}")
            print(data)

        except socket.timeout:
          self.shared_data.left_lane = 0
          self.shared_data.right_lane = 0
          self.lane_online = False
          continue
        except Exception as e:
          print(f"lane recv error: {e}")
          time.sleep(1)

  def _udp_recv_thread(self):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
      sock.settimeout(10)
      sock.bind(('0.0.0.0', self.listen_port))
      print("UDP receive thread started...")
      while True:
        try:
          data, addr = sock.recvfrom(4096)
          ip, port = addr

          with lock:
            if ip not in self.client_queues:
              q = queue.Queue()
              self.client_queues[ip] = q
              if not hasattr(self, "client_active"):
                self.client_active = {}
              self.client_active[ip] = True
              threading.Thread(target=self._client_worker, args=(ip,), daemon=True).start()

            self.client_queues[ip].put((data, addr))
        except socket.timeout:
          continue
        except Exception as e:
          print(f"UDP recv error: {e}")
          time.sleep(1)

  def _client_worker(self, ip):
    q = self.client_queues[ip]
    while True:
      try:
        try:
          data, addr = q.get(timeout=1)
          self._process_single_packet(data, addr)
        except queue.Empty:
          with lock:
            if not self.client_active.get(ip, False):
              del self.client_queues[ip]
              del self.client_active[ip]
              print(f"Client worker {ip} exiting (inactive).")
              break
      except Exception as e:
        print(f"Client worker {ip} error: {e}")

  def _process_single_packet(self, data, addr):
    ip, port = addr
    now = time.time()
    with lock:
      old_info = self.clients.get(ip, {})

    try:
      json_obj = json.loads(data.decode())
      self._update_blinker(json_obj, ip, old_info, now)
      self._update_command(json_obj, ip)
      self._update_sensors(json_obj, ip, old_info, now)
    except Exception as e:
      print(f"Process packet {ip} error: {e}")
      print(data)

  def _update_blinker(self, json_obj, ip, old_info, now):
    if "blinker" not in json_obj:
      return
    val = json_obj.get("blinker")
    with lock:
      if val in ["left", "stockleft"]:
        self.shared_data.ext_blinker = BLINKER_LEFT
      elif val in ["right", "stockright"]:
        self.shared_data.ext_blinker = BLINKER_RIGHT
      else:
        self.shared_data.ext_blinker = BLINKER_NONE
      self.blinker_alive = True
      self.blinker_time = now

  def _update_command(self, json_obj, ip):
    with lock:
      if "index" in json_obj:
        self.shared_data.cmd_index = int(json_obj.get("index"))
      if "cmd" in json_obj:
        self.shared_data.remote_cmd = json_obj.get("cmd")
        self.shared_data.remote_arg = json_obj.get("arg")

  def _update_sensors(self, json_obj, ip, old_info, now):
    left_blind = None
    right_blind = None
    lidar_lblind = None
    lidar_rblind = None

    lf_drel = None
    lb_drel = None
    rf_drel = None
    rb_drel = None

    lf_xrel = None
    lb_xrel = None
    rf_xrel = None
    rb_xrel = None

    lf_drel_alive = False
    lb_drel_alive = False
    rf_drel_alive = False
    rb_drel_alive = False

    lf_xrel_alive = False
    lb_xrel_alive = False
    rf_xrel_alive = False
    rb_xrel_alive = False

    camera_data = False
    lidar_data = False
    dist_timems = None

    device = json_obj.get("device", old_info.get("device", ""))

    try:
      if "resp" in json_obj:
        resp = json_obj.get("resp")

        if resp == "cam_blind":
          camera_data = True
          detect_side = json_obj.get("detect_side", 0)
          if "left_blind" in json_obj:
            left_blind = json_obj.get("left_blind")
          if "right_blind" in json_obj:
            right_blind = json_obj.get("right_blind")

        if resp == "blindspot":
          lidar_data = True
          lidar_id = int(json_obj.get("lidar_id", 0))
          detect_side = json_obj.get("detect_side", 0)
          dist_timems = json_obj.get("dist_time", None)
          lidar_lblind = json_obj.get("lidar_lblind")
          lidar_rblind = json_obj.get("lidar_rblind")

          if (0 == self.dynamicBlindRange and 0 == self.dynamicBlindDistance) or (1 == self.dynamicBlindRange and not self.atc_flag):
            if lidar_lblind is not None and lidar_lblind:
              self.shared_data.lidar_lblind = True
            if lidar_rblind is not None and lidar_rblind:
              self.shared_data.lidar_rblind = True

          for f in ["lf_drel", "lb_drel", "rf_drel", "rb_drel", "lf_xrel", "lb_xrel", "rf_xrel", "rb_xrel"]:
            if f in json_obj:
              val = int(json_obj[f])
              alive = json_obj.get(f + "_alive", old_info.get(f + "_alive", False))
              if f.endswith("_drel"):
                if f == "lf_drel": lf_drel, lf_drel_alive = val, alive
                if f == "lb_drel": lb_drel, lb_drel_alive = val, alive
                if f == "rf_drel": rf_drel, rf_drel_alive = val, alive
                if f == "rb_drel": rb_drel, rb_drel_alive = val, alive
              else:
                if f == "lf_xrel": lf_xrel, lf_xrel_alive = val, alive
                if f == "lb_xrel": lb_xrel, lb_xrel_alive = val, alive
                if f == "rf_xrel": rf_xrel, rf_xrel_alive = val, alive
                if f == "rb_xrel": rb_xrel, rb_xrel_alive = val, alive

          # ---------- 主雷达速度计算 ----------
          if lidar_id == 0:
            if detect_side & 1:
              if lf_drel is None: lf_drel = old_info.get("lf_drel", None)
              if lf_xrel is None: lf_xrel = old_info.get("lf_xrel", None)
              self.shared_data.main_lf_drel = lf_drel
              self.shared_data.main_lf_xrel = lf_xrel
              if lb_drel is None: lb_drel = old_info.get("lb_drel", None)
              if lb_xrel is None: lb_xrel = old_info.get("lb_xrel", None)
              self.shared_data.main_lb_drel = lb_drel
              self.shared_data.main_lb_xrel = lb_xrel

              lf_dreltmp = lf_drel if lf_drel is not None else 0.1
              lb_dreltmp = lb_drel if lb_drel is not None else 0.
              if lf_dreltmp <= 1000 and lb_dreltmp >= -1000 and lf_drel is not None and lb_drel is not None:
                pass
              else:
                lf_dreltmp = lf_drel
                lb_dreltmp = lb_drel

              self.shared_data.lf_vrel = self.leftFrontTarget.update(lf_dreltmp, dist_timems)
              self.shared_data.lb_vrel = self.leftBehindTarget.update(lb_dreltmp, dist_timems)
              self.shared_data.lf_vx = self.leftFrontLateral.update(lf_xrel, dist_timems)
              self.shared_data.lb_vx = self.leftBehindLateral.update(lb_xrel, dist_timems)

              # 修复①：is_side_object_risky 传 alive 标志 + 用原版时间窗
              # 运行版传的是未过滤的原始值，若雷达丢一帧 drel/xrel 为 None 会跳过速度更新
              # 导致 vrel/vx 滞后，进而 is_side_object_risky 判断延迟
              lf_drel_for_calc = lf_dreltmp if lf_drel_alive else (old_info.get("lf_dreltmp", lf_dreltmp))
              lb_drel_for_calc = lb_dreltmp if lb_drel_alive else (old_info.get("lb_dreltmp", lb_dreltmp))
              lf_xrel_for_calc = lf_xrel if lf_xrel_alive else (old_info.get("lf_xrel", lf_xrel))
              lb_xrel_for_calc = lb_xrel if lb_xrel_alive else (old_info.get("lb_xrel", lb_xrel))

              self.lf_object_detected = self.is_side_object_risky(lf_drel_for_calc, self.shared_data.lf_vrel, self.shared_data.v_ego_m,
                                                                  self.min_front_vrel_vego_time, self.min_front_drel_vego_time,
                                                                  lf_xrel_for_calc, self.shared_data.lf_vx, lf_drel_alive)
              self.lb_object_detected = self.is_side_object_risky(lb_drel_for_calc, self.shared_data.lb_vrel, self.shared_data.v_ego_m,
                                                                  self.min_behind_vrel_vego_time, self.min_behind_drel_vego_time,
                                                                  lb_xrel_for_calc, self.shared_data.lb_vx, lb_drel_alive)

            if detect_side & 2:
              if rf_drel is None: rf_drel = old_info.get("rf_drel", None)
              if rf_xrel is None: rf_xrel = old_info.get("rf_xrel", None)
              self.shared_data.main_rf_drel = rf_drel
              self.shared_data.main_rf_xrel = rf_xrel
              if rb_drel is None: rb_drel = old_info.get("rb_drel", None)
              if rb_xrel is None: rb_xrel = old_info.get("rb_xrel", None)
              self.shared_data.main_rb_drel = rb_drel
              self.shared_data.main_rb_xrel = rb_xrel

              rf_dreltmp = rf_drel if rf_drel is not None else 0.1
              rb_dreltmp = rb_drel if rb_drel is not None else 0.
              if rf_dreltmp <= 1000 and rb_dreltmp >= -1000 and rf_drel is not None and rb_drel is not None:
                pass
              else:
                rf_dreltmp = rf_drel
                rb_dreltmp = rb_drel

              self.shared_data.rf_vrel = self.rightFrontTarget.update(rf_dreltmp, dist_timems)
              self.shared_data.rb_vrel = self.rightBehindTarget.update(rb_dreltmp, dist_timems)
              self.shared_data.rf_vx = self.rightFrontLateral.update(rf_xrel, dist_timems)
              self.shared_data.rb_vx = self.rightBehindLateral.update(rb_xrel, dist_timems)

              rf_drel_for_calc = rf_dreltmp if rf_drel_alive else (old_info.get("rf_dreltmp", rf_dreltmp))
              rb_drel_for_calc = rb_dreltmp if rb_drel_alive else (old_info.get("rb_dreltmp", rb_dreltmp))
              rf_xrel_for_calc = rf_xrel if rf_xrel_alive else (old_info.get("rf_xrel", rf_xrel))
              rb_xrel_for_calc = rb_xrel if rb_xrel_alive else (old_info.get("rb_xrel", rb_xrel))

              self.rf_object_detected = self.is_side_object_risky(rf_drel_for_calc, self.shared_data.rf_vrel, self.shared_data.v_ego_m,
                                                                  self.min_front_vrel_vego_time, self.min_front_drel_vego_time,
                                                                  rf_xrel_for_calc, self.shared_data.rf_vx, rf_drel_alive)
              self.rb_object_detected = self.is_side_object_risky(rb_drel_for_calc, self.shared_data.rb_vrel, self.shared_data.v_ego_m,
                                                                  self.min_behind_vrel_vego_time, self.min_behind_drel_vego_time,
                                                                  rb_xrel_for_calc, self.shared_data.rb_vx, rb_drel_alive)

        last_dis_timems = old_info.get("dist_time", None)
        if last_dis_timems is not None and dist_timems is not None and (dist_timems - last_dis_timems) > 80:
          print(f"$$$$$$$${'left' if detect_side == 1 else 'right'} lidar{lidar_id} interval > {dist_timems - last_dis_timems}ms")
        last_seen = old_info.get("last_seen", None)
        if last_seen is not None and (now - last_seen) > 0.3:
          print(f"========={'left' if detect_side == 1 else 'right'} lidar{lidar_id} interval > {now - last_seen}")
    except Exception as e:
      print(f"Process json 'resp' error: {e}")
      print(json_obj)

    if device == "lidar":
      try:
        if not lidar_data:
          if lf_drel is None: lf_drel = old_info.get("lf_drel", None)
          if lb_drel is None: lb_drel = old_info.get("lb_drel", None)
          if rf_drel is None: rf_drel = old_info.get("rf_drel", None)
          if rb_drel is None: rb_drel = old_info.get("rb_drel", None)
          if lf_xrel is None: lf_xrel = old_info.get("lf_xrel", None)
          if lb_xrel is None: lb_xrel = old_info.get("lb_xrel", None)
          if rf_xrel is None: rf_xrel = old_info.get("rf_xrel", None)
          if rb_xrel is None: rb_xrel = old_info.get("rb_xrel", None)

        lf_drel_time = now if lf_drel_alive else old_info.get("lf_drel_time", now)
        lb_drel_time = now if lb_drel_alive else old_info.get("lb_drel_time", now)
        rf_drel_time = now if rf_drel_alive else old_info.get("rf_drel_time", now)
        rb_drel_time = now if rb_drel_alive else old_info.get("rb_drel_time", now)
        lf_xrel_time = now if lf_xrel_alive else old_info.get("lf_xrel_time", now)
        lb_xrel_time = now if lb_xrel_alive else old_info.get("lb_xrel_time", now)
        rf_xrel_time = now if rf_xrel_alive else old_info.get("rf_xrel_time", now)
        rb_xrel_time = now if rb_xrel_alive else old_info.get("rb_xrel_time", now)

        if (now - lf_drel_time) > 1.0 and lf_drel is not None: lf_drel = None
        if (now - lb_drel_time) > 1.0 and lb_drel is not None: lb_drel = None
        if (now - rf_drel_time) > 1.0 and rf_drel is not None: rf_drel = None
        if (now - rb_drel_time) > 1.0 and rb_drel is not None: rb_drel = None
        if (now - lf_xrel_time) > 1.0 and lf_xrel is not None: lf_xrel = None
        if (now - lb_xrel_time) > 1.0 and lb_xrel is not None: lb_xrel = None
        if (now - rf_xrel_time) > 1.0 and rf_xrel is not None: rf_xrel = None
        if (now - rb_xrel_time) > 1.0 and rb_xrel is not None: rb_xrel = None

        lidar_lblind_time = old_info.get("lidar_lblind_time", now)
        lidar_rblind_time = old_info.get("lidar_rblind_time", now)

        if (now - lidar_lblind_time) > 2. and lidar_lblind is not None: lidar_lblind = False
        if (now - lidar_rblind_time) > 2. and lidar_rblind is not None: lidar_rblind = False

        with lock:
          now = time.time()
          self.clients[ip] = {
            "port": int(json_obj.get("port", self.broadcast_port)),
            "last_seen": now,
            "device": device,
            "detect_side": json_obj.get("detect_side", old_info.get("detect_side", 0)),
            "dist_time": dist_timems,
            "lidar_lblind": lidar_lblind if lidar_lblind is not None else old_info.get("lidar_lblind", False),
            "lidar_rblind": lidar_rblind if lidar_rblind is not None else old_info.get("lidar_rblind", False),
            "lf_drel": lf_drel, "lb_drel": lb_drel, "rf_drel": rf_drel, "rb_drel": rb_drel,
            "lf_xrel": lf_xrel, "lb_xrel": lb_xrel, "rf_xrel": rf_xrel, "rb_xrel": rb_xrel,
            # 保存 alive 标志（修复②：is_side_object_risky 能感知数据有效性）
            "lf_drel_alive": lf_drel_alive, "lb_drel_alive": lb_drel_alive,
            "rf_drel_alive": rf_drel_alive, "rb_drel_alive": rb_drel_alive,
            "lf_xrel_alive": lf_xrel_alive, "lb_xrel_alive": lb_xrel_alive,
            "rf_xrel_alive": rf_xrel_alive, "rb_xrel_alive": rb_xrel_alive,
            "lidar_lblind_time": now if lidar_lblind is not None else old_info.get("lidar_lblind_time", now),
            "lidar_rblind_time": now if lidar_rblind is not None else old_info.get("lidar_rblind_time", now),
            "lf_drel_time": lf_drel_time, "lb_drel_time": lb_drel_time,
            "rf_drel_time": rf_drel_time, "rb_drel_time": rb_drel_time,
            "lf_xrel_time": lf_xrel_time, "lb_xrel_time": lb_xrel_time,
            "rf_xrel_time": rf_xrel_time, "rb_xrel_time": rb_xrel_time,
          }
      except Exception as e:
        print(f"Process lidar device error: {e}")
        print(json_obj)
    elif device == "camera":
      try:
        l_blindspot_time = old_info.get("l_blindspot_time", now)
        r_blindspot_time = old_info.get("r_blindspot_time", now)

        if (now - l_blindspot_time) > 2. and left_blind is not None: left_blind = False
        if (now - r_blindspot_time) > 2. and right_blind is not None: right_blind = False

        with lock:
          now = time.time()
          self.clients[ip] = {
            "port": int(json_obj.get("port", self.broadcast_port)),
            "last_seen": now,
            "device": device,
            "detect_side": json_obj.get("detect_side", old_info.get("detect_side", 0)),
            "left_blind": left_blind if left_blind is not None else old_info.get("left_blind", False),
            "right_blind": right_blind if right_blind is not None else old_info.get("right_blind", False),
            "l_blindspot_time": now if left_blind is not None else old_info.get("l_blindspot_time", now),
            "r_blindspot_time": now if right_blind is not None else old_info.get("r_blindspot_time", now),
          }
      except Exception as e:
        print(f"Process camera device error: {e}")
        print(json_obj)
    else:
      try:
        with lock:
          now = time.time()
          self.clients[ip] = {
            "port": int(json_obj.get("port", self.broadcast_port)),
            "last_seen": now,
            "device": device,
          }
      except Exception as e:
        print(f"Process other device error: {e}")
        print(json_obj)

  def is_side_object_risky(self, drel_mm, vrel_mps, v_ego_mps,
                           time_horizon=3.0,
                           min_drel_scale=1.0,
                           xrel_mm=None, vx_mps=None, drel_alive=True):
    """
    侧向车辆未来距离风险评估（前方和后方通用）
    修复版：保留原版基于TTC的精确判断为主，横向联合判断作为辅助增强
    """
    if drel_mm is None or vrel_mps is None or v_ego_mps is None:
      return False

    drel = abs(drel_mm) / 1000.0
    v_other = v_ego_mps + vrel_mps

    # ===== 修复①：drel_alive 为 False 时，不依赖可能过期的数据 =====
    # 运行版没有这个判断，当雷达丢帧时 drel_mm 可能用的是 old_info 的过期值
    # 导致 vrel 计算错误，TTC 算错，加塞判断延迟
    if not drel_alive:
      # 数据可能过期，退化为仅用横向距离判断（更保守但更准确）
      if xrel_mm is not None:
        xrel = abs(xrel_mm) / 1000.0
        if xrel < 1.5:
          return True
      return False

    if drel_mm > 0:
      closing_speed = max(v_ego_mps - v_other, 0.0)
      if min_drel_scale >= 0:
        danger_dist = max(v_ego_mps * min_drel_scale, 3.0)
      else:
        danger_dist = abs(min_drel_scale)
    else:
      closing_speed = max(v_other - v_ego_mps, 0.0)
      if min_drel_scale >= 0:
        danger_dist = max(v_ego_mps * min_drel_scale, 3.0)
      else:
        danger_dist = abs(min_drel_scale)

    future_dist = drel - closing_speed * time_horizon

    # ===== 修复②：恢复原版 TTC 精确判断（运行版这块逻辑被改坏了）=====
    # 运行版用 drel < danger_dist 直接判险，没有计算 future_dist
    # 导致：即使车辆还在远处，只要距离 < v_ego*scale 就立即判险
    # 这在加塞场景下意味着：加塞车还在隔壁车道时就触发盲区 → 系统过早进入盲区模式
    # → 后续 planner 的减速决策被盲区约束 → 加塞车真正切入时反应反而慢
    risk = (
      future_dist < danger_dist or
      drel < danger_dist * 0.7
    )

    # ===== 修复③：横向增强判断收紧（运行版这里太松导致加塞漏判）=====
    # 运行版：xrel < 3.0 且 vx < -0.3 → 判险
    # 问题：加塞车横向速度常常只有-0.15~-0.25m/s（不是急并线），xrel>3m 时完全不判断
    # 修复：用更精确的 TTC 横向判断
    if xrel_mm is not None and vx_mps is not None:
      xrel = abs(xrel_mm) / 1000.0
      # 横向TTC：车辆横向靠近本车的相对时间
      vx_abs = abs(vx_mps)
      # 加塞车横向速度只要明显朝本车方向运动（>0.1m/s）且距离<4m就值得警惕
      if xrel < 4.0 and vx_mps < -0.1:
        risk = True
      # 距离很近（<1.5m）无论横向速度如何都判险
      if xrel < 1.5:
        risk = True

    # 并行车保护：仅对"几乎完全并行+极近距离"的前方目标兜底
    # 运行版这里条件是 abs(v_ego - v_other) < 0.5 and drel < 8.0
    # 加塞车切入瞬间速度差常<0.5，距离<8m → 立即判险 → 系统进入盲区锁定
    # 盲区锁定后，planner 的减速力度被削弱 → 加塞识别"看起来"变迟钝
    # 修复：收紧到速度差<0.3 且 距离<5m，且要求确实是前方目标
    if drel_mm is not None and vrel_mps is not None and v_ego_mps is not None:
      drel_val = abs(drel_mm) / 1000.0
      v_other_val = v_ego_mps + vrel_mps
      if drel_mm > 0 and abs(v_ego_mps - v_other_val) < 0.3 and drel_val < 5.0:
        risk = True

    return risk

  def camera_data_timeout(self, ip, info):
    now = time.time()
    l_blindspot_time = info.get("l_blindspot_time", now)
    r_blindspot_time = info.get("r_blindspot_time", now)

    if (now - l_blindspot_time) > 2. : info["left_blind"] = False
    if (now - r_blindspot_time) > 2. : info["right_blind"] = False

    with lock:
      old_info = self.clients.get(ip, {})
      if old_info:
        self.clients[ip] = info

  def lidar_data_timeout(self, ip, info):
    now = time.time()
    lf_drel_time = info.get("lf_drel_time", now)
    lb_drel_time = info.get("lb_drel_time", now)
    rf_drel_time = info.get("rf_drel_time", now)
    rb_drel_time = info.get("rb_drel_time", now)
    lf_xrel_time = info.get("lf_xrel_time", now)
    lb_xrel_time = info.get("lb_xrel_time", now)
    rf_xrel_time = info.get("rf_xrel_time", now)
    rb_xrel_time = info.get("rb_xrel_time", now)

    if (now - lf_drel_time) > 1.0 : info["lf_drel"] = None
    if (now - lb_drel_time) > 1.0 : info["lb_drel"] = None
    if (now - rf_drel_time) > 1.0 : info["rf_drel"] = None
    if (now - rb_drel_time) > 1.0 : info["rb_drel"] = None
    if (now - lf_xrel_time) > 1.0 : info["lf_xrel"] = None
    if (now - lb_xrel_time) > 1.0 : info["lb_xrel"] = None
    if (now - rf_xrel_time) > 1.0 : info["rf_xrel"] = None
    if (now - rb_xrel_time) > 1.0 : info["rb_xrel"] = None

    lidar_lblind_time = info.get("lidar_lblind_time", now)
    lidar_rblind_time = info.get("lidar_rblind_time", now)

    if (now - lidar_lblind_time) > 2. : info["lidar_lblind"] = False
    if (now - lidar_rblind_time) > 2. : info["lidar_rblind"] = False

    with lock:
      old_info = self.clients.get(ip, {})
      if old_info:
        self.clients[ip] = info

  def _clean_clients_thread(self):
    while True:
      try:
        now = time.time()
        with lock:
          active_clients = {ip: info for ip, info in self.clients.items() if now - info["last_seen"] < 2.5}

        for ip, info in self.clients.items():
          if ip not in active_clients and ip in self.client_active:
            last = info.get("last_seen", 0)
            dt = now - last
            print(f"[Client Timeout] ip={ip}, last_seen={last:.3f}, now={now:.3f}, dt={dt:.3f}s")
            self.client_active[ip] = False

        self.clients = active_clients

        if self.clients:
          ext_state = len(self.clients)
        else:
          ext_state = 0
          self.shared_data.ext_blinker = BLINKER_NONE
        if self.lane_online:
          ext_state += 1
        self.shared_data.ext_state = ext_state

      except Exception as e:
        print(f"_clean_clients_thread error: {e}")
      finally:
        time.sleep(0.2)

  def navi_broadcast_info(self):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    frame = 0
    rk = Ratekeeper(10, print_delay_threshold=0.03)
    broadcast_cnt = 0

    while True:
      try:
        with lock:
          self.clients_copy = getattr(self, "clients", {}).copy()
          self.active_clients = list(self.clients_copy.keys())

        if frame % 20 == 0 or self.active_clients:
          try:
            if not PC:
              ip_address = socket.gethostbyname(socket.gethostname())
            else:
              ip_address = self.navi_get_local_ip()
            if ip_address != self.local_ip_address:
              self.local_ip_address = ip_address
              self.clients_copy = {}
              with lock:
                self.clients = {}

            navi_msg = navi_dat = lidar_msg = lidar_dat = blinker_msg = blinker_dat = None

            if navi_msg is None:
              navi_msg = self.make_navi_message()
              navi_dat = navi_msg.encode('utf-8') if navi_msg else None
            if navi_dat is not None and self.broadcast_ip is not None:
              sock.sendto(navi_dat, (self.broadcast_ip, self.navi_remote_port))

            if self.active_clients:
              if self.clients_copy:
                for ip, info in self.clients_copy.items():
                  try:
                    port_val = info.get("port", self.broadcast_port)
                    if port_val is not None:
                      port = int(port_val)
                    else:
                      port = self.broadcast_port
                    device_type = info.get("device", None)
                    detect_side = info.get("detect_side", None)

                    if device_type == "overtake" or device_type == "navi":
                      if navi_dat is not None:
                        sock.sendto(navi_dat, (ip, port))
                        sock.sendto(navi_dat, (ip, self.navi_remote_port))
                    elif (device_type == "lidar" or device_type == "camera") and ((frame % 3) == 0):
                      if lidar_msg is None:
                        lidar_msg = self.make_lidar_message()
                        lidar_dat = lidar_msg.encode('utf-8')
                      if lidar_dat is not None:
                        sock.sendto(lidar_dat, (ip, port))
                    elif ((frame + 3) % 2) == 0:
                      if blinker_msg is None:
                        blinker_msg = self.make_blinker_message()
                        blinker_dat = blinker_msg.encode('utf-8')
                      if blinker_dat is not None:
                        sock.sendto(blinker_dat, (ip, port))
                  except Exception as e:
                    if (self.shared_data.showDebugLog & 32) > 0:
                      print(f"sendto {ip} failed: {e}")

            if frame % 20 == 0:
              broadcast_msg = self.make_broadcast_message(self.listen_port, "op")
              broadcast_dat = broadcast_msg.encode('utf-8')
              if self.broadcast_ip is None:
                self.broadcast_ip = self.navi_get_broadcast_address()
              if self.broadcast_ip is not None and broadcast_dat is not None:
                sock.sendto(broadcast_dat, (self.broadcast_ip, self.broadcast_port))
                broadcast_cnt += 1
                if (self.shared_data.showDebugLog & 32) > 0:
                  print(f"broadcasting: {self.broadcast_ip}:{self.broadcast_port},{broadcast_msg}")

              lane_broadcast_msg = self.make_broadcast_message(self.lane_port, "lane")
              lane_broadcast_dat = lane_broadcast_msg.encode('utf-8')
              if self.broadcast_ip is not None and lane_broadcast_dat is not None:
                sock.sendto(lane_broadcast_dat, (self.broadcast_ip, self.lane_remote_port))

              navi_broadcast_msg = self.make_broadcast_message(self.navi_port, "navi")
              navi_broadcast_dat = navi_broadcast_msg.encode('utf-8')
              if self.broadcast_ip is not None and navi_broadcast_dat is not None:
                sock.sendto(navi_broadcast_dat, (self.broadcast_ip, self.navi_remote_port))

          except Exception as e:
            if (self.shared_data.showDebugLog & 32) > 0:
              print(f"##### navi_broadcast_error...: {e}")

        rk.keep_time()
        frame += 1
      except Exception as e:
        if (self.shared_data.showDebugLog & 32) > 0:
          print(f"navi_broadcast_info error...: {e}")
        time.sleep(1)

  def make_navi_message(self):
    msg = {}
    msg['ip'] = self.local_ip_address
    msg['port'] = self.listen_port
    msg['device'] = "op"
    isOnroad = self.params.get_bool("IsOnroad")
    msg['IsOnroad'] = isOnroad

    if isOnroad:
      if self.shared_data.carState:
        if self.shared_data.v_cruise_kph is not None:
          msg['v_cruise_kph'] = self.shared_data.v_cruise_kph
        if self.shared_data.v_ego_kph is not None:
          msg['v_ego_kph'] = self.shared_data.v_ego_kph
        if self.shared_data.vEgo is not None:
          msg["vego"] = self.shared_data.vEgo
        if self.shared_data.aEgo is not None:
          msg["aego"] = self.shared_data.aEgo
        if self.shared_data.steer_angle is not None:
          msg["steer_angle"] = self.shared_data.steer_angle
        if self.shared_data.gas_press is not None:
          msg["gas_press"] = self.shared_data.gas_press
        if self.shared_data.break_press is not None:
          msg["break_press"] = self.shared_data.break_press
        if self.shared_data.engaged is not None:
          msg["engaged"] = self.shared_data.engaged
        if not self.disableBlindSpot:
          if self.shared_data.left_blindspot is not None:
            msg["left_blindspot"] = self.shared_data.left_blindspot
          if self.shared_data.right_blindspot is not None:
            msg["right_blindspot"] = self.shared_data.right_blindspot
        else:
          msg["left_blindspot"] = False
          msg["right_blindspot"] = False

      if self.sm.alive['radarState']:
        radar_state = self.sm['radarState']
        if hasattr(radar_state, 'leadOne') and radar_state.leadOne and hasattr(radar_state.leadOne,'status') and radar_state.leadOne.status:
          msg["lead1"] = True
          if hasattr(radar_state, 'leadOne'):
            lead_one = radar_state.leadOne
            if hasattr(lead_one, 'dRel'): msg["drel"] = int(lead_one.dRel)
            if hasattr(lead_one, 'vLead'): msg["vlead"] = int(lead_one.vLead * 3.6)
            if hasattr(lead_one, 'vRel'): msg["vrel"] = int(lead_one.vRel * 3.6)
            if hasattr(lead_one, 'aRel'): msg["lead_accel"] = lead_one.aRel
        else:
          msg["lead1"] = False
        if not self.disableBlindSpot:
          if hasattr(radar_state, 'leadLeft') and radar_state.leadLeft and hasattr(radar_state.leadLeft,'status') and radar_state.leadLeft.status:
            self.lead_left_right = True
            msg["l_lead"] = True
            if hasattr(radar_state, 'leadLeft'):
              lead_left = radar_state.leadLeft
              if hasattr(lead_left, 'dRel'): msg["l_drel"] = int(lead_left.dRel)
              if hasattr(lead_left, 'vLead'): msg["l_vlead"] = int(lead_left.vLead * 3.6)
              if hasattr(lead_left, 'vRel'): msg["l_vrel"] = int(lead_left.vRel * 3.6)
          else:
            msg["l_lead"] = False
          if hasattr(radar_state, 'leadRight') and radar_state.leadRight and hasattr(radar_state.leadRight,'status') and radar_state.leadRight.status:
            self.lead_left_right = True
            msg["r_lead"] = True
            if hasattr(radar_state, 'leadRight'):
              lead_right = radar_state.leadRight
              if hasattr(lead_right, 'dRel'): msg["r_drel"] = int(lead_right.dRel)
              if hasattr(lead_right, 'vLead'): msg["r_vlead"] = int(lead_right.vLead * 3.6)
              if hasattr(lead_right, 'vRel'): msg["r_vrel"] = int(lead_right.vRel * 3.6)
          else:
            msg["r_lead"] = False
        else:
          msg["l_lead"] = False
          msg["r_lead"] = False

      if self.shared_data.lf_vrel is not None:
        msg["lf_vrel"] = int(self.shared_data.lf_vrel * 3.6)
      if self.shared_data.rf_vrel is not None:
        msg["rf_vrel"] = int(self.shared_data.rf_vrel * 3.6)
      if self.shared_data.lf_vx is not None:
        msg["lf_vx"] = int(self.shared_data.lf_vx * 3.6)
      if self.shared_data.rf_vx is not None:
        msg["rf_vx"] = int(self.shared_data.rf_vx * 3.6)
      if self.shared_data.lb_vrel is not None:
        msg["lb_vrel"] = int(self.shared_data.lb_vrel * 3.6)
      if self.shared_data.rb_vrel is not None:
        msg["rb_vrel"] = int(self.shared_data.rb_vrel * 3.6)
      if self.shared_data.lb_vx is not None:
        msg["lb_vx"] = int(self.shared_data.lb_vx * 3.6)
      if self.shared_data.rb_vx is not None:
        msg["rb_vx"] = int(self.shared_data.rb_vx * 3.6)

      if self.shared_data.leftFrontBlind is not None:
        msg['l_front_blind'] = self.shared_data.leftFrontBlind
      if self.shared_data.rightFrontBlind is not None:
        msg['r_front_blind'] = self.shared_data.rightFrontBlind

      msg['lidar_lblind'] = self.left_blindspot()
      msg['lidar_rblind'] = self.right_blindspot()

      fields = ["lf_drel", "lb_drel", "rf_drel", "rb_drel", "lf_xrel", "lb_xrel", "rf_xrel", "rb_xrel"]
      all_lidar_ids = set()
      for f in fields:
        all_lidar_ids.update(getattr(self.shared_data, f).keys())
      for idx in sorted(all_lidar_ids):
        for field in fields:
          d = getattr(self.shared_data, field)
          if idx in d and d[idx] is not None:
            key = field if idx == 0 else f"{field}{idx}"
            msg[key] = d[idx]

      msg['lidar_l'] = self.shared_data.lidar_l
      msg['lidar_r'] = self.shared_data.lidar_r
      msg['camera_l'] = self.shared_data.camera_l
      msg['camera_r'] = self.shared_data.camera_r

      if self.shared_data.roadcate is not None:
        msg['roadcate'] = self.shared_data.roadcate
      if self.shared_data.lat_a is not None:
        msg['lat_a'] = f2(self.shared_data.lat_a)
      if self.shared_data.max_curve is not None:
        msg['max_curve'] = f2(self.shared_data.max_curve)

      if self.sm.alive['carrotMan']:
        carrotMan = self.sm['carrotMan']
        msg["desire_speed"] = int(carrotMan.desiredSpeed)
        atc_type = carrotMan.atcType
        road_name = carrotMan.szPosRoadName
        x_spd_type = carrotMan.xSpdType
        x_spd_dist = carrotMan.xSpdDist
        op_blocked = ("none" not in atc_type and "prepare" not in atc_type)
        self.shared_data.op_blocked = op_blocked
        self.shared_data.road_blocked = ("隧道" in road_name) or (x_spd_type >= 0 and 0 < x_spd_dist < 500)

      msg['blind_enable'] = (self.shared_data.lidar_l or self.shared_data.camera_l) and (self.shared_data.lidar_r or self.shared_data.camera_r)
      msg['op_blocked'] = self.shared_data.op_blocked
      msg['road_blocked'] = self.shared_data.road_blocked

    if self.sm.alive['modelV2']:
      modelV2 = self.sm['modelV2']
      meta = modelV2.meta
      if hasattr(meta, 'eventType'):
        model_event_type = meta.eventType
        if model_event_type > 0 and model_event_type != self.model_event_type:
          self.model_event_type = model_event_type
          event_type_val = model_event_type & 255
          event_type_id = int((model_event_type - event_type_val) / 256)
          msg['sound'] = event_type_val
      if hasattr(meta, 'leftSec'):
        sec_count_down = meta.leftSec
        if self.sec_count_down != sec_count_down:
          self.sec_count_down = sec_count_down
          if sec_count_down == 0:
            msg['sound'] = 26
          elif 0 < sec_count_down <= 10:
            msg['sound'] = 30 + sec_count_down
          elif sec_count_down == 11:
            msg['sound'] = 23
      if hasattr(meta, 'blinker'):
        msg['blinker'] = meta.blinker
      if isOnroad:
        msg['l_lane_width'] = round(meta.laneWidthLeft, 1)
        msg['r_lane_width'] = round(meta.laneWidthRight, 1)
        msg['l_edge_dist'] = round(meta.distanceToRoadEdgeLeft, 1)
        msg['r_edge_dist'] = round(meta.distanceToRoadEdgeRight, 1)
        msg['atc_state'] = meta.laneChangeState.raw
        if hasattr(meta, 'laneWidth'):
          msg['lane_width'] = round(meta.laneWidth, 1)

        if self.shared_data.max_curve is None and hasattr(modelV2, 'orientationRate') and len(modelV2.orientationRate.z) > 0:
          orientation_rate_z = self._capnp_list_to_list(modelV2.orientationRate.z)
          if orientation_rate_z:
            max_index = max(range(len(orientation_rate_z)), key=lambda i: abs(orientation_rate_z[i]))
            max_orientation_rate = orientation_rate_z[max_index]
            msg['max_curve'] = f1(max_orientation_rate)

        if hasattr(modelV2, 'position') and len(modelV2.position.x) > 0:
            msg['path_x'] = self._capnp_list_to_list(modelV2.position.x, max_items=140)
            msg['path_y'] = self._capnp_list_to_list(modelV2.position.y, max_items=140)

        turn_right = 0
        turn_left = 0
        turn_uturn = 0

        if self.sm.alive.get('carrotMan', False):
            carrotMan = self.sm['carrotMan']
            atc = carrotMan.atcType.lower()
            if "right" in atc:
                turn_right = 1
                NAV_MANEUVER = "right"
            if "left" in atc:
                turn_left = 1
                NAV_MANEUVER = "left"
            if "uturn" in atc or "u-turn" in atc or "掉头" in atc:
                turn_uturn = 1
                NAV_MANEUVER = "uTurn"

        msg['turn_right'] = turn_right
        msg['turn_left'] = turn_left
        msg['turn_uturn'] = turn_uturn

    return json.dumps(msg)

  def make_lidar_message(self):
    msg = {}
    msg['ip'] = self.local_ip_address
    msg['port'] = self.listen_port
    msg['device'] = "op"
    isOnroad = self.params.get_bool("IsOnroad")
    msg['IsOnroad'] = isOnroad

    if isOnroad:
      if self.shared_data.carState:
        if self.shared_data.v_cruise_kph is not None:
          msg['v_cruise_kph'] = self.shared_data.v_cruise_kph
        if self.shared_data.v_ego_kph is not None:
          msg['v_ego_kph'] = self.shared_data.v_ego_kph

      if self.sm.alive['selfdriveState']:
        selfdrive = self.sm['selfdriveState']
        self.shared_data.selfdrive_active = True if selfdrive.active else False
      if self.shared_data.cruise_valid is not None:
        msg['active'] = self.shared_data.cruise_valid
      cruise_enable = bool(self.shared_data.selfdrive_active)
      if cruise_enable:
        msg['active'] = True
      if not msg.get('engaged', False):
        msg['engaged'] = cruise_enable

      if self.sm.alive['carrotMan']:
        carrotMan = self.sm['carrotMan']
        msg['atc_type'] = carrotMan.atcType
        msg['road_name'] = carrotMan.szPosRoadName

    return json.dumps(msg)

  def make_blinker_message(self):
    msg = {}
    msg['ip'] = self.local_ip_address
    msg['port'] = self.listen_port
    msg['device'] = "op"
    isOnroad = self.params.get_bool("IsOnroad")
    msg['IsOnroad'] = isOnroad

    if isOnroad:
      if self.shared_data.carState:
        if self.shared_data.v_cruise_kph is not None:
          msg['v_cruise_kph'] = self.shared_data.v_cruise_kph
        if self.shared_data.v_ego_kph is not None:
          msg['v_ego_kph'] = self.shared_data.v_ego_kph
        if self.shared_data.vEgo is not None:
          msg["vego"] = self.shared_data.vEgo
        if self.shared_data.gas_press is not None:
          msg["gas_press"] = self.shared_data.gas_press
        if self.shared_data.break_press is not None:
          msg["break_press"] = self.shared_data.break_press
      if self.sm.alive['radarState']:
        radar_state = self.sm['radarState']
        if hasattr(radar_state, 'leadOne') and radar_state.leadOne and hasattr(radar_state.leadOne,'status') and radar_state.leadOne.status:
          msg["lead1"] = True
          if hasattr(radar_state, 'leadOne'):
            lead_one = radar_state.leadOne
            if hasattr(lead_one, 'dRel'): msg["drel"] = f1(lead_one.dRel)
            if hasattr(lead_one, 'vLead'): msg["vlead"] = f1(lead_one.vLead * 3.6)
            if hasattr(lead_one, 'vRel'): msg["vrel"] = f1(lead_one.vRel * 3.6)
            if hasattr(lead_one, 'aRel'): msg["lead_accel"] = lead_one.aRel
        else:
          msg["lead1"] = False

    if self.sm.alive['modelV2']:
      meta = self.sm['modelV2'].meta
      if hasattr(meta, 'blinker'):
        msg['blinker'] = meta.blinker

    if self.sm.alive['selfdriveState']:
      selfdrive = self.sm['selfdriveState']
      self.shared_data.selfdrive_active = True if selfdrive.active else False
    if self.shared_data.cruise_valid is not None:
      msg['active'] = self.shared_data.cruise_valid
    cruise_enable = False
    if self.shared_data.selfdrive_active is not None and self.shared_data.selfdrive_active:
      cruise_enable = True
    if cruise_enable:
      msg['active'] = True
    if not msg.get('engaged', False):
      msg['engaged'] = cruise_enable

    return json.dumps(msg)

  def make_broadcast_message(self, port, device):
    msg = {}
    msg['ip'] = self.local_ip_address
    msg['port'] = port
    msg['device'] = device
    return json.dumps(msg)

  def navi_get_broadcast_address(self):
    if PC:
        interfaces = ['wlan0', 'eth0', 'enp0s3', 'br0']
        for iface in interfaces:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    ip = fcntl.ioctl(
                        s.fileno(),
                        0x8919,
                        struct.pack('256s', iface.encode('utf-8')[:15])
                    )[20:24]
                    return socket.inet_ntoa(ip)
            except Exception:
                continue
        return "255.255.255.255"
    else:
      iface = b'wlan0'
      try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
          ip = fcntl.ioctl(
            s.fileno(),
            0x8919,
            struct.pack('256s', iface)
          )[20:24]
          return socket.inet_ntoa(ip)
      except (OSError, Exception):
        return None

  def navi_get_local_ip(self):
      try:
          with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
              s.connect(("8.8.8.8", 80))
              return s.getsockname()[0]
      except Exception as e:
          return f"Error: {e}"

def main():
  amap_navi = AmapNaviServ()

if __name__ == "__main__":
  main()
