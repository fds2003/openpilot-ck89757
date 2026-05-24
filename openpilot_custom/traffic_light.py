#!/usr/bin/env python3
import time

# 基础参数
STANDSTILL_LOCK_TIME = 2.8    # 红灯停稳锁定时长
GREEN_CONFIRM_FRAME = 3       # 绿灯连续识别帧数
GREEN_START_DELAY = 1.2       # 绿灯起步延迟
NO_GAODe_MODE = True          # 默认纯本地稳定模式

# 新增：黄灯与安全通过参数（修复二次起步核心）
YELLOW_LIGHT_DURATION = 3.0
GREEN_MIN_SAFE_SEC = 2.5      # 绿灯剩余<此值 绝不起步
STOP_DECEL_LIMIT = 0.8
TIME_TO_STOPLINE = 1.8
CANNOT_GO_LOCK_TIME = 1.5

local_tl_state = "unknown"
state_count = 0
last_state = ""
standstill_time = 0
car_stop_flag = False

# 切换模式函数
def switch_gaode_mode(use_gaode:bool):
    global NO_GAODe_MODE
    NO_GAODe_MODE = not use_gaode

# 纯本地视觉稳定判定（无高德百分百稳）
def local_tl_check(raw_color, confidence):
    global state_count, last_state
    # 低置信直接默认红灯保守
    if confidence < 0.78:
        return "red"
    if raw_color == "green":
        if last_state == "green":
            state_count +=1
        else:
            state_count = 1
            last_state = "green"
        # 凑够帧数才认定绿灯
        if state_count >= GREEN_CONFIRM_FRAME:
            return "green"
        return "red"
    elif raw_color == "yellow":
        state_count = 0
        last_state = "yellow"
        return "yellow"
    else:
        state_count = 0
        last_state = raw_color
        return raw_color

# 主状态输出（完整修复：黄灯+倒计时+过不去停车+防二次起步）
def get_tl_status(distance, car_speed, gaode_color="unknown", gaode_time=0):
    global car_stop_flag, standstill_time, local_tl_state
    now = time.time()

    # 车辆静止判定
    if car_speed < 0.3:
        if not car_stop_flag:
            standstill_time = now
            car_stop_flag = True
    else:
        car_stop_flag = False

    # ============== 核心修复：过不去直接强制停车 ==============
    cannot_go = False
    # 1. 黄灯直接停车
    if local_tl_state == "yellow" or gaode_color == "yellow":
        cannot_go = True
    # 2. 绿灯倒计时不足 不起步
    elif (local_tl_state == "green" and gaode_color == "green"
          and gaode_time > 0 and gaode_time < GREEN_MIN_SAFE_SEC):
        cannot_go = True
    # 3. 距离远速度慢，预估到线超时 → 停车
    elif distance > 0 and car_speed < STOP_DECEL_LIMIT:
        est_time = distance / max(car_speed, 0.1)
        if est_time > TIME_TO_STOPLINE:
            cannot_go = True

    # 强制停车锁定，防止二次起步
    if cannot_go:
        if car_stop_flag and (now - standstill_time < CANNOT_GO_LOCK_TIME):
            return ("red", 1, True)
        return ("red", 1, False)
    # ==========================================================

    # 无高德导航：纯本地稳定逻辑
    if NO_GAODe_MODE:
        res = local_tl_check(local_tl_state, 0.8)
        # 静止红灯强制锁定
        if res == "red" and car_stop_flag:
            if now - standstill_time < STANDSTILL_LOCK_TIME:
                return ("red", 1, True)
        # 绿灯延迟放行
        if res == "green":
            time.sleep(GREEN_START_DELAY)
            return ("green", 0, False)
        return (res, 0, False)
    
    # 开启高德导航：高德优先兜底
    else:
        if gaode_color == "red":
            if car_stop_flag and now - standstill_time < STANDSTILL_LOCK_TIME:
                return ("red", 1, True)
            return ("red", 1, False)
        elif gaode_color == "green" and gaode_time > GREEN_MIN_SAFE_SEC:
            return ("green", 0, False)
        # 高德异常回落本地
        return (local_tl_check(local_tl_state,0.8),0,False)