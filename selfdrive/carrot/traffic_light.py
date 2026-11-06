#!/usr/bin/env python3
"""adbridge 4215 红绿灯报文 -> C3 traffic_state。

报文示例：{"tl":"red|green","cd":18,"st":1,"dir":"left","src":"adbridge"}
DETECT 指令（carrotCmd="DETECT"）优先级更高；bridge 状态仅在 DETECT 不活跃时生效。
"""
import time

TRAFFIC_NONE = 0
TRAFFIC_RED = 1
TRAFFIC_GREEN = 2

BRIDGE_TL_PORT = 4215
BRIDGE_FRESH_S = 3.0


def state_from_wire(tl):
    if tl == "red":
        return TRAFFIC_RED
    if tl == "green":
        return TRAFFIC_GREEN
    return TRAFFIC_NONE


def is_fresh(ts, now=None, timeout=BRIDGE_FRESH_S):
    if not ts:
        return False
    if now is None:
        now = time.time()
    return (now - ts) <= timeout


def bridge_state_allowed(detect_count, ts, now=None):
    """DETECT 活跃时不用 bridge；bridge 数据必须新鲜。"""
    return detect_count <= 0 and is_fresh(ts, now)
