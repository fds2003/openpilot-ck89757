#!/usr/bin/env python3
"""
AI车速建议发送器 - 最安全版本
通过 customData 主题发送JSON格式的AI建议
无需修改.capnp，无需重新编译
"""

import json
import time
import cereal.messaging as messaging
from openpilot.common.realtime import Ratekeeper

class AISpeedSender:
    def __init__(self, config=None):
        """初始化发送器"""
        self.pm = messaging.PubMaster(['customData'])
        self.message_id = 0
        self.config = config or {}
        
        print("✅ AI车速发送器初始化完成")
        print("   使用主题: customData")
        print("   格式: JSON序列化")
    
    def get_ai_speed_suggestion(self):
        """
        获取AI车速建议
        这里替换为您的AI模型或逻辑
        """
        # 示例：模拟AI建议
        import random
        return {
            'speed': 20.0 + random.uniform(-3, 5),  # 17-25 m/s
            'reason': random.choice([
                "前方路况良好，建议保持速度",
                "检测到前车，建议保持安全距离",
                "弯道建议，适当减速",
                "高速路段，建议稳定车速"
            ]),
            'confidence': 0.7 + random.uniform(0, 0.3),
            'source': 'ai_speed_model_v1'
        }
    
    def send_suggestion(self, suggestion=None):
        """发送AI车速建议"""
        if suggestion is None:
            suggestion = self.get_ai_speed_suggestion()
        
        # 构建消息数据
        ai_data = {
            'type': 'ai_speed_suggestion',
            'id': self.message_id,
            'timestamp': time.time(),
            'data': suggestion
        }
        
        # 创建customData消息
        msg = messaging.new_message('customData')
        msg.customData.custom = json.dumps(ai_data, ensure_ascii=False)
        
        # 发送
        self.pm.send('customData', msg)
        self.message_id += 1
        
        print(f"📤 发送AI建议 #{self.message_id}: "
              f"速度={suggestion['speed']:.1f}m/s, "
              f"原因={suggestion['reason']}, "
              f"置信度={suggestion['confidence']:.2f}")
        
        return True
    
    def run_continuous(self, interval=2.0):
        """连续运行模式"""
        print(f"🚀 启动连续发送模式 (间隔: {interval}秒)")
        rk = Ratekeeper(1.0/interval)
        
        try:
            while True:
                self.send_suggestion()
                rk.keep_time()
        except KeyboardInterrupt:
            print("\n🛑 停止发送")

# 测试入口
if __name__ == "__main__":
    sender = AISpeedSender()
    
    # 测试单次发送
    print("🧪 测试单次发送...")
    if sender.send_suggestion():
        print("✅ 测试成功！")
        
        # 询问是否启动连续模式
        choice = input("\n是否启动连续发送模式？(y/n): ").strip().lower()
        if choice == 'y':
            sender.run_continuous(interval=2.0)
    else:
        print("❌ 测试失败")