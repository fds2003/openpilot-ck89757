#!/usr/bin/env python3
"""
AI车速桥接器 - 集成发送和接收
作为统一入口点
"""

import threading
import time
from ai_speed_sender import AISpeedSender
from ai_speed_receiver import AISpeedReceiver

class AISpeedBridge:
    def __init__(self, config=None):
        self.config = config or {}
        self.sender = AISpeedSender(config)
        self.receiver = AISpeedReceiver(config)
        self.running = False
        
    def start(self, send_interval=2.0):
        """启动整个系统"""
        self.running = True
        print("🚀 启动AI车速控制系统...")
        
        # 启动接收器线程
        receiver_thread = threading.Thread(
            target=self.receiver.run,
            daemon=True
        )
        receiver_thread.start()
        print("✅ AI接收器已启动")
        
        # 等待接收器初始化
        time.sleep(1)
        
        # 启动发送器循环
        print(f"📤 AI发送器启动 (间隔: {send_interval}秒)")
        try:
            while self.running:
                self.sender.send_suggestion()
                time.sleep(send_interval)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """停止系统"""
        self.running = False
        print("\n🛑 停止AI车速控制系统...")

# 启动入口
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='AI车速控制系统')
    parser.add_argument('--interval', type=float, default=2.0,
                       help='发送间隔（秒）')
    
    args = parser.parse_args()
    
    bridge = AISpeedBridge()
    bridge.start(send_interval=args.interval)