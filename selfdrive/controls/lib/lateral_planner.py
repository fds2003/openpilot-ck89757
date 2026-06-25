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

# ===================== 【全局优化参数】=====================
LANE_LINE_SOLID_THRESHOLD = 0.3
LANE_CHANGE_SOLID_BLOCK = True
LEFT_TURN_PATH_SUPPRESS = True
SPEED_LOW = 8.0
SPEED_HIGH = 25.0
SPEED_GRID_KPH = [0, 15, 30, 50, 80, 110]
PLAN_GAIN_TABLE = [1.18, 1.12, 1.06, 1.01, 0.95, 0.91]
ANGLE_ERR_THRESH = 10.0
ANGLE_ERR_EXTRA_GAIN = 1.02
RIGHT_TURN_ANGLE_THRESH = 3.2
RIGHT_TURN_CURV_COMP = 1.48
CURV_COMP_SCALE = 1e-4
HIGH_SPEED_DAMP = 0.83
HIGH_SPEED_DAMP_PLUS = 0.89
INTERSECTION_MAX_STEER_RATIO = 0.55

# ========== 路径条安全兜底 ==========
LAST_VALID_PATH_Y = np.zeros(TRAJECTORY_SIZE)
LAST_VALID_PATH_YAW = np.zeros(TRAJECTORY_SIZE)
LAST_STEER_CMD = 0.0
LAST_VALID_X_SOL = np.zeros((TRAJECTORY_SIZE, 4), dtype=np.float32)
TURN_LOCK_TIMEOUT = 2.5
IN_TURN_AVOID_SCALE = 0.28
global_in_turn = False
global_turn_lock_ts = 0.0

LINE_NONE = 0.0
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

# ========== 右转贴边专用 ==========
RIGHT_TURN_SAFE_MARGIN = 0.06
RIGHT_TURN_FIX_OFFSET = -0.08

# ========== 全局轨迹 UI 安全边界 ==========
GLOBAL_Y_MIN = -3.0
GLOBAL_Y_MAX = 3.0

# ========== 障碍物避让全局参数（增强版，不动刹车） ==========
OBSTACLE_MAX_DETECT_LONG = 30.0
OBSTACLE_SMOOTH_ALPHA = 0.35
ONCOMING_SHIFT_MAX = 0.60
PEDESTRIAN_SHIFT_MAX = 0.80
STATIC_OBSTACLE_SHIFT_MAX = 1.20
ROADSIDE_PARKED_SHIFT_MAX = 1.60
OBS_EXTRA_GAIN_MAX = 1.50
OBS_STEER_RATE_DAMP = 0.60
STATIC_CURV_LIMIT_SCALE = 1.15
HIGH_SPEED_NO_AVOID = 80.0 / 3.6

# ========== 导航变道动态参数 ==========
NAV_DYNAMIC_DIST_SHORT = 60
NAV_DYNAMIC_DIST_MID = 100
NAV_DYNAMIC_DIST_LONG = 200
NAV_DYNAMIC_DIST_DEFAULT = 250
NAV_CROSS_JUDGE_DIST = 400
RED_LIGHT_EXTRA_MARGIN = 0.5
NAV_LANE_WIDTH_EXTEND = 0.8

# ========== 红绿灯路口变道权限控制 ==========
IN_INTERSECTION_SOLID_DIST = 80
NAV_RELEASE_EARLY_DIST = 120

# ========== 路边停车检测阈值 ==========
ROADSIDE_DIST_THRESH = 2.2

# ========== 【新增】打灯避让参数 ==========
BLINKER_DELAY_TIME = 0.8
BLINKER_HOLD_TIME = 2.5
MIN_OBS_DIST_TO_BLINK = 25.0

# ========== 【新增】汇入主路提速参数 ==========
MERGE_SPEED_BOOST = 12.0
MERGE_TRIGGER_DIST = 180.0
MERGE_MIN_SPEED = 75.0


def is_nav_active():
    global last_nav_update, nav_hold_mode, g_narrow_road, g_big_cross, g_near_edge, g_nav_gain, g_has_right_truck, g_truck_left_offset
    try:
        from openpilot.selfdrive.carrot.amap_navi import NAV_ACTIVE, NAV_LAST_UPDATE, NAV_MSG_DATA
        now = time.time()
        g_narrow_road = NAV_MSG_DATA.get("is_narrow_road", False)
        g_big_cross = NAV_MSG_DATA.get("is_big_cross", False)
        g_near_edge = NAV_MSG_DATA.get("near_road_edge", False)
        g_nav_gain = NAV_MSG_DATA.get("navi_correct_gain", 0.9)
        g_has_right_truck = NAV_MSG_DATA.get("has_right_big_truck", False)
        g_truck_left_offset = NAV_MSG_DATA.get("truck_left_offset", 0.0)
        if NAV_ACTIVE and (now - NAV_LAST_UPDATE) <= NAV_TIMEOUT:
            last_nav_update = now
            nav_hold_mode = True
            return True
        if nav_hold_mode and (now - last_nav_update) <= 2.0:
            return True
        nav_hold_mode = False
        return False
    except Exception:
        g_narrow_road = False
        g_big_cross = False
        g_near_edge = False
        g_nav_gain = 0.9
        g_has_right_truck = False
        g_truck_left_offset = 0.0
        return False


def get_nav_cross_info():
    try:
        from openpilot.selfdrive.carrot.amap_navi import NAV_MSG_DATA
        cross_total_len = NAV_MSG_DATA.get("cross_total_length", 0)
        cross_remain_dist = NAV_MSG_DATA.get("cross_remain_dist", 9999)
        turn_dir = NAV_MSG_DATA.get("turn_dir", 0.0)
        has_target_lane = NAV_MSG_DATA.get("has_target_lane", False)
        is_short_cross = cross_total_len < 150
        is_mid_cross = 150 <= cross_total_len < 300
        return cross_total_len, cross_remain_dist, turn_dir, has_target_lane, is_short_cross, is_mid_cross
    except Exception:
        return 0.0, 9999, 0.0, False, False, False


def is_turn_active():
    try:
        from openpilot.selfdrive.carrot.amap_navi import NAV_MSG_DATA
        return NAV_MSG_DATA.get("turn_active", 0) == 1
    except Exception:
        return False


def is_u_turn():
    try:
        from openpilot.selfdrive.carrot.amap_navi import NAV_MANEUVER
        return NAV_MANEUVER == 'uTurn'
    except Exception:
        return False


def is_left_turn():
    try:
        from openpilot.selfdrive.carrot.amap_navi import NAV_MANEUVER, NAV_MSG_DATA
        big_cross_left = NAV_MSG_DATA.get("is_big_cross", False) and NAV_MSG_DATA.get("turn_dir", 0.0) == 1
        return NAV_MANEUVER in ("turnLeft", "rampLeft") or big_cross_left
    except Exception:
        return False


def is_right_turn():
    try:
        from openpilot.selfdrive.carrot.amap_navi import NAV_MANEUVER, NAV_MSG_DATA
        big_cross_right = NAV_MSG_DATA.get("is_big_cross", False) and NAV_MSG_DATA.get("turn_dir", 0.0) == 2
        return NAV_MANEUVER in ("turnRight", "rampRight") or big_cross_right
    except Exception:
        return False


def check_solid_lane_line(md):
    try:
        left_solid = md.laneLines[0].isSolid and md.laneLines[0].prob > LANE_LINE_SOLID_THRESHOLD
        right_solid = md.laneLines[1].isSolid and md.laneLines[1].prob > LANE_LINE_SOLID_THRESHOLD
        return left_solid or right_solid
    except Exception:
        return False


def is_intersection_left_turn(sm):
    md = sm['modelV2']
    desire = md.meta.desire
    is_inter = g_big_cross or g_narrow_road
    return is_inter and desire == log.Desire.turnLeft


def get_divide_line_type(md):
    try:
        left_line = md.laneLines[0]
        is_yellow = left_line.color == log.LaneLineColor.yellow
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


def estimate_turn_angle(md):
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
        self.last_cloudlog_t = 0.0
        self.solution_invalid_cnt = 0.0
        self.path_xyz = np.zeros((TRAJECTORY_SIZE, 3))
        self.velocity_xyz = np.zeros((TRAJECTORY_SIZE, 3))
        self.v_plan = np.zeros((TRAJECTORY_SIZE,))
        self.x_sol = np.zeros((TRAJECTORY_SIZE, 4), dtype=np.float32)
        self.v_ego = MIN_SPEED
        self.l_lane_change_prob = 0.0
        self.r_lane_change_prob = 0.0
        self.debug_mode = debug
        self.params = Params()
        self.latDebugText = ""
        self.LP = LanePlanner()
        self.readParams = 0.0
        self.lanelines_active = False
        self.lanelines_active_tmp = False
        self.useLaneLineSpeedApply = self.params.get_int("UseLaneLineSpeed")
        self.pathOffset = float(self.params.get_int("PathOffset")) * 0.01
        self.useLaneLineMode = False
        self.plan_a = np.zeros((TRAJECTORY_SIZE,))
        self.plan_yaw = np.zeros((TRAJECTORY_SIZE,))
        self.plan_yaw_rate = np.zeros((TRAJECTORY_SIZE,))
        self.t_idxs = np.arange(TRAJECTORY_SIZE)
        self.y_pts = np.zeros((TRAJECTORY_SIZE,))
        self.d_path_w_lines_xyz = np.zeros((TRAJECTORY_SIZE, 3))
        self.lat_mpc = LateralMpc()
        self.reset_mpc(np.zeros(4))
        self.curve_speed = 0.0
        self.lanemode_possible_count = 0.0
        self.laneless_only = True
        self.lookahead_time = 2.8
        self.min_path_length = 200

        self.obs_target_offset = 0.0
        self.obs_smooth_offset = 0.0
        self.obs_curv_gain = 1.0
        self.obs_closest_dist = float("inf")
        self.has_static_obstacle = False
        self.has_roadside_parked = False
        self.default_steering_rate_cost = STEERING_RATE_COST

        self.nav_release_dist = NAV_DYNAMIC_DIST_DEFAULT
        self.nav_last_turn_dir = 0.0
        self.nav_lane_extended = False

        self.blinker_request_ts = 0.0
        self.blinker_active = False
        self.blinker_dir = 0.0
        self.blinker_delay_ts = 0.0
        self.blinker_hold_ts = 0.0
        self.avoidance_active = False

        self.merge_boost = 0.0

    def reset_mpc(self, x0=None):
        if x0 is None:
            x0 = np.zeros(4)
        self.x0 = x0
        self.lat_mpc.reset(x0=self.x0)

    def _calc_obstacle_avoid_param(self, carrot):
        target_offset = 0.0
        curv_gain = 1.0
        min_dist = float("inf")
        has_static = False
        has_roadside_parked = False
        try:
            obs_list = carrot.obstacles
        except Exception:
            self.obs_target_offset = 0.0
            self.obs_curv_gain = 1.0
            self.obs_closest_dist = float("inf")
            self.has_static_obstacle = False
            self.has_roadside_parked = False
            return

        for obs in obs_list:
            try:
                d_long = float(obs.longDistance)
                d_lat = float(obs.latDistance)
                o_type = str(obs.type)
            except Exception:
                continue

            if d_long > OBSTACLE_MAX_DETECT_LONG or d_long < 0.5:
                continue

            dist_scale = max(0.0, 1.0 - d_long / OBSTACLE_MAX_DETECT_LONG)
            min_dist = min(min_dist, d_long)

            if o_type in ("parked", "static") and abs(d_lat) < ROADSIDE_DIST_THRESH:
                has_roadside_parked = True
                dir_sign = 1.0 if d_lat > 0 else -1.0
                shift = dir_sign * ROADSIDE_PARKED_SHIFT_MAX * dist_scale
                curv_gain = 1.0
            elif o_type == "oncoming":
                shift = -ONCOMING_SHIFT_MAX * dist_scale
                curv_gain = 1.0
            elif o_type in ("pedestrian", "motorcycle"):
                dir_sign = 1.0 if d_lat > 0 else -1.0
                shift = dir_sign * PEDESTRIAN_SHIFT_MAX * dist_scale
                curv_gain = 1.0
            elif o_type in ("static", "parked", "unknown"):
                has_static = True
                dir_sign = 1.0 if d_lat > 0 else -1.0
                shift = dir_sign * STATIC_OBSTACLE_SHIFT_MAX * dist_scale
                curv_gain = 1.0
            else:
                shift = 0.0
                curv_gain = 1.0

            target_offset += shift
            curv_gain *= curv_gain

        target_offset = np.clip(target_offset, -1.5, 1.5)
        self.obs_smooth_offset = OBSTACLE_SMOOTH_ALPHA * target_offset + (1 - OBSTACLE_SMOOTH_ALPHA) * self.obs_smooth_offset
        self.obs_target_offset = self.obs_smooth_offset
        self.obs_curv_gain = np.clip(curv_gain, 1.0, OBS_EXTRA_GAIN_MAX)
        self.obs_closest_dist = min_dist
        self.has_static_obstacle = has_static
        self.has_roadside_parked = has_roadside_parked

    def _calc_nav_dynamic_release(self, sm):
        cross_total_len, cross_remain_dist, turn_dir, has_target_lane, is_short_cross, is_mid_cross = get_nav_cross_info()
        release_dist = NAV_DYNAMIC_DIST_DEFAULT

        if cross_total_len > 0:
            if is_short_cross:
                release_dist = NAV_DYNAMIC_DIST_SHORT
            elif is_mid_cross:
                release_dist = NAV_DYNAMIC_DIST_MID
            else:
                release_dist = NAV_DYNAMIC_DIST_LONG

        if g_big_cross:
            release_dist = max(release_dist, NAV_DYNAMIC_DIST_MID)
        if g_narrow_road:
            release_dist = max(release_dist, NAV_DYNAMIC_DIST_MID)

        self.nav_release_dist = release_dist
        self.nav_last_turn_dir = turn_dir
        need_extend = has_target_lane and cross_remain_dist < (release_dist + 50)
        return need_extend, turn_dir

    def _calc_merge_speed_boost(self):
        try:
            from openpilot.selfdrive.carrot.amap_navi import NAV_MSG_DATA
            turn_active = NAV_MSG_DATA.get("turn_active", 0) == 1
            cross_remain_dist = NAV_MSG_DATA.get("cross_remain_dist", 9999)
            speed_limit = NAV_MSG_DATA.get("speed_limit", 0)
            is_ramp = NAV_MSG_DATA.get("is_ramp", False)

            ramp_to_highway = is_ramp and speed_limit > 80

            if turn_active and ramp_to_highway:
                if cross_remain_dist < MERGE_TRIGGER_DIST:
                    return MERGE_SPEED_BOOST
            return 0.0
        except Exception:
            return 0.0

    def update(self, sm, carrot):
        global LATERAL_ACCEL_COST, LATERAL_JERK_COST, STEERING_RATE_COST
        global g_narrow_road, g_big_cross, g_near_edge, g_nav_gain, g_has_right_truck, g_truck_left_offset
        global last_truck_offset, smooth_y_prev, smooth_yaw_prev
        global LAST_VALID_PATH_Y, LAST_VALID_PATH_YAW, LAST_STEER_CMD, LAST_VALID_X_SOL
        global global_in_turn, global_turn_lock_ts

        now_ts = time.time()
        high_speed_mode = self.v_ego > HIGH_SPEED_NO_AVOID

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
            self.default_steering_rate_cost = STEERING_RATE_COST

        if high_speed_mode:
            self.obs_target_offset = 0.0
            self.obs_smooth_offset = 0.0
            self.obs_curv_gain = 1.0
            self.obs_closest_dist = float("inf")
            self.has_static_obstacle = False
            self.has_roadside_parked = False
        else:
            self._calc_obstacle_avoid_param(carrot)

        measured_curvature = sm['controlsState'].curvature
        v_ego_car = sm['carState'].vEgo
        self.curve_speed = sm['carrotMan'].vTurnSpeed
        v_kph = v_ego_car * 3.6
        speed_steer_gain = float(np.interp(v_kph, SPEED_GRID_KPH, PLAN_GAIN_TABLE))

        if not high_speed_mode and self.obs_closest_dist < OBSTACLE_MAX_DETECT_LONG:
            obs_extra_gain = 1.0 + max(0.0, (OBSTACLE_MAX_DETECT_LONG - self.obs_closest_dist) / OBSTACLE_MAX_DETECT_LONG * 0.4)
        else:
            obs_extra_gain = 1.0

        try:
            act_steer_deg = sm['carState'].steeringAngleDeg
            des_steer_deg = self.lat_mpc.x_sol[0, 3] * 180 / np.pi
            angle_err = abs(des_steer_deg - act_steer_deg)
            if angle_err > ANGLE_ERR_THRESH:
                speed_steer_gain *= ANGLE_ERR_EXTRA_GAIN
        except Exception:
            angle_err = 0.0
            des_steer_deg = 0.0

        right_turn_comp = 0.0
        if des_steer_deg > RIGHT_TURN_ANGLE_THRESH:
            right_turn_comp = RIGHT_TURN_CURV_COMP

        blinker_gain = 0.70 if self.blinker_active else 1.0

        measured_curvature *= speed_steer_gain * self.obs_curv_gain * obs_extra_gain * blinker_gain
        measured_curvature += right_turn_comp * CURV_COMP_SCALE

        nav_active = is_nav_active()
        uturn_active = is_u_turn()
        right_turn_active = is_right_turn()
        left_turn_active = is_left_turn()
        turn_locked = is_turn_active()

        if turn_locked:
            global_in_turn = True
            global_turn_lock_ts = now_ts
        if global_in_turn and (now_ts - global_turn_lock_ts) > TURN_LOCK_TIMEOUT:
            global_in_turn = False

        if nav_active and (right_turn_active or left_turn_active or g_big_cross or turn_locked):
            self.lat_mpc.nav_gain = 1.45
        else:
            self.lat_mpc.nav_gain = 1.0

        temp_path_cost = self.lateralPathCost

        if not high_speed_mode and self.has_static_obstacle and self.obs_closest_dist < 20.0:
            temp_steer_rate_cost = self.default_steering_rate_cost * OBS_STEER_RATE_DAMP * speed_steer_gain
        elif not high_speed_mode and self.obs_closest_dist < 25.0:
            temp_steer_rate_cost = self.default_steering_rate_cost * 0.7 * speed_steer_gain
        else:
            temp_steer_rate_cost = self.default_steering_rate_cost * speed_steer_gain

        self.merge_boost = self._calc_merge_speed_boost()

        if (g_narrow_road or g_big_cross or g_near_edge) and self.v_ego > 40:
            temp_path_cost = self.lateralPathCost * g_nav_gain

        v100 = 100 / 3.6
        v110 = 110 / 3.6
        v120 = 120 / 3.6
        if v100 <= self.v_ego <= v120 and self.obs_closest_dist >= 25:
            steer_mod = np.interp(self.v_ego, [v100, v110, v120], [1.01, 0.99, 1.00])
            path_mod = np.interp(self.v_ego, [v100, v110, v120], [0.94, 0.86, 0.88])
            temp_steer_rate_cost = self.default_steering_rate_cost * steer_mod * speed_steer_gain
            temp_path_cost = temp_path_cost * path_mod * speed_steer_gain
        elif self.v_ego > v120 and self.obs_closest_dist >= 25:
            temp_steer_rate_cost = self.default_steering_rate_cost * 1.00 * speed_steer_gain
            temp_path_cost *= 0.87 * speed_steer_gain
        else:
            temp_path_cost *= speed_steer_gain

        # ========== ✅ 修改 1：大幅放宽最大曲率 ==========
        base_max_curv = 0.055 if (left_turn_active or right_turn_active or g_big_cross or global_in_turn) else 0.042
        if self.has_static_obstacle:
            curr_max_curv = base_max_curv * STATIC_CURV_LIMIT_SCALE
        else:
            curr_max_curv = base_max_curv
        measured_curvature = np.clip(measured_curvature, -curr_max_curv, curr_max_curv)

        # ========== ✅ 修改 2：低速限幅大幅放宽 ==========
        if self.v_ego < 30:
            measured_curvature = np.clip(measured_curvature, -0.032, 0.032)

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

            vkph = self.v_ego * 3.6
            if left_turn_active or right_turn_active or g_big_cross:
                smooth_alpha = 0.11
            elif vkph > 100:
                smooth_alpha = 0.80
            elif vkph > 40:
                smooth_alpha = 0.45
            else:
                smooth_alpha = 0.22

            smooth_y = smooth_alpha * smooth_y_prev + (1 - smooth_alpha) * raw_y
            smooth_yaw = smooth_alpha * smooth_yaw_prev + (1 - smooth_alpha) * raw_yaw
            smooth_y_prev = smooth_y.copy()
            smooth_yaw_prev = smooth_yaw.copy()

            self.path_xyz[:, 1] = smooth_y
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
                self.lanemode_possible_count = 0.0
                self.laneless_only = True
            else:
                self.lanemode_possible_count += 1
                if self.lanemode_possible_count > int(1 / DT_MDL):
                    self.laneless_only = False
        else:
            self.path_xyz[:, 1] = LAST_VALID_PATH_Y
            self.plan_yaw = LAST_VALID_PATH_YAW

        if self.merge_boost > 0:
            self.v_plan = np.clip(self.v_plan + self.merge_boost / 3.6, MIN_SPEED, np.inf)
            self.v_ego = self.v_plan[0]

        self.LP.parse_model(md)

        if global_in_turn and not high_speed_mode:
            self.LP.obstacle_avoid_scale = 0.6
        elif global_in_turn:
            self.LP.obstacle_avoid_scale = 1.0
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

        if global_in_turn and not right_turn_active and not left_turn_active:
            final_scale *= 0.97
            final_total_margin += 0.02

        is_left_turn_scene = is_intersection_left_turn(sm)
        if is_left_turn_scene or left_turn_active:
            final_scale *= LEFT_TURN_ADD_SCALE
            final_total_margin += LEFT_TURN_EXTRA_LEFT_MARGIN

        self.path_xyz[:, 1] *= final_scale

        try:
            result = self.LP.get_d_path(
                sm['carState'], self.v_ego, self.t_idxs, self.path_xyz, self.curve_speed
            )
            if isinstance(result, tuple) and len(result) == 2:
                self.path_xyz, self.lanelines_active = result
            else:
                self.path_xyz = result
                self.lanelines_active = False
        except Exception:
            self.lanelines_active = False

        lane_left_bound = -(lane_w_left / 2.0)
        lane_right_bound = lane_w_right / 2.0
        safe_left = lane_left_bound + final_total_margin + 0.04
        safe_right = lane_right_bound - curr_margin

        if left_turn_active or is_left_turn_scene:
            safe_left += 0.16
            self.path_xyz[:, 1] -= 0.06
        if right_turn_active:
            safe_right = lane_right_bound - RIGHT_TURN_SAFE_MARGIN
            self.path_xyz[:, 1] += RIGHT_TURN_FIX_OFFSET
        if is_left_turn_scene or left_turn_active:
            safe_left += 0.05

        if not high_speed_mode:
            if self.has_roadside_parked:
                if self.obs_closest_dist < 15.0:
                    safe_left -= 1.0
                    safe_right += 1.0
                elif self.obs_closest_dist < 25.0:
                    safe_left -= 0.7
                    safe_right += 0.7
                final_total_margin *= 0.4
            elif self.has_static_obstacle:
                if self.obs_closest_dist < 20.0:
                    safe_left -= 0.5
                    safe_right += 0.5
                elif self.obs_closest_dist < 30.0:
                    safe_left -= 0.3
                    safe_right += 0.3

        self.path_xyz[:, 1] = np.clip(self.path_xyz[:, 1], safe_left, safe_right)
        self.path_xyz[:, 1] = np.clip(self.path_xyz[:, 1], GLOBAL_Y_MIN, GLOBAL_Y_MAX)
        LAST_VALID_PATH_Y = self.path_xyz[:, 1].copy()

        if nav_active:
            need_extend, turn_dir = self._calc_nav_dynamic_release(sm)
            if need_extend:
                if turn_dir == 1:
                    safe_left -= NAV_LANE_WIDTH_EXTEND
                elif turn_dir == 2:
                    safe_right += NAV_LANE_WIDTH_EXTEND
                self.nav_lane_extended = True
            else:
                self.nav_lane_extended = False
        else:
            self.nav_lane_extended = False

        # ========== 【新增】障碍物避让打灯逻辑（不破坏原导航变道打灯）==========
        want_blinker = False
        blinker_dir = 0.0

        if not high_speed_mode and self.obs_closest_dist < MIN_OBS_DIST_TO_BLINK:
            if self.has_roadside_parked or self.has_static_obstacle:
                want_blinker = True
                blinker_dir = 1 if self.obs_smooth_offset > 0 else -1

        if want_blinker:
            if not self.blinker_active:
                self.blinker_active = True
                self.blinker_dir = blinker_dir
                self.blinker_delay_ts = now_ts + BLINKER_DELAY_TIME
                self.blinker_request_ts = now_ts
            # 持续续期 hold_ts，障碍物消失后自然过期
            self.blinker_hold_ts = now_ts + BLINKER_HOLD_TIME
            # 通过 carrot_serv.set_blinker_request 发送打灯信号（与导航变道共用 ext_blinker 通道）
            try:
                carrot.carrot_serv.set_blinker_request(int(self.blinker_dir))
            except Exception:
                pass
        else:
            # 障碍物消失，等 hold_ts 过期后重置状态并熄灭转向灯
            if self.blinker_active and now_ts > self.blinker_hold_ts:
                self.blinker_active = False
                self.avoidance_active = False
                try:
                    carrot.carrot_serv.set_blinker_request(0)
                except Exception:
                    pass

        if self.blinker_active:
            if now_ts >= self.blinker_delay_ts:
                self.avoidance_active = True
            else:
                self.avoidance_active = False
        else:
            self.avoidance_active = False

        # 避让激活时用全量偏移，否则仅 20%
        if self.avoidance_active:
            final_offset = self.pathOffset - last_truck_offset + self.obs_smooth_offset
        else:
            final_offset = self.pathOffset - last_truck_offset + self.obs_smooth_offset * 0.2
        # ========== 【新增结束】 ==========

        solid_line_block = LANE_CHANGE_SOLID_BLOCK and check_solid_lane_line(md)

        if solid_line_block:
            self.LP.lane_change_multiplier = 0.0
        elif nav_active:
            cross_total_len, cross_remain_dist, turn_dir, has_target_lane, is_short_cross, is_mid_cross = get_nav_cross_info()
            release_dist = self.nav_release_dist

            if cross_remain_dist > release_dist:
                self.LP.lane_change_multiplier = 0.0
            else:
                if md.meta.desire != log.Desire.none or carrot.atc_active:
                    self.LP.lane_change_multiplier = 1.0
                else:
                    self.LP.lane_change_multiplier = 0.0
        else:
            if md.meta.desire != log.Desire.none or carrot.atc_active:
                self.LP.lane_change_multiplier = 1.0
            else:
                self.LP.lane_change_multiplier = 0.0

        if self.v_ego < 18:
            self.useLaneLineMode = False
        else:
            if self.useLaneLineSpeedApply == 0 or self.laneless_only:
                self.useLaneLineMode = False
            else:
                self.useLaneLineMode = True

        curvature = measured_curvature
        if right_turn_active:
            curvature *= 1.15
        if left_turn_active:
            curvature *= 1.12

        if 0.0006 < abs(curvature) < 0.0015 and self.v_ego < 30:
            curvature = np.sign(curvature) * 0.0018
        if abs(curvature) >= 0.0015 and self.v_ego < 30:
            curvature *= 1.55
        if abs(curvature) >= 0.0012 and 30 <= self.v_ego < 50:
            curvature *= 1.22

        self.LP.curvature = curvature

        if nav_active:
            cross_total_len, cross_remain_dist, turn_dir, has_target_lane, is_short_cross, is_mid_cross = get_nav_cross_info()
            if 0 < cross_remain_dist < IN_INTERSECTION_SOLID_DIST:
                self.LP.lane_change_multiplier = 0.0

        self.LP.lanefull_mode = self.useLaneLineMode
        self.LP.lane_width_left = md.meta.laneWidthLeft
        self.LP.lane_width_right = md.meta.laneWidthRight
        self.LP.curvature = curvature

        delta = g_truck_left_offset - last_truck_offset
        delta = np.clip(delta, -0.04, 0.04)
        last_truck_offset += delta

        try:
            from selfdrive.car.toyota.values import LANE_OFFSET
            if abs(LANE_OFFSET) > 0.001:
                self.path_xyz[:, 1] += LANE_OFFSET
        except Exception:
            pass

        if right_turn_active or left_turn_active:
            final_offset = 0.0 - last_truck_offset + self.obs_smooth_offset
        else:
            final_offset = self.pathOffset - last_truck_offset + self.obs_smooth_offset

        final_offset = np.clip(final_offset, -0.6, 0.6)
        self.path_xyz[:, 1] += final_offset
        self.path_xyz[:, 1] = np.clip(self.path_xyz[:, 1], GLOBAL_Y_MIN, GLOBAL_Y_MAX)
        LAST_VALID_PATH_Y = self.path_xyz[:, 1].copy()

        # ========== ✅ 修改 3：高速锁舵软化（不再焊死） ==========
        HIGH_SPEED_LOCK = 80 / 3.6
        CURV_LOCK = 0.0006
        if self.v_ego > HIGH_SPEED_LOCK and abs(measured_curvature) < CURV_LOCK:
            self.x_sol[:, 3] = 0.85 * self.x_sol[:, 3] + 0.15 * np.full_like(self.x_sol[:, 3], self.x_sol[0, 3])

        if uturn_active:
            self.lat_mpc.set_weights(1.5, 2.4, 1.0, 0.7, 1.2, True, False, self.v_ego > 100 / 3.6, self.v_ego * 3.6)
        else:
            if self.v_ego > 100 / 3.6:
                self.lat_mpc.set_weights(
                    temp_path_cost * 0.85,
                    self.lateralMotionCost * 1.2,
                    LATERAL_ACCEL_COST * 1.5,
                    LATERAL_JERK_COST * 2.0,
                    temp_steer_rate_cost * 1.1,
                    False,
                    True,
                    self.v_ego * 3.6
                )
            else:
                self.lat_mpc.set_weights(
                    temp_path_cost,
                    self.lateralMotionCost,
                    LATERAL_ACCEL_COST,
                    LATERAL_JERK_COST,
                    temp_steer_rate_cost,
                    False,
                    False,
                    self.v_ego * 3.6
                )

        self.y_pts = self.path_xyz[:LAT_MPC_N + 1, 1]
        heading_pts = self.plan_yaw[:LAT_MPC_N + 1]
        yaw_rate_pts = self.plan_yaw_rate[:LAT_MPC_N + 1]

        lateral_factor = np.clip(self.factor1 - (self.factor2 * self.v_plan ** 2), 0.0, np.inf)
        p = np.column_stack([self.v_plan, lateral_factor])

        try:
            self.lat_mpc.run(self.x0, p, self.y_pts, heading_pts, yaw_rate_pts)
            if not np.all(np.isfinite(self.lat_mpc.x_sol)):
                raise ValueError("MPC NaN")
            self.x_sol = self.lat_mpc.x_sol.copy()
            LAST_VALID_X_SOL = self.x_sol.copy()
            self.solution_invalid_cnt = 0.0
        except Exception as e:
            cloudlog.warning("MPC solve exception, using fallback: %s", str(e))
            self.x_sol = LAST_VALID_X_SOL.copy()
            self.solution_invalid_cnt = min(self.solution_invalid_cnt + 1, 5)

        current_steer = self.x_sol[0, 3]
        if self.v_ego >= SPEED_HIGH:
            if self.v_ego >= 110 / 3.6:
                current_steer = HIGH_SPEED_DAMP_PLUS * LAST_STEER_CMD + (1 - HIGH_SPEED_DAMP_PLUS) * current_steer
            else:
                current_steer = HIGH_SPEED_DAMP * LAST_STEER_CMD + (1 - HIGH_SPEED_DAMP) * current_steer
        LAST_STEER_CMD = current_steer

        # ========== ✅ 修改 4：方向盘输出限幅大幅放宽 ==========
        if self.v_ego < 30:
            current_steer = np.clip(current_steer, -0.93, 0.93)   # ≈ 53°
        else:
            current_steer = np.clip(current_steer, -0.68, 0.68)   # ≈ 39°

        self.x_sol[:, 3] = current_steer
        self.x0[3] = np.interp(DT_MDL, self.t_idxs[:LAT_MPC_N + 1], self.x_sol[:, 3])

        mpc_nans = np.isnan(self.x_sol[:, 3]).any()
        t = time.monotonic()
        if mpc_nans or self.lat_mpc.solution_status != 0:
            self.reset_mpc()
            self.x0[3] = measured_curvature * self.v_ego
            if t > self.last_cloudlog_t + 5.0:
                self.last_cloudlog_t = t
        if self.lat_mpc.cost > 1e6 or mpc_nans:
            self.solution_invalid_cnt += 1
        else:
            self.solution_invalid_cnt = 0.0

    def publish(self, sm, pm, carrot):
        plan_solution_valid = self.solution_invalid_cnt < 1
        plan_send = messaging.new_message('lateralPlan')
        plan_send.valid = sm.all_checks(service_list=['carState', 'controlsState', 'modelV2'])
        lateralPlan = plan_send.lateralPlan
        lateralPlan.modelMonoTime = sm.logMonoTime['modelV2']

        path_y = self.path_xyz[:, 1].copy()
        path_y = np.clip(path_y, GLOBAL_Y_MIN, GLOBAL_Y_MAX)
        lateralPlan.dPathPoints = path_y.tolist()

        lateralPlan.psis = self.x_sol[0:CONTROL_N, 2].tolist()
        lateralPlan.distances = self.x_sol[0:CONTROL_N, 0].tolist()

        if len(self.v_plan) == TRAJECTORY_SIZE:
            lateralPlan.curvatures = (self.x_sol[0:CONTROL_N, 3] / self.v_plan[0:CONTROL_N]).tolist()
        else:
            lateralPlan.curvatureRates = [
                float(x / self.v_ego) for x in self.lat_mpc.u_sol.flatten().tolist()
            ] + [0.0]

        lateralPlan.mpcSolutionValid = bool(plan_solution_valid)
        lateralPlan.solverExecutionTime = self.lat_mpc.solve_time

        if self.debug_mode:
            lateralPlan.solverCost = self.lat_mpc.cost
            lateralPlan.solverState = log.LateralPlan.SolverState.new_message()
            lateralPlan.solverState.x = self.x_sol.tolist()

        lateralPlan.position.x = self.x_sol[:, 0].tolist()
        lateralPlan.position.y = path_y.tolist()
        lateralPlan.position.z = self.path_xyz[:, 2].tolist()

        debugText = (
            f"{'lanemode' if self.lanelines_active else 'laneless'} | "
            f"obs={self.obs_closest_dist:.1f}m parked={self.has_roadside_parked} | "
            f"blink={self.blinker_active} hold={self.avoidance_active} | "
            f"merge_boost={self.merge_boost:.1f}km/h | "
            f"offset={self.obs_smooth_offset:.2f}"
        )
        lateralPlan.latDebugText = debugText
        pm.send('lateralPlan', plan_send)
