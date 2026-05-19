#!/usr/bin/env python3
"""
AI 消息接收器 - 最终稳定版
监听 logMessage 主题，解析 AI 车速建议
"""

import json
import cereal.messaging as messaging
import time

class AIMessageReceiver:
    def __init__(self):
        self.sm = messaging.SubMaster(['logMessage'])
        self.received_count = 0
        print("✅ AI 消息接收器初始化完成")
    
    def process_message(self):
        """处理接收到的消息"""
        self.sm.update()
        
        if self.sm.updated['logMessage']:
            msg = self.sm['logMessage']
            if hasattr(msg, 'custom') and msg.custom:
                try:
                    data = json.loads(msg.custom)
                    if data.get('type') == 'ai_speed_suggestion':
                        self.received_count += 1
                        print(f"\n📥 收到AI消息 #{self.received_count}")
                        print(f"   速度: {data.get('speed', 0):.1f} m/s")
                        print(f"   原因: {data.get('reason', '')}")
                        print(f"   置信度: {data.get('confidence', 0):.2%}")
                except:
                    pass
    
    def run(self):
        """主运行循环"""
        print("👂 开始监听AI消息...")
        while True:
            self.process_message()
            time.sleep(0.01)

if __name__ == "__main__":
    receiver = AIMessageReceiver()
    receiver.run()