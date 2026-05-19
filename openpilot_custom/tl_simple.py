#!/usr/bin/env python3
import subprocess
import numpy as np
from io import BytesIO
from PIL import Image

print("✅ 免依赖红绿灯检测（直接读取摄像头）")

# 摄像头设备路径（通常是 /dev/video0）
CAM_DEV = "/dev/video0"

# 用系统自带工具 ffmpeg 读取摄像头
def get_frame():
    cmd = [
        "ffmpeg", "-i", CAM_DEV,
        "-vframes", "1",
        "-f", "image2pipe", "-vcodec", "png", "-"
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        img = Image.open(BytesIO(out))
        return np.array(img)
    except Exception as e:
        print("读取摄像头失败:", e)
        return None

# 颜色识别（红灯/绿灯）
def detect_light(frame):
    if frame is None:
        return "unknown"
    
    # 缩小图片，减少计算量
    h, w = frame.shape[:2]
    small = frame[h//4:3*h//4, w//4:3*w//4]
    
    # 统计红/绿色像素
    red = np.sum((small[:,:,0] > 150) & (small[:,:,1] < 100) & (small[:,:,2] < 100))
    green = np.sum((small[:,:,1] > 150) & (small[:,:,0] < 100) & (small[:,:,2] < 100))
    
    if red > 500:
        return "red"
    elif green > 500:
        return "green"
    else:
        return "none"

# 主循环
while True:
    frame = get_frame()
    light = detect_light(frame)
    if light == "red":
        print("🔴 检测到红灯")
    elif light == "green":
        print("🟢 检测到绿灯")
    else:
        print("⚪ 无红绿灯信号")
