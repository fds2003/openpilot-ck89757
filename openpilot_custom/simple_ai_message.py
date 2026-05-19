#!/usr/bin/env python3
"""
AI 车速消息发送器 - 最终稳定版
通过 logMessage 主题发送 JSON 格式的 AI 车速建议
无依赖修改，无编译需求
"""

import json
import time
import cereal.messaging as messaging
from openpilot.common.realtime import Ratekeeper

class SimpleAIMessenger:
    def __init__(self):
        self.pm = messaging.PubMaster(['logMessage'])
        self.message_id = 0
        print("✅ AI 消息发送器初始化完成")
    
    def send_ai_speed_message(self, speed, reason="", confidence=0.0, metadata=None):
        """发送 AI 车速建议"""
        ai_data = {
            'type': 'ai_speed_suggestion',
            'id': self.message_id,
            'speed': float(speed),
            'reason': str(reason),
            'confidence': float(confidence),
            'timestamp': time.time()
        }
        if metadata:
            ai_data['metadata'] = metadata
        
        # 创建消息
        msg = messaging.new_message('logMessage')
        msg.logMessage.custom = json.dumps(ai_data)
        
        # 发送
        self.pm.send('logMessage', msg)
        self.message_id += 1
        
        print(f"📤 发送AI消息 #{self.message_id}: 速度={speed:.1f}m/s")
        return True
    
    def run_continuous(self, interval=1.0):
        """连续运行模式"""
        rk = Ratekeeper(1.0/interval)
        while True:
            # 这里调用您的AI逻辑生成speed
            import random
            speed = 20.0 + random.uniform(-5, 5)
            self.send_ai_speed_message(
                speed=speed,
                reason="连续运行测试",
                confidence=0.8
            )
            rk.keep_time()

if __name__ == "__main__":
    messenger = SimpleAIMessenger()
    messenger.send_ai_speed_message(22.5, "测试消息", 0.9)