#!/bin/bash
set -e

# 1. 修改停车减速参数（真实路径）
sed -i 's/StoppingDecelRate = [0-9.]*/StoppingDecelRate = 0.75/' /data/openpilot/selfdrive/carrot/carrot_functions.py
sed -i 's/ComfortBrake = [0-9.]*/ComfortBrake = 0.45/' /data/openpilot/selfdrive/carrot/carrot_functions.py

# 2. 修改停止线预留距离（真实路径）
sed -i 's/stop_line_buffer = [0-9.]*/stop_line_buffer = 2.0/' /data/openpilot/selfdrive/controls/lib/longitudinal_planner.py

echo "✅ 红绿灯停车参数已优化完成！"
echo "推荐：StoppingDecelRate=0.75 | ComfortBrake=0.45 | stop_line_buffer=2.0"