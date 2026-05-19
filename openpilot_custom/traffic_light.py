#!/usr/bin/env python3
import time
import random

print("="*40)
print("🚦 红绿灯状态显示 [V2.0]")
print("="*40)

# 状态标记
is_red = False
red_start_time = 0

def get_state(dist):
    global is_red, red_start_time
    
    # 1. 如果当前是红灯状态
    if is_red:
        # 自动解锁逻辑：红灯超过 30 秒，或者距离再次远离路口，就重置
        current_time = time.time()
        if (current_time - red_start_time > 30) or (dist > 100):
            is_red = False
            red_start_time = 0
            return ("⚪", "离开路口，状态已重置")
        
        # 维持红灯显示
        return ("🔴 红灯", "停车等待中...")

    # 2. 正常行驶逻辑
    if dist < 100:
        light = random.choice([1, 2, 3])
        if light == 1:
            is_red = True
            red_start_time = time.time()  # 记录红灯开始时间
            return ("🔴 红灯", "请停车等待")
        elif light == 2:
            return ("🟢 绿灯", "可正常通行")
        else:
            return ("⚠️ 黄灯", "请减速通行")
    
    # 3. 距离远时，强制重置
    return ("⚪", "无路口，正常行驶")

while True:
    dist = random.randint(0, 500)
    color, state = get_state(dist)
    print(f"距离路口: {dist}m | 状态: {color} {state}")
    print("-" * 30)
    time.sleep(1)
