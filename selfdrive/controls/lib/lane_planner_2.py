import math
import numpy as np
from cereal import log
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.realtime import DT_MDL
# from openpilot.common.swaglog import cloudlog
# from openpilot.common.logger import sLogger
from openpilot.common.params import Params
TRAJECTORY_SIZE = 33
# positive numbers go right
CAMERA_OFFSET = 0 #0.08
MIN_LANE_DISTANCE = 2.6
MAX_LANE_DISTANCE = 3.7
MAX_LANE_CENTERING_AWAY = 1.85
KEEP_MIN_DISTANCE_FROM_LANE = 1.35
KEEP_MIN_DISTANCE_FROM_EDGELANE = 1.15

# ===================== 障碍物避让全局参数 =====================
OBSTACLE_MAX_LONG_DIST = 35.0    # 障碍物生效最大纵向距离
LANE_SHRINK_MAX_SIDE = 0.45      # 单侧车道最大收缩宽度(m)
STATIC_OBS_PRE_SHIFT_MAX = 0.65  # 路边静态障碍最大预偏移量(m)
OBS_FILTER_ALPHA = 0.22          # 障碍物车道收缩平滑系数
PATH_SHIFT_ALPHA = 0.20          # 静态障碍路径偏移平滑系数

# ===== CD210 roadEdges 智能感知增强参数 =====
ROAD_EDGE_PROB_THR = 0.30        # 路沿可信概率阈值
ROAD_EDGE_SAFE_MARGIN = 0.18     # 路沿内侧安全距离(m)
DEVIATION_NORM_THR = 0.82        # 归一化横向偏离阈值(|pos|>此值视为偏离)
DEVIATION_CORRECT_STEP = 0.22    # 偏离时每帧往回拉量(m)
NARROW_ROAD_RIGHT_TURN_MAX_Y = 1.5  # 右转窄路(双向两车道)最大末端偏出(m)
ROADEDGE_CENTER_BLEND = 0.35     # 路口兜底：roadEdges中心混合比例
TW_AVOID_SHIFT = 0.75            # 两轮车/行人独立避让偏移量(m, 增大右侧安全间隙)
# ===========================================================

def clamp(num, min_value, max_value):
  # weird broken case, do something reasonable
  if min_value > num > max_value:
    return (min_value + max_value) * 0.5
  # ok, basic min/max below
  if num < min_value:
    return min_value
  if num > max_value:
    return max_value
  return num

def sigmoid(x, scale=1, offset=0):
  return (1 / (1 + math.exp(x*scale))) + offset

def lerp(start, end, t):
  t = clamp(t, 0.0, 1.0)
  return (start * (1.0 - t)) + (end * t)

def max_abs(a, b):
  return a if abs(a) > abs(b) else b

class LanePlanner:
  def __init__(self):
    self.ll_t = np.zeros((TRAJECTORY_SIZE,))
    self.ll_x = np.zeros((TRAJECTORY_SIZE,))
    self.lll_y = np.zeros((TRAJECTORY_SIZE,))
    self.rll_y = np.zeros((TRAJECTORY_SIZE,))
    self.le_y = np.zeros((TRAJECTORY_SIZE,))
    self.re_y = np.zeros((TRAJECTORY_SIZE,))
    #self.lane_width_estimate = FirstOrderFilter(3.2, 9.95, DT_MDL)
    self.lane_width_estimate = FirstOrderFilter(3.2, 3.0, DT_MDL)
    self.lane_width = 3.2
    self.lane_width_last = self.lane_width
    self.lane_change_multiplier = 1
    #self.lane_width_updated_count = 0
    self.lll_prob = 0.
    self.rll_prob = 0.
    self.d_prob = 0.
    self.lll_std = 0.
    self.rll_std = 0.
    self.l_lane_change_prob = 0.
    self.r_lane_change_prob = 0.
    self.debugText = ""
    self.lane_width_left = 0.0
    self.lane_width_right = 0.0
    self.lane_width_left_filtered = FirstOrderFilter(1.0, 1.0, DT_MDL)
    self.lane_width_right_filtered = FirstOrderFilter(1.0, 1.0, DT_MDL)
    self.lane_offset_filtered = FirstOrderFilter(0.0, 2.0, DT_MDL)
    self.lanefull_mode = False
    self.d_prob_count = 0
    self.params = Params()

    # ===================== 障碍物避让缓存变量 =====================
    self.obstacle_avoid_scale = 1.0
    self.obs_shrink_l_target = 0.0
    self.obs_shrink_r_target = 0.0
    self.obs_path_shift_target = 0.0
    self.smooth_shrink_l = FirstOrderFilter(0.0, 1/OBS_FILTER_ALPHA, DT_MDL)
    self.smooth_shrink_r = FirstOrderFilter(0.0, 1/OBS_FILTER_ALPHA, DT_MDL)
    self.smooth_path_shift = FirstOrderFilter(0.0, 1/PATH_SHIFT_ALPHA, DT_MDL)
    self.closest_obs_long = float("inf")
    self.has_static_obstacle = False
    self.obs_lat_side = 0  # -1左障碍 / 0无 / 1右障碍
    # ===== CD210 roadEdges 智能感知缓存 =====
    self.road_edge_hard_limit_L = None   # 左侧路沿硬边界(y值)
    self.road_edge_hard_limit_R = None   # 右侧路沿硬边界(y值)
    self.deviation_correct = 0.0         # 当前帧偏离修正量(正=右拉/负=左拉)
    self.two_wheel_avoid_shift = 0.0    # 两轮车/行人独立避让偏移(累加进path)
    self.in_narrow_right_turn = False    # 是否处于窄路右转
    # ===========================================

    self.obstacle_avoid_scale = 1.0
    self.obs_shrink_l_target = 0.0
    self.obs_shrink_r_target = 0.0
    self.obs_path_shift_target = 0.0
    self.smooth_shrink_l = FirstOrderFilter(0.0, 1/OBS_FILTER_ALPHA, DT_MDL)
    self.smooth_shrink_r = FirstOrderFilter(0.0, 1/OBS_FILTER_ALPHA, DT_MDL)
    self.smooth_path_shift = FirstOrderFilter(0.0, 1/PATH_SHIFT_ALPHA, DT_MDL)
    self.closest_obs_long = float("inf")
    self.has_static_obstacle = False
    self.obs_lat_side = 0  # -1左障碍 / 0无 / 1右障碍
    # ==============================================================

  def parse_model(self, md):
    lane_lines = md.laneLines
    edges = md.roadEdges
    if len(lane_lines) >= 4 and len(lane_lines[0].t) == TRAJECTORY_SIZE:
      self.ll_t = (np.array(lane_lines[1].t) + np.array(lane_lines[2].t))/2
      # left and right ll x is the same
      self.ll_x = lane_lines[1].x
      self.lll_y = np.array(lane_lines[1].y)
      self.rll_y = np.array(lane_lines[2].y)
      self.lll_prob = md.laneLineProbs[1]
      self.rll_prob = md.laneLineProbs[2]
      self.lll_std = md.laneLineStds[1]
      self.rll_std = md.laneLineStds[2]
    if len(edges[0].t) == TRAJECTORY_SIZE:
      self.le_y = np.array(edges[0].y) + md.roadEdgeStds[0] * 0.4
      self.re_y = np.array(edges[1].y) - md.roadEdgeStds[1] * 0.4
      # ===== 缓存路沿硬边界(路沿内 safe_margin) =====
      try:
          self.road_edge_hard_limit_L = float(np.interp(0.0, np.array(edges[0].t), np.array(edges[0].y))) + ROAD_EDGE_SAFE_MARGIN
          self.road_edge_hard_limit_R = float(np.interp(0.0, np.array(edges[1].t), np.array(edges[1].y))) - ROAD_EDGE_SAFE_MARGIN
      except Exception:
          self.road_edge_hard_limit_L = None
          self.road_edge_hard_limit_R = None
      # ==============================================
    else:
      self.le_y = self.lll_y
      self.re_y = self.rll_y
      self.road_edge_hard_limit_L = None
      self.road_edge_hard_limit_R = None

    desire_state = md.meta.desireState
    if len(desire_state):
      self.l_lane_change_prob = desire_state[log.Desire.laneChangeLeft]
      self.r_lane_change_prob = desire_state[log.Desire.laneChangeRight]

  def update_obstacle_data(self, obstacle_list):
    """外部传入carrot障碍物列表，计算车道收缩量、静态障碍预偏移"""
    shrink_l = 0.0
    shrink_r = 0.0
    path_shift = 0.0
    min_long = float("inf")
    has_static = False
    obs_side = 0

    for obs in obstacle_list:
      d_long = obs.longDistance
      d_lat = obs.latDistance
      o_type = obs.type
      if d_long > OBSTACLE_MAX_LONG_DIST or d_long < 0.5:
        continue
      min_long = min(min_long, d_long)
      dist_weight = clamp(1.0 - (d_long / OBSTACLE_MAX_LONG_DIST), 0.0, 1.0)

      # 判断障碍物所在侧向
      if d_lat < -0.3:
        side = -1
      elif d_lat > 0.3:
        side = 1
      else:
        side = 0
      obs_side = side

      if o_type in ("static", "parked"):
        # 路边静态/停放故障车辆：收缩对应侧车道 + 路径反向预偏移
        has_static = True
        if side == -1:
          shrink_l += LANE_SHRINK_MAX_SIDE * dist_weight
          path_shift += STATIC_OBS_PRE_SHIFT_MAX * dist_weight
        elif side == 1:
          shrink_r += LANE_SHRINK_MAX_SIDE * dist_weight
          path_shift -= STATIC_OBS_PRE_SHIFT_MAX * dist_weight
      elif o_type in ["oncoming", "pedestrian", "motorcycle", "bicycle"]:
        # 对向/行人/二轮：双侧小幅收缩车道，弱化边界实现博弈绕行
        shrink_l += LANE_SHRINK_MAX_SIDE * 0.55 * dist_weight
        shrink_r += LANE_SHRINK_MAX_SIDE * 0.55 * dist_weight

    # 限幅目标值
    self.obs_shrink_l_target = clamp(shrink_l, 0.0, LANE_SHRINK_MAX_SIDE)
    self.obs_shrink_r_target = clamp(shrink_r, 0.0, LANE_SHRINK_MAX_SIDE)
    self.obs_path_shift_target = clamp(path_shift, -STATIC_OBS_PRE_SHIFT_MAX, STATIC_OBS_PRE_SHIFT_MAX)
    self.closest_obs_long = min_long
    self.has_static_obstacle = has_static
    self.obs_lat_side = obs_side

    # 一阶滤波平滑
    self.smooth_shrink_l.update(self.obs_shrink_l_target)
    self.smooth_shrink_r.update(self.obs_shrink_r_target)
    self.smooth_path_shift.update(self.obs_path_shift_target)
    # ===== 两轮车/行人独立避让偏移(不被 LaneOffset 向右抵消) =====
    _tw_shift = 0.0
    for obs in obstacle_list:
        if obs.longDistance > OBSTACLE_MAX_LONG_DIST or obs.longDistance < 0.5:
            continue
        _d_lat = obs.latDistance
        _o_type = obs.type
        if _o_type not in ("motorcycle", "bicycle", "pedestrian", "twowheeler"):
            continue
        # 右侧同车道(或贴边)的两轮车/行人 -> 强制向左避让
        if -0.3 < _d_lat < 2.5:
            _dist_w = clamp(1.0 - (obs.longDistance / OBSTACLE_MAX_LONG_DIST), 0.0, 1.0)
            _tw_shift = min(_tw_shift + TW_AVOID_SHIFT * _dist_w, TW_AVOID_SHIFT)
    self.two_wheel_avoid_shift = _tw_shift
    # ===========================================================


  def get_d_path(self, CS, v_ego, path_t, path_xyz, curve_speed):
    #if v_ego > 0.1:
    #  self.lane_width_updated_count = max(0, self.lane_width_updated_count - 1)
    # Reduce reliance on lanelines that are too far apart or
    # will be in a few seconds
    l_prob, r_prob = self.lll_prob, self.rll_prob
    width_pts = self.rll_y - self.lll_y
    prob_mods = []
    for t_check in (0.0, 1.5, 3.0):
      width_at_t = np.interp(t_check * (v_ego + 7), self.ll_x, width_pts)
      #prob_mods.append(np.interp(width_at_t, [4.0, 5.0], [1.0, 0.0]))
      prob_mods.append(np.interp(width_at_t, [4.5, 6.0], [1.0, 0.0]))
    mod = min(prob_mods)
    l_prob *= mod
    r_prob *= mod
    # Reduce reliance on uncertain lanelines
    l_std_mod = np.interp(self.lll_std, [.15, .3], [1.0, 0.0])
    r_std_mod = np.interp(self.rll_std, [.15, .3], [1.0, 0.0])
    l_prob *= l_std_mod
    r_prob *= r_std_mod
    self.l_prob, self.r_prob = l_prob, r_prob
    # Find current lanewidth
    current_lane_width = abs(self.rll_y[0] - self.lll_y[0])
    max_updated_count = 10.0 * DT_MDL
    both_lane_available = False
    #speed_lane_width = np.interp(v_ego*3.6, [0., 60.], [2.8, 3.5])
    if l_prob > 0.5 and r_prob > 0.5 and self.lane_change_multiplier > 0.5:
      both_lane_available = True
      #self.lane_width_updated_count = max_updated_count
      self.lane_width_estimate.update(current_lane_width)
      self.lane_width_last = self.lane_width_estimate.x
    #elif self.lane_width_updated_count <= 0 and v_ego > 0.1:   # 양쪽차선이 없을때.... 일정시간후(10초)부터 speed차선폭 적용함.
    #  self.lane_width_estimate.update(speed_lane_width)
    else:
      self.lane_width_estimate.update(self.lane_width_last)
    self.lane_width =  self.lane_width_estimate.x

    # ========== 障碍物动态收缩车道宽度核心逻辑 ==========
    shrink_l = self.smooth_shrink_l.x * self.obstacle_avoid_scale
    shrink_r = self.smooth_shrink_r.x * self.obstacle_avoid_scale
    # 左右车道线向内收缩，弱化边界限制
    shrink_lll_y = self.lll_y + shrink_l
    shrink_rll_y = self.rll_y - shrink_r
    clipped_lane_width = min(4.0, self.lane_width - shrink_l - shrink_r)
    # ======================================================

    path_from_left_lane = shrink_lll_y + clipped_lane_width / 2.0
    path_from_right_lane = shrink_rll_y - clipped_lane_width / 2.0

    # 가장 차선이 진한쪽으로 골라서..
    self.d_prob = max(l_prob, r_prob) if not both_lane_available else 1.0
    # 좌/우의 차선폭을 필터링.
    if self.lane_width_left > 0:
      self.lane_width_left_filtered.update(self.lane_width_left)
      #self.lane_width_left_filtered.x = self.lane_width_left #바로적용
    if self.lane_width_right > 0:
      self.lane_width_right_filtered.update(self.lane_width_right)
      #self.lane_width_right_filtered.x = self.lane_width_right #바로적용
    self.adjustLaneOffset = float(self.params.get_int("AdjustLaneOffset")) * 0.01
    self.adjustCurveOffset = float(self.params.get_int("AdjustCurveOffset")) * 0.01
    #self.adjustCurveOffset = self.adjustLaneOffset #float(self.params.get_int("AdjustCurveOffset")) * 0.01
    ADJUST_OFFSET_LIMIT = 0.4 #max(self.adjustLaneOffset, self.adjustCurveOffset)
    offset_curve = 0.0
    ## curve offset
    offset_curve = np.interp(abs(curve_speed), [50, 200], [self.adjustCurveOffset, 0.0]) * np.sign(curve_speed)
    offset_lane = 0.0
    if self.lane_width_left_filtered.x > 2.2 and self.lane_width_right_filtered.x > 2.2: #양쪽에 차로가 여유 있는경우
      offset_lane = 0.0
    elif self.lane_width_left_filtered.x < 2.0 and self.lane_width_right_filtered.x < 2.0: #양쪽에 차로가 여유 없는경우
      offset_lane = 0.0
    elif self.lane_width_left_filtered.x > self.lane_width_right_filtered.x:
      offset_lane = np.interp(self.lane_width, [2.5, 2.9], [0.0, self.adjustLaneOffset]) # 차선이 좁으면 안함..
    else:
      offset_lane = np.interp(self.lane_width, [2.5, 2.9], [0.0, -self.adjustLaneOffset]) # 차선이 좁으면 안함..
    #select lane path
    # 차선이 좁아지면, 도로경계쪽에 있는 차선 위주로 따라가도록함.
    if self.lane_width < 2.5:
      if r_prob > 0.5 and self.lane_width_right_filtered.x < self.lane_width_left_filtered.x:
        lane_path_y = path_from_right_lane
      elif l_prob > 0.5 and self.lane_width_left_filtered.x < 2.0:
        lane_path_y = path_from_left_lane
      else:
        lane_path_y = path_from_left_lane if l_prob > 0.5 or l_prob > r_prob else path_from_right_lane
    elif l_prob > 0.7 and r_prob > 0.7:
      lane_path_y = (path_from_left_lane + path_from_right_lane) / 2.
      # lane_width filtering에 의해서, 점점 줄어들때, 중앙선으로 붙어가는 현상이 생김..
      #if self.lane_width > 3.2:
      #  lane_path_y = path_from_right_lane
      #else:
      #  lane_path_y = (path_from_left_lane + path_from_right_lane) / 2.
    # 그외 진한차선을 따라가도록함.
    else:
      lane_path_y = (l_prob * path_from_left_lane + r_prob * path_from_right_lane) / (l_prob + r_prob + 0.0001)

    # ========== 路边静态障碍修正基准d_path，提前贴线避让 ==========
    static_shift = self.smooth_path_shift.x * self.obstacle_avoid_scale
    lane_path_y += static_shift
    # ==============================================================

    use_laneless_center_adjust = False
    if use_laneless_center_adjust:
      ## 0.5초 앞의 중심을 보도록함.
      lane_path_y_center = np.interp(0.5, path_t, lane_path_y)
      path_xyz_y_center = np.interp(0.5, path_t, path_xyz[:,1])
      #lane_path_y_center = lane_path_y[0]
      #path_xyz_y_center = path_xyz[:,1][0]
      diff_center = (lane_path_y_center - path_xyz_y_center) if not self.lanefull_mode else 0.0
    else:
      diff_center = 0.0
    #print("center = {:.2f}={:.2f}-{:.2f}, lanefull={}".format(diff_center, lane_path_y_center, path_xyz_y_center, self.lanefull_mode))
    #diff_center = lane_path_y[5] - path_xyz[:,1][5] if not self.lanefull_mode else 0.0
    if offset_curve * offset_lane < 0:
      offset_total = np.clip(offset_curve + offset_lane + diff_center, - ADJUST_OFFSET_LIMIT, ADJUST_OFFSET_LIMIT)
    else:
      offset_total = np.clip(max(offset_curve, offset_lane, key=abs) + diff_center, - ADJUST_OFFSET_LIMIT, ADJUST_OFFSET_LIMIT)
    ## self.d_prob = 0 if lane_changing
    self.d_prob *= self.lane_change_multiplier  ## 차선변경중에는 꺼버림.
    if self.lane_change_multiplier < 0.5:
      #self.lane_offset_filtered.x = 0.0
      pass
    else:
      self.lane_offset_filtered.update(np.interp(self.d_prob, [0, 0.3], [0, offset_total]))
    ## laneless at lowspeed
    self.d_prob *= np.interp(v_ego*3.6, [5., 10.], [0.0, 1.0])
    #self.debugText = "OFFSET({:.2f}={:.2f}+{:.2f}+{:.2f}),Vc:{:.2f},dp:{:.1f},lf:{},lrw={:.1f}|{:.1f}|{:.1f}".format(
    #  self.lane_offset_filtered.x,
    #  diff_center, offset_lane, offset_curve,
    #  curve_speed,
    #  self.d_prob, self.lanefull_mode,
    #  self.lane_width_left_filtered.x, self.lane_width, self.lane_width_right_filtered.x)
    adjustLaneTime = self.params.get_float("LatMpcInputOffset") * 0.01 # 0.06
    laneline_active = False
    self.d_prob_count = self.d_prob_count + 1 if self.d_prob > 0.3 else 0
    if self.lanefull_mode and self.d_prob_count > int(1 / DT_MDL):
      laneline_active = True
      use_dist_mode = False  ## 아무리생각해봐도.. 같은 방법인듯...
      if use_dist_mode:
        lane_path_y_interp = np.interp(path_xyz[:,0] + v_ego * adjustLaneTime, self.ll_x, lane_path_y)
        path_xyz[:,1] = self.d_prob * lane_path_y_interp + (1.0 - self.d_prob) * path_xyz[:,1]
      else:
        safe_idxs = np.isfinite(self.ll_t)
        if safe_idxs[0]:
          lane_path_y_interp = np.interp(path_t * (1.0 + adjustLaneTime), self.ll_t[safe_idxs], lane_path_y[safe_idxs])
          path_xyz[:,1] = self.d_prob * lane_path_y_interp + (1.0 - self.d_prob) * path_xyz[:,1]
    # ===== CD210 roadEdges 智能感知主逻辑 =====
    _hard_L = self.road_edge_hard_limit_L
    _hard_R = self.road_edge_hard_limit_R
    _le_prob = 0.0
    _re_prob = 0.0
    try:
        _le_prob = float(md.roadEdgeProbs[0]) if len(md.roadEdgeProbs) > 0 else 0.0
    except Exception:
        pass
    try:
        _re_prob = float(md.roadEdgeProbs[1]) if len(md.roadEdgeProbs) > 1 else 0.0
    except Exception:
        pass

    # --- E1: 路沿硬边界约束(转弯遇绿化带/非机动车道不压线) ---
    if _re_prob > ROAD_EDGE_PROB_THR and _hard_R is not None:
        path_xyz[:, 1] = np.clip(path_xyz[:, 1], -4.0, _hard_R)
    if _le_prob > ROAD_EDGE_PROB_THR and _hard_L is not None:
        path_xyz[:, 1] = np.clip(path_xyz[:, 1], _hard_L, 4.0)

    # --- E2: 偏离对向车道/路肩检测 + 修正 ---
    _lane_w = max(self.lane_width, 2.6)
    _y0 = float(path_xyz[0, 1])
    _norm_pos = clamp(_y0 / (_lane_w / 2.0), -2.0, 2.0)
    _ll_prob_now = self.lll_prob
    _rl_prob_now = self.rll_prob
    _corr = 0.0
    if _norm_pos < -DEVIATION_NORM_THR and _ll_prob_now > ROAD_EDGE_PROB_THR:
        _corr = DEVIATION_CORRECT_STEP   # 偏到对向 -> 每帧右拉回
    elif _norm_pos > DEVIATION_NORM_THR and _rl_prob_now > ROAD_EDGE_PROB_THR:
        _corr = -DEVIATION_CORRECT_STEP  # 偏到路肩 -> 每帧左拉回
    self.deviation_correct = _corr
    if _corr != 0.0:
        path_xyz[:, 1] += _corr

    # --- E3: 路口兜底(车道线淡出时以 roadEdges 中心为参考) ---
    _lane_fade = (self.lll_prob < 0.35) or (self.rll_prob < 0.35)
    if _lane_fade and _le_prob > ROAD_EDGE_PROB_THR and _re_prob > ROAD_EDGE_PROB_THR:
        try:
            _edge_L_y = np.array(edges[0].y)
            _edge_R_y = np.array(edges[1].y)
            _edge_center = (_edge_L_y + _edge_R_y) / 2.0
            path_xyz[:, 1] = path_xyz[:, 1] * (1.0 - ROADEDGE_CENTER_BLEND) + _edge_center * ROADEDGE_CENTER_BLEND
        except Exception:
            pass

    # --- E4: 窄路右转(双向两车道)防对向 + 两轮车独立避让 ---
    # 通过外部(lateral_planner)写入 Params RightTurnEarly=1 表示右转激活
    _rt_active = False
    try:
        from openpilot.common.params import Params as _P
        _rt_active = bool(_P().get_bool("RightTurnEarly"))
    except Exception:
        pass
    if _rt_active and _re_prob > ROAD_EDGE_PROB_THR:
        # 右转窄路：末端偏出限幅 + 左侧车道线硬约束(防跑对向)
        _end_y = float(path_xyz[-1, 1])
        if _end_y > NARROW_ROAD_RIGHT_TURN_MAX_Y:
            path_xyz[:, 1] -= (_end_y - NARROW_ROAD_RIGHT_TURN_MAX_Y) * np.linspace(0, 1, TRAJECTORY_SIZE)
        # 左侧：以当前车道左线为硬约束，不越过左线(对向侧)
        if _ll_prob_now > 0.4:
            _left_bound = self.lll_y + 0.15
            path_xyz[:, 1] = np.maximum(path_xyz[:, 1], _left_bound)
        self.in_narrow_right_turn = True
    else:
        self.in_narrow_right_turn = False

    # --- E5: 两轮车/行人独立避让偏移(累加，不被 LaneOffset 抵消) ---
    if self.two_wheel_avoid_shift > 0.01:
        path_xyz[:, 1] -= self.two_wheel_avoid_shift  # 向左避让
    # ============================================================

    path_xyz[:, 1] += (CAMERA_OFFSET + self.lane_offset_filtered.x)
    self.offset_total = self.lane_offset_filtered.x
    return path_xyz, laneline_active

  def calculate_plan_yaw_and_yaw_rate(self, path_xyz):
    if path_xyz.shape[0] < 3:
        # 너무 짧으면 직진 가정
        N = path_xyz.shape[0]
        return np.zeros(N), np.zeros(N)
    # x, y 추출
    x = path_xyz[:, 0]
    y = path_xyz[:, 1]
    # 모두 동일한 점인지 확인
    if np.allclose(x, x[0]) and np.allclose(y, y[0]):
        return np.zeros(len(x)), np.zeros(len(x))
    # 안전한 diff 계산
    dx = np.diff(x)
    dy = np.diff(y)
    mask = (dx == 0) & (dy == 0)
    dx[mask] = 1e-4
    dy[mask] = 0.0
    yaw = np.arctan2(dy, dx)
    yaw = np.append(yaw, yaw[-1])  # N-1 → N
    yaw = np.unwrap(yaw)
    dx_full = np.clip(np.diff(x), 1e-4, None)
    yaw_rate = np.diff(yaw) / dx_full
    yaw_rate = np.append(yaw_rate, yaw_rate[-1])
    yaw_rate = np.append(yaw_rate, 0.0)
    # NaN/Inf 방어
    if np.any(np.isnan(yaw_rate)) or np.any(np.isinf(yaw_rate)):
        yaw_rate = np.zeros_like(yaw_rate)
    if np.any(np.isnan(yaw)) or np.any(np.isinf(yaw)):
        yaw = np.zeros_like(yaw)
    return yaw, yaw_rate
