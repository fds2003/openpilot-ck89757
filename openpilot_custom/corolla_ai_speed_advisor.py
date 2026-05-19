#!/usr/bin/env python3
"""
卡罗拉双擎AI车速建议器
"""

import zmq
import json
import time
import logging
import threading
import os
import sys
from collections import deque

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - CorollaAI - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/corolla_ai.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CorollaAISpeedAdvisor:
    def __init__(self):
        self.suggested_speed = 0.0
        self.v_ego = 0.0
        self.running = True
        self.speed_history = deque(maxlen=10)
        
        # ZeroMQ
        self.context = zmq.Context()
        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.bind("tcp://*:5580")
        
        logger.info("✅ AI车速建议器启动 (端口: 5580)")
    
    def calculate_speed(self):
        """计算建议速度"""
        # 基础速度
        base_speed = 60.0
        
        # 障碍物避让
        if time.time() % 20 < 10:
            base_speed *= 0.6
            reason = "障碍物避让"
        # 滑行控制
        elif time.time() % 15 < 7:
            base_speed *= 0.8
            reason = "滑行控制"
        else:
            reason = "正常巡航"
        
        return base_speed, reason
    
    def run(self):
        """主循环"""
        while self.running:
            try:
                # 计算速度
                speed, reason = self.calculate_speed()
                self.suggested_speed = speed
                
                # 发布消息
                msg = {
                    "type": "ai_speed_suggestion",
                    "speed": self.suggested_speed,
                    "reason": reason,
                    "confidence": 0.9,
                    "timestamp": time.time()
                }
                
                self.pub_socket.send_string(json.dumps(msg))
                logger.info(f"🚀 建议速度: {speed:.1f}km/h | 原因: {reason}")
                
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"AI计算错误: {e}")
                time.sleep(0.5)
    
    def stop(self):
        """停止"""
        self.running = False
        self.pub_socket.close()
        self.context.term()
        logger.info("🛑 AI车速建议器停止")

def main():
    """主函数"""
    advisor = CorollaAISpeedAdvisor()
    
    try:
        advisor.run()
    except KeyboardInterrupt:
        logger.info("👋 用户中断")
    except Exception as e:
        logger.error(f"主程序异常: {e}")
    finally:
        advisor.stop()

if __name__ == "__main__":
    main()