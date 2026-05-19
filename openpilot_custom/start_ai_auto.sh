#!/bin/bash
# start_ai_auto.sh - 自动启动AI车速控制系统

echo "🚗 AI车速控制系统 - 自动启动"
echo "================================"

# 设置环境
cd /data/openpilot/openpilot_custom
export PYTHONPATH=/data/openpilot

# 检查是否已在运行
if pgrep -f "ai_speed_sender.py" > /dev/null; then
    echo "⚠️  AI控制系统已在运行"
    echo "    PID: $(pgrep -f "ai_speed_sender.py")"
    read -p "是否停止现有进程? (y/N): " choice
    if [[ $choice == "y" || $choice == "Y" ]]; then
        pkill -f "ai_speed_sender.py"
        echo "✅ 已停止现有进程"
        sleep 2
    else
        echo "❌ 启动中止"
        exit 1
    fi
fi

# 设置运行参数
DURATION=0      # 0=无限运行
INTERVAL=0.5    # 更新间隔
LOG_FILE="/tmp/ai_control_$(date +%Y%m%d_%H%M%S).log"

echo "⏱️  运行模式: $(if [ $DURATION -eq 0 ]; then echo "无限运行"; else echo "${DURATION}秒"; fi)"
echo "📡 更新间隔: ${INTERVAL}秒"
echo "📝 日志文件: ${LOG_FILE}"
echo "================================"

# 倒计时
for i in {3..1}; do
    echo -n "⏳ ${i}秒后启动... "
    sleep 1
done
echo "启动！"

# 启动AI控制系统
nohup python3 ai_speed_sender.py --auto-start --duration $DURATION --interval $INTERVAL > "$LOG_FILE" 2>&1 &
PID=$!

echo "✅ AI控制系统已启动"
echo "📊 进程PID: $PID"
echo "📁 日志文件: $LOG_FILE"
echo ""
echo "🛠️  管理命令:"
echo "   查看日志: tail -f $LOG_FILE"
echo "   停止系统: pkill -f 'ai_speed_sender.py'"
echo "   查看进程: ps aux | grep ai_speed_sender"