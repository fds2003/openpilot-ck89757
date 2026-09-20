#!/usr/bin/env python3
"""curve_sync.py — 横纵 MPC 联动限速状态（单例）。"""
import time
import numpy as np


class CurveSync:
    _speed_ms = 0.0
    _curvature = 0.0
    _is_real_corner = False
    _confidence = 0.0
    _last_update_ts = 0.0
    _has_valid_value = False
    _last_smooth_ts = None

    _LP_ALPHA = 0.35
    _MAX_DROP_PER_S = 4.0
    _MAX_RISE_PER_S = 1.5
    _EXPIRE_S = 0.5
    MIN_VALID_SPEED_MS = 1.0
    MIN_CURVATURE = 0.0005

    @classmethod
    def set_from_lateral(cls, target_v_ms, curvature=0.0, is_real_corner=False,
                         confidence=1.0, force_zero=False):
        v = 0.0
        try:
            v = float(target_v_ms) if target_v_ms is not None else 0.0
        except (TypeError, ValueError):
            v = 0.0
        now = time.monotonic()
        cls._curvature = abs(float(curvature))
        cls._is_real_corner = bool(is_real_corner)
        cls._confidence = float(np.clip(confidence, 0.0, 1.0))
        cls._last_update_ts = now
        if force_zero or v <= 0.0:
            cls._speed_ms = 0.0
            cls._has_valid_value = False
            return
        is_valid = (v > cls.MIN_VALID_SPEED_MS) and (
            cls._curvature > cls.MIN_CURVATURE or cls._is_real_corner)
        if is_valid:
            if not cls._has_valid_value:
                cls._speed_ms = v
                cls._has_valid_value = True
            else:
                cls._speed_ms = cls._apply_smooth(v, now)
                cls._has_valid_value = True
        else:
            cls._has_valid_value = False

    @classmethod
    def _apply_smooth(cls, new_v, now):
        prev = cls._speed_ms
        dt = 0.050 if cls._last_smooth_ts is None else max(now - cls._last_smooth_ts, 1e-3)
        cls._last_smooth_ts = now
        out = cls._LP_ALPHA * new_v + (1.0 - cls._LP_ALPHA) * prev
        max_drop = cls._MAX_DROP_PER_S * dt
        if prev - out > max_drop:
            out = prev - max_drop
        max_rise = cls._MAX_RISE_PER_S * dt
        if out - prev > max_rise:
            out = prev + max_rise
        return out

    @classmethod
    def get_speed_ms(cls, default=None, v_ego_ms=0.0):
        if not cls._has_valid_value:
            return default
        if (time.monotonic() - cls._last_update_ts) > cls._EXPIRE_S:
            return default
        limit = cls._speed_ms
        if limit < cls.MIN_VALID_SPEED_MS:
            return default
        if v_ego_ms > 0.0 and limit >= v_ego_ms - 0.5:
            return default
        return limit

    @classmethod
    def get_info(cls):
        return {
            "speed_kph": float(cls._speed_ms * 3.6),
            "curvature": float(cls._curvature),
            "is_real_corner": bool(cls._is_real_corner),
            "has_valid": bool(cls._has_valid_value),
            "age_s": float(time.monotonic() - cls._last_update_ts),
        }

    @classmethod
    def reset(cls):
        cls._speed_ms = 0.0
        cls._curvature = 0.0
        cls._is_real_corner = False
        cls._confidence = 0.0
        cls._last_update_ts = 0.0
        cls._has_valid_value = False


curve_sync = CurveSync()
