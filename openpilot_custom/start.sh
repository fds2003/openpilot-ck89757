#!/bin/bash
# 延时等待系统启动完成
sleep 10
# 后台运行脚本，输出日志到文件
nohup python3 /data/openpilot/openpilot_custom/traffic_light.py > /data/openpilot/openpilot_custom/log.txt 2>&1 &
