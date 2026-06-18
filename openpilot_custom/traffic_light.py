#!/usr/bin/env python3
import time
import json
from io import StringIO
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
# ==================== 全局状态变量 ====================
local_tl_state = "unknown"
state_count = 0
last_state = ""
standstill_time = 0.0
car_stop_flag = False
green_trigger_time = 0
is_night = False              # 昼夜标记
# 内存共享状态（对齐tl_status.json/carrot读取格式）
SHARED_TL_STATE = {
    "tl_color": "red",
    "tl_mode": 1,
    "tl_lock": False,
    "timestamp": 1781233914.4454553,
    "is_highway": False,
    "has_toll": False
}
def switch_gaode_mode(use_gaode: bool):
    """切换高德导航/纯本地视觉模式"""
    global NO_GAODE_MODE
    NO_GAODE_MODE = not use_gaode
def local_tl_check(raw_color: str, confidence: float, dist: float) -> str:
    """纯本地视觉多帧防抖 + 远距离过滤"""
    global state_count, last
    # 远距离直接作废
    if dist > TL_MAX_VALID_DIST:
        state_count = 0
        return "unknown"
    # 夜间下调置信门槛
    valid_conf = 0.78
    if is_night:
        valid_conf += NIGHT_CONF_OFFSET
    if confidence < valid_conf:
        state_count = 0
        last_state = "red"
        return "red"
    if raw_color == "green":
        if last_state == "green":
            state_count += 1
        else:
            state_count = 1
        last_state = "green"
        if state_count >= GREEN_CONFIRM_FRAME:
            return "green"
        return "red"
    state_count = 0
    last_state = raw_color
    return raw_color
def get_tl_status(distance: float, car_speed: float, raw_color: str, confidence: float,
                  gaode_color: str = "unknown", gaode_time: float = 0,
                  is_pure_highway=False, has_toll=False):
    """红绿灯主逻辑入口，新增高速收费站拦截"""
    global car_stop_flag, standstill_time, local_tl_state, green_trigger_time, state_count
    now = time.time()
    # 核心兜底：纯高速/前方收费站 强制屏蔽红灯逻辑
    if is_pure_highway or has_toll:
        return ("unknown", 0, False, True, True)
    local_tl_state = raw_color
    tl_stable = local_tl_check(raw_color, confidence, distance)
    # 车辆静止判定
    if car_speed < 0.3:
        if not car_stop_flag:
            standstill_time = now
            car_stop_flag = True
    else:
        car_stop_flag = False
    # 判定是否无法通行
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
    # 模式分支
    if NO_GAODE_MODE:
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
    else:
        if gaode_color == "red":
            if car_stop_flag and now - standstill_time < STANDSTILL_LOCK_TIME:
                return ("red", 1, True, False, False)
            return ("red", 1, False, False, False)
        elif gaode_color == "green" and gaode_time > GREEN_MIN_SAFE_SEC:
            return ("green", 0, False, False, False)
        res = tl_stable
        if res == "green":
            if green_trigger_time == 0:
                green_trigger_time = now
            if now - green_trigger_time >= GREEN_START_DELAY:
                return ("green", 0, False, False, False)
            else:
                return ("red", 1, False, False, False)
        return (res, 0, False, False, False)
# ==================== 后台主进程（订阅模型+导航+车辆数据） ====================
if __name__ == "__main__":
    print("Traffic light filter service started, optimize highway toll avoid red brake")
    # 消息订阅
    sm = messaging.SubMaster([
        "modelV2", "carState", "amapNavi", "deviceState"
    ])
    while True:
        sm.update(0)
        # 1. 读取车辆速度
        car_speed = sm["carState"].vEgo
        # 2. 昼夜判断（根据设备亮度简单区分）
        dev_state = sm["deviceState"]
        # 若无brightness字段，默认按白天处理（亮度100）
        brightness = dev_state.brightness if hasattr(dev_state, "brightness") else 100
        is_night = brightness < 60
        # 3. 读取模型原始红绿灯数据
        raw_color = "unknown"
        max_conf = 0.0
        min_dist = 999.0
        model_msg = sm["modelV2"]
        if hasattr(model_msg, "traffic_lights"):
            tl_list = sm["modelV2"].traffic_lights
            for tl in tl_list:
                if tl.confidence > max_conf:
                    max_conf = tl.confidence
                    raw_color = tl.state
                    min_dist = tl.distance
        # 4. 安全读取高德导航
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
        # 5. 执行红绿灯判定主函数
        tl_color, tl_mode, tl_lock, out_high, out_toll = get_tl_status(
            distance=min_dist,
            car_speed=car_speed,
            raw_color=raw_color,
            confidence=max_conf,
            gaode_color=gaode_color,
            gaode_time=gaode_time,
            is_pure_highway=is_pure_highway,
            has_toll=has_toll
        )
        # 6 更新共享状态供给carrot读取
        SHARED_TL_STATE["tl_color"] = tl_color
        SHARED_TL_STATE["tl_mode"] = tl_mode
        SHARED_TL_STATE["tl_lock"] = tl_lock
        SHARED_TL_STATE["timestamp"] = time.time()
        SHARED_TL_STATE["is_highway"] = out_high
        SHARED_TL_STATE["has_toll"] = out_toll
        frame = 0
        while True:
            # 原有业务代码...
            frame += 1
            # 每200帧打印一次运行状态，不再刷屏
            # if frame % 200 == 0:
            #     #print("Traffic service running")