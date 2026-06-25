#!/usr/bin/env python3
import time
import cereal.messaging as messaging

# ==================== 基础配置参数 ====================
STANDSTILL_LOCK_TIME = 2.8    # 红灯停稳锁定时长(s)
GREEN_CONFIRM_FRAME = 3       # 绿灯连续识别帧数（视觉防抖）
GREEN_START_DELAY = 1.2       # 绿灯起步延迟(s)
NO_GAODE_MODE = False         # False=高德导航优先 True=纯本地视觉
# 黄灯 & 绿灯倒计时安全阈值
YELLOW_LIGHT_DURATION = 3.0
GREEN_MIN_SAFE_SEC = 2.5      # 绿灯剩余秒数小于该值，禁止起步
STOP_DECEL_LIMIT = 0.8        # 低速判定阈值(m/s)
TIME_TO_STOPLINE = 1.8        # 预估到达停止线超时阈值(s)
CANNOT_GO_LOCK_TIME = 1.5     # 无法通行状态锁定时长
# 新增优化常量
TL_MAX_VALID_DIST = 80.0      # 超过80米直接忽略（过滤远处路灯）
HIGHWAY_ROAD_CLASS = 0
TOLL_GATE_FLAG = 1
URBAN_FAST_ROAD = 6           # 城市快速路保留红绿灯
NIGHT_CONF_OFFSET = -0.12     # 夜间降低置信阈值，减少反光误检
CONF_MIN_LIMIT = 0.55
CONF_MAX_LIMIT = 0.85
BASE_CONF_THRESH = 0.78
# ==================== 全局状态变量 ====================
local_tl_state = "unknown"
state_count = 0
last_state = ""
standstill_time = 0.0
car_stop_flag = False
green_trigger_time = 0
is_night = False
stop_line_dist_global = None
# 内存共享状态（对齐tl_status.json/carrot读取格式）
SHARED_TL_STATE = {
    "tl_color": "unknown",
    "tl_mode": 1,
    "tl_lock": False,
    "timestamp": time.time(),
    "is_highway": False,
    "has_toll": False
}

def switch_gaode_mode(use_gaode: bool):
    global NO_GAODE_MODE
    NO_GAODE_MODE = not use_gaode

def local_tl_check(raw_color: str, confidence: float, dist: float, lat_offset: float, stop_line_dist) -> str:
    global state_count, last_state
    dynamic_thresh = BASE_CONF_THRESH

    # 1. 停止线距离分级修正
    if stop_line_dist is None or stop_line_dist > 100:
        dynamic_thresh += 0.08
    elif 30 < stop_line_dist <= 100:
        dynamic_thresh += 0.03
    elif stop_line_dist <= 30:
        dynamic_thresh -= 0.05

    # 2. 横向偏移修正，远离车道大幅提高门槛
    if abs(lat_offset) > 5:
        dynamic_thresh += 0.06
    elif 3 < abs(lat_offset) <= 5:
        dynamic_thresh += 0.03

    # 3. 夜间阈值偏移
    if is_night:
        dynamic_thresh += NIGHT_CONF_OFFSET

    # 阈值钳位防止越界
    dynamic_thresh = max(CONF_MIN_LIMIT, min(CONF_MAX_LIMIT, dynamic_thresh))

    # 远距离直接丢弃
    if dist > TL_MAX_VALID_DIST:
        state_count = 0
        return "unknown"

    # 置信度不达标直接丢弃
    if confidence < dynamic_thresh:
        state_count = 0
        last_state = "unknown"
        return "unknown"

    # 多帧状态防抖逻辑
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

def get_tl_status(distance: float, lat_offset: float, car_speed: float, raw_color: str, confidence: float,
                  gaode_color: str = "unknown", gaode_time: float = 0,
                  is_pure_highway=False, has_toll=False):
    global car_stop_flag, standstill_time, local_tl_state, green_trigger_time, state_count
    now = time.time()
    # 高速/收费站直接屏蔽红绿灯逻辑
    if is_pure_highway or has_toll:
        return ("unknown", 0, False, True, True)

    tl_stable = local_tl_check(raw_color, confidence, distance, lat_offset, stop_line_dist_global)

    # 车辆静止判定
    if car_speed < 0.3:
        if not car_stop_flag:
            standstill_time = now
            car_stop_flag = True
    else:
        car_stop_flag = False

    cannot_go = False
    if tl_stable == "yellow" or gaode_color == "yellow":
        cannot_go = True
    elif tl_stable == "green" and gaode_color == "green" and gaode_time > 0:
        if gaode_time < GREEN_MIN_SAFE_SEC:
            cannot_go = True
    elif distance > 0 and car_speed < STOP_DECEL_LIMIT:
        est_time = distance / max(car_speed, 0.1)
        if est_time > TIME_TO_STOPLINE:
            cannot_go = True

    if cannot_go:
        green_trigger_time = 0.0
        if car_stop_flag and (now - standstill_time) < CANNOT_GO_LOCK_TIME:
            return ("red", 1, True, False, False)
        return ("red", 1, False, False, False)

    # 高德优先模式
    if not NO_GAODE_MODE:
        if gaode_color == "red":
            if car_stop_flag and now - standstill_time < STANDSTILL_LOCK_TIME:
                return ("red", 1, True, False, False)
            return ("red", 1, False, False, False)
        elif gaode_color == "green" and gaode_time > GREEN_MIN_SAFE_SEC:
            return ("green", 0, False, False, False)

    # 纯视觉分支
    res = tl_stable
    if res == "red" and car_stop_flag:
        if now - standstill_time < STANDSTILL_LOCK_TIME:
            return ("red", 1, True, False, False)
    if res == "green":
        if green_trigger_time == 0:
            green_trigger_time = now
        if now - green_trigger_time >= GREEN_START_DELAY:
            return ("green", 0, False, False, False)
        else:
            return ("red", 1, False, False, False)
    return (res, 0, False, False, False)

# ==================== 后台主进程 ====================
if __name__ == "__main__":
    print("Traffic light filter service started, optimize highway toll avoid red brake")
    sm = messaging.SubMaster([
        "modelV2", "carState", "amapNavi", "deviceState"
    ])
    while True:
        sm.update(0)
        car_speed = sm["carState"].vEgo

        # 昼夜亮度判断
        dev_state = sm["deviceState"]
        brightness = dev_state.brightness if hasattr(dev_state, "brightness") else 100
        is_night = brightness < 60

        # 读取停止线距离
        model_msg = sm["modelV2"]
        stop_line_dist_global = None
        if len(model_msg.stopLines.position) > 0:
            stop_line_dist_global = model_msg.stopLines.position[0][0]

        # 解析最优红绿灯
        raw_color = "unknown"
        max_conf = 0.0
        min_dist = 999.0
        best_lat_offset = 0.0
        tl_list = model_msg.trafficLights
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

        # 高德导航数据解析
        gaode_color = "unknown"
        gaode_time = 0.0
        is_pure_highway = False
        has_toll = False
        if sm.seen.get("amapNavi", False):
            nav = sm["amapNavi"]
            if hasattr(nav, "roadClass") and nav.roadClass == HIGHWAY_ROAD_CLASS:
                is_pure_highway = True
            if hasattr(nav, "tollGateStatus") and nav.tollGateStatus == TOLL_GATE_FLAG:
                has_toll = True
            if hasattr(nav, "trafficLightColor"):
                gaode_color = nav.trafficLightColor
            if hasattr(nav, "trafficLightCountdown"):
                gaode_time = nav.trafficLightCountdown

        # 执行红绿灯决策
        tl_color, tl_mode, tl_lock, out_high, out_toll = get_tl_status(
            distance=min_dist,
            lat_offset=best_lat_offset,
            car_speed=car_speed,
            raw_color=raw_color,
            confidence=max_conf,
            gaode_color=gaode_color,
            gaode_time=gaode_time,
            is_pure_highway=is_pure_highway,
            has_toll=has_toll
        )

        # 更新全局共享状态，供carrot读取
        SHARED_TL_STATE["tl_color"] = tl_color
        SHARED_TL_STATE["tl_mode"] = tl_mode
        SHARED_TL_STATE["tl_lock"] = tl_lock
        SHARED_TL_STATE["timestamp"] = time.time()
        SHARED_TL_STATE["is_highway"] = out_high
        SHARED_TL_STATE["has_toll"] = out_toll
