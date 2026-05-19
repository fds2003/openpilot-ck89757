#!/usr/bin/env python3
import cereal.messaging as messaging
import json
import time

print("🔍 验证AI控制消息接收状态")
print("="*60)

# 订阅AI控制消息
sm = messaging.SubMaster(['customReservedRawData0'])

received_count = 0
for i in range(30):  # 监听3秒
    sm.update(100)
    
    if sm.updated['customReservedRawData0']:
        received_count += 1
        data_bytes = sm['customReservedRawData0'].data
        if data_bytes:
            try:
                data = json.loads(data_bytes.decode('utf-8'))
                if data.get('type') == 'ai_speed_control':
                    speed = data.get('control_command', {}).get('target_speed_kmh', 0)
                    print(f"✅ 收到AI消息 #{received_count}: 目标车速 {speed} km/h")
            except:
                print(f"📦 收到消息 #{received_count} (无法解析)")
    
    time.sleep(0.1)

print("="*60)
if received_count > 0:
    print(f"📡 消息接收状态: 正常 ({received_count}条消息)")
else:
    print(f"❌ 消息接收状态: 异常 (未收到任何消息)")
    print("   可能原因:")
    print("   1. AI脚本没有运行")
    print("   2. 消息通道名称错误")
    print("   3. 订阅服务未启动")
