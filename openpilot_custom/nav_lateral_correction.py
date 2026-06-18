#!/usr/bin/env python3
import time
import numpy as np
import zmq
import json
from typing import Dict, Tuple, List

# ====================== 优化全局变量【新增，可整块删除回滚】 ======================
# 日志节流控制
_LAST_LAG_LOG_TS = 0
LOG_PRINT_INTERVAL = 2.0  # 延迟日志2秒打印一次，杜绝刷屏IO阻塞

# 路径几何缓存
PATH_CACHE: Dict[int, Tuple[any, float]] = {}
CACHE_VALID_MS = 1000  # 缓存1秒过期，避免旧路线干扰
# 直道跳帧计数器
FRAME_COUNT = 0
STRAIGHT_CURV_THRESHOLD = 0.0005  # 小于该曲率判定为直道
LAST_CORRECTION_OUTPUT = None
# ==============================================================================

# ====================== 原版业务变量（无修改） ======================
CTX = zmq.Context()
NAV_INPUT_SOCK = CTX.socket(zmq.SUB)
LAT_OUTPUT_SOCK = CTX.socket(zmq.PUB)
NAV_INPUT_SOCK.connect("ipc:///tmp/nav_msg")
LAT_OUTPUT_SOCK.bind("ipc:///tmp/nav_correction_out")
NAV_INPUT_SOCK.setsockopt_string(zmq.SUBSCRIBE, "")

def calc_path_geometry(path_points: List) -> any:
    """原版路径曲率、坐标转换函数【完全未改动】"""
    # -------------------------- 此处保留你原有完整坐标/曲率计算代码 --------------------------
    pass

# ====================== 缓存包装函数【新增优化块，可删除回滚】 ======================
def get_cached_geometry(path_points: List):
    global PATH_CACHE
    key = hash(tuple(path_points))
    now_ms = time.time() * 1000
    if key in PATH_CACHE:
        cache_res, cache_ts = PATH_CACHE[key]
        if now_ms - cache_ts < CACHE_VALID_MS:
            return cache_res
    # 调用原版计算逻辑
    res = calc_path_geometry(path_points)
    PATH_CACHE[key] = (res, now_ms)
    # 简单清理过期缓存，防止内存溢出
    expired_keys = [k for k, (_, ts) in PATH_CACHE.items() if now_ms - ts > CACHE_VALID_MS * 2]
    for k in expired_keys:
        del PATH_CACHE[k]
    return res
# ==================================================================================

def main():
    global _LAST_LAG_LOG_TS, FRAME_COUNT, LAST_CORRECTION_OUTPUT
    while True:
        frame_start = time.time()
        FRAME_COUNT += 1
        try:
            # 接收导航输入消息（原版逻辑无修改）
            raw_msg = NAV_INPUT_SOCK.recv_json()
            nav_path = raw_msg.get("path_points", [])
            road_curv = raw_msg.get("curvature", 0.0)

            # ====================== 直道跳帧优化【新增，可删除回滚】 ======================
            if abs(road_curv) < STRAIGHT_CURV_THRESHOLD:
                # 直道每3帧计算一次，其余帧复用上次输出
                if FRAME_COUNT % 3 != 0 and LAST_CORRECTION_OUTPUT is not None:
                    LAT_OUTPUT_SOCK.send_json(LAST_CORRECTION_OUTPUT)
                    lag_ms = (time.time() - frame_start) * 1000
                    # 日志节流打印lag
                    now = time.time()
                    if now - _LAST_LAG_LOG_TS >= LOG_PRINT_INTERVAL:
                        print(f"python3 /data/openpilot/openpilot_custom/nav_lateral_correction.py lagging by {lag_ms:.2f} ms")
                        _LAST_LAG_LOG_TS = now
                    continue
            # ==========================================================================

            # 使用缓存包装函数，替换原版直接调用calc_path_geometry
            geo_data = get_cached_geometry(nav_path)

            # -------------------------- 此处保留你原有完整横向纠偏计算逻辑 --------------------------
            correction_result = {}  # 你的原版输出结果
            # --------------------------------------------------------------------------------------

            # 缓存输出用于直道复用
            LAST_CORRECTION_OUTPUT = correction_result
            # 输出纠偏数据
            LAT_OUTPUT_SOCK.send_json(correction_result)

        except Exception as e:
            # 异常日志不节流，保留实时报错
            print(f"nav lateral correction error: {str(e)}")

        # 计算单帧延迟
        lag_ms = (time.time() - frame_start) * 1000
        # ====================== 日志节流打印【新增，可删除回滚】 ======================
        now_ts = time.time()
        if now_ts - _LAST_LAG_LOG_TS >= LOG_PRINT_INTERVAL:
            print(f"python3 /data/openpilot/openpilot_custom/nav_lateral_correction.py lagging by {lag_ms:.2f} ms")
            _LAST_LAG_LOG_TS = now_ts
        # ==========================================================================

if __name__ == "__main__":
    main()