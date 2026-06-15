import time
import numpy as np
from openpilot.common.realtime import DT_MDL
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.controls.lib.lateral_mpc_lib.lat_mpc import LateralMpc
from openpilot.selfdrive.controls.lib.lateral_mpc_lib.lat_mpc import N as LAT_MPC_N
from openpilot.selfdrive.controls.lib.drive_helpers import CONTROL_N, MIN_SPEED, get_speed_error
import cereal.messaging as messaging
from cereal import log
from openpilot.common.params import Params
from openpilot.selfdrive.controls.lib.lane_planner_2 import LanePlanner
from collections import deque
TRAJECTORY_SIZE = 33
CAMERA_OFFSET = 0.04
PATH_COST = 1.0
LATERAL_MOTION_COST = 0.11
LATERAL_ACCEL_COST = 0.0
LATERAL_JERK_COST = 0.04
STEERING_RATE_COST = 220.0
# ===================== 导航联动优化（与 amap_navi 对接）=====================
NAV_TIMEOUT = 3.5
last_nav_update = 0.0
nav_hold_mode = False
g_narrow_road = False
g_big_cross = False
g_near_edge = False
g_nav_gain = 0.9
g_has_right_truck = False
g_truck_left_offset = 0.0
last_truck_offset = 0.0
smooth_y_prev = np.zeros(TRAJECTORY_SIZE)
smooth_yaw_prev = np.zeros(TRAJECTORY_SIZE)
# ===================== 【全局优化参数 - 不改动原参数】=====================
LANE_LINE_SOLID_THRESHOLD = 0.3
LANE_CHANGE_SOLID_BLOCK = True
LEFT_TURN_PATH_SUPPRESS = True
SPEED_LOW = 8.0
SPEED_HIGH = 25.0
# ========== 高速防抖&防锁死核心参数【路径条安全版】 ==========
SPEED_GRID_KPH = [0, 15, 30, 50, 80, 110]
PLAN_GAIN_TABLE = [1.18, 1.12, 1.06, 1.01, 0.95, 0.91]
ANGLE_ERR_THRESH = 10.0
ANGLE_ERR_EXTRA_GAIN = 1.02
# 【优化】提升右转补偿力度，增强曲线跟随
RIGHT_TURN_ANGLE_THRESH = 3.2
RIGHT_TURN_CURV_COMP = 1.48
CURV_COMP_SCALE = 1e-4
HIGH_SPEED_DAMP = 0.83
HIGH_SPEED_DAMP_PLUS = 0.89
INTERSECTION_MAX_STEER_RATIO = 0.55
# 【路径条强制兜底，绝对不消失】
LAST_VALID_PATH_Y = np.zeros(TRAJECTORY_SIZE)
LAST_VALID_PATH_YAW = np.zeros(TRAJECTORY_SIZE)
LAST_STEER_CMD = 0.0
LAST_VALID_X_SOL = np.zeros((TRAJECTORY_SIZE, 4), dtype=np.float32)
TURN_LOCK_TIMEOUT = 2.5
IN_TURN_AVOID_SCALE = 0.28
global_in_turn = False
global_turn_lock_ts = 0.0
LINE_NONE = 0
LINE_WHITE_DASH = 1
LINE_SINGLE_YELLOW = 2
LINE_DOUBLE_YELLOW = 3
BASE_MARGIN_NORMAL = 0.12
BASE_MARGIN_BIG = 0.10
BASE_MARGIN_NARROW = 0.26
YELLOW_SINGLE_ADD = 0.10
YELLOW_DOUBLE_ADD = 0.15
SCALE_BIG = 1.00
SCALE_NORMAL = 1.00
SCALE_NARROW = 0.78
SCALE_SINGLE_YELLOW = 0.85
SCALE_DOUBLE_YELLOW = 0.72
ANGLE_THRESH_MID = 45
ANGLE_THRESH_BIG = 80
TURN_ANGLE_MID_SCALE = 0.90
TURN_ANGLE_BIG_SCALE = 0.82
LEFT_TURN_RAW_Y_SCALE = 0.72
LEFT_TURN_EXTRA_LEFT_MARGIN = 0.08
LEFT_TURN_GLOBAL_OFFSET = 0.06
LEFT_TURN_ADD_SCALE = 0.91
TURN_LOOKAHEAD_FACTOR = 1.8
BASE_PATH_POINTS = TRAJECTORY_SIZE
PATH_STITCH_TURN_TOL = 0.5

# ========== 右转贴边专用新增参数 ==========
# 右转右侧安全余量(越小越贴边线)
RIGHT_TURN_SAFE_MARGIN = 0.06
# 右转整体向右偏移量(负值=靠右)
RIGHT_TURN_FIX_OFFSET = -0.08

def is_nav_active():
    global last_nav_update, nav_hold_mode,g_narrow_road,g_big_cross,g_near_edge,g_nav_gain,g_has_right_truck,g_truck_left_offset
    try:
        from openpilot.selfdrive.carrot.amap_navi import NAV_ACTIVE, NAV_LAST_UPDATE, NAV_MSG_DATA
        now = time.time()
        g_narrow_road = NAV_MSG_DATA.get("is_narrow_road",False)
        g_big_cross = NAV_MSG_DATA.get("is_big_cross",False)
        g_near_edge = NAV_MSG_DATA.get("near_road_edge",False)
        g_nav_gain = NAV_MSG_DATA.get("navi_correct_gain",0.9)
        g_has_right_truck = NAV_MSG_DATA.get("has_right_big_truck",False)
        g_truck_left_offset = NAV_MSG_DATA.get("truck_left_offset",0.0)
        if NAV_ACTIVE and (now - NAV_LAST_UPDATE) <= NAV_TIMEOUT:
            last_nav_update = now
            nav_hold_mode = True
            return True
        if nav_hold_mode and (now - last_nav_update) <= 2.0:
            return True
        nav_hold_mode = False
        return False
    except:
        g_narrow_road = False
        g_big_cross = False
        g_near_edge = False
        g_nav_gain = 0.9
        g_has_right_truck = False
        g_truck_left_offset = 0.0
        return False
def is_turn_active():
    try:
        from openpilot.selfdrive.carrot.amap_navi import NAV_MSG_DATA
        return NAV_MSG_DATA.get("turn_active", 0) == 1
    except:
        return False
def is_u_turn():
    try:
        from openpilot.selfdrive.carrot.amap_navi import NAV_MANEUVER
        return NAV_MANEUVER == 'uTurn'
    except:
        return False
def is_right_turn():
    try:
        from openpilot.selfdrive.carrot.amap_navi import NAV_MANEUVER
        return NAV_MANEUVER in ("turnRight", "rampRight")
    except:
        return False
def check_solid_lane_line(md) -> bool:
    try:
        left_solid = md.laneLines[0].isSolid and md.laneLines[0].prob > LANE_LINE_SOLID_THRESHOLD
        right_solid = md.laneLines[1].isSolid and md.laneLines[1].prob > LANE_LINE_SOLID_THRESHOLD
        return left_solid or right_solid
    except:
        return False
def is_intersection_left_turn(sm) -> bool:
    md = sm['modelV2']
    desire = md.meta.desire
    is_inter = g_big_cross or g_narrow_road
    return is_inter and desire == log.Desire.turnLeft
def get_divide_line_type(md) -> int:
    try:
        left_line = md.laneLines[0]
        is_yellow = left_line.color == log.LaneLineColor.yellow
        is_dashed = not left_line.isSolid
        prob_ok = left_line.prob > LANE_LINE_SOLID_THRESHOLD
        if not prob_ok:
            return LINE_NONE
        if not is_yellow:
            return LINE_WHITE_DASH
        if len(md.laneLines) >= 2 and md.laneLines[1].color == log.LaneLineColor.yellow:
            return LINE_DOUBLE_YELLOW
        else:
            return LINE_SINGLE_YELLOW
    except Exception:
        return LINE_NONE
def estimate_turn_angle(md) -> float:
    try:
        yaw_seq = np.array(md.orientation.z)
        delta_yaw = abs(yaw_seq[-1] - yaw_seq[0])
        return np.rad2deg(delta_yaw)
    except Exception:
        return 0.0
class LateralPlanner:
  def __init__(self, CP, debug=False):
    self.factor1 = CP.wheelbase - CP.centerToFront
    self.factor2 = (CP.centerToFront * CP.mass) / (CP.wheelbase * CP.tireStiffnessRear)
    self.last_cloudlog_t = 0
    self.solution_invalid_cnt = 0
    self.path_xyz = np.zeros((TRAJECTORY_SIZE, 3))
    self.velocity_xyz = np.zeros((TRAJECTORY_SIZE, 3))
    self.v_plan = np.zeros((TRAJECTORY_SIZE,))
    self.x_sol = np.zeros((TRAJECTORY_SIZE, 4), dtype=np.float32)
    self.v_ego = MIN_SPEED
    self.l_lane_change_prob = 0.0
    self.r_l_lane_change_prob = 0.0
    self.debug_mode = debug
    self.params = Params()
    self.latDebugText = ""
    self.LP = LanePlanner()
    self.readParams = 0
    self.lanelines_active = False
    self.lanelines_active_tmp = False
    self.useLaneLineSpeedApply = self.params.get_int("UseLaneLineSpeed")
    self.pathOffset = float(self.params.get_int("PathOffset")) * 0.01
    self.useLaneLineMode = False
    self.plan_a = np.zeros((TRAJECTORY_SIZE, ))
    self.plan_yaw = np.zeros((TRAJECTORY_SIZE,))
    self.plan_yaw_rate = np.zeros((TRAJECTORY_SIZE,))
    self.t_idxs = np.arange(TRAJECTORY_SIZE)
    self.y_pts = np.zeros((TRAJECTORY_SIZE,))
    self.d_path_w_lines_xyz = np.zeros((TRAJECTORY_SIZE, 3))
    self.lat_mpc = LateralMpc()
    self.reset_mpc(np.zeros(4))
    self.curve_speed = 0
    self.lanemode_possible_count = 0
    self.laneless_only = True
    self.lookahead_time = 2.8
    self.min_path_length = 200
  def reset_mpc(self, x0=None):
    if x0 is None:
      x0 = np.zeros(4)
    self.x0 = x0
    self.lat_mpc.reset(x0=self.x0)
  def update(self, sm, carrot):
    global LATERAL_ACCEL_COST, LATERAL_JERK_COST, STEERING_RATE_COST,g_narrow_road,g_big_cross,g_near_edge,g_nav_gain,g_has_right_truck,g_truck_left_offset,last_truck_offset,smooth_y_prev,smooth_yaw_prev
    global LAST_VALID_PATH_Y, LAST_VALID_PATH_YAW, LAST_STEER_CMD, LAST_VALID_X_SOL
    global global_in_turn, global_turn_lock_ts
    now_ts = time.time()
    self.readParams -= 1
    if self.readParams <= 0:
      self.readParams = 100
      self.useLaneLineSpeedApply = sm['carState'].useLaneLineSpeed
      self.pathOffset = float(self.params.get_int("PathOffset")) * 0.01
      self.lateralPathCost = self.params.get_float("LatMpcPathCost") * 0.01
      self.lateralMotionCost = self.params.get_float("LatMpcMotionCost") * 0.01
      LATERAL_ACCEL_COST = self.params.get_float("LatMpcAccelCost") * 0.01
      LATERAL_JERK_COST = self.params.get_float("LatMpcJerkCost") * 0.01
      STEERING_RATE_COST = self.params.get_float("LatMpcSteeringRateCost")
    measured_curvature = sm['controlsState'].curvature
    v_ego_car = sm['carState'].vEgo
    self.curve_speed = sm['carrotMan'].vTurnSpeed
    v_kph = v_ego_car * 3.6
    speed_steer_gain = float(np.interp(v_kph, SPEED_GRID_KPH, PLAN_GAIN_TABLE))
    try:
        act_steer_deg = sm['carState'].steeringAngleDeg
        des_steer_deg = self.lat_mpc.x_sol[0, 3] * 180 / np.pi
        angle_err = abs(des_steer_deg - act_steer_deg)
        if angle_err > ANGLE_ERR_THRESH:
            speed_steer_gain *= ANGLE_ERR_EXTRA_GAIN
    except:
        angle_err = 0.0
        des_steer_deg = 0.0
    right_turn_comp = 0.0
    if des_steer_deg > RIGHT_TURN_ANGLE_THRESH:
        right_turn_comp = RIGHT_TURN_CURV_COMP
    measured_curvature *= speed_steer_gain
    measured_curvature += right_turn_comp * CURV_COMP_SCALE
    nav_active = is_nav_active()
    uturn_active = is_u_turn()
    right_turn_active = is_right_turn()
    turn_locked = is_turn_active()
    if turn_locked:
        global_in_turn = True
        global_turn_lock_ts = now_ts
    if global_in_turn and (now_ts - global_turn_lock_ts) > TURN_LOCK_TIMEOUT:
        global_in_turn = False
    if nav_active and (right_turn_active or g_big_cross or turn_locked):
        self.lat_mpc.nav_gain = 1.45
    else:
        self.lat_mpc.nav_gain = 1.0
    temp_path_cost = self.lateralPathCost
    temp_steer_rate_cost = STEERING_RATE_COST
    if (g_narrow_road or g_big_cross or g_near_edge) and self.v_ego > 40:
        temp_path_cost = self.lateralPathCost * g_nav_gain
    v100 = 100 / 3.6
    v110 = 110 / 3.6
    v120 = 120 / 3.6
    if v100 <= self.v_ego <= v120:
        steer_mod = np.interp(self.v_ego, [v100, v110, v120], [1.01, 0.99, 1.00])
        path_mod = np.interp(self.v_ego, [v100, v110, v120], [0.94, 0.86, 0.88])
        temp_steer_rate_cost = STEERING_RATE_COST * steer_mod * speed_steer_gain
        temp_path_cost = temp_path_cost * path_mod * speed_steer_gain
    elif self.v_ego > v120:
        temp_steer_rate_cost = STEERING_RATE_COST * 1.00 * speed_steer_gain
        temp_path_cost *= 0.87 * speed_steer_gain
    else:
        temp_steer_rate_cost *= speed_steer_gain
        temp_path_cost *= speed_steer_gain
    # ========= 【核心优化1】区分场景放宽曲率限幅，右转/路口允许更大曲率 =========
    if right_turn_active or g_big_cross or global_in_turn:
        # 转弯/大路口：放宽上限，保证曲线形态
        measured_curvature = np.clip(measured_curvature, -0.038, 0.038)
    else:
        # 正常直行道路：保留原限制，保证稳定
        measured_curvature = np.clip(measured_curvature, -0.026, 0.026)
    md = sm['modelV2']
    model_valid = (len(md.position.x) == TRAJECTORY_SIZE and len(md.orientation.x) == TRAJECTORY_SIZE)
    if model_valid:
        self.path_xyz = np.column_stack([md.position.x, md.position.y, md.position.z])
        self.t_idxs = np.array(md.position.t)
        raw_y = np.array(md.position.y)
        raw_yaw = np.array(md.orientation.z)
        if LEFT_TURN_PATH_SUPPRESS and is_intersection_left_turn(sm) and self.v_ego > SPEED_LOW:
            raw_y[1:] *= LEFT_TURN_RAW_Y_SCALE
            raw_yaw[1:] *= 0.90
            raw_y += LEFT_TURN_GLOBAL_OFFSET
        vkph = self.v_ego *3.6
        # ========= 【核心优化2】右转场景降低平滑强度，曲线更灵动不僵硬 =========
        if right_turn_active or g_big_cross:
            smooth_alpha = 0.11
        elif vkph > 100:
            smooth_alpha = 0.80
        elif vkph > 40:
            smooth_alpha = 0.45
        else:
            smooth_alpha = 0.22
        smooth_y = smooth_alpha*smooth_y_prev + (1-smooth_alpha)*raw_y
        smooth_yaw = smooth_alpha*smooth_yaw_prev + (1-smooth_alpha)*raw_yaw
        smooth_y_prev = smooth_y.copy()
        smooth_yaw_prev = smooth_yaw.copy()
        self.path_xyz[:,1] = smooth_y
        self.plan_yaw = smooth_yaw
        self.plan_yaw_rate = np.array(md.orientationRate.z)
        self.velocity_xyz = np.column_stack([md.velocity.x, md.velocity.y, md.velocity.z])
        car_speed = np.linalg.norm(self.velocity_xyz, axis=1) - get_speed_error(md, v_ego_car)
        self.v_plan = np.clip(car_speed, MIN_SPEED, np.inf)
        self.v_ego = self.v_plan[0]
        self.plan_a = np.array(md.acceleration.x)
        LAST_VALID_PATH_Y = self.path_xyz[:, 1].copy()
        LAST_VALID_PATH_YAW = self.plan_yaw.copy()
        if md.velocity.x[-1] < md.velocity.x[0] * 0.7:
            self.lanemode_possible_count = 0
            self.laneless_only = True
        else:
            self.lanemode_possible_count += 1
            if self.lanemode_possible_count > int(1/DT_MDL):
                self.laneless_only = False
    else:
        # 【路径条强制兜底】模型数据无效时，用最后有效数据填充
        self.path_xyz[:, 1] = LAST_VALID_PATH_Y
        self.plan_yaw = LAST_VALID_PATH_YAW
    self.LP.parse_model(md)
    if global_in_turn:
        self.LP.obstacle_avoid_scale = IN_TURN_AVOID_SCALE
    else:
        self.LP.obstacle_avoid_scale = 1.0
    line_type = get_divide_line_type(md)
    turn_angle = estimate_turn_angle(md)
    lane_w_left = self.LP.lane_width_left
    lane_w_right = self.LP.lane_width_right
    if g_big_cross:
        curr_margin = BASE_MARGIN_BIG
        base_scale = SCALE_BIG
    elif g_narrow_road:
        curr_margin = BASE_MARGIN_NARROW
        base_scale = SCALE_NARROW
    else:
        curr_margin = BASE_MARGIN_NORMAL
        base_scale = SCALE_NORMAL
    if turn_angle >= ANGLE_THRESH_BIG:
        turn_scale = TURN_ANGLE_BIG_SCALE
    elif turn_angle >= ANGLE_THRESH_MID:
        turn_scale = TURN_ANGLE_MID_SCALE
    else:
        turn_scale = 1.0
    line_scale = 1.0
    line_extra_margin = 0.0
    if line_type == LINE_DOUBLE_YELLOW:
        line_scale = SCALE_DOUBLE_YELLOW
        line_extra_margin = YELLOW_DOUBLE_ADD
    elif line_type == LINE_SINGLE_YELLOW:
        line_scale = SCALE_SINGLE_YELLOW
        line_extra_margin = YELLOW_SINGLE_ADD
    final_scale = base_scale * turn_scale * line_scale
    final_total_margin = curr_margin + line_extra_margin
    # ========= 【核心优化3】右转场景取消额外缩放压制，完整保留转弯轨迹 =========
    if global_in_turn and not right_turn_active:
        final_scale *= 0.97
        final_total_margin += 0.02
    is_left_turn_scene = is_intersection_left_turn(sm)
    if is_left_turn_scene:
        final_scale *= LEFT_TURN_ADD_SCALE
        final_total_margin += LEFT_TURN_EXTRA_LEFT_MARGIN
    self.path_xyz[:, 1] *= final_scale
    lane_left_bound = - (lane_w_left / 2.0)
    lane_right_bound = (lane_w_right / 2.0)
    safe_left = lane_left_bound + final_total_margin + 0.04

    # 右转收紧右侧安全边距，贴近车道最右侧
    if right_turn_active:
        safe_right = lane_right_bound - RIGHT_TURN_SAFE_MARGIN
    else:
        safe_right = lane_right_bound - curr_margin

    if is_left_turn_scene:
        safe_left += 0.05

    # 右转整体路径向右偏移，进一步贴紧右侧
    if right_turn_active:
        self.path_xyz[:, 1] += RIGHT_TURN_FIX_OFFSET

    self.path_xyz[:, 1] = np.clip(self.path_xyz[:, 1], safe_left, safe_right)

    if LANE_CHANGE_SOLID_BLOCK and check_solid_lane_line(md):
        self.LP.lane_change_multiplier = 0.0
    if self.v_ego < 18:
        self.useLaneLineMode = False
    else:
        if self.useLaneLineSpeedApply == 0 or self.laneless_only:
            self.useLaneLineMode = False
        else:
            self.useLaneLineMode = True
    curvature = measured_curvature
    # 右转专属曲率强化，弯道不向外飘
    if right_turn_active:
        curvature *= 1.15
    # ========= 【核心优化4】强化低速转弯曲率增益，路口右转不被拉直 =========
    if 0.0006 < abs(curvature) < 0.0015 and self.v_ego < 30:
        curvature = np.sign(curvature) * 0.0018
    # 低速(<30km/h)大曲率 增强增益
    if abs(curvature) >= 0.0015 and self.v_ego < 30:
        curvature *= 1.55
    # 中速(30~50km/h)弯道 小幅增强
    if abs(curvature) >= 0.0012 and 30 <= self.v_ego < 50:
        curvature *= 1.22
    self.LP.curvature = curvature
    if nav_active:
        self.LP.lane_change_multiplier = 0.0
    else:
        if md.meta.desire != log.Desire.none or carrot.atc_active:
            self.LP.lane_change_multiplier = 0.0
        elif not (LANE_CHANGE_SOLID_BLOCK and check_solid_lane_line(md)):
            self.LP.lane_change_multiplier = 1.0
    self.LP.lanefull_mode = self.useLaneLineMode
    self.LP.lane_width_left = md.meta.laneWidthLeft
    self.LP.lane_width_right = md.meta.laneWidthRight
    self.LP.curvature = curvature
    self.path_xyz, self.lanelines_active = self.LP.get_d_path(sm['carState'], self.v_ego, self.t_idxs, self.path_xyz, self.curve_speed)
    delta = g_truck_left_offset - last_truck_offset
    delta = np.clip(delta, -0.04, 0.04)
    last_truck_offset += delta
    final_offset = self.pathOffset - last_truck_offset
    self.path_xyz[:, 1] += final_offset
    if uturn_active:
        self.lat_mpc.set_weights(1.5,2.4,1.0,0.7,1.2,True,False,self.v_ego>100/3.6,self.v_ego*3.6)
    else:
        self.lat_mpc.set_weights(temp_path_cost, self.lateralMotionCost, LATERAL_ACCEL_COST, LATERAL_JERK_COST, temp_steer_rate_cost,False,self.v_ego>100/3.6,self.v_ego*3.6)
    y_pts = self.path_xyz[:LAT_MPC_N+1, 1]
    heading_pts = self.plan_yaw[:LAT_MPC_N+1]
    yaw_rate_pts = self.plan_yaw_rate[:LAT_MPC_N+1]
    self.y_pts = y_pts
    lateral_factor = np.clip(self.factor1 - (self.factor2 * self.v_plan**2), 0.0, np.inf)
    p = np.column_stack([self.v_plan, lateral_factor])
    # ========= 【MPC求解失败兜底，路径条绝对不消失】 =========
    try:
        self.lat_mpc.run(self.x0, p, y_pts, heading_pts, yaw_rate_pts)
        if not np.all(np.isfinite(self.lat_mpc.x_sol)):
            raise ValueError("MPC求解结果包含NaN/Inf")
        self.x_sol = self.lat_mpc.x_sol.copy()
        LAST_VALID_X_SOL = self.x_sol.copy()
    except Exception as e:
        cloudlog.warning(f"MPC求解异常，使用兜底数据: {e}")
        self.x_sol = LAST_VALID_X_SOL.copy()
    # =========================================================
    current_steer = self.x_sol[0, 3]
    if self.v_ego >= SPEED_HIGH:
        if self.v_ego >= 110/3.6:
            current_steer = HIGH_SPEED_DAMP_PLUS * LAST_STEER_CMD + (1 - HIGH_SPEED_DAMP_PLUS) * current_steer
        else:
            current_steer = HIGH_SPEED_DAMP * LAST_STEER_CMD + (1 - HIGH_SPEED_DAMP) * current_steer
    LAST_STEER_CMD = current_steer
    # ========= 【核心优化5】低速转向区间进一步放宽，适配大角度右转 =========
    if self.v_ego < 30:
        current_steer = np.clip(current_steer, -0.65, 0.65)
    else:
        current_steer = np.clip(current_steer, -0.52, 0.52)
    self.x_sol[:, 3] = current_steer
    self.x0[3] = np.interp(DT_MDL, self.t_idxs[:LAT_MPC_N + 1], self.x_sol[:, 3])
    mpc_nans = np.isnan(self.x_sol[:, 3]).any()
    t = time.monotonic()
    if mpc_nans or self.lat_mpc.solution_status != 0:
        self.reset_mpc()
        self.x0[3] = measured_curvature * self.v_ego
        if t > self.last_cloudlog_t + 5.0:
            self.last_cloudlog_t = t
            cloudlog.warning("Lateral mpc - nan: True")
    if self.lat_mpc.cost > 1e6 or mpc_nans:
        self.solution_invalid_cnt += 1
    else:
        self.solution_invalid_cnt = 0
  def publish(self, sm, pm, carrot):
    plan_solution_valid = self.solution_invalid_cnt < 1
    plan_send = messaging.new_message('lateralPlan')
    plan_send.valid = sm.all_checks(service_list=['carState', 'controlsState', 'modelV2'])
    lateralPlan = plan_send.lateralPlan
    lateralPlan.modelMonoTime = sm.logMonoTime['modelV2']
    lateralPlan.dPathPoints = self.y_pts.tolist()
    lateralPlan.psis = self.x_sol[0:CONTROL_N, 2].tolist()
    lateralPlan.distances = self.x_sol[0:CONTROL_N, 0].tolist()
    if len(self.v_plan) == TRAJECTORY_SIZE:
        lateralPlan.curvatures = (self.x_sol[0:CONTROL_N, 3] / self.v_plan[0:CONTROL_N]).tolist()
    else:
        lateralPlan.curvatureRates = [float(x.item() / self.v_ego) for x in self.lat_mpc.u_sol.flatten().tolist()] + [0.0]
    lateralPlan.mpcSolutionValid = bool(plan_solution_valid)
    lateralPlan.solverExecutionTime = self.lat_mpc.solve_time
    if self.debug_mode:
        lateralPlan.solverCost = self.lat_mpc.cost
        lateralPlan.solverState = log.LateralPlan.SolverState.new_message()
    lateralPlan.solverState.x = self.x_sol.tolist()
    lateralPlan.position.x = self.x_sol[:, 0].tolist()
    lateralPlan.position.y = self.x_sol[:, 1].tolist()
    lateralPlan.position.z = self.path_xyz[:, 2].tolist()
    debugText = ( f"{'lanemode' if self.lanelines_active else 'laneless'} | " +
                  f"{self.LP.lane_width_left:.1f}m | {self.LP.lane_width:.1f}m | {self.LP.lane_width_right:.1f}m | " +
                  f"offset={self.pathOffset * 100:.1f}cm |truck_off={last_truck_offset:.2f}" )
    lateralPlan.latDebugText = debugText
    pm.send('lateralPlan', plan_send)