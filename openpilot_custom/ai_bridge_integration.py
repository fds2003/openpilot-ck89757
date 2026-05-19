#!/usr/bin/env python3
"""
AI 桥接集成器 - 完整版
协调消息发送和接收，作为系统主入口
"""

import threading
import time
from simple_ai_message import SimpleAIMessenger
from ai_message_receiver import AIMessageReceiver

class AIBridgeIntegration:
    def __init__(self, config=None):
        self.config = config or {}
        self.messenger = SimpleAIMessenger()
        self.receiver = AIMessageReceiver()
        self.running = False
        
        # 线程
        self.receiver_thread = None
        self.sender_thread = None
    
    def start_receiver(self):
        """启动消息接收器线程"""
        self.receiver_thread = threading.Thread(
            target=self.receiver.run,
            daemon=True
        )
        self.receiver_thread.start()
        print("✅ AI消息接收器已启动")
    
    def start_sender(self, interval=2.0):
        """启动消息发送器线程"""
        def sender_loop():
            while self.running:
                # 这里集成您的AI逻辑
                # 例如：speed = your_ai_model.predict()
                speed = 22.5
                self.messenger.send_ai_speed_message(
                    speed=speed,
                    reason="AI车速建议",
                    confidence=0.85
                )
                time.sleep(interval)
        
        self.sender_thread = threading.Thread(
            target=sender_loop,
            daemon=True
        )
        self.sender_thread.start()
        print(f"✅ AI消息发送器已启动 (间隔: {interval}秒)")
    
    def start(self):
        """启动整个AI系统"""
        self.running = True
        print("🚀 启动AI车速控制系统...")
        
        # 启动接收器
        self.start_receiver()
        time.sleep(1)
        
        # 启动发送器
        self.start_sender(interval=2.0)
        
        # 保持主线程运行
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """停止AI系统"""
        self.running = False
        print("\n🛑 停止AI车速控制系统...")
        if self.receiver_thread:
            self.receiver_thread.join(timeout=2)
        if self.sender_thread:
            self.sender_thread.join(timeout=2)
        print("✅ 系统已停止")

if __name__ == "__main__":
    system = AIBridgeIntegration()
    system.start()