#!/usr/bin/env python3
import time
import json
from io import StringIO

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

# ==================== 全局状态变量 ====================
local_tl_state = "unknown"
state_count = 0
last_state = ""
standstill_time = 0.0
car_stop_flag = False
green_trigger_time = 0.0

# 内存共享状态（对齐tl_status.json格式）
SHARED_TL_STATE = {
    "tl_color": "red",
    "tl_mode": 1,
    "tl_lock": False,
    "timestamp": 1781233914.4454553
}

def switch_gaode_mode(use_gaode: bool):
    """切换高德导航/纯本地视觉模式"""
    global NO_GAODE_MODE
    NO_GAODE_MODE = not use_gaode

def local_tl_check(raw_color: str, confidence: float) -> str:
    """纯本地视觉多帧防抖判定"""
    global state_count, last_state
    if confidence < 0.78:
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

def get_tl_status(distance: float, car_speed: float,
                  raw_color: str, confidence: float,
                  gaode_color: str = "unknown", gaode_time: float = 0):
    """红绿灯主逻辑入口"""
    global car_stop_flag, standstill_time, local_tl_state
    global green_trigger_time, state_count
    now = time.time()

    local_tl_state = raw_color
    tl_stable = local_tl_check(raw_color, confidence)

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
            return ("red", 1, True)
        return ("red", 1, False)

    # 模式分支
    if NO_GAODE_MODE:
        res = tl_stable
        if res == "red" and car_stop_flag:
            if now - standstill_time < STANDSTILL_LOCK_TIME:
                return ("red", 1, True)
        if res == "green":
            if green_trigger_time == 0.0:
                green_trigger_time = now
            if now - green_trigger_time >= GREEN_START_DELAY:
                return ("green", 0, False)
            else:
                return ("red", 1, False)
        return (res, 0, False)
    else:
        if gaode_color == "red":
            if car_stop_flag and now - standstill_time < STANDSTILL_LOCK_TIME:
                return ("red", 1, True)
            return ("red", 1, False)
        elif gaode_color == "green" and gaode_time > GREEN_MIN_SAFE_SEC:
            return ("green", 0, False)
        res = tl_stable
        if res == "green":
            if green_trigger_time == 0.0:
                green_trigger_time = now
            if now - green_trigger_time >= GREEN_START_DELAY:
                return ("green", 0, False)
            else:
                return ("red", 1, False)
        return (res, 0, False)

# ==================== 后台运行主循环 ====================
if __name__ == "__main__":
    print("Traffic light service started in background...")
    while True:
        try:
            # 【此处务必替换为真实业务数据】
            input_data = {
                "distance": 50.0,
                "car_speed": 0.0,
                "raw_color": "unknown",
                "confidence": 0.0,
                "gaode_color": "unknown",
                "gaode_time": 0
            }

            tl_color, tl_mode, tl_lock = get_tl_status(
                distance=input_data["distance"],
                car_speed=input_data["car_speed"],
                raw_color=input_data["raw_color"],
                confidence=input_data["confidence"],
                gaode_color=input_data["gaode_color"],
                gaode_time=input_data["gaode_time"]
            )

            # 更新共享状态
            SHARED_TL_STATE["tl_color"] = tl_color
            SHARED_TL_STATE["tl_mode"] = tl_mode
            SHARED_TL_STATE["tl_lock"] = tl_lock
            SHARED_TL_STATE["timestamp"] = time.time()

        except Exception as e:
            print(f"TL Service Error: {e}")
            # 异常安全兜底
            SHARED_TL_STATE["tl_color"] = "red"
            SHARED_TL_STATE["tl_mode"] = 1
            SHARED_TL_STATE["tl_lock"] = True

        time.sleep(0.05)