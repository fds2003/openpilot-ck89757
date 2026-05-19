#!/usr/bin/env python3
"""
AI 车速建议接收器 - 最终修复版
监听 OpenPilot 预留通道 customReservedRawData0
格式: JSON 字符串 (从 bytes 解码)
零编译，零源码修改
"""

import json
import time
import cereal.messaging as messaging

class AISpeedReceiver:
    def __init__(self):
        """初始化接收器"""
        self.sm = messaging.SubMaster(['customReservedRawData0'])
        self.count = 0
        self.start_time = time.time()
        
        print("✅ AI 车速接收器初始化完成")
        print("监听主题: customReservedRawData0 (OpenPilot 预留通道)")
        print("格式: JSON 字符串 (从 bytes 解码)")
        print("零编译，零源码修改")
        print("等待接收 AI 车速建议...")

    def run(self):
        """主循环"""
        while True:
            self.sm.update()
            if self.sm.updated['customReservedRawData0']:
                msg = self.sm['customReservedRawData0']
                if msg.valid and msg.data:
                    try:
                        # 从 bytes 解码为 JSON 字符串
                        json_str = msg.data.decode('utf-8')
                        data = json.loads(json_str)
                        self.count += 1
                        print(f"📩 收到第 {self.count} 条 AI 车速建议: {data}")
                    except Exception as e:
                        print(f"❌ 解析失败: {e}")
            time.sleep(0.01)

if __name__ == "__main__":
    receiver = AISpeedReceiver()
    try:
        receiver.run()
    except KeyboardInterrupt:
        print("\n🛑 接收器已停止")