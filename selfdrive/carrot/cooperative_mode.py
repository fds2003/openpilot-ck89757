#!/usr/bin/env python3
"""协同模式：车机意图优先时，禁用 C3 自主 ATC。

规则：
- cooperative_mode=False：保持原行为，C3 自主 ATC 可用；
- cooperative_mode=True 且车机在线：C3 不自主发起转向，只执行车机指令；
- cooperative_mode=True 且车机失联：回退 C3 自主，避免双端都失效。
"""
import time

HU_ALIVE_TIMEOUT_S = 15.0  # 车机每 5s 探针一次，连续丢失 3 次判定失联


def hu_alive(last_seen_ts, now=None, timeout=HU_ALIVE_TIMEOUT_S):
    if last_seen_ts is None:
        return False
    if now is None:
        now = time.time()
    return (now - last_seen_ts) <= timeout


def auto_turn_allowed(cooperative_mode, is_hu_alive):
    return (not cooperative_mode) or (not is_hu_alive)
