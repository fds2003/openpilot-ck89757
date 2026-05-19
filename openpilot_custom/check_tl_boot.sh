#!/bin/bash
echo "====================================="
echo "🔍 开机自启服务状态校验（红绿灯+导航修正）"
echo "====================================="

# 检查 tl_system.py
tl_pid=$(pgrep -f "tl_system.py")
if [ -n "$tl_pid" ]; then
    echo "1. 红绿灯核心系统（tl_system.py）: ✅ 运行中 (PID: $tl_pid)"
else
    echo "1. 红绿灯核心系统（tl_system.py）: ❌ 未启动"
fi

# 检查 nav_lateral_correction.py
nav_pid=$(pgrep -f "nav_lateral_correction.py")
if [ -n "$nav_pid" ]; then
    echo "2. 导航横向修正（nav_lateral_correction.py）: ✅ 运行中 (PID: $nav_pid)"
else
    echo "2. 导航横向修正（nav_lateral_correction.py）: ❌ 未启动"
fi

echo "====================================="
echo "📋 详细运行列表（仅包含红绿灯相关）:"
ps aux | grep -E "tl_system|nav_lateral_correction" | grep -v grep
echo "====================================="
