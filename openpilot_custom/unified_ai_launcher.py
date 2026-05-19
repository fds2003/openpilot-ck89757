#!/usr/bin/env python3
"""
统一AI启动器 - 集成AI车速控制模块
管理所有AI相关进程的启动和停止
"""

import subprocess
import time
import signal
import sys
import os

class UnifiedAILauncher:
    def __init__(self):
        self.processes = []
        self.modules = [
            {
                "name": "AI车速控制系统",
                "script": "ai_bridge_integration.py",
                "log": "/tmp/ai_bridge.log"
            },
            {
                "name": "AI消息接收器",
                "script": "ai_message_receiver.py",
                "log": "/tmp/ai_receiver.log"
            },
            {
                "name": "AI消息发送器",
                "script": "simple_ai_message.py",
                "log": "/tmp/ai_sender.log"
            }
        ]
    
    def start_module(self, module):
        """启动单个模块"""
        print(f"🚀 启动: {module['name']}")
        log_file = open(module['log'], 'w')
        proc = subprocess.Popen(
            ['python3', module['script']],
            stdout=log_file,
            stderr=subprocess.STDOUT
        )
        self.processes.append((module['name'], proc, log_file))
        time.sleep(1)  # 给进程启动时间
        return proc
    
    def start_all(self):
        """启动所有模块"""
        print("="*50)
        print("🤖 启动AI车速控制系统")
        print("="*50)
        
        for module in self.modules:
            self.start_module(module)
        
        print("\n✅ 所有模块已启动")
        print("📊 监控日志:")
        for module in self.modules:
            print(f"  - {module['name']}: tail -f {module['log']}")
        
        # 保持运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop_all()
    
    def stop_all(self):
        """停止所有模块"""
        print("\n🛑 停止所有模块...")
        for name, proc, log_file in self.processes:
            print(f"  停止: {name}")
            proc.terminate()
            proc.wait(timeout=5)
            log_file.close()
        print("✅ 系统已完全停止")

if __name__ == "__main__":
    launcher = UnifiedAILauncher()
    launcher.start_all()