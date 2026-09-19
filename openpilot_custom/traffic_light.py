#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
红绿灯决策模块（完整增强版 v3.1 —— 在 v3 基础上修复"起步防抖被 cannot_go 复位"导致二次启停复发）

- 保留 v3 全部原有逻辑：视觉最早稳定版、右转硬隔离、高德真接入融合、绿灯读秒放行
- v3 原有补丁全部保留：
  [P1] 绿灯起步后 2.5s 防抖维持（green_hold_after_start）
  [P2] 高速红灯 ETA 预判减速（high_speed_red_decel）
  [P3] 高德 cross/remain 合理性校验
  [P4] 高德红需视觉共识
  [P5] tl_reason 写入 Param，供 longitudinal_planner 消费
- ★ v3.1 新增 3 处补丁（根治"好了一段时间又出现"）：
  [F1] cannot_go 分支不复位 GREEN_STARTED（起步防抖窗口内保持 True）
  [F2] _write_reason 值没变则不写 Param（减少 I/O 抖动/丢帧）
  [F3] cannot_go 分支开头加闸门：起步防抖窗口内直接返回 green_hold_after_start
"""
import time
import cereal.messaging as messaging
from openpilot.common.params import Params  # ★v3 Param 写入 tl_reason

# ==================== 基础配置参数 ====================
STANDSTILL_LOCK_TIME = 2.8    # 红灯停稳锁定期(s)
GREEN_CONFIRM_FRAME = 3       # 绿灯连续识别帧数（视觉防抖，最早版）
GREEN_START_DELAY = 0.4       # 绿灯起步延迟(v2)
NO_GAODE_MODE = False
# 黄灯 & 绿灯倒计时安全阈值
YELLOW_LIGHT_DURATION = 3.0
GREEN_MIN_SAFE_SEC = 1.0
STOP_DECEL_LIMIT = 0.8
TIME_TO_STOPLINE = 1.8
CANNOT_GO_LOCK_TIME = 1.5
# 视觉过滤
TL_MAX_VALID_DIST = 80.0
HIGHWAY_ROAD_CLASS = 0
TOLL_GATE_FLAG = 1
URBAN_FAST_ROAD = 6
NIGHT_CONF_OFFSET = -0.12
CONF_MIN_LIMIT = 0.55
CONF_MAX_LIMIT = 0.85
BASE_CONF_THRESH = 0.78
# 高德融合参数
GAODE_VALID_REMAIN = 0.5
CROSS_PASS_MARGIN = 0.8
# ★v3 新增参数
GREEN_STARTED_HOLD = 2.5       # 绿灯起步后防抖维持窗口(s)——解决二次启停
HIGH_SPEED_RED_MIN_V = 3.0     # 高速红灯预判最低车速(m/s)
HIGH_SPEED_RED_ETA = 3.0       # 到达停止线预估<此秒数且红灯→开始预判减速
GAODE_CROSS_MIN = -50.0        # 高德剩余距离合理下限(m)，过滤异常负值
GAODE_CROSS_MAX = 600.0        # 高德剩余距离合理上限(m)
GAODE_REMAIN_MAX = 180.0       # 高德读秒合理上限(s)
# ==================== 全局状态变量 ====================
local_tl_state = "unknown"
state_count = 0
last_state = ""
standstill_time = 0.0
car_stop_flag = False
green_trigger_time = 0
is_night = False
stop_line_dist_global = None
# ★v3 起步防抖状态
GREEN_STARTED = False
GREEN_STARTED_TIME = 0.0
# ★v3.1 _write_reason 去重状态
_prev_written_reason = None
# 内存共享状态
SHARED_TL_STATE = {
    "tl_color": "unknown",
    "tl_mode": 1,
    "tl_lock": False,
    "timestamp": time.time(),
    "is_highway": False,
    "has_toll": False
}
_params_writer = None  # 延迟初始化 Param 写入器


def _write_reason(reason: str):
    """★v3.1 将 tl_reason 写入 Param；值没变则不写，减少 I/O 抖动"""
    global _params_writer, _prev_written_reason
    try:
        if _params_writer is None:
            _params_writer = Params()
        if reason == _prev_written_reason:
            return  # ★ 没变就不写
        _params_writer.put("tl_reason", reason.encode("utf-8"))
        _prev_written_reason = reason
    except Exception:
        pass


def switch_gaode_mode(use_gaode: bool):
    global NO_GAODE_MODE
    NO_GAODE_MODE = not use_gaode


# -------------------- 工具函数 --------------------
def _is_right_turn(turn_dir) -> bool:
    if turn_dir in (2, "2"):
        return True
    try:
        s = str(turn_dir).strip().lower()
    except Exception:
        return False
    return s in ("right", "右转", "r")


def _gaode_color_map(code) -> str:
    if isinstance(code, str):
        s = code.strip().lower()
        if s in ("1", "red"):
            return "red"
        if s in ("2", "green"):
            return "green"
        if s in ("3", "yellow"):
            return "yellow"
        return "unknown"
    try:
        c = int(code)
    except (ValueError, TypeError):
        return "unknown"
    return {1: "red", 2: "green", 3: "yellow"}.get(c, "unknown")


def _read_gaode_from_amap_navi():
    """从 amap_navi.shared_data 读取高德字段，含合理性校验(v3)"""
    color = "unknown"
    remain = 0.0
    cross = 9999.0
    turn = 0
    valid = False
    try:
        from openpilot.selfdrive.carrot import amap_navi as AN
        inst = getattr(AN, "amap_navi", None)
        if inst is None:
            inst = AN
        sd = getattr(inst, "shared_data", None)
        if sd is None:
            return color, remain, cross, turn, False
        c = getattr(sd, "trafficLightColor", None)
        color = _gaode_color_map(c)
        try:
            remain = float(getattr(sd, "trafficLightRemain", 0) or 0)
        except (ValueError, TypeError):
            remain = 0.0
        try:
            cross = float(getattr(sd, "cross_remain_dist", 9999) or 9999)
        except (ValueError, TypeError):
            cross = 9999.0
        try:
            turn = int(getattr(sd, "turn_dir", 0) or 0)
        except (ValueError, TypeError):
            turn = 0
        # ★v3 合理性校验：距离/读秒异常 → 判无效
        if cross < GAODE_CROSS_MIN or cross > GAODE_CROSS_MAX:
            cross = 9999.0
            valid = False
        if remain < 0 or remain > GAODE_REMAIN_MAX:
            remain = 0.0
            if color != "unknown":
                valid = False
        if color != "unknown" and remain > GAODE_VALID_REMAIN:
            valid = True
    except Exception:
        valid = False
    return color, remain, cross, turn, valid


# -------------------- 视觉本地判定 --------------------
def local_tl_check(raw_color: str, confidence: float, dist: float, lat_offset: float, stop_line_dist) -> str:
    global state_count, last_state
    dynamic_thresh = BASE_CONF_THRESH
    if stop_line_dist is None or stop_line_dist > 100:
        dynamic_thresh += 0.08
    elif 30 < stop_line_dist <= 100:
        dynamic_thresh += 0.03
    elif stop_line_dist <= 30:
        dynamic_thresh -= 0.05
    if abs(lat_offset) > 5:
        dynamic_thresh += 0.06
    elif 3 < abs(lat_offset) <= 5:
        dynamic_thresh += 0.03
    if is_night:
        dynamic_thresh += NIGHT_CONF_OFFSET
    dynamic_thresh = max(CONF_MIN_LIMIT, min(CONF_MAX_LIMIT, dynamic_thresh))
    if dist > TL_MAX_VALID_DIST:
        state_count = 0
        return "unknown"
    if confidence < dynamic_thresh:
        state_count = 0
        last_state = "unknown"
        return "unknown"
    if raw_color == "green":
        if last_state == "green":
            state_count += 1
        else:
            state_count = 1
        last_state = "green"
        if state_count >= GREEN_CONFIRM_FRAME:
            return "green"
        return "unknown"
    elif raw_color in ("red", "yellow"):
        state_count = 0
        last_state = raw_color
        return raw_color
    else:
        state_count = 0
        return "unknown"


# -------------------- 核心决策 --------------------
def get_tl_status(distance: float, lat_offset: float, car_speed: float,
                  raw_color: str, confidence: float,
                  gaode_color: str = "unknown", gaode_time: float = 0,
                  is_pure_highway=False, has_toll=False,
                  turn_dir=0):
    """核心决策 v3.1：保留 v3 全部逻辑 + 起步防抖不被 cannot_go 复位(F1/F3)"""
    # 右转硬隔离
    if _is_right_turn(turn_dir):
        _write_reason("right_turn_bypass")
        return ("unknown", 0, False, is_pure_highway, has_toll, "right_turn_bypass")

    global car_stop_flag, standstill_time, local_tl_state, green_trigger_time, state_count
    global GREEN_STARTED, GREEN_STARTED_TIME
    now = time.time()

    if is_pure_highway or has_toll:
        _write_reason("highway_or_toll")
        return ("unknown", 0, False, True, True, "highway_or_toll")

    tl_stable = local_tl_check(raw_color, confidence, distance, lat_offset, stop_line_dist_global)

    if car_speed < 0.3:
        if not car_stop_flag:
            standstill_time = now
            car_stop_flag = True
    else:
        car_stop_flag = False

    # 综合灯色
    _visual_green = (raw_color == "green")
    is_green = _visual_green or (gaode_color == "green" and gaode_time > 0)
    gaode_has_countdown = (gaode_color == "green" and gaode_time > 0)

    # ★v3 高速红灯预判（补丁 P2）：在 cannot_go 判定之前，优先处理高速红灯
    if tl_stable == "red" and car_speed > HIGH_SPEED_RED_MIN_V and distance > 0:
        eta = distance / car_speed
        if eta < HIGH_SPEED_RED_ETA:
            _write_reason("high_speed_red_decel")
            return ("red", 1, False, False, False, "high_speed_red_decel")

    # ★v3.1 [F3] 起步防抖窗口内：即使条件满足 cannot_go，也强制维持 green（双保险）
    if GREEN_STARTED and (now - GREEN_STARTED_TIME) < GREEN_STARTED_HOLD:
        # 防抖窗口内任何 red/cannot_go 都不锁红，维持放行
        _write_reason("green_hold_after_start")
        return ("green", 0, False, False, False, "green_hold_after_start")

    cannot_go = False
    reason_cannot = ""

    if tl_stable == "yellow" or gaode_color == "yellow":
        cannot_go = True
        reason_cannot = "yellow"
    elif is_green and gaode_has_countdown:
        if car_speed > 0.5:
            est_time = distance / car_speed
        else:
            est_time = distance / 1.5
        needed = est_time + CROSS_PASS_MARGIN
        if needed > gaode_time:
            cannot_go = True
            reason_cannot = "green_but_cannot_pass"
    elif is_green and not gaode_has_countdown:
        cannot_go = False
    else:
        if distance > 0 and car_speed < STOP_DECEL_LIMIT:
            est_time = distance / max(car_speed, 0.1)
            if est_time > TIME_TO_STOPLINE:
                cannot_go = True
                reason_cannot = "low_speed_timeout"

    if cannot_go:
        green_trigger_time = 0.0
        # ★v3.1 [F1] 起步防抖窗口内不复位 GREEN_STARTED（已被上方闸门拦截，这里再保险）
        if not (GREEN_STARTED and (now - GREEN_STARTED_TIME) < GREEN_STARTED_HOLD):
            GREEN_STARTED = False
        if car_stop_flag and (now - standstill_time) < CANNOT_GO_LOCK_TIME:
            _write_reason("cannot_go_lock:" + reason_cannot)
            return ("red", 1, True, False, False, "cannot_go_lock:" + reason_cannot)
        _write_reason("cannot_go:" + reason_cannot)
        return ("red", 1, False, False, False, "cannot_go:" + reason_cannot)

    # ★v3 高德红需视觉共识（补丁 P4）：视觉非红/绿时不被高德误红放大
    if not NO_GAODE_MODE and gaode_color != "unknown" and gaode_time > 0:
        if gaode_color == "red":
            _visual_agree = tl_stable in ("red", "yellow", "unknown")
            if _visual_agree and car_stop_flag:
                if now - standstill_time < STANDSTILL_LOCK_TIME:
                    _write_reason("gaode_red_lock")
                    return ("red", 1, True, False, False, "gaode_red_lock")
                _write_reason("gaode_red")
                return ("red", 1, False, False, False, "gaode_red")
        if gaode_color == "green" and gaode_time >= GREEN_MIN_SAFE_SEC:
            if tl_stable == "green" or tl_stable == "unknown":
                _write_reason("gaode_green")
                return ("green", 0, False, False, False, "gaode_green")

    # 纯视觉分支
    res = tl_stable
    if res == "red" and car_stop_flag:
        if now - standstill_time < STANDSTILL_LOCK_TIME:
            _write_reason("visual_red_lock")
            return ("red", 1, True, False, False, "visual_red_lock")

    if res == "green":
        # ★v3 起步防抖（补丁 P1）：起步后窗口内维持 green（上方闸门已优先处理，这里兜底）
        if GREEN_STARTED and (now - GREEN_STARTED_TIME) < GREEN_STARTED_HOLD:
            _write_reason("green_hold_after_start")
            return ("green", 0, False, False, False, "green_hold_after_start")
        if green_trigger_time == 0:
            green_trigger_time = now
        if now - green_trigger_time >= GREEN_START_DELAY:
            GREEN_STARTED = True
            GREEN_STARTED_TIME = now
            _write_reason("visual_green")
            return ("green", 0, False, False, False, "visual_green")
        else:
            _write_reason("visual_green_pending")
            return ("red", 1, False, False, False, "visual_green_pending")

    _write_reason("default")
    return (res, 0, False, False, False, "default")


# ==================== 后台主进程 ====================
if __name__ == "__main__":
    print("Traffic light filter service started (v3.1 Stable+RightTurnBypass+GaodeFusion+AntiStutter+HighSpeedDecel+NoReset)")
    sm = messaging.SubMaster([
        "modelV2", "carState", "amapNavi", "deviceState"
    ])
    while True:
        sm.update(0)
        car_speed = sm["carState"].vEgo
        dev_state = sm["deviceState"]
        brightness = dev_state.brightness if hasattr(dev_state, "brightness") else 100
        is_night = brightness < 60
        model_msg = sm["modelV2"]
        stop_line_dist_global = None
        try:
            if hasattr(model_msg, 'stopLines') and len(model_msg.stopLines.position) > 0:
                stop_line_dist_global = model_msg.stopLines.position[0][0]
        except Exception:
            stop_line_dist_global = None

        raw_color = "unknown"
        max_conf = 0.0
        min_dist = 999.0
        best_lat_offset = 0.0
        try:
            if hasattr(model_msg, 'trafficLights'):
                tl_list = model_msg.trafficLights
            else:
                tl_list = []
        except Exception:
            tl_list = []
        for tl in tl_list:
            dist_tl = tl.position[0]
            lat_tl = tl.position[1]
            if tl.confidence > max_conf:
                max_conf = tl.confidence
                min_dist = dist_tl
                best_lat_offset = lat_tl
                if tl.state == 1:
                    raw_color = "red"
                elif tl.state == 2:
                    raw_color = "green"
                elif tl.state == 3:
                    raw_color = "yellow"
                else:
                    raw_color = "unknown"
        turn_dir = 0
        is_pure_highway = False
        has_toll = False
        if sm.seen.get("amapNavi", False):
            nav = sm["amapNavi"]
            if hasattr(nav, "roadClass") and nav.roadClass == HIGHWAY_ROAD_CLASS:
                is_pure_highway = True
            if hasattr(nav, "tollGateStatus") and nav.tollGateStatus == TOLL_GATE_FLAG:
                has_toll = True
            if hasattr(nav, "turn_dir"):
                turn_dir = nav.turn_dir
        gaode_color, gaode_time, gaode_cross, gaode_turn, gaode_valid = _read_gaode_from_amap_navi()
        if gaode_turn not in (0, None):
            turn_dir = gaode_turn
        result = get_tl_status(
            distance=min_dist,
            lat_offset=best_lat_offset,
            car_speed=car_speed,
            raw_color=raw_color,
            confidence=max_conf,
            gaode_color=gaode_color if gaode_valid else "unknown",
            gaode_time=gaode_time if gaode_valid else 0.0,
            is_pure_highway=is_pure_highway,
            has_toll=has_toll,
            turn_dir=turn_dir
        )
        if len(result) == 6:
            tl_color, tl_mode, tl_lock, out_high, out_toll, _reason = result
        else:
            tl_color, tl_mode, tl_lock, out_high, out_toll = result
            _reason = "legacy"
        SHARED_TL_STATE["tl_color"] = tl_color
        SHARED_TL_STATE["tl_mode"] = tl_mode
        SHARED_TL_STATE["tl_lock"] = tl_lock
        SHARED_TL_STATE["timestamp"] = time.time()
        SHARED_TL_STATE["is_highway"] = out_high
        SHARED_TL_STATE["has_toll"] = out_toll
    # 兜底：每 10 帧强制写一次（确保 UI 有数据）
    frame_counter += 1
    if frame_counter % 10 == 0:
        if not hasattr(model_msg, 'trafficLights') or len(model_msg.trafficLights) == 0:
            _write_reason("default", force=True)
