#!/usr/bin/env python3
"""
AI极简代理 - 连接AI和红绿灯系统
"""

import zmq
import json
import time
import logging
import threading

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - AIProxy - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/ai_proxy.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AISimpleProxy:
    def __init__(self):
        self.running = True
        
        # ZeroMQ
        self.context = zmq.Context()
        
        # 订阅AI建议
        self.ai_sub = self.context.socket(zmq.SUB)
        self.ai_sub.connect("tcp://localhost:5580")
        self.ai_sub.setsockopt_string(zmq.SUBSCRIBE, "")
        
        # 转发到红绿灯系统
        self.tl_pub = self.context.socket(zmq.PUB)
        self.tl_pub.bind("tcp://*:5581")
        
        logger.info("✅ AI极简代理启动")
    
    def run(self):
        """主循环"""
        while self.running:
            try:
                # 接收AI建议
                msg = self.ai_sub.recv_string(zmq.NOBLOCK)
                ai_data = json.loads(msg)
                
                if ai_data.get("type") == "ai_speed_suggestion":
                    speed = ai_data.get("speed", 0.0)
                    reason = ai_data.get("reason", "")
                    
                    # 转发到红绿灯系统
                    forward_msg = {
                        "type": "forwarded_ai_suggestion",
                        "ai_speed": speed,
                        "reason": reason,
                        "target": "traffic_light_system",
                        "timestamp": time.time()
                    }
                    
                    self.tl_pub.send_string(json.dumps(forward_msg))
                    logger.info(f"📤 转发AI建议: {speed:.1f}km/h")
                
            except zmq.Again:
                time.sleep(0.01)
            except Exception as e:
                logger.error(f"代理错误: {e}")
                time.sleep(0.1)
    
    def stop(self):
        """停止"""
        self.running = False
        self.ai_sub.close()
        self.tl_pub.close()
        self.context.term()
        logger.info("🛑 AI极简代理停止")

def main():
    """主函数"""
    proxy = AISimpleProxy()
    
    try:
        proxy.run()
    except KeyboardInterrupt:
        logger.info("👋 用户中断")
    except Exception as e:
        logger.error(f"主程序异常: {e}")
    finally:
        proxy.stop()

if __name__ == "__main__":
    main()