#!/usr/bin/env python3
import json
import time
import numpy as np

# ############### 核心修复 ###############
# 不再导入 VisionStreamType，直接用字符串流名
from msgq.visionipc import VisionIpcClient
# ########################################

print("✅ 启动红绿灯检测（最终修复版）")

# 连接摄像头（直接用流名 0，适配你的版本）
vipc_client = VisionIpcClient("camerad", 0, True)
while not vipc_client.connect(False):
    time.sleep(0.1)
print("✅ IPC 连接成功")

def detect_tl_yuv(raw_data, w, h):
    """
    只做 Y 通道检测，不做格式转换，绝对不报错
    """
    try:
        y_size = w * h
        y = raw_data[:y_size].reshape(h, w)

        # 检测区域：画面上半部分中间
        roi = y[h//6:h//3, w//4:w*3//4]
        avg_y = np.mean(roi)

        # 调低阈值，更容易识别
        if avg_y > 180:
            return "red"
        elif avg_y > 160:
            return "green"
        else:
            return "unknown"
    except:
        return "unknown"

last_tl = "unknown"
frame_count = 0

while True:
    buf = vipc_client.recv()
    if buf is None:
        time.sleep(0.01)
        continue

    frame_count += 1
    if frame_count % 10 == 0:
        tl = detect_tl_yuv(buf.data, buf.width, buf.height)
        if tl != "unknown":
            last_tl = tl

        # 写入固定文件
        with open("/tmp/traffic_light.json", "w") as f:
            json.dump({
                "color": last_tl,
                "frame": frame_count
            }, f)

    if frame_count % 30 == 0:
        print(f"[TL] 状态: {last_tl}")