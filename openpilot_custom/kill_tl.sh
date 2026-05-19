#!/bin/bash
# 彻底杀掉所有红绿灯相关进程，包括僵尸进程
pkill -9 -f tl_system.py
pkill -9 -f "python3 /data/openpilot/openpilot_custom/tl_system.py"
ps aux | grep tl_system | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null
echo "✅ 所有tl_system进程已彻底清除"