import time
import numpy as np
from openpilot.common.realtime import DT_MDL
from openpilot.common.swaglog import cloudlog
from .curve_sync import CurveSync
try:
    from openpilot.selfdrive.controls.lib.lateral_mpc_lib.lat_mpc import LateralMpc as _RealLateralMpc
    from openpilot.selfdrive.controls.lib.lateral_mpc_lib.lat_mpc import N as LAT_MPC_N
    LateralMpc = _RealLateralMpc
except Exception:
    if "LateralMpc" not in globals():
        class LateralMpc:
            def __init__(self): pass
            def reset(self, x0): pass
            def update(self, *a, **k): pass
            def set_weights(self, *a, **k): pass
            def run(self, *a, **k): pass
            x_sol = np.zeros((33, 4), dtype=np.float32)
            u_sol = np.zeros((33, 1), dtype=np.float32)
            solve_time = 0.0
            solution_status = 0
            cost = 0.0
            nav_gain = 1.0
    if "LAT_MPC_N" not in globals():
        LAT_MPC_N = 33
try:
    from openpilot.selfdrive.controls.lib.drive_helpers import CONTROL_N, MIN_SPEED, get_speed_error
except Exception:
    if "CONTROL_N" not in globals():
        CONTROL_N = 33
    if "MIN_SPEED" not in globals():
        MIN_SPEED = 0.001
    if "get_speed_error" not in globals():
        def get_speed_error(*a, **k): return 0.0
try:
    from openpilot.common.params import Params as _Params_rt
    def _set_right_turn_early(flag):
        try:
            _Params_rt().put_bool("RightTurnEarly", bool(flag))
        except Exception:
            pass
except Exception:
    def _set_right_turn_early(flag):
        pass
import cereal.messaging as messaging
from cereal import log
from openpilot.common.params import Params
try:
    from openpilot.selfdrive.controls.lib.lane_planner_2 import LanePlanner as _RealLanePlanner
    LanePlanner = _RealLanePlanner
except Exception:
    if "LanePlanner" not in globals():
        class LanePlanner:
            def __init__(self): pass
            def parse_model(self, md): pass
            def get_d_path(self, *a, **k): return None
            obstacle_avoid_scale = 1.0
            lane_change_multiplier = 0.0
            lanefull_mode = False
            lane_width_left = 3.7
            lane_width_right = 3.7
            curvature = 0.0
try:
    from openpilot.selfdrive.carrot.carrot_serv import (
        get_carrot_serv_instance, BLINKER_LEFT, BLINKER_RIGHT, BLINKER_NONE,
    )
except Exception:
    get_carrot_serv_instance = lambda: None
    BLINKER_LEFT, BLINKER_RIGHT, BLINKER_NONE = 1, 2, 0
from collections import deque

TRAJECTORY_SIZE = 33
CAMERA_OFFSET = 0.04
PATH_COST = 1.0
LATERAL_MOTION_COST = 0.11
LATERAL_ACCEL_COST = 0.0
LATERAL_JERK_COST = 0.04
STEERING_RATE_COST = 160.0

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
RIGHT_TURN_CURV_COMP = 8.0
CORNERING_ANGLE_THRESH = 25.0
CORNERING_MAX_CURV = 0.062
CORNERING_LOW_SPEED_CLIP = 0.040
CORNERING_CURV_GAIN = 1.28
CURV_COMP_SCALE = 1e-4
HIGH_SPEED_DAMP = 0.83
HIGH_SPEED_DAMP_PLUS = 0.89
INTERSECTION_MAX_STEER_RATIO = 0.55

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

RIGHT_TURN_SAFE_MARGIN = 0.06
RIGHT_TURN_FIX_OFFSET = 0.00

TURN_RAMP_OFFSET_UI = 0.00

TURN_PATH_COST_MULT = 1.1
TURN_MOTION_COST_MULT = 0.85
TURN_STEER_RATE_MULT = 0.90

GLOBAL_Y_MIN = -2.4
GLOBAL_Y_MAX = 2.4
GLOBAL_Y_MAX_EXIT = 2.0

ROAD_EDGE_PROB_THRESH = 0.30
ROAD_EDGE_SAFE_MARGIN = 0.15
DEVIATION_CORRECT_STEP = 0.25
DEVIATION_NORM_THRESH = 0.82
NARROW_ROAD_RIGHT_TURN_MAX_Y = 1.6
ROADEDGE_CENTER_BLEND = 0.35
ROADEDGE_BOUND_ENABLED = True

OBSTACLE_MAX_DETECT_LONG = 30.0
OBSTACLE_SMOOTH_ALPHA = 0.35
ONCOMING_SHIFT_MAX = 0.60
PEDESTRIAN_SHIFT_MAX = 1.20
STATIC_OBSTACLE_SHIFT_MAX = 1.20
ROADSIDE_PARKED_SHIFT_MAX = 1.60
OBS_EXTRA_GAIN_MAX = 1.50
OBS_STEER_RATE_DAMP = 0.60
STATIC_CURV_LIMIT_SCALE = 1.15
HIGH_SPEED_NO_AVOID = 80.0 / 3.6

NAV_DYNAMIC_DIST_SHORT = 60
NAV_DYNAMIC_DIST_MID = 60
NAV_DYNAMIC_DIST_LONG = 200
NAV_DYNAMIC_DIST_DEFAULT = 250
NAV_CROSS_JUDGE_DIST = 400
RED_LIGHT_EXTRA_MARGIN = 0.5
NAV_LANE_WIDTH_EXTEND = 0.8

IN_INTERSECTION_SOLID_DIST = 80
NAV_RELEASE_EARLY_DIST = 120

ROADSIDE_DIST_THRESH = 3.5

BLINKER_DELAY_TIME = 1.5
BLINKER_HOLD_TIME = 2.5
MIN_OBS_DIST_TO_BLINK = 25.0

MERGE_SPEED_BOOST = 12.0
MERGE_TRIGGER_DIST = 180.0
MERGE_MIN_SPEED = 75.0

PUBLISH_RATE_NORMAL = 20
PUBLISH_RATE_CONGESTED = 10
PUBLISH_RATE_PARKED = 5
CONGESTION_VELO_THRESH = 8.0

TURN_EXIT_TRANSITION_TIME = 1.5

LANE_PROB_NARROW_THRESH = 0.40
LANE_FADE_ALPHA = 0.40
LANE_FADE_CURV_GAIN = 1.10

# ★ 低速弯道减速保护阈值（m/s），低于此速度不主动减速
_LOW_SPEED_DECEL_PROTECT = 40.0 / 3.6

# ★ 快速路岔道减速过渡步长（每帧最多降多少 m/s）
_V_DECEL_STEP_FAST = 3.0 / 3.6
# ★ 曲率减速过渡步长
_V_DECEL_STEP_CURV = 2.0 / 3.6


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
    try:
        if is_right_turn():
            return False
    except Exception:
        pass
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


class ObstacleItem:
    def __init__(self, long_dist, lat_dist, o_type, v_rel=0.0, v_lead=0.0):
        self.longDistance = float(long_dist)
        # 避让坐标系：正数为右侧障碍，负数为左侧障碍
        self.latDistance = float(lat_dist)
        self.type = str(o_type)
        self.vRel = float(v_rel)
        self.vLead = float(v_lead)

    def __repr__(self):
        return f"ObstacleItem(long={self.longDistance:.1f}, lat={self.latDistance:.1f}, type={self.type}, vLead={self.vLead:.1f})"


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
        self.plan_yaw = np.zeros((TRAJECTORY_SIZE))
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
        self.has_left_pressure = False
        self.right_avoid_dist_m = 1.0
        self.has_oncoming_traffic = False
        self.last_oncoming_detected_ts = 0.0
        self.passing_obstacle = False
        self.passed_distance = 0.0
        self.last_avoid_offset = 0.0
        self.extracted_obstacles = []
        self.current_safe_left = -1.5
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
        self.blinker_avoid_speed_max = 25.0 / 3.6
        self.blinker_avoid_boost = 0.6
        self.blinker_avoid_min_obs = 0.15

        self.merge_boost = 0.0
        self._last_publish_t = 0.0

        self.curve_speed_limit = 0.0
        self.curve_decel_active = False
        self.curve_decel_speed_kph = 35.0
        self.curve_decel_min_kph = 12.0
        self.curve_decel_curv_thresh = 0.0010
        self.turn_decel_min_kph = 12.0

        self.obs_offset_profile = np.zeros(TRAJECTORY_SIZE)

        self.right_turn_released = True
        self.right_turn_lock_ts = 0.0
        self._exit_reset_alpha = 0.15

        self._steer_active_hyst = False
        self._steer_active_enter_deg = 12.0
        self._steer_active_exit_deg = 6.0

        self.available_road_width = 4.0
        self.left_boost = 1.15
        self.left_smooth_alpha = 0.55
        self.left_gravity = 0.30

        self._rt_path_mem = np.zeros(TRAJECTORY_SIZE)
        self._rt_path_mem_valid = False
        self._rt_curv_mem = 0.0
        self._rt_curv_mem_valid = False
        self._edge_center_offset = 0.0
        self._edge_valid = False
        self._deviation_dir = 0

        self._obs_profile_prev = np.zeros(TRAJECTORY_SIZE)
        self._was_right_turning = False

        self.curve_decel_target_v = 0.0

    def reset_mpc(self, x0=None):
        if x0 is None:
            x0 = np.zeros(4)
        self.x0 = x0
        self.lat_mpc.reset(x0=self.x0)

    def _extract_obstacles_and_oncoming(self, sm):
        """
        从 radarState 与 modelV2 实时提取右侧障碍物（行人、非机动车、故障车辆），
        并全面监测左侧对向车道是否有来车（Oncoming Traffic）。
        """
        obs_list = []
        has_oncoming = False
        v_ego = self.v_ego
        now_ts = time.time()

        # 1. 监测毫米波雷达
        if sm.seen['radarState'] and sm.alive['radarState']:
            rs = sm['radarState']

            # --- A. 监测左侧对向来车 (leadsLeft, leadsLeft2, leadLeft) ---
            left_candidates = []
            if rs.leadLeft.status:
                left_candidates.append(rs.leadLeft)
            for ld in getattr(rs, 'leadsLeft2', []):
                if ld.status:
                    left_candidates.append(ld)
            for ld in getattr(rs, 'leadsLeft', []):
                if ld.status:
                    left_candidates.append(ld)

            for ld in left_candidates:
                d_rel = float(ld.dRel)
                y_rel = float(ld.yRel)
                v_rel = float(ld.vRel)
                v_lead = float(ld.vLead)

                # 左侧区域: y_rel > 0 (雷达坐标系下正数为左)
                # 判定对向来车条件: 距离在75米以内，且对向驶来 (v_rel < -1.5m/s 或 v_lead < -1.0m/s，或 closing 速度明显大于自车速)
                if 2.0 < d_rel < 75.0 and y_rel > 0.3:
                    if v_rel < -1.5 or v_lead < -1.0 or (v_ego > 2.0 and v_rel < -v_ego + 1.0):
                        has_oncoming = True
                        break

            # --- B. 提取右侧障碍物 (leadsRight, leadsRight2, leadRight) ---
            right_candidates = []
            if rs.leadRight.status:
                right_candidates.append(rs.leadRight)
            for ld in getattr(rs, 'leadsRight2', []):
                if ld.status:
                    right_candidates.append(ld)
            for ld in getattr(rs, 'leadsRight', []):
                if ld.status:
                    right_candidates.append(ld)

            seen_pos = []
            for ld in right_candidates:
                d_long = float(ld.dRel)
                y_rel = float(ld.yRel)
                v_rel = float(ld.vRel)
                v_lead = float(ld.vLead)

                # 雷达坐标系下负数为右，转为避让坐标系 d_lat = -y_rel > 0
                d_lat = -y_rel
                if 1.0 < d_long < 42.0 and 0.4 < d_lat < 3.8:
                    # 避免近距离重复目标
                    dup = False
                    for (slong, slat) in seen_pos:
                        if abs(d_long - slong) < 3.5 and abs(d_lat - slat) < 0.8:
                            dup = True
                            break
                    if dup:
                        continue
                    seen_pos.append((d_long, d_lat))

                    # 目标类型判定
                    if abs(v_lead) < 1.5:
                        # 速度极低或静止: 故障车/路边停放车/静止障碍物
                        o_type = "parked" if d_lat > 1.1 else "static"
                    elif 1.5 <= v_lead < 8.5:
                        # 速度在5~30km/h: 行人/自行车/电瓶车等非机动车
                        o_type = "motorcycle" if v_lead > 4.0 else "pedestrian"
                    else:
                        o_type = "car"

                    obs_list.append(ObstacleItem(d_long, d_lat, o_type, v_rel, v_lead))

        # 2. 监测视觉模型 modelV2
        if sm.seen['modelV2'] and sm.alive['modelV2']:
            md = sm['modelV2']
            if len(md.leadsV3) > 0:
                for lead in md.leadsV3:
                    if lead.prob > 0.35 and len(lead.x) > 0 and len(lead.y) > 0:
                        lx = float(lead.x[0])
                        ly = float(lead.y[0])
                        lv = float(lead.v[0]) if len(lead.v) > 0 else 0.0

                        # 视觉坐标系下: ly > 0 为左，ly < 0 为右
                        # 对向来车校验
                        if 3.0 < lx < 65.0 and ly > 0.4:
                            if lv < -1.0 or (v_ego > 2.0 and lv < v_ego * 0.4):
                                has_oncoming = True

                        # 右侧目标补充 (d_lat = -ly > 0)
                        d_lat_v = -ly
                        if 1.5 < lx < 35.0 and 0.5 < d_lat_v < 3.2:
                            dup = False
                            for o in obs_list:
                                if abs(lx - o.longDistance) < 4.0 and abs(d_lat_v - o.latDistance) < 1.0:
                                    dup = True
                                    break
                            if not dup:
                                o_type_v = "parked" if abs(lv) < 1.5 else "motorcycle"
                                obs_list.append(ObstacleItem(lx, d_lat_v, o_type_v, 0.0, lv))

        # 对向来车安全锁定与平滑冷却（维持1.8秒，防止闪烁）
        if has_oncoming:
            self.last_oncoming_detected_ts = now_ts
        self.has_oncoming_traffic = (now_ts - getattr(self, 'last_oncoming_detected_ts', 0.0)) < 1.8

        return obs_list

    def _calc_obstacle_avoid_param(self, carrot, obs_list=None):
        HALF_CAR_WIDTH = 0.925   # 现代库斯途车宽1.85m -> 半宽0.925m
        FAR_DIST = 35.0
        ROADSIDE_DIST_THRESH = 3.5
        OBS_HALF_WIDTH = {
            "pedestrian": 0.35, "motorcycle": 0.45, "bicycle": 0.40,
            "parked": 0.95, "static": 0.75, "car": 0.90, "unknown": 0.60,
        }
        target_offset = 0.0
        curv_gain = 1.0
        min_dist = float("inf")
        has_static = False
        has_roadside_parked = False
        has_left_pressure = False
        max_left_push = 0.0
        max_right_push = 0.0
        profile = np.zeros(TRAJECTORY_SIZE, dtype=np.float64)

        if obs_list is None:
            try:
                obs_list = getattr(self, 'extracted_obstacles', [])
            except Exception:
                obs_list = []

        # 动态安全净距离：从参数读取（默认1.0m，可在80cm~150cm菜单调节）
        D_safe_base = getattr(self, 'right_avoid_dist_m', 1.0)
        D_safe_base = float(np.clip(D_safe_base, 0.70, 1.50))

        closest_obs = None
        for obs in obs_list:
            try:
                d_long = float(obs.longDistance)
                d_lat = float(obs.latDistance)
                o_type = str(obs.type)
            except Exception:
                continue

            if d_long > OBSTACLE_MAX_DETECT_LONG or d_long < 0.5:
                continue

            if d_long < min_dist:
                min_dist = d_long
                closest_obs = obs

            # 区分不同障碍物类型的目标安全净距
            if o_type in ("pedestrian", "motorcycle", "bicycle"):
                # 行人/非机动车：由于摇摆不稳定性，安全净距上浮0.1m
                D_safe = max(D_safe_base, 1.05)
            elif o_type in ("parked", "static"):
                D_safe = D_safe_base
            else:
                D_safe = D_safe_base * 0.9

            obs_hw = OBS_HALF_WIDTH.get(o_type, 0.60)

            # d_lat > 0 表示位于自车右侧
            # 计算自车右边缘与障碍物左边缘之间的真实物理间隙（gap）
            # gap = d_lat - obs_hw - HALF_CAR_WIDTH
            gap = abs(d_lat) - obs_hw - HALF_CAR_WIDTH
            gap_deficit = max(0.0, D_safe - gap)

            # 纵向距离平滑加权 (接近12m以内满响应，至35m平滑衰减)
            dist_weight = float(np.clip(1.0 - (d_long - 12.0) / 23.0, 0.0, 1.0))
            required_shift = gap_deficit * dist_weight

            # 限幅单次最大避让量（不超过0.95m，避免过激转向）
            required_shift = float(np.clip(required_shift, 0.0, 0.95))

            if d_lat >= 0:
                # 右侧障碍物 -> 向左避让 (当前fork坐标系负数为左)
                push = -required_shift
                max_left_push = max(max_left_push, required_shift)
                if d_lat > 0.3:
                    has_left_pressure = True
            else:
                # 左侧障碍物 -> 向右避让 (正数为右)
                push = required_shift
                max_right_push = max(max_right_push, push)

            if o_type in ("parked", "static") and abs(d_lat) < ROADSIDE_DIST_THRESH:
                has_roadside_parked = True
            if o_type in ("static", "parked", "unknown"):
                has_static = True

            idx_center = int(np.clip(d_long / max(FAR_DIST, 1.0) * (TRAJECTORY_SIZE - 1), 0, TRAJECTORY_SIZE - 1))
            span = 4
            i0 = max(0, idx_center - span)
            i1 = min(TRAJECTORY_SIZE, idx_center + span + 1)
            for i in range(i0, i1):
                w = 1.0 - abs(i - idx_center) / (span + 1)
                if push < 0:
                    profile[i] = min(profile[i], push * w)
                else:
                    profile[i] = max(profile[i], push * w)

        now_ts = time.time()
        # ===== 超车并排保持 (Pass-by Hold) 与 通过后立即回中 (Immediate Return) =====
        dt = DT_MDL
        if min_dist < 3.5 and closest_obs is not None:
            # 障碍物进入车头近区 -> 启动超车保持状态
            self.passing_obstacle = True
            self.passed_distance = 0.0
            self.last_avoid_offset = -max_left_push if max_left_push > 0 else (max_right_push if max_right_push > 0 else self.obs_smooth_offset)
        elif self.passing_obstacle:
            # 车身正在掠过障碍物：前雷达视野可能丢失，此时积分车身位移
            self.passed_distance += max(self.v_ego, 0.5) * dt
            # 车长约4.8m，位移超过5.2m说明车尾已完全通过障碍物
            if self.passed_distance < 5.2:
                # 依然在侧面掠过期间，维持之前的避让偏移量
                if abs(self.last_avoid_offset) > 0.10:
                    if self.last_avoid_offset < 0:
                        max_left_push = max(max_left_push, abs(self.last_avoid_offset))
                    else:
                        max_right_push = max(max_right_push, self.last_avoid_offset)
            else:
                # 完全越过障碍物！立即结束超车保持状态
                self.passing_obstacle = False
                self.passed_distance = 0.0

        if max_left_push > 0:
            target_offset = -max_left_push
        elif max_right_push > 0:
            target_offset = max_right_push
        else:
            target_offset = 0.0

        # 限幅目标偏置量
        target_offset = np.clip(target_offset, -1.2, 1.2)

        # 滤波平滑：
        # 如果当前需要避让 (target_offset != 0)，平滑介入
        # 如果已经通过障碍物 (target_offset == 0)，“通过障碍物后，立即回到自己的车道居中行驶”
        if abs(target_offset) < 0.02:
            # 立即回中：采用高滤波响应速率 (alpha = 0.45)，约0.8秒完全居中
            _smooth_alpha = 0.45
            self.obs_smooth_offset = _smooth_alpha * 0.0 + (1 - _smooth_alpha) * self.obs_smooth_offset
            if abs(self.obs_smooth_offset) < 0.03:
                self.obs_smooth_offset = 0.0
        else:
            _smooth_alpha = self.left_smooth_alpha if target_offset < 0 else OBSTACLE_SMOOTH_ALPHA
            self.obs_smooth_offset = _smooth_alpha * target_offset + (1 - _smooth_alpha) * self.obs_smooth_offset

        self.obs_target_offset = self.obs_smooth_offset
        self.obs_curv_gain = np.clip(curv_gain, 1.0, OBS_EXTRA_GAIN_MAX)
        self.obs_closest_dist = min_dist
        self.has_static_obstacle = has_static
        self.has_roadside_parked = has_roadside_parked
        self.has_left_pressure = has_left_pressure

        prev = getattr(self, '_obs_profile_prev', np.zeros(TRAJECTORY_SIZE))
        a = 0.45 if abs(target_offset) < 0.02 else OBSTACLE_SMOOTH_ALPHA
        profile_smooth = a * profile + (1 - a) * prev
        self._obs_profile_prev = profile_smooth.copy()
        self.obs_offset_profile = np.clip(profile_smooth, -1.2, 1.2).astype(np.float32)

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
            self.left_boost = 1.15
            self.left_smooth_alpha = 0.55
            self.left_gravity = 0.30
            try:
                self.right_avoid_dist_m = float(self.params.get_int("RightAvoidDistance")) * 0.01
                if self.right_avoid_dist_m < 0.5:
                    self.right_avoid_dist_m = 1.0
            except Exception:
                try:
                    from openpilot.selfdrive.carrot.config import CarrotConfig
                    self.right_avoid_dist_m = float(CarrotConfig().get_int("RightAvoidDistance", 100)) * 0.01
                except Exception:
                    self.right_avoid_dist_m = 1.0

        # 从雷达与视觉融合提取右侧障碍物及左侧对向来车
        self.extracted_obstacles = self._extract_obstacles_and_oncoming(sm)

        if high_speed_mode:
            if self.v_ego > 110.0 / 3.6:
                self.obs_target_offset = 0.0
                self.obs_smooth_offset = 0.0
                self.obs_curv_gain = 1.0
                self.obs_closest_dist = float("inf")
                self.has_static_obstacle = False
                self.has_roadside_parked = False
                self.has_left_pressure = False
            else:
                self.obs_target_offset = 0.0
                self.obs_smooth_offset = 0.15 * self.obs_smooth_offset
                self.obs_curv_gain = 1.0
                self.obs_closest_dist = min(self.obs_closest_dist, 20.0)
                self.has_static_obstacle = True
                self.has_roadside_parked = False
                self.has_left_pressure = False
        else:
            self._calc_obstacle_avoid_param(carrot, self.extracted_obstacles)

        # 盲区雷达兜底逻辑已移至 _in_turn_scene 判定之后(下方),转弯/弯道场景排除,避免误触发降速。

        measured_curvature = sm['controlsState'].curvature
        v_ego_car = sm['carState'].vEgo
        try:
            self.curve_speed = sm['carrotMan'].vTurnSpeed
        except Exception:
            self.curve_speed = 0.0
        v_kph = v_ego_car * 3.6
        speed_steer_gain = float(np.interp(v_kph, SPEED_GRID_KPH, PLAN_GAIN_TABLE))

        if not high_speed_mode and self.obs_closest_dist < OBSTACLE_MAX_DETECT_LONG:
            obs_extra_gain = 1.0 + max(0.0, (OBSTACLE_MAX_DETECT_LONG - self.obs_closest_dist) / OBSTACLE_MAX_DETECT_LONG * 0.4)
        else:
            obs_extra_gain = 1.0

        try:
            act_steer_deg = sm['carState'].steeringAngleDeg
            des_steer_deg = self.lat_mpc.x_sol[0, 3] * 180 / np.pi
            angle_err = abs(act_steer_deg - des_steer_deg)
            if angle_err > ANGLE_ERR_THRESH:
                speed_steer_gain *= ANGLE_ERR_EXTRA_GAIN
        except Exception:
            angle_err = 0.0
            des_steer_deg = 0.0

        right_turn_comp = 0.0
        if des_steer_deg < -RIGHT_TURN_ANGLE_THRESH:
            right_turn_comp = RIGHT_TURN_CURV_COMP

        blinker_gain = 0.70 if self.blinker_active else 1.0

        measured_curvature *= speed_steer_gain * self.obs_curv_gain * obs_extra_gain * blinker_gain
        measured_curvature += right_turn_comp * CURV_COMP_SCALE

        nav_active = is_nav_active()
        uturn_active = is_u_turn()
        right_turn_active = is_right_turn()
        _RT_MEM_TIMEOUT = 4.0
        if not hasattr(self, '_rt_mem'):
            self._rt_mem = False
            self._rt_mem_t = 0.0
        _y_mean_rt = float(np.mean(self.y_pts)) if len(self.y_pts) else 0.0
        # 车辆自身右转证据(完全不依赖导航)：
        #   1) 右转向灯亮            —— 最直接、无歧义
        #   2) 右打方向(des_steer_deg 为负且越过阈值)
        #   3) 路径已明显偏右(_y_mean_rt 正=右) —— 维持已建立的右转，避免抖动退出
        # 只要命中其一即视为右转场景 → _sign=+1.0 → 路径贴右。导航开不开都生效。
        try:
            _right_blink = bool(sm['carState'].rightBlinker)
        except Exception:
            _right_blink = False
        _rt_self = (_right_blink
                    or (des_steer_deg < -RIGHT_TURN_ANGLE_THRESH)
                    or (_y_mean_rt > 0.20))
        # _rt_mem：右转证据消失后保持一小段时间，平滑退出(低速停车时冻结超时不重置)
        if _rt_self:
            self._rt_mem = True
            self._rt_mem_t = now_ts
        elif _y_mean_rt < -0.20:
            self._rt_mem = False
        if self._rt_mem and (now_ts - self._rt_mem_t) > _RT_MEM_TIMEOUT:
            self._rt_mem = False
        _is_stopped_rt = self.v_ego < 0.5
        if self._rt_mem and _is_stopped_rt:
            self._rt_mem_t = now_ts
        # 右转场景 = 导航右转 OR 记忆 OR 车辆自身右转证据。三者任一即贴右，绝不依赖导航。
        right_turn_active = right_turn_active or self._rt_mem or _rt_self
        try:
            if _y_mean_rt > 0.30:
                _set_right_turn_early(True)
            elif _y_mean_rt < -0.20:
                _set_right_turn_early(False)
        except Exception:
            pass
        try:
            _md_for_corner = sm['modelV2']
            _corner_angle = estimate_turn_angle(_md_for_corner)
        except Exception:
            _corner_angle = 0.0
        is_cornering = _corner_angle >= CORNERING_ANGLE_THRESH
        left_turn_active = is_left_turn()
        turn_locked = is_turn_active()

        if turn_locked:
            global_in_turn = True
            global_turn_lock_ts = now_ts
        if global_in_turn and (now_ts - global_turn_lock_ts) > TURN_LOCK_TIMEOUT:
            global_in_turn = False

        _in_turn_scene = left_turn_active or right_turn_active or (g_big_cross and not right_turn_active) or (g_narrow_road and not right_turn_active) or turn_locked or global_in_turn or is_cornering

        md_for_corner = sm['modelV2']
        _turn_angle_val = estimate_turn_angle(md_for_corner)
        is_cornering = _turn_angle_val > CORNERING_ANGLE_THRESH or is_cornering

        _steer_on = (abs(des_steer_deg) > self._steer_active_enter_deg) or right_turn_active or left_turn_active or is_cornering or self._rt_mem
        _steer_off = (abs(des_steer_deg) < self._steer_active_exit_deg) and (not right_turn_active) and (not left_turn_active) and (not is_cornering) and (not self._rt_mem)
        if _steer_on:
            self._steer_active_hyst = True
        elif _steer_off:
            self._steer_active_hyst = False
        steer_active = self._steer_active_hyst
        is_cornering = is_cornering or steer_active
        _in_turn_scene = left_turn_active or right_turn_active or (g_big_cross and not right_turn_active) or (g_narrow_road and not right_turn_active) or turn_locked or global_in_turn or is_cornering

        # 盲区雷达兜底:右侧盲区确认有车(停放/对向)时,即便主雷达漏检也置位 has_roadside_parked,
        # 让 longitudinal_planner 触发降速/停车(否则"过不去却不减速")。
        # ★ 仅在「非高速 + 非转弯/弯道/窄路/交叉口」时生效:否则盲区把弯道护栏/对向车误判为
        #   路侧停车 → 转弯时 longitudinal 误降速,表现为"转弯迟迟不给角度";且高速分支(615-631)
        #   已清掉该标志,此处不再越权置位(避免高速也减速)。
        if not high_speed_mode and not _in_turn_scene:
            try:
                from openpilot.selfdrive.carrot.amap_navi import NAV_MSG_DATA
                if NAV_MSG_DATA.get("has_right_obstacle", False):
                    self.has_roadside_parked = True
            except Exception:
                pass

        if nav_active and (left_turn_active or right_turn_active or (g_big_cross and not right_turn_active) or turn_locked or is_cornering):
            self.lat_mpc.nav_gain = 1.25
        else:
            self.lat_mpc.nav_gain = 1.0

        temp_path_cost = self.lateralPathCost
        temp_motion_cost = self.lateralMotionCost
        temp_steer_rate_cost = self.default_steering_rate_cost

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

        if _in_turn_scene or steer_active:
            temp_path_cost = temp_path_cost * TURN_PATH_COST_MULT
            temp_motion_cost = temp_motion_cost * TURN_MOTION_COST_MULT
            if right_turn_active:
                temp_steer_rate_cost = temp_steer_rate_cost * 0.85
            else:
                temp_steer_rate_cost = temp_steer_rate_cost * TURN_STEER_RATE_MULT
        if steer_active and not _in_turn_scene:
            temp_path_cost = temp_path_cost * (1.2 / TURN_PATH_COST_MULT)
            temp_motion_cost = temp_motion_cost * (0.85 / TURN_MOTION_COST_MULT)
            temp_steer_rate_cost = temp_steer_rate_cost * 0.9

        if right_turn_active or is_cornering:
            base_max_curv = 0.120
        elif left_turn_active or g_big_cross or global_in_turn:
            base_max_curv = 0.075
        else:
            base_max_curv = 0.055
        if self.has_static_obstacle:
            curr_max_curv = base_max_curv * STATIC_CURV_LIMIT_SCALE
        else:
            curr_max_curv = base_max_curv
        measured_curvature = np.clip(measured_curvature, -curr_max_curv, curr_max_curv)

        # ★ 低速曲率限幅放宽（原 0.072/0.040/0.032 太小，抵消了前面的放宽效果）
        if self.v_ego < 30:
            if right_turn_active or is_cornering:
                measured_curvature = np.clip(measured_curvature, -0.110, 0.110)
            elif is_cornering:
                measured_curvature = np.clip(measured_curvature, -0.075, 0.075)
            else:
                measured_curvature = np.clip(measured_curvature, -0.055, 0.055)

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
            _lane_probs = None
            try:
                _lane_probs = md.laneLineProbs
            except Exception:
                _lane_probs = None
            _lane_fade = False
            if _lane_probs is not None and len(_lane_probs) >= 3:
                _min_lane_prob = min(float(_lane_probs[0]), float(_lane_probs[2]))
                if 0 < _min_lane_prob < LANE_PROB_NARROW_THRESH:
                    _lane_fade = True
                    if (now_ts - getattr(self, '_last_lane_fade_log_t', 0.0)) > 5.0:
                        cloudlog.info(f"[LaneFade] low prob L={_lane_probs[0]:.2f} R={_lane_probs[2]:.2f} alpha={LANE_FADE_ALPHA}")
                        self._last_lane_fade_log_t = now_ts

            if _lane_fade:
                smooth_alpha = LANE_FADE_ALPHA
            elif steer_active:
                smooth_alpha = 0.10
            elif right_turn_active or is_cornering:
                smooth_alpha = 0.0
            elif not self.right_turn_released and (now_ts - self.right_turn_lock_ts) <= TURN_EXIT_TRANSITION_TIME:
                smooth_alpha = 0.35
            elif vkph > 100:
                smooth_alpha = 0.80
            elif vkph > 40:
                smooth_alpha = 0.45
            else:
                smooth_alpha = 0.35

            if not self.right_turn_released and (now_ts - self.right_turn_lock_ts) <= TURN_EXIT_TRANSITION_TIME:
                smooth_y_prev = 0.6 * smooth_y_prev + 0.4 * raw_y
                smooth_yaw_prev *= 0.6

            smooth_y = smooth_alpha * smooth_y_prev + (1 - smooth_alpha) * raw_y
            smooth_yaw = smooth_alpha * smooth_yaw_prev + (1 - smooth_alpha) * raw_yaw
            smooth_y_prev = smooth_y.copy()
            smooth_yaw_prev = smooth_yaw.copy()


            _pure_straight = (not steer_active) and (not is_cornering) and (not right_turn_active) and (not left_turn_active)
            if _pure_straight:
                _far_mean = np.abs(smooth_y[20:].mean()) if len(smooth_y) > 20 else 0.0
                if _far_mean > 0.3:
                    _decay = np.linspace(1.0, 0.5, len(smooth_y))
                    smooth_y = smooth_y * _decay

            if ROADEDGE_BOUND_ENABLED:
                try:
                    _edges = md.roadEdges
                    _edge_L = _edges[0]
                    _edge_R = _edges[1]
                    _ep_L = float(_edge_L.prob)
                    _ep_R = float(_edge_R.prob)
                    _ey_L = float(_edge_L.y)
                    _ey_R = float(_edge_R.y)
                    _edge_std_L = float(md.roadEdgeStds[0]) if len(md.roadEdgeStds) > 0 else 0.0
                    _edge_std_R = float(md.roadEdgeStds[1]) if len(md.roadEdgeStds) > 1 else 0.0

                    _lane_w = (self.LP.lane_width_left + self.LP.lane_width_right) / 2.0
                    _y0 = smooth_y[0]
                    _norm_pos = np.clip(_y0 / (_lane_w / 2.0), -2.0, 2.0) if _lane_w > 0.5 else 0.0

                    _ll_prob_L = float(md.laneLineProbs[0]) if len(md.laneLineProbs) > 0 else 0.0
                    _ll_prob_R = float(md.laneLineProbs[2]) if len(md.laneLineProbs) > 2 else 0.0
                    self._deviation_dir = 0
                    if _norm_pos < -DEVIATION_NORM_THRESH and _ll_prob_L > 0.30:
                        smooth_y = smooth_y + DEVIATION_CORRECT_STEP
                        self._deviation_dir = -1
                    elif _norm_pos > DEVIATION_NORM_THRESH and _ll_prob_R > 0.30:
                        smooth_y = smooth_y - DEVIATION_CORRECT_STEP
                        self._deviation_dir = 1

                    if _lane_fade and _ep_L > ROAD_EDGE_PROB_THRESH and _ep_R > ROAD_EDGE_PROB_THRESH:
                        _edge_center = (_ey_L + _ey_R) / 2.0
                        smooth_y = (1.0 - ROADEDGE_CENTER_BLEND) * smooth_y + ROADEDGE_CENTER_BLEND * np.full_like(smooth_y, _edge_center)
                        self._edge_center_offset = _edge_center
                        self._edge_valid = True
                    else:
                        self._edge_valid = (_ep_L > ROAD_EDGE_PROB_THRESH or _ep_R > ROAD_EDGE_PROB_THRESH)

                    if _ep_R > ROAD_EDGE_PROB_THRESH:
                        _hard_R = _ey_R - ROAD_EDGE_SAFE_MARGIN - _edge_std_R * 0.5
                        smooth_y = np.clip(smooth_y, -10.0, _hard_R)
                    if _ep_L > ROAD_EDGE_PROB_THRESH:
                        _hard_L = _ey_L + ROAD_EDGE_SAFE_MARGIN + _edge_std_L * 0.5
                        smooth_y = np.clip(smooth_y, _hard_L, 10.0)

                    if right_turn_active and g_narrow_road:
                        if _ll_prob_L > 0.30:
                            _left_bound = _ey_L + ROAD_EDGE_SAFE_MARGIN if _ep_L > ROAD_EDGE_PROB_THRESH else (-lane_w_left / 2.0 + 0.05)
                            smooth_y = np.clip(smooth_y, _left_bound, 10.0)
                        _end_idx = min(len(smooth_y) - 1, 25)
                        if smooth_y[_end_idx] > NARROW_ROAD_RIGHT_TURN_MAX_Y:
                            smooth_y[_end_idx:] = np.clip(smooth_y[_end_idx:], -10.0, NARROW_ROAD_RIGHT_TURN_MAX_Y)
                        if abs(measured_curvature) > 0.080:
                            measured_curvature = np.sign(measured_curvature) * 0.080

                    if left_turn_active and _ep_L > ROAD_EDGE_PROB_THRESH:
                        _hard_L = _ey_L + ROAD_EDGE_SAFE_MARGIN + _edge_std_L * 0.5
                        smooth_y = np.clip(smooth_y, _hard_L, 10.0)

                    if (now_ts - getattr(self, '_last_edge_log_t', 0.0)) > 8.0:
                        cloudlog.info(f"[RoadEdge] Lprob={_ep_L:.2f} Rprob={_ep_R:.2f} "
                                      f"dev={'LEFT' if self._deviation_dir==-1 else ('RIGHT' if self._deviation_dir==1 else 'OK')} "
                                      f"narrow={g_narrow_road} turnR={right_turn_active}")
                        self._last_edge_log_t = now_ts
                except Exception:
                    pass

            self.path_xyz[:, 1] = smooth_y
            self.plan_yaw = smooth_yaw
            self.plan_yaw_rate = np.array(md.orientationRate.z)
            self.velocity_xyz = np.column_stack([md.velocity.x, md.velocity.y, md.velocity.z])
            car_speed = np.linalg.norm(self.velocity_xyz, axis=1) - get_speed_error(md, v_ego_car)
            self.v_plan = np.maximum(car_speed, self.v_ego)  # ← 加这一行
            # ★★★ 修复：高速弯道平滑减速（每帧最多降 _V_DECEL_STEP_CURV m/s）★★★
            _target_v = self.v_ego
            if _in_turn_scene or is_cornering or abs(measured_curvature) > 0.001:
                _turn_min = max(self.turn_decel_min_kph / 3.6, 12.0 / 3.6)
                _turn_target = max(self.curve_decel_speed_kph / 3.6, _turn_min)
                _target_v = _turn_target
                self.curve_decel_active = True
            else:
                self.curve_decel_active = False

            if self.v_ego > _target_v:
                # 每帧最多降 _V_DECEL_STEP_CURV (约 2km/h per frame)
                _max_drop = _V_DECEL_STEP_CURV * self.v_ego
                self.v_ego = max(self.v_ego - _max_drop, _target_v)
            else:
                self.v_ego = max(_target_v, self.v_ego)

            self.v_plan[0] = self.v_ego


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

        _raw_y_mean = float(np.mean(raw_y)) if model_valid and len(raw_y) else 0.0
        if right_turn_active and _raw_y_mean > 0.20:
            _shape = self.path_xyz[:, 1] - self.path_xyz[0, 1]
            self._rt_path_mem = _shape.copy()
            self._rt_path_mem_valid = True
            if abs(measured_curvature) > 1e-4:
                self._rt_curv_mem = abs(measured_curvature)
                self._rt_curv_mem_valid = True
        elif right_turn_active and self._rt_path_mem_valid and self.v_ego < 1.0:
            _decay = max(0.55, 1.0 - 0.02 * (now_ts - self._rt_mem_t))
            _reuse = self._rt_path_mem * _decay
            self.path_xyz[:, 1] = self.path_xyz[0, 1] + _reuse
        if not self._rt_mem and self._rt_path_mem_valid and (now_ts - self._rt_mem_t) > _RT_MEM_TIMEOUT:
            self._rt_path_mem_valid = False
            self._rt_curv_mem_valid = False

        if self.merge_boost > 0:
            self.v_plan = np.clip(self.v_plan + self.merge_boost / 3.6, MIN_SPEED, np.inf)
            self.v_ego = self.v_plan[0]

        self.LP.parse_model(md)
        try:
            self.LP.update_obstacle_data(self.extracted_obstacles)
        except Exception:
            pass

        if global_in_turn and not high_speed_mode:
            self.LP.obstacle_avoid_scale = 0.6
        else:
            self.LP.obstacle_avoid_scale = 1.0

        line_type = get_divide_line_type(md)
        turn_angle = estimate_turn_angle(md)
        lane_w_left = self.LP.lane_width_left
        lane_w_right = self.LP.lane_width_right

        if right_turn_active:
            curr_margin = BASE_MARGIN_NORMAL
            base_scale = SCALE_NORMAL
            turn_scale = 1.0
        elif g_big_cross:
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
        base_safe_left = lane_left_bound + final_total_margin + 0.04
        safe_right = lane_right_bound - curr_margin

        if left_turn_active or is_left_turn_scene:
            base_safe_left += 0.16
            self.path_xyz[:, 1] += 0.10
        if right_turn_active:
            safe_right = lane_right_bound - RIGHT_TURN_SAFE_MARGIN
            self.path_xyz[:, 1] += 0.10
        if is_left_turn_scene or left_turn_active:
            base_safe_left += 0.05

        # ===== 故障车越实线借道与对向来车严苛判定 =====
        # 1. 默认执行严格的左侧车道硬约束。
        # 2. 如果右侧有故障车/静止车，允许越过实线借道避让。
        # 3. 必须保证对向车道没有来车！如果有对向来车，坚决不允许越过实线，严格保持车道内硬约束。
        # 4. 通过障碍物后，立即恢复车道硬约束，居中行驶。
        is_broken_down = self.has_roadside_parked or self.has_static_obstacle
        is_needing_borrow = self.obs_smooth_offset < -0.15
        allow_borrow_line = (
            is_broken_down
            and not self.has_oncoming_traffic
            and is_needing_borrow
            and not high_speed_mode
            and not _in_turn_scene
        )

        if allow_borrow_line:
            # 对向无来车，允许越过左侧实线借道避让（向左放宽0.85米）
            safe_left = lane_left_bound - 0.85
        else:
            # 对向有来车，或无故障车，或已通过障碍物：严格执行左侧车道硬约束
            safe_left = base_safe_left

        self.current_safe_left = safe_left

        if not _in_turn_scene:
            self.path_xyz[:, 1] = np.clip(self.path_xyz[:, 1], safe_left, safe_right)

        try:
            _avail = float(safe_right - safe_left)
            if _avail > 0:
                self.available_road_width = _avail
        except Exception:
            pass

        _in_exit_window = (not self.right_turn_released) and (now_ts - self.right_turn_lock_ts) <= TURN_EXIT_TRANSITION_TIME
        if right_turn_active:
            _gy_max = GLOBAL_Y_MAX
            _gy_min = GLOBAL_Y_MIN
        elif _in_exit_window:
            _gy_max = GLOBAL_Y_MAX_EXIT
            _gy_min = -GLOBAL_Y_MAX_EXIT
        else:
            _gy_max = GLOBAL_Y_MAX
            _gy_min = GLOBAL_Y_MIN
        self.path_xyz[:, 1] = np.clip(self.path_xyz[:, 1], _gy_min, _gy_max)
        LAST_VALID_PATH_Y = self.path_xyz[:, 1].copy()

        if right_turn_active or left_turn_active or g_big_cross or turn_locked:
            ramp = np.clip(np.arange(TRAJECTORY_SIZE) / max(TRAJECTORY_SIZE - 1, 1), 0.0, 1.0)
            if right_turn_active or (g_big_cross and global_turn_lock_ts != 0.0):
                self.path_xyz[:, 1] += (-TURN_RAMP_OFFSET_UI) * ramp
            if left_turn_active:
                self.path_xyz[:, 1] += TURN_RAMP_OFFSET_UI * ramp

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

        _cs = get_carrot_serv_instance()
        _drv_left = False
        _drv_right = False
        try:
            _drv_left = bool(sm['carState'].leftBlinker)
            _drv_right = bool(sm['carState'].rightBlinker)
        except Exception:
            pass
        _drv_dir = 0
        if _drv_left and not _drv_right:
            _drv_dir = 1
        elif _drv_right and not _drv_left:
            _drv_dir = -1

        _turn_just_ended = (not self.right_turn_released) and (not right_turn_active)

        _standstill = False
        _has_lead = False
        try:
            _standstill = bool(sm['carState'].standstill)
        except Exception:
            pass
        try:
            _lead = sm['radarState'].leadOne
            _has_lead = bool(_lead.status) and float(_lead.dRel) < 40.0 and abs(float(_lead.yRel)) < 1.5
        except Exception:
            _has_lead = False
        _follow_block = (_standstill and _has_lead)

        _safe_to_boost = True
        _has_roadside = False
        try:
            _obs_list = getattr(self, 'extracted_obstacles', [])
            for _obs in _obs_list:
                try:
                    _d_long = float(_obs.longDistance)
                    _d_lat = float(_obs.latDistance)
                    _o_type = str(_obs.type)
                except Exception:
                    continue
                if _d_long > OBSTACLE_MAX_DETECT_LONG or _d_long < 0.5:
                    continue
                if _d_long < 30.0 and abs(_d_lat) < 0.8:
                    if _o_type in ("static", "unknown", "oncoming"):
                        _safe_to_boost = False
                        break
                if abs(_d_lat) > 1.2 and _o_type in ("parked", "static", "unknown"):
                    _has_roadside = True
        except Exception:
            pass

        if (_drv_dir != 0 and self.v_ego < self.blinker_avoid_speed_max
                and not _follow_block and _safe_to_boost
                and not _turn_just_ended):
            _base_boost = 0.4
            _extra = _drv_dir * self.blinker_avoid_boost if _has_roadside else 0.0
            self.obs_smooth_offset = np.clip(
                self.obs_smooth_offset + _drv_dir * _base_boost + _extra, -2.0, 1.8)
            self.obs_target_offset = self.obs_smooth_offset
            try:
                _cs.set_blinker_request(BLINKER_LEFT if _drv_dir == 1 else BLINKER_RIGHT)
            except Exception:
                pass

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
            self.blinker_hold_ts = now_ts + BLINKER_HOLD_TIME
            try:
                try:
                    carrot.carrot_serv.set_blinker_request(int(self.blinker_dir))
                except Exception:
                    pass
            except Exception:
                pass
        else:
            if self.blinker_active and now_ts > self.blinker_hold_ts:
                self.blinker_active = False
                self.avoidance_active = False
                try:
                    try:
                        carrot.carrot_serv.set_blinker_request(0)
                    except Exception:
                        pass
                except Exception:
                    pass

        if self.blinker_active:
            if now_ts >= self.blinker_delay_ts:
                self.avoidance_active = True
            else:
                self.avoidance_active = False
        else:
            self.avoidance_active = False

        if right_turn_active:
            self.right_turn_lock_ts = now_ts
            self.right_turn_released = False
        elif not self.right_turn_released and (now_ts - self.right_turn_lock_ts) > TURN_EXIT_TRANSITION_TIME:
            self.right_turn_released = True

        turn_just_ended = (not self.right_turn_released) and (not right_turn_active)

        if right_turn_active:
            _po = self.pathOffset
            if self.v_ego < 1.0:
                _po = max(self.pathOffset, 0.30)
            final_offset = self.obs_smooth_offset * IN_TURN_AVOID_SCALE + _po
        elif turn_just_ended:
            _obs_part = max(0.0, self.obs_smooth_offset) * 0.5
            final_offset = -last_truck_offset * 0.5 + _obs_part
        else:
            final_offset = self.pathOffset - last_truck_offset + self.obs_smooth_offset

        final_offset = np.clip(final_offset, -1.8, 1.5)

        if (now_ts - getattr(self, '_last_obs_chk2_t', 0.0)) > 5.0:
            cloudlog.warning(f"[OBS-CHK] final_offset={final_offset:.2f} y0={self.path_xyz[0, 1]:.2f} steer={sm['carState'].steeringAngleDeg:.1f} dsteer={des_steer_deg:.1f} curv={measured_curvature:.4f} rblink={_right_blink} rt_act={right_turn_active} rt_mem={self._rt_mem} closest={self.obs_closest_dist:.1f}")
            self._last_obs_chk2_t = now_ts

        _prof = getattr(self, 'obs_offset_profile', None)
        if _prof is not None and len(_prof) == TRAJECTORY_SIZE and not right_turn_active:
            self.path_xyz[:, 1] += _prof
            # ★ 大货车压线修复：左侧安全偏移必须叠加，不能被障碍廓线覆盖。
            #   obs_offset_profile 只来自主雷达 carrot.obstacles，与盲区/侧车探测
            #   (amap_navi 写入 truck_left_offset → last_truck_offset) 是不同源；
            #   原逻辑在 _prof 有效时整体改用 _prof，导致右有大车时的横向避险
            #   偏移(final_offset 中的 -last_truck_offset)被完全丢弃 → 高速大货车
            #   压线不偏移。这里恒叠加卡车左移，转弯分支已由 final_offset 覆盖。
            self.path_xyz[:, 1] -= last_truck_offset
            if (now_ts - getattr(self, '_last_truck_log_t', 0.0)) > 5.0:
                cloudlog.info(f"[TRUCK-OFFSET] applied=-{last_truck_offset:.2f} "
                              f"prof_max={float(np.max(np.abs(_prof))):.2f} y0={self.path_xyz[0, 1]:.2f}")
                self._last_truck_log_t = now_ts
        else:
            self.path_xyz[:, 1] += final_offset

        if self.has_left_pressure:
            _g = float(np.clip(getattr(self, 'left_gravity', 0.30), 0.0, 1.0))
            _prof = getattr(self, 'obs_offset_profile', None)
            if _g > 0.0 and _prof is not None and len(_prof) == TRAJECTORY_SIZE:
                _sl = float(np.clip(safe_left, -4.5, 0.0))
                _y = self.path_xyz[:, 1]
                _w = np.abs(np.array(_prof, dtype=np.float64))
                _w_max = float(np.max(_w))
                if _w_max > 1e-6:
                    _w = _w / _w_max
                else:
                    _w = np.zeros_like(_w)
                _y = _y + (_sl - _y) * (_g * _w)
                self.path_xyz[:, 1] = _y
            _current_y0 = self.path_xyz[0, 1]
            if _current_y0 > -0.10:
                self.path_xyz[0, 1] = -0.10

        _eff_safe_left = getattr(self, 'current_safe_left', safe_left)
        self.path_xyz[:, 1] = np.clip(self.path_xyz[:, 1], _eff_safe_left, _gy_max)

        if _in_turn_scene and not right_turn_active:
            _rate_limit = 0.30
            _y = self.path_xyz[:, 1]
            _y_limited = _y.copy()
            for i in range(1, len(_y)):
                _y_limited[i] = np.clip(_y[i], _y_limited[i-1] - _rate_limit, _y_limited[i-1] + _rate_limit)
            self.path_xyz[:, 1] = _y_limited

        if _in_exit_window and (now_ts - getattr(self, '_last_exit_chk_t', 0.0)) > 5.0:
            _y_dbg = self.path_xyz[:, 1]
            cloudlog.info(f"[EXIT-CHK] exit_window y_range=[{_y_dbg.min():.2f},{_y_dbg.max():.2f}] y0={_y_dbg[0]:.2f} y_mid={np.median(_y_dbg[5:20]):.2f}")
            self._last_exit_chk_t = now_ts

        LAST_VALID_PATH_Y = self.path_xyz[:, 1].copy()

        solid_line_block = LANE_CHANGE_SOLID_BLOCK and check_solid_lane_line(md)
        if solid_line_block:
            self.LP.lane_change_multiplier = 0.0
        elif nav_active:
            if right_turn_active:
                if md.meta.desire != log.Desire.none or carrot.atc_active:
                    self.LP.lane_change_multiplier = 1.0
                else:
                    self.LP.lane_change_multiplier = 0.0
            else:
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
            curvature *= 1.28
        elif is_cornering:
            curvature *= 1.28
        elif _lane_fade:
            curvature *= LANE_FADE_CURV_GAIN
        if left_turn_active:
            curvature *= 1.12

        if right_turn_active and self.v_ego < 1.0:
            _curv_floor = 0.028
            if self._rt_curv_mem_valid and self._rt_curv_mem > _curv_floor:
                _curv_floor = self._rt_curv_mem
            if abs(curvature) < _curv_floor:
                curvature = _curv_floor

        if 0.0006 < abs(curvature) < 0.0015 and self.v_ego < 30:
            curvature = np.sign(curvature) * 0.0018
        if abs(curvature) >= 0.0015 and self.v_ego < 30:
            curvature *= 1.55
        if abs(curvature) >= 0.0012 and 30 <= self.v_ego < 50:
            curvature *= 1.22

        self.LP.curvature = curvature

        if nav_active:
            cross_total_len, cross_remain_dist, turn_dir, has_target_lane, is_short_cross, is_mid_cross = get_nav_cross_info()
            if 0 < cross_remain_dist < IN_INTERSECTION_SOLID_DIST and not right_turn_active:
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

        HIGH_SPEED_LOCK = 80 / 3.6
        CURV_LOCK = 0.0006
        if self.v_ego > HIGH_SPEED_LOCK and abs(measured_curvature) < CURV_LOCK:
            self.x_sol[:, 3] = 0.85 * self.x_sol[:, 3] + 0.15 * np.full_like(self.x_sol[:, 3], self.x_sol[0, 3])

        if uturn_active:
            self.lat_mpc.set_weights(1.5, 2.4, 1.0, 0.7, 1.2, True, False, self.v_ego > 100 / 3.6, self.v_ego * 3.6)
        else:
            if self.v_ego > 100 / 3.6:
                self.lat_mpc.set_weights(
                    temp_path_cost * 0.85, temp_motion_cost * 1.2,
                    LATERAL_ACCEL_COST * 1.5, LATERAL_JERK_COST * 2.0,
                    temp_steer_rate_cost * 1.1, False, True, self.v_ego * 3.6
                )
            else:
                self.lat_mpc.set_weights(
                    temp_path_cost, temp_motion_cost,
                    LATERAL_ACCEL_COST, LATERAL_JERK_COST,
                    temp_steer_rate_cost, False, False, self.v_ego * 3.6
                )

        if right_turn_active:
            try:
                from openpilot.selfdrive.carrot.amap_navi import NAV_MSG_DATA
                _crd = float(NAV_MSG_DATA.get("cross_remain_dist", 60))
            except Exception:
                _crd = 60.0
            if _crd < 100.0:
                _tgt = max(8.0, 18.0 * (_crd / 100.0))
                _tgt = min(_tgt, 20.0)
            else:
                _tgt = 20.0
            if getattr(self, 'curve_speed', 0.0) > 0:
                self.curve_speed = min(self.curve_speed, _tgt)
            else:
                self.curve_speed = _tgt
            self.curve_decel_active = True

        heading_pts = self.plan_yaw[:LAT_MPC_N + 1]
        yaw_rate_pts = self.plan_yaw_rate[:LAT_MPC_N + 1]

        lateral_factor = np.clip(self.factor1 - (self.factor2 * self.v_plan ** 2), 0.0, np.inf)
        p = np.column_stack([self.v_plan, lateral_factor])

        turn_y_pts = None
        _curv_abs = abs(measured_curvature) if 'measured_curvature' in dir() else 0.0
        try:
            _curv_abs = abs(float(measured_curvature))
        except Exception:
            _curv_abs = 0.0
        _is_cornering_hug = (_curv_abs > CORNERING_LOW_SPEED_CLIP) and not is_intersection_left_turn(sm)
        _turn_scene = right_turn_active or left_turn_active or _is_cornering_hug
        if _turn_scene:
            try:
                if right_turn_active:
                    _sign = 1.0
                elif left_turn_active:
                    _sign = -1.0
                else:  # 过弯：本 fork 正曲率=右，按曲率符号贴向弯道内侧(切 apex)
                    _sign = 1.0 if measured_curvature > 0 else -1.0

                _t = np.linspace(0, 1, LAT_MPC_N + 1)
                _sin_arc = np.sin(_t * np.pi)

                try:
                    from openpilot.selfdrive.carrot.amap_navi import NAV_MSG_DATA
                    _cross_remain = float(NAV_MSG_DATA.get("cross_remain_dist", 60))
                except Exception:
                    _cross_remain = 60.0

                _urg = np.clip((60.0 - min(_cross_remain, 60.0)) / 60.0, 0.0, 1.0)
                _spd_f = np.clip(self.v_ego / 10.0, 0.5, 2.0)

                # ★ 贴边量收敛：原来 _target 下限硬编码 1.2m（末端≈1.6m），叠加转弯本身
                #   的曲率后转向需求顶到车辆极限 → openpilot steerSaturated
                #   ("Turn Exceeds Steering Limit") 报接管、横向退出。这里把上限收到 1.6、
                #   下限收到 0.5，贴边仍在(末端不回零)，但不再顶爆转向。
                _target = min(1.2 * _urg * _spd_f, 1.6)
                _target = max(_target, 0.5)

                # ★ 形状(关键)：近场必须从 0 平滑起步，绝不能硬性横移。
                #   之前用 _arc_base = _sign*0.40 让 t=0 处就有 0.40m 横移，近场 x 极小，
                #   等效"假航向/假曲率"需求极大 → MPC 打满方向 → 饱和退出。
                #   smoothstep s(t)=3t²-2t³：s(0)=0(近场不动) 且 s'(0)=0(近场无假曲率)，
                #   末端 s(1)=1 且 s'(1)=0(保持最大、不回零"贴到最后")。
                #   纯过弯 -> 仍用对称正弦(先切 apex 再回正)。
                if right_turn_active or left_turn_active:
                    _profile = _t * _t * (3.0 - 2.0 * _t)
                else:
                    _profile = _sin_arc
                _arc = _profile * _target * _sign

                if self.v_ego < 1.0 and self._rt_path_mem_valid:
                    _arc = self._rt_path_mem[:LAT_MPC_N + 1].copy() * _sign
                elif self.v_ego >= 1.0:
                    self._rt_path_mem = np.abs(_arc) if right_turn_active else _arc.copy()
                    self._rt_path_mem_valid = True

                turn_y_pts = _arc
            except Exception:
                turn_y_pts = None

        if right_turn_active and turn_y_pts is not None:
            _blend = 0.70
            _tpl = turn_y_pts[:TRAJECTORY_SIZE]
            self.path_xyz[:, 1] = (1.0 - _blend) * self.path_xyz[:, 1] + _blend * _tpl
            smooth_y = self.path_xyz[:, 1].copy()
            smooth_y_prev = smooth_y.copy()
        self.y_pts = self.path_xyz[:LAT_MPC_N + 1, 1]
        if turn_y_pts is not None and len(turn_y_pts) > TRAJECTORY_SIZE:
            turn_y_pts = turn_y_pts[:TRAJECTORY_SIZE]
        self.turn_y_pts = turn_y_pts

        try:
            _run_turn_y = turn_y_pts if (_is_cornering_hug or right_turn_active or left_turn_active) else None
            self.lat_mpc.run(self.x0, p, self.y_pts, heading_pts, yaw_rate_pts, _run_turn_y)
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
        if right_turn_active and LAT_MPC_N >= 2:
            # ★ 近端前馈权重从 0.60 降到 0.15：60% 的近端转角前馈会把 MPC 需求放大，
            #   是"转向顶到限幅 → steerSaturated 退出"的元凶之一。
            _ff = float(self.x_sol[1, 3])
            current_steer = 0.85 * current_steer + 0.15 * _ff
        if self.v_ego >= SPEED_HIGH:
            if self.v_ego >= 110 / 3.6:
                current_steer = HIGH_SPEED_DAMP_PLUS * LAST_STEER_CMD + (1 - HIGH_SPEED_DAMP_PLUS) * current_steer
            else:
                current_steer = HIGH_SPEED_DAMP * LAST_STEER_CMD + (1 - HIGH_SPEED_DAMP) * current_steer
        LAST_STEER_CMD = current_steer

        if self.v_ego < 30:
            current_steer = np.clip(current_steer, -0.93, 0.93)
        else:
            current_steer = np.clip(current_steer, -0.78, 0.78)

        # [SAT-CHK] 转向需求是否真的顶到限幅(接近/贴住 clip 上限就是饱和，
        # 就会触发 openpilot 的 steerSaturated "Turn Exceeds Steering Limit" 接管)。
        if abs(current_steer) > 0.85 and (now_ts - getattr(self, '_last_sat_t', 0.0)) > 5.0:
            _ys = np.abs(self.path_xyz[:, 1])
            cloudlog.warning(f"[SAT-CHK] steer={current_steer:.2f} y0={self.path_xyz[0,1]:.2f} y_max={_ys.max():.2f} y@5m={self.path_xyz[3,1]:.2f} curv={measured_curvature:.3f} rt={right_turn_active}")
            self._last_sat_t = now_ts

        self.x_sol[:, 3] = current_steer
        self.x0[3] = np.interp(DT_MDL, self.t_idxs[:LAT_MPC_N + 1], self.x_sol[:LAT_MPC_N + 1, 3])

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

        # ========== ★UNIFIED 横纵联动：写入 CurveSync（含低速保护）==========
        try:
            _nav_v = abs(float(self.curve_speed or 0.0))
            # ★ 修复：高速岔道用导航限速（如岔道限速60km/h），不再被 _decel_v(35) 钳制
            if _nav_v > 1.0:
                _t = _nav_v
                # 有导航限速目标：需要纵向 planner 配合减速
                self.curve_decel_active = True
            else:
                _t = max(float(getattr(self, 'curve_decel_speed_kph', 35.0)) / 3.6, 1.0)
                # 无导航限速：仅低速弯道时激活减速
                self.curve_decel_active = bool(self._steer_active_hyst or _in_turn_scene or is_cornering or abs(measured_curvature) > 0.001)
            _is_real_turn = bool(self._steer_active_hyst or abs(float(measured_curvature)) > 0.001)
            # ★ 修复：只要有有效目标速度就传给纵向（高速岔道也能生效）
            if _t > 1.0 and self.curve_decel_active:
                _conf = 1.0 if _nav_v > 1.0 else 0.6
                CurveSync.set_from_lateral(_t, curvature=abs(float(measured_curvature)), is_real_corner=_is_real_turn, confidence=_conf)
                self.curve_decel_target_v = _t
            else:
                CurveSync.set_from_lateral(0.0, force_zero=True)
                self.curve_decel_target_v = 0.0
        except Exception as e:
            cloudlog.warning("[CurveSync] pub failed: %s", str(e))
            self.curve_decel_target_v = 0.0
        # ========== ★UNIFIED 结束 ==========

    def publish(self, sm, pm, carrot):
        now = time.monotonic()
        if self.v_ego < 0.5:
            target_period = 1.0 / PUBLISH_RATE_PARKED
        elif self.v_ego < CONGESTION_VELO_THRESH:
            target_period = 1.0 / PUBLISH_RATE_CONGESTED
        else:
            target_period = 1.0 / PUBLISH_RATE_NORMAL

        if (now - self._last_publish_t) < target_period:
            return
        self._last_publish_t = now

        try:
            plan_solution_valid = self.solution_invalid_cnt < 1
            plan_send = messaging.new_message('lateralPlan')
            plan_send.valid = True
            try:
                plan_send.valid = sm.all_checks(service_list=['carState', 'controlsState', 'modelV2'])
            except Exception:
                pass
            lateralPlan = plan_send.lateralPlan
            try:
                lateralPlan.modelMonoTime = sm.logMonoTime['modelV2']
            except Exception:
                lateralPlan.modelMonoTime = 0

            # update() 已把转向弧线并入 path_xyz（近场基线0.40 + 0.70 弧线权重），
            # 此处若再混 0.35 弧线会把模型近场权重二次压到 ~20% → 右转贴不住，故不再二次混合。
            path_y = self.path_xyz[:, 1].copy()
            path_y = np.clip(path_y, GLOBAL_Y_MIN, GLOBAL_Y_MAX)
            lateralPlan.dPathPoints = path_y.tolist()
            try:
                _tp = None
                if (hasattr(self, 'turn_y_pts') and self.turn_y_pts is not None
                        and len(self.turn_y_pts) == CONTROL_N):
                    _tp = np.clip(self.turn_y_pts, GLOBAL_Y_MIN, GLOBAL_Y_MAX).tolist()
                else:
                    _tp = np.clip(path_y, GLOBAL_Y_MIN, GLOBAL_Y_MAX).tolist()
                lateralPlan.turnPathPoints = _tp
            except Exception:
                pass

            try:
                lateralPlan.psis = self.x_sol[0:CONTROL_N, 2].tolist()
            except Exception:
                lateralPlan.psis = [0.0] * CONTROL_N

            if len(self.v_plan) == TRAJECTORY_SIZE:
                try:
                    lateralPlan.curvatures = (self.x_sol[0:CONTROL_N, 3] / self.v_plan[0:CONTROL_N]).tolist()
                except Exception:
                    lateralPlan.curvatures = [0.0] * CONTROL_N
            else:
                try:
                    lateralPlan.curvatureRates = [
                        float(x / max(self.v_ego, MIN_SPEED)) for x in self.lat_mpc.u_sol.flatten().tolist()
                    ] + [0.0]
                except Exception:
                    lateralPlan.curvatureRates = [0.0] * (CONTROL_N + 1)

            lateralPlan.mpcSolutionValid = bool(plan_solution_valid)
            try:
                lateralPlan.solverExecutionTime = self.lat_mpc.solve_time
            except Exception:
                lateralPlan.solverExecutionTime = 0.0

            if self.debug_mode:
                try:
                    lateralPlan.solverCost = self.lat_mpc.cost
                    lateralPlan.solverState = log.LateralPlan.SolverState.new_message()
                    lateralPlan.solverState.x = self.x_sol.tolist()
                except Exception:
                    pass

            try:
                lateralPlan.position.x = self.x_sol[:, 0].tolist()
                lateralPlan.position.y = path_y.tolist()
                lateralPlan.position.z = self.path_xyz[:, 2].tolist()
            except Exception:
                pass

            try:
                _obs = int(min(self.obs_closest_dist, 99)) if self.obs_closest_dist < float("inf") else 0
                _off = self.obs_smooth_offset
                _prof_raw = np.max(np.abs(getattr(self, '_obs_profile_prev', np.zeros(TRAJECTORY_SIZE))))
                _prof_max = float(_prof_raw)
                _spd = int(self.v_ego * 3.6) if (self.curve_decel_active or self.v_ego > 0) else 0
                _mode = "车道" if self.lanelines_active else "无车道"
                _parked = "停" if self.has_roadside_parked else ""
                _avoid = "避" if self.avoidance_active else ""
                _curve = f"弯{int(self.curve_speed_limit)}" if self.curve_decel_active else ""
                _left_pressure = "左压" if self.has_left_pressure else ""
                _edge_tag = ""
                if getattr(self, '_deviation_dir', 0) == -1:
                    _edge_tag = "对向"
                elif getattr(self, '_deviation_dir', 0) == 1:
                    _edge_tag = "路肩"
                elif getattr(self, '_edge_valid', False):
                    _edge_tag = "路沿"
                _prefix = ""
                if abs(_off) > 0.05:
                    _prefix += f"偏{_off:+.2f}"
                if _prof_raw > 0.1:
                    _prefix += f"|廓{_prof_max:.2f}"
                if self.curve_decel_active:
                    _prefix += f"|弯{_spd}"
                lateralPlan.latDebugText = f"{_mode}{_prefix}|障{_obs}m{_parked}{_avoid}{_curve}{_left_pressure}{_edge_tag}"
            except Exception:
                lateralPlan.latDebugText = "lateral OK"

            pm.send('lateralPlan', plan_send)
        except Exception as e:
            cloudlog.warning("publish exception: %s", str(e))
            try:
                plan_send = messaging.new_message('lateralPlan')
                plan_send.valid = False
                lateralPlan = plan_send.lateralPlan
                lateralPlan.dPathPoints = [0.0] * CONTROL_N
                lateralPlan.psis = [0.0] * CONTROL_N
                lateralPlan.curvatures = [0.0] * CONTROL_N
                lateralPlan.mpcSolutionValid = False
                lateralPlan.latDebugText = "lateral err"
                pm.send('lateralPlan', plan_send)
            except Exception:
                pass


def main():
    pass


if __name__ == '__main__':
    main()
