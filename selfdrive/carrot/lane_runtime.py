#!/usr/bin/env python3
"""lane_runner 运行时前置条件（纯标准库，便于测试与启动自检）。"""
import importlib.util
import os


def check_runtime(model_path):
    """返回 (ok, message)。不导入 onnxruntime，避免在缺少依赖时崩溃。"""
    if importlib.util.find_spec("onnxruntime") is None:
        return False, "onnxruntime not installed: pip install -r selfdrive/carrot/requirements_lane.txt"
    if not os.path.exists(model_path):
        return False, f"lane model not found: {model_path}"
    return True, ""
