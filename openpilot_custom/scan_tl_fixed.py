#!/usr/bin/env python3
import cereal.messaging as messaging

# 只保留cpv9-dev中存在的消息类型
possible_services = [
    'carState', 'controlsState', 'modelV2', 'radarState',
    'liveTracks', 'pandaStates', 'ubloxGnss'
]

print("=== 扫描所有消息中的红绿灯字段 ===")
sm = messaging.SubMaster(possible_services)

while True:
    sm.update()
    for service in possible_services:
        msg = sm[service]
        # 遍历消息的所有字段
        for field in dir(msg):
            if 'light' in field.lower() or 'tl' in field.lower() or 'traffic' in field.lower():
                value = getattr(msg, field, None)
                print(f"[FOUND] 服务: {service} | 字段: {field} | 值: {value}")
