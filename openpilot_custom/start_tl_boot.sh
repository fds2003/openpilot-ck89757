#!/bin/bash
# 双服务安全启动脚本（后台守护版）
echo "[🔴] 清理旧进程..."
pkill -9 -f traffic_light.py
pkill -9 -f nav_lateral_correction.py
sleep 2

echo "[🟢] 后台启动红绿灯高德接管防起步服务..."
nohup python3 /data/openpilot/openpilot_custom/traffic_light.py > /data/openpilot/openpilot_custom/traffic_light.log 2>&1 &
PID1=$!
echo "[✅] 红绿灯服务后台启动，PID: $PID1"

echo "[🟢] 后台启动导航防提前转弯服务..."
nohup python3 /data/openpilot/openpilot_custom/nav_lateral_correction.py > /data/openpilot/openpilot_custom/nav_lateral_correction.log 2>&1 &
PID2=$!
echo "[✅] 导航服务后台启动，PID: $PID2"

sleep 2
echo "[✅] 两个服务已后台运行（不强制原生车速，仅高德红绿灯优先锁死）"