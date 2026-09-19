#!/usr/bin/env python3
import math
import numpy as np
import cereal.messaging as messaging
from opendbc.car.interfaces import ACCEL_MIN, ACCEL_MAX
from openpilot.common.conversions import Conversions as CV
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.selfdrive.controls.lib.longcontrol import LongCtrlState
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc, N
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import T_IDXS as T_IDXS_MPC
from openpilot.selfdrive.controls.lib.drive_helpers import CONTROL_N, get_accel_from_plan
from openpilot.selfdrive.car.cruise import V_CRUISE_MAX, V_CRUISE_UNSET
from openpilot.common.swaglog import cloudlog
from openpilot.common.params import Params
from openpilot.selfdrive.carrot.config import UnifiedParams

LON_MPC_STEP = 0.2
A_CRUISE_MIN = -3.0
A_CRUISE_MAX_VALS = [1.6, 1.2, 0.8, 0.6]
A_CRUISE_MAX_BP = [0., 10.0, 25., 40.]
CONTROL_N_T_IDX = ModelConstants.T_IDXS[:CONTROL_N]
ALLOW_THROTTLE_THRESHOLD = 0.5
MIN_ALLOW_THROTTLE_SPEED = 2.5

HIGHWAY_SPEED_ON = 65.0
HIGHWAY_SPEED_OFF = 50.0

COAST_STRONG_OFFSET = -0.22

# ===== 窄路/村路降速参数 =====
NARROW_ROAD_TARGET_KPH = 20.0
NARROW_ROAD_SPEED_RATIO = 0.80
NARROW_ROAD_MIN_V_CRUISE_KPH = 15.0
NARROW_ROAD_MODEL_WIDTH_THRESH = 5.5
NARROW_ROAD_RADAR_WIDTH_THRESH = 4.5
NARROW_ROAD_RADAR_DIST = 25.0
NARROW_ROAD_LOG_PERIOD = 20
NARROW_ROAD_PATH_JITTER_THRESH = 0.12
NARROW_ROAD_AVAIL_WIDTH_THRESH = 3.5
LANE_PROB_NARROW_THRESH = 0.40

# ===== 弯道减速参数（已修复：放宽弯道表）=====
# ===== 弯道减速参数 =====
CORNER_STEER_BP = [10.0, 20.0, 30.0, 45.0, 60.0]
CORNER_STEER_VALS = [65.0, 60.0, 50.0, 35.0, 25.0]
CORNER_SPEED_COMP_FACTOR = 0.10
CORNER_SPEED_COMP_MAX = 25.0
CORNER_MIN_KPH = 8.0
CORNER_AY_MAX = 2.5
CORNER_SPEED_FACTOR = 0.93
A_TOTAL_MAX_BP = [20., 40., 60., 80., 120.]
A_TOTAL_MAX_VALS = [2.5, 3.8, 4.5, 5.0, 5.5]
JERK_FACTOR_BASE = 1.5
JERK_FACTOR_MIN = 0.8

# 紧急弯参数
# 紧急弯参数（只在方向盘打很大时才介入）
EMERGENCY_STEER_BP = [45.0, 60.0, 75.0]
EMERGENCY_STEER_VALS = [30.0, 22.0, 15.0]

# 限速过渡参数
LIMIT_DROP_THRESHOLD = 15.0 / 3.6
LIMIT_DROP_RATIO = 0.85
LIMIT_DROP_HOLD_FRAMES = int(2.0 / DT_MDL)

LIMIT_DROP_MAX_KPH_PER_FRAME = 30.0
LIMIT_UP_MAX_KPH_PER_FRAME = 60.0


def get_max_accel(v_ego):
    return np.interp(v_ego, A_CRUISE_MAX_BP, A_CRUISE_MAX_VALS)


def get_coast_accel(pitch):
    return np.sin(pitch) * -5.65 + COAST_STRONG_OFFSET


def limit_accel_in_turns(v_ego, angle_steers, a_target, CP):
    steer_abs = abs(angle_steers)
    if v_ego > 20 or steer_abs < 3.0:
        return a_target
    a_total_max = np.interp(v_ego, A_TOTAL_MAX_BP, A_TOTAL_MAX_VALS)
    a_y = v_ego ** 2 * angle_steers * CV.DEG_TO_RAD / (CP.steerRatio * CP.wheelbase)
    a_x_allowed = math.sqrt(max(a_total_max ** 2 - a_y ** 2, 0.0))
    if steer_abs > 20.0:
        a_x_allowed = min(a_x_allowed, 0.6)
    return [a_target[0], min(a_target[1], a_x_allowed)]



class LongitudinalPlanner:
    def __init__(self, CP, init_v=0.0, init_a=0.0, dt=DT_MDL):
        self.CP = CP
        self.mpc = LongitudinalMpc(dt=dt)
        self.mpc.mode = 'acc'
        self.fcw = False
        self.dt = dt
        self.allow_throttle = True
        self.a_desired = init_a
        self.v_desired_filter = FirstOrderFilter(init_v, 3.5, self.dt)
        self.output_a_target = 0.0
        self.output_v_target_now = 0.0
        self.output_j_target_now = 0.0
        self.output_should_stop = False
        self.v_desired_trajectory = np.zeros(CONTROL_N)
        self.a_desired_trajectory = np.zeros(CONTROL_N)
        self.j_desired_trajectory = np.zeros(CONTROL_N)
        self.solverExecutionTime = 0.0
        self.vCluRatio = 1.0
        self.v_cruise_kph = 0.0
        self.params = UnifiedParams()
        self.sys_params = Params()
        self.frame = 0
        self.red_hold = False
        self.is_highway_latched = False

        self._limit_drop_target = 0.0
        self._limit_drop_timer = 0
        self._limit_drop_stage = 0
        self._prev_v_cruise_raw = 0.0

        self._carrot_smooth_limit = 30.0
        self._corner_v_smooth = FirstOrderFilter(CORNER_MIN_KPH / 3.6, 0.5, self.dt)


    @staticmethod
    def parse_model(model_msg):
        if (len(model_msg.position.x) == ModelConstants.IDX_N and
            len(model_msg.velocity.x) == ModelConstants.IDX_N and
            len(model_msg.acceleration.x) == ModelConstants.IDX_N):
            x = np.interp(T_IDXS_MPC, ModelConstants.T_IDXS, model_msg.position.x)
            v = np.interp(T_IDXS_MPC, ModelConstants.T_IDXS, model_msg.velocity.x)
            a = np.interp(T_IDXS_MPC, ModelConstants.T_IDXS, model_msg.acceleration.x)
            j = np.zeros(len(T_IDXS_MPC))
        else:
            x = np.zeros(len(T_IDXS_MPC))
            v = np.zeros(len(T_IDXS_MPC))
            a = np.zeros(len(T_IDXS_MPC))
            j = np.zeros(len(T_IDXS_MPC))
        throttle_prob = 1.0
        if len(model_msg.meta.disengagePredictions.gasPressProbs) > 1:
            throttle_prob = model_msg.meta.disengagePredictions.gasPressProbs[1]
        return x, v, a, j, throttle_prob

    def _detect_narrow_road(self, sm, lateral_planner=None):
        debug = {"lane_w": 0.0, "radar_span": None, "nav_narrow": False,
                 "jitter": None, "avail_w": None}
        reasons = []
        try:
            _model = sm['modelV2']
            _lw = 0.0
            _lw += float(getattr(_model, 'laneWidthLeft', 0.0) or 0.0)
            _lw += float(getattr(_model, 'laneWidthRight', 0.0) or 0.0)
            debug["lane_w"] = _lw
            if 0 < _lw < NARROW_ROAD_MODEL_WIDTH_THRESH:
                reasons.append(f"modelW={_lw:.2f}")
        except Exception as e:
            debug["model_err"] = str(e)
        try:
            _radar = sm['radarState']
            _left_y, _right_y = None, None
            for lead in (_radar.leadOne, _radar.leadTwo):
                if not lead.status:
                    continue
                d = float(getattr(lead, 'dRel', 0.0) or 0.0)
                y = float(getattr(lead, 'yRel', 0.0) or 0.0)
                if 0 < d < NARROW_ROAD_RADAR_DIST:
                    if y < 0 and (_left_y is None or d < _left_y[1]):
                        _left_y = (y, d)
                    elif y > 0 and (_right_y is None or d < _right_y[1]):
                        _right_y = (y, d)
            if _left_y is not None and _right_y is not None:
                span = abs(_right_y[0]) + abs(_left_y[0])
                debug["radar_span"] = span
                if span < NARROW_ROAD_RADAR_WIDTH_THRESH:
                    reasons.append(f"radarSpan={span:.2f}")
        except Exception as e:
            debug["radar_err"] = str(e)
        try:
            from openpilot.selfdrive.carrot.nav import NAV_MSG_DATA
            _nav_narrow = bool(NAV_MSG_DATA.get("is_narrow_road", False))
            debug["nav_narrow"] = _nav_narrow
            if _nav_narrow:
                reasons.append("navNarrow=True")
        except Exception:
            debug["nav_narrow"] = None
        try:
            _pos_y = sm['modelV2'].position.y
            if len(_pos_y) >= 10:
                _py = np.array(_pos_y[:10], dtype=float)
                _std = float(np.std(np.diff(_py)))
                debug["jitter"] = round(_std, 3)
                if _std > NARROW_ROAD_PATH_JITTER_THRESH:
                    reasons.append(f"pathJitter={_std:.3f}")
        except Exception as e:
            debug["jitter_err"] = str(e)
        if lateral_planner is not None:
            try:
                _avail = getattr(lateral_planner, 'available_road_width', None)
                if _avail is not None:
                    _avail_f = float(_avail)
                    debug["avail_w"] = round(_avail_f, 2)
                    if 0 < _avail_f < NARROW_ROAD_AVAIL_WIDTH_THRESH:
                        reasons.append(f"availW={_avail_f:.2f}")
            except Exception:
                pass
        is_narrow = len(reasons) > 0
        reason = ";".join(reasons) if is_narrow else ""
        return is_narrow, reason, debug

    def _calc_corner_limit_v(self, steer_abs_d, v_ego):
        _corner_kph = float(np.interp(steer_abs_d, CORNER_STEER_BP, CORNER_STEER_VALS))
        _comp = min(CORNER_SPEED_COMP_FACTOR * (v_ego * 3.6 / 80.0), CORNER_SPEED_COMP_MAX / 100.0)
        _corner_kph = max(_corner_kph * (1.0 - _comp), CORNER_MIN_KPH)
        _corner_ms = _corner_kph / 3.6
        self._corner_v_smooth.update(_corner_ms)
        return max(self._corner_v_smooth.x, CORNER_MIN_KPH / 3.6)


    def _sync_carrot_smooth_limit(self, carrot):
        try:
            _lim = getattr(carrot, 'nRoadLimitSpeed_smooth', None)
            if _lim is not None:
                self._carrot_smooth_limit = float(_lim)
        except Exception:
            pass
        try:
            if self._carrot_smooth_limit <= 0:
                self._carrot_smooth_limit = 30.0
        except Exception:
            pass

    def update(self, sm, carrot, lateral_planner=None):
        self.frame += 1
        v_ego = sm['carState'].vEgo
        left_blink = sm['carState'].leftBlinker
        right_blink = sm['carState'].rightBlinker
        is_turn_signal = left_blink or right_blink
        v_ego_kph = v_ego * 3.6
        if v_ego_kph >= HIGHWAY_SPEED_ON:
            self.is_highway_latched = True
        elif v_ego_kph < HIGHWAY_SPEED_OFF:
            self.is_highway_latched = False

        steer_angle_without_offset = sm['carState'].steeringAngleDeg - sm['liveParameters'].angleOffsetDeg
        _steer_abs_d = abs(steer_angle_without_offset)

        v_cruise_kph = min(sm['carState'].vCruise, V_CRUISE_MAX)
        self.v_cruise_kph = carrot.update(sm, v_cruise_kph, self.mpc.mode)
        self.mpc.mode = carrot.mode
        v_cruise = self.v_cruise_kph * CV.KPH_TO_MS
        _v_cruise_raw = v_cruise

        self._sync_carrot_smooth_limit(carrot)

        try:
            _is_narrow, _reason, _dbg = self._detect_narrow_road(sm, lateral_planner)
            if _is_narrow:
                _target_kph = max(NARROW_ROAD_TARGET_KPH, NARROW_ROAD_MIN_V_CRUISE_KPH)
                if self.v_cruise_kph > _target_kph:
                    v_cruise = _target_kph * CV.KPH_TO_MS
                if (self.frame % NARROW_ROAD_LOG_PERIOD) == 0:
                    cloudlog.info(f"[NarrowRoad] TRIGGER {self.v_cruise_kph:.0f}"
                                  f"->{_target_kph:.0f} kph reason={_reason}")
            else:
                if (self.frame % NARROW_ROAD_LOG_PERIOD) == 0:
                    cloudlog.info(f"[NarrowRoad] no-trigger laneW={_dbg.get('lane_w',0):.2f}")
        except Exception as e:
            cloudlog.warning(f"[NarrowRoad] check failed: {e}")

        vCluRatio = sm['carState'].vCluRatio
        if vCluRatio > 0.5:
            self.vCluRatio = vCluRatio
            v_cruise *= vCluRatio
            _v_cruise_raw = v_cruise

        v_cruise_initialized = sm['carState'].vCruise != V_CRUISE_UNSET
        long_control_off = sm['controlsState'].longControlState == LongCtrlState.off
        force_slow_decel = sm['controlsState'].forceDecel

        reset_state = long_control_off
        if self.CP.openpilotLongitudinalControl:
            reset_state = reset_state or not sm['selfdriveState'].enabled
        reset_state = reset_state or not v_cruise_initialized or carrot.soft_hold_active

        prev_accel_constraint = not (reset_state or sm['carState'].standstill)

        if self.mpc.mode == 'acc':
            accel_limits = [A_CRUISE_MIN, carrot.get_carrot_accel(v_ego)]
            accel_limits_turns = limit_accel_in_turns(v_ego, steer_angle_without_offset, accel_limits, self.CP)
        else:
            accel_limits = [ACCEL_MIN, ACCEL_MAX]
            accel_limits_turns = [ACCEL_MIN, ACCEL_MAX]

        if is_turn_signal:
            accel_limits_turns[0] = max(accel_limits_turns[0], -0.45)

        if reset_state:
            self.v_desired_filter.x = v_ego
            self.a_desired = np.clip(sm['carState'].aEgo, accel_limits_turns[0], accel_limits_turns[1])
            self.mpc.prev_a = np.full(N + 1, self.a_desired)
            accel_limits_turns[0] = 0.0

        self.v_desired_filter.x = max(0.0, self.v_desired_filter.x)

        x, v, a, j, throttle_prob = self.parse_model(sm['modelV2'])

        if self.params.get_int("CommaLongAcc") > 0:
            self.allow_throttle = (throttle_prob > ALLOW_THROTTLE_THRESHOLD) or (v_ego <= MIN_ALLOW_THROTTLE_SPEED)

        if not self.allow_throttle:
            _v_interp = np.clip(v_ego, MIN_ALLOW_THROTTLE_SPEED, MIN_ALLOW_THROTTLE_SPEED * 2)
            clipped_accel_coast_interp = np.interp(
                _v_interp,
                [MIN_ALLOW_THROTTLE_SPEED, MIN_ALLOW_THROTTLE_SPEED * 2],
                [accel_limits_turns[1], COAST_STRONG_OFFSET]
            )
            accel_limits_turns[1] = min(accel_limits_turns[1], clipped_accel_coast_interp)


        has_lead = sm['radarState'].leadOne.status

        if not has_lead:
            accel_limits_turns[0] = max(accel_limits_turns[0], -0.15)

        if force_slow_decel:
            v_cruise = 0.0
            _v_cruise_raw = 0.0

        if not has_lead and self.v_desired_filter.x < v_ego + 1.0:
            self.v_desired_filter.x = v_ego

        _limit_drop = self._prev_v_cruise_raw - _v_cruise_raw
        if _limit_drop > LIMIT_DROP_THRESHOLD and self._limit_drop_stage == 0:
            self._limit_drop_target = self._prev_v_cruise_raw * LIMIT_DROP_RATIO
            self._limit_drop_stage = 1
            self._limit_drop_timer = 0
            cloudlog.info(f"[LimitDrop] 跳变检测: {self._prev_v_cruise_raw*3.6:.0f}"
                          f"→{_v_cruise_raw*3.6:.0f}, 过渡值={self._limit_drop_target*3.6:.0f}")

        if self._limit_drop_stage == 1:
            _v_cruise_raw = min(_v_cruise_raw, self._limit_drop_target)
            self._limit_drop_timer += 1
            if self._limit_drop_timer > LIMIT_DROP_HOLD_FRAMES:
                self._limit_drop_stage = 2
                cloudlog.info(f"[LimitDrop] 过渡结束，进入最终限速 {_v_cruise_raw*3.6:.0f}")

        if self._limit_drop_stage == 2:
            pass

        if _limit_drop < 5.0 / 3.6:
            if self._limit_drop_stage != 0:
                cloudlog.info("[LimitDrop] 限速恢复，重置过渡状态")
            self._limit_drop_stage = 0
            self._limit_drop_timer = 0

        self._prev_v_cruise_raw = v_cruise

        if _steer_abs_d > 3.0 and v_ego > 5.0:
            _corner_v = self._calc_corner_limit_v(_steer_abs_d, v_ego)
            if _steer_abs_d > EMERGENCY_STEER_BP[0]:
                _emer_v = float(np.interp(_steer_abs_d, EMERGENCY_STEER_BP, EMERGENCY_STEER_VALS)) / 3.6
                _corner_v = min(_corner_v, _emer_v)
            _effective_v = min(_v_cruise_raw, _corner_v)
            v_cruise = _effective_v

            _overspeed = v_ego - _effective_v
            if _overspeed > 3.0 / 3.6:
                accel_limits_turns[0] = min(accel_limits_turns[0], -3.0)
            elif _overspeed > 1.0 / 3.6:
                accel_limits_turns[0] = min(accel_limits_turns[0], -2.0)
            elif _overspeed > 0.3 / 3.6:
                accel_limits_turns[0] = min(accel_limits_turns[0], -1.0)

            if (self.frame % 20) == 0:
                cloudlog.info(f"[CornerDecel] steer={_steer_abs_d:.1f}° "
                              f"v={v_ego*3.6:.0f}km/h -> effective={_effective_v*3.6:.0f}kph")
        else:
            v_cruise = _v_cruise_raw


        if lateral_planner is not None:
            _MIN_SPEED = 1.0
            _lp_curv = abs(float(getattr(lateral_planner, 'measured_curvature', 0.0) or 0.0))
            _gate = (_steer_abs_d > 30.0) or (_lp_curv > 0.004)
            if _gate:
                _target_v = getattr(lateral_planner, 'curve_decel_target_v', 0.0)
                if _target_v and _target_v > _MIN_SPEED:
                    _target_v = max(_target_v * CORNER_SPEED_FACTOR, _MIN_SPEED)
                    v_cruise = min(v_cruise, _target_v)
                    if (self.frame % 20) == 0:
                        cloudlog.info(f"[CurveSync] ACTIVE steer={_steer_abs_d:.1f} "
                                      f"curv={_lp_curv:.4f} -> {_target_v*3.6:.1f}kph")
            elif (self.frame % 20) == 0:
                cloudlog.info(f"[CurveSync] skip(mild) steer={_steer_abs_d:.1f} "
                              f"curv={_lp_curv:.4f}")


        _carrot_limit_ms = self._carrot_smooth_limit / 3.6
        if _carrot_limit_ms > 0.0 and _carrot_limit_ms < 300.0:
            v_cruise = min(v_cruise, _carrot_limit_ms)
            if (self.frame % 20) == 0:
                cloudlog.info(f"[CarrotLimit] using nRoadLimitSpeed_smooth="
                              f"{self._carrot_smooth_limit:.0f}km/h -> {_carrot_limit_ms*3.6:.1f}m/s")

        if lateral_planner is not None and not has_lead:
            _has_parked = getattr(lateral_planner, 'has_roadside_parked', False)
            _has_static = getattr(lateral_planner, 'has_static_obstacle', False)
            if _has_parked or _has_static:
                _obs_dist = getattr(lateral_planner, 'obs_closest_dist', float('inf'))
                if 0 < _obs_dist < 45.0 and v_ego > 3.0:
                    _park_kph = np.interp(_obs_dist, [10.0, 20.0, 35.0, 45.0],
                                          [8.0, 11.0, 16.0, 20.0])
                    v_cruise = min(v_cruise, _park_kph / 3.6)

        try:
            _radar = sm['radarState']
            _near_left = _near_right = None
            for _ld in (_radar.leadOne, _radar.leadTwo):
                if not _ld.status:
                    continue
                _d = float(getattr(_ld, 'dRel', 0.0) or 0.0)
                _y = float(getattr(_ld, 'yRel', 0.0) or 0.0)
                if 0 < _d < 30.0 and abs(_y) > 0.6:
                    if _y < 0 and (_near_left is None or _d < _near_left[1]):
                        _near_left = (_y, _d)
                    elif _y > 0 and (_near_right is None or _d < _near_right[1]):
                        _near_right = (_y, _d)
            if _near_left is not None and _near_right is not None and not has_lead:
                _span = abs(_near_left[0]) + abs(_near_right[0])
                if _span < 5.0 and v_ego > 3.0:
                    v_cruise = min(v_cruise, 12.0 / 3.6)
        except Exception:
            pass

        v_cruise_for_mpc = v_cruise
        if has_lead and sm['radarState'].leadOne.status:
            try:
                _lead_v_rel = float(sm['radarState'].leadOne.vRel)
            except Exception:
                _lead_v_rel = None
            if _lead_v_rel is not None:
                _lead_v = max(0.0, v_ego - _lead_v_rel)
                if _lead_v < v_cruise:
                    v_cruise_for_mpc = _lead_v
        elif not has_lead and self.v_cruise_kph > 0:
            if v_ego * 3.6 > self.v_cruise_kph + 1.0:
                v_cruise_for_mpc = v_ego
            else:
                v_cruise_for_mpc = v_cruise

        _jerk_factor = JERK_FACTOR_BASE
        if _steer_abs_d > 3.0:
            if _steer_abs_d > 25.0:
                _jerk_factor = 0.8
            else:
                _jerk_factor = max(JERK_FACTOR_BASE - 0.5 * (min(_steer_abs_d, 15.0) / 15.0), JERK_FACTOR_MIN)

        self.mpc.set_weights(prev_accel_constraint, personality=sm['selfdriveState'].personality,
                              jerk_factor=_jerk_factor)
        self.mpc.set_accel_limits(accel_limits_turns[0], accel_limits_turns[1])
        self.mpc.set_cur_state(self.v_desired_filter.x, self.a_desired)
        self.mpc.update(carrot, reset_state, sm['radarState'], v_cruise_for_mpc,
                        x, v, a, j, personality=sm['selfdriveState'].personality)

        self.v_desired_trajectory = np.interp(CONTROL_N_T_IDX, T_IDXS_MPC, self.mpc.v_solution)
        self.a_desired_trajectory = np.interp(CONTROL_N_T_IDX, T_IDXS_MPC, self.mpc.a_solution)
        self.j_desired_trajectory = np.interp(CONTROL_N_T_IDX, T_IDXS_MPC[:-1], self.mpc.j_solution)

        self.fcw = self.mpc.crash_cnt > 2 and not sm['carState'].standstill and not reset_state

        a_prev = self.a_desired
        self.a_desired = float(np.interp(self.dt, CONTROL_N_T_IDX, self.a_desired_trajectory))
        self.v_desired_filter.x += self.dt * (self.a_desired + a_prev) / 2.0

        longitudinalActuatorDelay = self.params.get_float("LongActuatorDelay") * 0.01
        vEgoStopping = self.params.get_float("VEgoStopping") * 0.01
        action_t = longitudinalActuatorDelay + DT_MDL

        output_a_target_mpc, output_should_stop_mpc, output_v_target_mpc, _ = get_accel_from_plan(
            self.v_desired_trajectory, self.a_desired_trajectory, CONTROL_N_T_IDX,
            action_t=action_t, vEgoStopping=vEgoStopping)

        self.output_a_target = output_a_target_mpc
        self.output_v_target_now = output_v_target_mpc
        self.output_should_stop = output_should_stop_mpc
        self.output_j_target_now = self.j_desired_trajectory[0]

    def publish(self, sm, pm, carrot):
        plan_send = messaging.new_message('longitudinalPlan')
        plan_send.valid = sm.all_checks(service_list=['carState', 'controlsState', 'selfdriveState'])
        longitudinalPlan = plan_send.longitudinalPlan
        longitudinalPlan.modelMonoTime = sm.logMonoTime['modelV2']
        longitudinalPlan.processingDelay = (plan_send.logMonoTime / 1e9) - sm.logMonoTime['modelV2']
        longitudinalPlan.solverExecutionTime = self.mpc.solve_time
        longitudinalPlan.speeds = self.v_desired_trajectory.tolist()
        longitudinalPlan.accels = self.a_desired_trajectory.tolist()
        longitudinalPlan.jerks = self.j_desired_trajectory.tolist()
        longitudinalPlan.hasLead = sm['radarState'].leadOne.status
        longitudinalPlan.longitudinalPlanSource = self.mpc.source
        longitudinalPlan.fcw = self.fcw
        longitudinalPlan.aTarget = float(self.output_a_target)
        longitudinalPlan.vTargetNow = float(self.output_v_target_now)
        longitudinalPlan.jTargetNow = float(self.output_j_target_now)
        longitudinalPlan.shouldStop = bool(self.output_should_stop)
        longitudinalPlan.allowBrake = True
        longitudinalPlan.allowThrottle = self.allow_throttle
        longitudinalPlan.xState = carrot.xState.value
        longitudinalPlan.trafficState = carrot.trafficState.value
        longitudinalPlan.cruiseTarget = self.v_cruise_kph
        longitudinalPlan.tFollow = float(self.mpc.t_follow)
        longitudinalPlan.desiredDistance = float(self.mpc.desired_distance)
        longitudinalPlan.events = carrot.events.to_msg()
        longitudinalPlan.myDrivingMode = carrot.myDrivingMode.value
        pm.send('longitudinalPlan', plan_send)
